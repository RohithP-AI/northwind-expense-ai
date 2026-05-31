"""
Policy ingestion pipeline.

Reads every PDF in /policies ONE FILE AT A TIME, extracts text page by page,
splits each page into overlapping token windows, attaches a (placeholder)
section heading detected via regex, embeds each chunk with OpenAI
text-embedding-3-small, and stores the results in policy_documents and
policy_chunks.

This pipeline is intentionally GENERIC: it keys everything off the filename
(document_id = file stem, e.g. "policy1") and makes no assumptions about the
internal structure of any particular policy document.

Usage (from the backend/ directory):
    python ingest_policies.py

Optional flags:
    --dry-run            Parse + chunk only. No OpenAI calls, no DB writes.
    --verbose            Show per-chunk DEBUG lines.
    --chunk-size N       Tokens per chunk (default 800).
    --overlap N          Token overlap between chunks (default 150).

Re-running is safe: each document's chunks are deleted and re-inserted, and
policy_documents rows are upserted on document_id.
"""

import argparse
import asyncio
import json
import logging
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from dotenv import load_dotenv

# NOTE: asyncpg and openai are imported lazily inside main() so that a
# --dry-run works with neither a database driver nor an API key installed.

# ── Paths ────────────────────────────────────────────────────────────────────
BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent
POLICIES_DIR = PROJECT_ROOT / "policies"

# Load .env from project root so DATABASE_URL / OPENAI_API_KEY are available
# when the script is run from backend/.
load_dotenv(PROJECT_ROOT / ".env", override=False)

# ── Config (read directly from env to avoid importing app settings, which
#    require ANTHROPIC_API_KEY at import time) ────────────────────────────────
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDING_DIM = 1536  # text-embedding-3-small output dimensionality
EMBED_BATCH_SIZE = 96  # inputs per OpenAI embeddings request

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("ingest_policies")


# ── Tokenizer ─────────────────────────────────────────────────────────────────
# text-embedding-3-small uses the cl100k_base encoding. We chunk on real tokens
# when tiktoken is available, and fall back to a whitespace approximation if the
# encoding cannot be loaded (e.g. fully offline first run).
class Tokenizer:
    def __init__(self) -> None:
        self._enc = None
        try:
            import tiktoken

            self._enc = tiktoken.get_encoding("cl100k_base")
            log.info("Tokenizer: tiktoken cl100k_base")
        except Exception as exc:  # network / import failure
            log.warning("tiktoken unavailable (%s) — using whitespace approximation", exc)

    def encode(self, text: str) -> list:
        if self._enc is not None:
            return self._enc.encode(text)
        return text.split()

    def decode(self, tokens: list) -> str:
        if self._enc is not None:
            return self._enc.decode(tokens)
        return " ".join(tokens)


# ── Section detection (PLACEHOLDER) ───────────────────────────────────────────
# Matches numbered headings like:
#   "1. Purpose"  /  "2.3. High-cost cities"  /  "10. Document control"
# This is a deliberately simple regex placeholder; a production version would
# parse the document's actual heading styles / font sizes.
SECTION_RE = re.compile(
    r"^\s*(\d+(?:\.\d+)*)\.?\s+([A-Z][A-Za-z0-9 ,&/()'\-]{2,80})\s*$",
    re.MULTILINE,
)


def detect_last_section(text: str) -> str | None:
    """Return the last numbered heading appearing in `text`, or None."""
    matches = list(SECTION_RE.finditer(text))
    if not matches:
        return None
    num, title = matches[-1].group(1), matches[-1].group(2)
    return f"{num} {title.strip()}"


# ── Data model ────────────────────────────────────────────────────────────────
@dataclass
class Chunk:
    document_id: str
    filename: str
    page_number: int
    section: str | None
    chunk_text: str
    token_count: int
    chunk_index: int
    embedding: list[float] | None = field(default=None, repr=False)


# ── PDF reading (one file, one page at a time) ────────────────────────────────
def iter_pdf_paths() -> list[Path]:
    return sorted(POLICIES_DIR.glob("*.pdf"))


