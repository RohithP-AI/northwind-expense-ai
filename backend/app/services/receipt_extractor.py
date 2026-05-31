"""
Receipt text + field extraction.

Given a receipt file, produce a structured record:
    merchant, transaction_date, amount, currency, category, description,
    raw_extracted_text

Strategy by file type:
    .txt              → read text directly
    .pdf              → extract text with pypdf (page by page)
    .jpg/.jpeg/.png   → Claude vision (requires ANTHROPIC_API_KEY)

For text-based receipts (.txt/.pdf) the raw text is always returned. The
structured fields are then parsed from that text with Claude *if* a key is
available; without a key the raw text is still returned and the fields are left
null (the AI reviewer can still work off raw_extracted_text).

All Claude extraction uses schema-constrained JSON (a forced tool call whose
input_schema is exactly the ExtractedReceipt shape).
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from pypdf import PdfReader

from app.core.config import settings
from app.services.anthropic_client import (
    AnthropicNotConfigured,
    extract_tool_use,
    get_anthropic_client,
)

log = logging.getLogger("receipt_extractor")

CATEGORIES = ["flight", "hotel", "transport", "meal", "registration", "other"]

TEXT_SUFFIXES = {".txt"}
PDF_SUFFIXES = {".pdf"}
IMAGE_MEDIA_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}

# Schema-constrained extraction tool. Claude is forced to call this, so its
# `input` arrives already shaped like the fields we need.
_EXTRACTION_TOOL = {
    "name": "record_receipt",
    "description": "Record the structured fields extracted from a single expense receipt.",
    "input_schema": {
        "type": "object",
        "properties": {
            "merchant": {
                "type": ["string", "null"],
                "description": "Merchant / vendor name as printed on the receipt.",
            },
            "transaction_date": {
                "type": ["string", "null"],
                "description": "Transaction date in strict YYYY-MM-DD format, or null if absent.",
            },
            "amount": {
                "type": ["number", "null"],
                "description": "Grand total actually charged, as a number (no currency symbol).",
            },
            "currency": {
                "type": "string",
                "description": "ISO-4217 currency code, e.g. USD. Default USD if not shown.",
            },
            "category": {
                "type": "string",
                "enum": CATEGORIES,
                "description": "Best-fit expense category.",
            },
            "description": {
                "type": ["string", "null"],
                "description": "One-line human summary of what was purchased.",
            },
        },
        "required": ["currency", "category"],
    },
}


@dataclass
class ExtractedReceipt:
    raw_extracted_text: str
    merchant: str | None = None
    transaction_date: date | None = None
    amount: Decimal | None = None
    currency: str = "USD"
    category: str | None = None
    description: str | None = None
    warnings: list[str] = field(default_factory=list)


# ── Coercion helpers ──────────────────────────────────────────────────────────
def _coerce_date(value) -> date | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except ValueError:
        log.debug("Could not parse transaction_date %r", value)
        return None


def _coerce_amount(value) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        log.debug("Could not parse amount %r", value)
        return None


def _coerce_currency(value) -> str:
    if isinstance(value, str) and len(value.strip()) == 3:
        return value.strip().upper()
    return "USD"


def _coerce_category(value) -> str | None:
    if isinstance(value, str) and value.strip().lower() in CATEGORIES:
        return value.strip().lower()
    return None


def _apply_fields(record: ExtractedReceipt, data: dict) -> None:
    record.merchant = (data.get("merchant") or None) if data.get("merchant") else None
    record.transaction_date = _coerce_date(data.get("transaction_date"))
    record.amount = _coerce_amount(data.get("amount"))
    record.currency = _coerce_currency(data.get("currency"))
    record.category = _coerce_category(data.get("category"))
    record.description = (data.get("description") or None) if data.get("description") else None


# ── Text extraction ───────────────────────────────────────────────────────────
def _read_txt(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace").strip()


def _read_pdf(path: Path) -> str:
    reader = PdfReader(str(path))
    pages = []
    for page in reader.pages:
        text = page.extract_text() or ""
        if text.strip():
            pages.append(text.strip())
    return "\n\n".join(pages).strip()


# ── Claude-backed field parsing ───────────────────────────────────────────────
async def _parse_fields_from_text(raw_text: str) -> dict:
    client = get_anthropic_client()
    resp = await client.messages.create(
        model=settings.ANTHROPIC_MODEL,
        max_tokens=settings.ANTHROPIC_MAX_TOKENS,
        tools=[_EXTRACTION_TOOL],
        tool_choice={"type": "tool", "name": "record_receipt"},
        messages=[
            {
                "role": "user",
                "content": (
                    "Extract the structured fields from this expense receipt text. "
                    "Only use information present in the text; use null when a field "
                    "is not shown.\n\n--- RECEIPT TEXT ---\n" + raw_text
                ),
            }
        ],
    )
    return extract_tool_use(resp, "record_receipt")


async def _extract_from_image(path: Path, media_type: str) -> dict:
    client = get_anthropic_client()
    b64 = base64.standard_b64encode(path.read_bytes()).decode("ascii")
    resp = await client.messages.create(
        model=settings.ANTHROPIC_MODEL,
        max_tokens=settings.ANTHROPIC_MAX_TOKENS,
        tools=[_EXTRACTION_TOOL],
        tool_choice={"type": "tool", "name": "record_receipt"},
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": (
                            "Read this receipt image. First transcribe all legible text, "
                            "then record the structured fields by calling the tool. Use null "
                            "for anything you cannot read."
                        ),
                    },
                ],
            }
        ],
    )
    data = extract_tool_use(resp, "record_receipt")
    # Vision doesn't give us a separate raw transcript via the tool; synthesize a
    # readable raw_extracted_text from the structured fields so the audit trail
    # and the reviewer still have something to work with.
    data.setdefault(
        "_raw",
        "\n".join(
            f"{k}: {v}"
            for k, v in (
                ("merchant", data.get("merchant")),
                ("date", data.get("transaction_date")),
                ("amount", data.get("amount")),
                ("currency", data.get("currency")),
                ("category", data.get("category")),
                ("description", data.get("description")),
            )
            if v
        ),
    )
    return data


# ── Public entry point ────────────────────────────────────────────────────────
async def extract_receipt(file_path: Path | str, original_filename: str | None = None) -> ExtractedReceipt:
    """
    Extract text + structured fields from a single receipt file.

    Raises AnthropicNotConfigured for image receipts when no API key is set
    (images cannot be read without Claude vision). Text/PDF receipts never
    raise on a missing key — they return raw text with null fields.
    """
    path = Path(file_path)
    suffix = path.suffix.lower()
    name = original_filename or path.name

    if not path.exists():
        raise FileNotFoundError(f"Receipt file not found: {path}")

    # ── Image: requires Claude vision ──
    if suffix in IMAGE_MEDIA_TYPES:
        if not settings.ANTHROPIC_API_KEY:
            raise AnthropicNotConfigured(
                f"Cannot extract image receipt {name!r}: ANTHROPIC_API_KEY is not set "
                "and image OCR requires Claude vision."
            )
        data = await _extract_from_image(path, IMAGE_MEDIA_TYPES[suffix])
        record = ExtractedReceipt(raw_extracted_text=data.pop("_raw", "").strip())
        _apply_fields(record, data)
        return record

    # ── Text / PDF: always recover raw text first ──
    if suffix in TEXT_SUFFIXES:
        raw = _read_txt(path)
    elif suffix in PDF_SUFFIXES:
        raw = _read_pdf(path)
    else:
        raise ValueError(
            f"Unsupported receipt type {suffix!r} for {name!r} "
            f"(supported: .txt, .pdf, .jpg, .jpeg, .png)."
        )

    record = ExtractedReceipt(raw_extracted_text=raw)

    if not raw:
        record.warnings.append(f"No text could be extracted from {name!r}.")
        return record

    # Parse structured fields from the text if Claude is available.
    if settings.ANTHROPIC_API_KEY:
        try:
            data = await _parse_fields_from_text(raw)
            _apply_fields(record, data)
        except Exception as exc:  # noqa: BLE001 — extraction is best-effort
            log.warning("Field parsing failed for %s: %s", name, exc)
            record.warnings.append(f"Field parsing failed for {name!r}: {exc}")
    else:
        record.warnings.append(
            f"ANTHROPIC_API_KEY not set — stored raw text for {name!r} without parsed fields."
        )

    return record
