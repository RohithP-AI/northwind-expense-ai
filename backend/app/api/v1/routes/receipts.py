import logging
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.receipt import Receipt
from app.models.submission import Submission
from app.schemas.receipt import ReceiptRead, ReceiptUploadResponse
from app.services.anthropic_client import AnthropicNotConfigured
from app.services.receipt_extractor import extract_receipt

log = logging.getLogger("receipts")
router = APIRouter()

# backend/app/api/v1/routes/receipts.py → parents[4] = backend/ , parents[5] = project root
BACKEND_DIR = Path(__file__).resolve().parents[4]
PROJECT_ROOT = BACKEND_DIR.parent
UPLOADS_DIR = BACKEND_DIR / "uploads"

ALLOWED_SUFFIXES = {".txt", ".pdf", ".jpg", ".jpeg", ".png"}

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_filename(name: str) -> str:
    cleaned = _SAFE_NAME.sub("_", Path(name).name).strip("_")
    return cleaned or "receipt"


def _unique_path(directory: Path, filename: str) -> Path:
    candidate = directory / filename
    if not candidate.exists():
        return candidate
    stem, suffix = candidate.stem, candidate.suffix
    return directory / f"{stem}_{uuid.uuid4().hex[:8]}{suffix}"


async def _get_submission(db: AsyncSession, submission_id: uuid.UUID) -> Submission:
    submission = await db.scalar(select(Submission).where(Submission.id == submission_id))
    if submission is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found"
        )
    return submission


@router.post(
    "/{submission_id}/receipts",
    response_model=ReceiptUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_receipts(
    submission_id: uuid.UUID,
    files: list[UploadFile] = File(..., description="One or more receipt files"),
    db: AsyncSession = Depends(get_db),
):
    """Upload one or more receipt files, extract their fields, and store them.

    Files are saved under backend/uploads/{submission_id}/. Extraction is
    best-effort: a file that can't be parsed (e.g. an image with no
    ANTHROPIC_API_KEY) is still saved and recorded, with a warning.
    """
    await _get_submission(db, submission_id)

    dest_dir = UPLOADS_DIR / str(submission_id)
    dest_dir.mkdir(parents=True, exist_ok=True)

    created: list[Receipt] = []
    warnings: list[str] = []

    for upload in files:
        original = upload.filename or "receipt"
        suffix = Path(original).suffix.lower()
        if suffix not in ALLOWED_SUFFIXES:
            warnings.append(
                f"{original!r}: unsupported type {suffix!r}; skipped "
                f"(allowed: {', '.join(sorted(ALLOWED_SUFFIXES))})."
            )
            continue

        dest = _unique_path(dest_dir, _safe_filename(original))
        dest.write_bytes(await upload.read())
        rel_path = dest.relative_to(PROJECT_ROOT).as_posix()

        merchant = transaction_date = amount = category = raw_text = None
        currency = "USD"
        try:
            extracted = await extract_receipt(dest, original)
            merchant = extracted.merchant
            transaction_date = extracted.transaction_date
            amount = extracted.amount
            currency = extracted.currency
            category = extracted.category
            raw_text = extracted.raw_extracted_text or None
            warnings.extend(extracted.warnings)
        except AnthropicNotConfigured as exc:
            warnings.append(f"{original!r}: {exc} File saved without extracted fields.")
        except Exception as exc:  # noqa: BLE001 — keep the upload resilient
            log.warning("Extraction failed for %s: %s", original, exc)
            warnings.append(f"{original!r}: extraction failed ({exc}). File saved anyway.")

        receipt = Receipt(
            submission_id=submission_id,
            original_filename=original,
            file_path=rel_path,
            merchant=merchant,
            transaction_date=transaction_date,
            amount=amount,
            currency=currency,
            category=category,
            raw_extracted_text=raw_text,
        )
        db.add(receipt)
        created.append(receipt)

    await db.flush()
    for receipt in created:
        await db.refresh(receipt)

    return ReceiptUploadResponse(
        submission_id=submission_id,
        receipts=[ReceiptRead.model_validate(r) for r in created],
        warnings=warnings,
    )


@router.get("/{submission_id}/receipts", response_model=list[ReceiptRead])
async def list_receipts(
    submission_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """List all receipts attached to a submission."""
    await _get_submission(db, submission_id)
    result = await db.execute(
        select(Receipt)
        .where(Receipt.submission_id == submission_id)
        .order_by(Receipt.created_at)
    )
    return result.scalars().all()