def extract_pages(path: Path) -> Iterator[tuple[int, str]]:
    """Yield (page_number, text) for each page. Page numbers are 1-based."""
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    for i, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        yield i, text


def extract_title(first_page_text: str, fallback: str) -> str:
    """Best-effort title: first non-empty line of page 1, truncated."""
    for line in first_page_text.splitlines():
        line = line.strip()
        if line:
            return line[:255]
    return fallback


# ── Chunking ──────────────────────────────────────────────────────────────────
def chunk_document(
    document_id: str,
    filename: str,
    pages: Iterator[tuple[int, str]],
    tok: Tokenizer,
    chunk_size: int,
    overlap: int,
) -> list[Chunk]:
    """
    Split each page into overlapping token windows of `chunk_size` tokens with
    `overlap` tokens of carry-over. Chunking is done per page so that every
    chunk maps to exactly one page_number. The current section heading is
    carried across pages.
    """
    stride = max(1, chunk_size - overlap)
    chunks: list[Chunk] = []
    current_section: str | None = None
    chunk_index = 0

    for page_number, page_text in pages:
        clean = page_text.strip()
        if not clean:
            continue

        tokens = tok.encode(clean)
        start = 0
        while start < len(tokens):
            window = tokens[start : start + chunk_size]
            chunk_text = tok.decode(window).strip()
            if chunk_text:
                # Update section if this chunk introduces a new heading;
                # otherwise inherit the most recent one.
                found = detect_last_section(chunk_text)
                if found:
                    current_section = found
                chunks.append(
                    Chunk(
                        document_id=document_id,
                        filename=filename,
                        page_number=page_number,
                        section=current_section,
                        chunk_text=chunk_text,
                        token_count=len(window),
                        chunk_index=chunk_index,
                    )
                )
                chunk_index += 1
            start += stride

    return chunks


# ── Embeddings ────────────────────────────────────────────────────────────────
async def embed_chunks(client, chunks: list[Chunk]) -> int:
    """Embed all chunks in batches; mutate each Chunk.embedding in place."""
    embedded = 0
    for i in range(0, len(chunks), EMBED_BATCH_SIZE):
        batch = chunks[i : i + EMBED_BATCH_SIZE]
        resp = await client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=[c.chunk_text for c in batch],
        )
        for chunk, item in zip(batch, resp.data):
            chunk.embedding = item.embedding
            embedded += 1
    return embedded


# ── Database ──────────────────────────────────────────────────────────────────
def vector_literal(embedding: list[float]) -> str:
    """pgvector text input format: '[0.1,0.2,...]'."""
    return "[" + ",".join(repr(float(x)) for x in embedding) + "]"


async def store_document(
    conn: asyncpg.Connection,
    document_id: str,
    filename: str,
    title: str,
    chunks: list[Chunk],
) -> int:
    """Upsert the document row, replace its chunks. Returns chunks inserted."""
    async with conn.transaction():
        await conn.execute(
            """
            INSERT INTO policy_documents (document_id, filename, title)
            VALUES ($1, $2, $3)
            ON CONFLICT (document_id)
            DO UPDATE SET filename = EXCLUDED.filename, title = EXCLUDED.title
            """,
            document_id, filename, title,
        )
        # Clean re-ingest: drop any prior chunks for this document.
        await conn.execute(
            "DELETE FROM policy_chunks WHERE document_id = $1", document_id
        )
        for c in chunks:
            await conn.execute(
                """
                INSERT INTO policy_chunks
                    (document_id, section, page_number, chunk_text, embedding, metadata)
                VALUES ($1, $2, $3, $4, $5::vector, $6::jsonb)
                """,
                c.document_id,
                c.section,
                c.page_number,
                c.chunk_text,
                vector_literal(c.embedding) if c.embedding is not None else None,
                json.dumps(
                    {
                        "filename": c.filename,
                        "chunk_index": c.chunk_index,
                        "token_count": c.token_count,
                        "embedding_model": EMBEDDING_MODEL,
                    }
                ),
            )
    return len(chunks)


# ── Orchestration ─────────────────────────────────────────────────────────────
async def main(dry_run: bool, verbose: bool, chunk_size: int, overlap: int) -> None:
    if verbose:
        log.setLevel(logging.DEBUG)
    if overlap >= chunk_size:
        log.error("--overlap (%d) must be smaller than --chunk-size (%d)", overlap, chunk_size)
        sys.exit(1)

    pdf_paths = iter_pdf_paths()
    if not pdf_paths:
        log.warning("No PDFs found in %s — nothing to ingest.", POLICIES_DIR)
        return
    log.info("Found %d PDF(s) in %s", len(pdf_paths), POLICIES_DIR)

    tok = Tokenizer()

    # Lazily set up OpenAI + DB only when we are actually going to use them.
    openai_client = None
    conn = None
    if not dry_run:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            log.error("OPENAI_API_KEY is not set. Add it to the project-root .env file.")
            sys.exit(1)
        from openai import AsyncOpenAI

        openai_client = AsyncOpenAI(api_key=api_key)

        import asyncpg

        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            log.error("DATABASE_URL is not set. Copy .env.example to .env at the project root.")
            sys.exit(1)
        dsn = (
            database_url.replace("postgresql+asyncpg://", "postgresql://")
            .replace("postgresql+psycopg://", "postgresql://")
        )
        try:
            conn = await asyncpg.connect(dsn)
        except (asyncpg.PostgresError, OSError) as exc:
            log.error("Could not connect to database: %s", exc)
            sys.exit(1)

    # ── Totals ────────────────────────────────────────────────────────────────
    docs_processed = 0
    total_chunks = 0
    total_embeddings = 0

    try:
        # FILE-BY-FILE: each PDF is fully parsed, chunked, embedded, and stored
        # before the next one is opened, keeping memory bounded.
        for path in pdf_paths:
            document_id = path.stem  # e.g. "policy1"
            filename = path.name  # e.g. "policy1.pdf"
            log.info("Processing %s (document_id=%s)", filename, document_id)

            pages = list(extract_pages(path))
            if not pages:
                log.warning("  %s has no extractable text — skipping", filename)
                continue
            title = extract_title(pages[0][1], fallback=document_id)

            chunks = chunk_document(
                document_id, filename, iter(pages), tok, chunk_size, overlap
            )
            log.info("  %d page(s) -> %d chunk(s)", len(pages), len(chunks))
            if verbose:
                for c in chunks:
                    log.debug(
                        "    p%-2d #%-3d [%s] %d tok",
                        c.page_number, c.chunk_index, c.section or "—", c.token_count,
                    )

            docs_processed += 1
            total_chunks += len(chunks)

            if dry_run:
                continue

            n_emb = await embed_chunks(openai_client, chunks)
            total_embeddings += n_emb
            inserted = await store_document(conn, document_id, filename, title, chunks)
            log.info("  embedded %d, stored %d chunk(s)", n_emb, inserted)
    finally:
        if conn is not None:
            await conn.close()

    # ── Summary ─────────────────────────────────────────────────────────────────
    mode = " (dry run - no embeddings or DB writes)" if dry_run else ""
    log.info(
        "Ingestion complete%s - PDFs processed: %d | chunks created: %d | embeddings stored: %d",
        mode, docs_processed, total_chunks, total_embeddings,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest policy PDFs into pgvector")
    parser.add_argument("--dry-run", action="store_true", help="Parse + chunk only; no API/DB")
    parser.add_argument("--verbose", action="store_true", help="Show per-chunk DEBUG lines")
    parser.add_argument("--chunk-size", type=int, default=800, help="Tokens per chunk")
    parser.add_argument("--overlap", type=int, default=150, help="Token overlap between chunks")
    args = parser.parse_args()

    asyncio.run(
        main(
            dry_run=args.dry_run,
            verbose=args.verbose,
            chunk_size=args.chunk_size,
            overlap=args.overlap,
        )
    )
