# Northwind Expense AI

AI-powered expense review and approval platform built with Next.js 14, FastAPI, Supabase (Postgres + pgvector), and Claude.

## Tech stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 14 (App Router), TypeScript, Tailwind CSS |
| Backend | FastAPI, SQLAlchemy (async), Alembic |
| Database | Supabase Postgres 16 + pgvector |
| AI | Anthropic Claude API |
| Auth | Supabase Auth + JWT |
| Infra | Docker / docker-compose |

## Project structure

```
northwind-expense-ai/
├── frontend/                  # Next.js 14 app
│   ├── src/
│   │   ├── app/               # App Router pages & layouts
│   │   ├── components/        # Reusable UI components
│   │   ├── lib/
│   │   │   ├── api.ts         # Typed fetch wrapper for FastAPI
│   │   │   └── supabase/      # Browser & server Supabase clients
│   │   └── types/             # Shared TypeScript types
│   ├── Dockerfile
│   └── package.json
│
├── backend/                   # FastAPI service
│   ├── app/
│   │   ├── api/v1/routes/     # per-resource route files
│   │   ├── core/              # config.py, database.py
│   │   ├── models/            # SQLAlchemy ORM models (7 domain tables)
│   │   ├── schemas/           # Pydantic request/response schemas
│   │   ├── services/          # ai_reviewer.py, receipt_extractor.py, retrieval.py, anthropic_client.py
│   │   └── main.py
│   ├── tests/
│   └── requirements.txt
│
├── policies/                  # Source policy PDFs (policy1.pdf … policy8.pdf)
├── submissions/               # Sample expense submissions
│   └── NN_<name>/
│       ├── employee_info.json
│       └── receipts/          # Receipt PDFs for that trip
│
├── supabase/
│   ├── config.toml
│   └── migrations/
│       ├── 001_enable_extensions.sql   # uuid-ossp, pgcrypto, vector
│       ├── 002_initial_schema.sql      # skeleton tables (superseded)
│       ├── 003_northwind_schema.sql    # production domain schema
│       └── 004_review_vocabulary.sql   # verdict/status check constraints
│
├── Dockerfile                 # Backend production image
├── docker-compose.yml         # Full local stack
└── .env.example
```

## Local development

### Prerequisites
- Docker Desktop
- Node.js 20+
- Python 3.12+
- Supabase CLI (`npm install -g supabase`)

### 1. Environment variables

```bash
cp .env.example .env
# Fill in ANTHROPIC_API_KEY and Supabase credentials
```

### 2. Start the full stack with Docker

```bash
docker compose up --build
```

Services:
- Frontend → http://localhost:3000
- Backend API → http://localhost:8000
- API docs → http://localhost:8000/api/v1/docs
- Postgres → localhost:54322

### 3. Run database migrations

```bash
supabase db push
# or manually:
psql postgresql://postgres:password@localhost:54322/postgres \
  -f supabase/migrations/001_enable_extensions.sql \
  -f supabase/migrations/002_initial_schema.sql \
  -f supabase/migrations/003_northwind_schema.sql
```

### 4. Seed employees

After the database is running and migrations have been applied, seed the five
sample employees from the `submissions/` folder:

```bash
cd backend
python seed_employees.py
```

Expected output:

```
2025-06-01 12:00:00 [INFO] Scanning submissions at: .../submissions
2025-06-01 12:00:00 [INFO] Found 5 unique employee record(s) across 5 submission folder(s)
2025-06-01 12:00:00 [INFO] Connecting to database…
2025-06-01 12:00:00 [INFO] Seeding complete — inserted: 5 | already existed: 0 | manager links resolved: 0
2025-06-01 12:00:00 [INFO] 5 manager_id reference(s) left as NULL (those managers are not in
                           the submissions data — populate from HR export).
```

**Flags**

| Flag | Effect |
|------|--------|
| `--dry-run` | Print what would be inserted; no DB writes |
| `--verbose` | Show a DEBUG line for every row |

**Re-running is safe** — the script uses `ON CONFLICT (employee_id) DO NOTHING` so
existing rows are never duplicated or overwritten.

**Manager IDs** — each employee references a manager (`NW-03012`, `NW-01104`, etc.)
who is not present in the sample submissions. Those `manager_id` columns are left
`NULL` on first seed. Populate them by loading a full HR employee export or by
running the seed script again after those managers are inserted.

**Verify via API** — once the backend is running:

```bash
# list all seeded employees
curl http://localhost:8000/api/v1/employees

# filter by department
curl "http://localhost:8000/api/v1/employees?department=Logistics%20Ops"

# fetch a single employee by business key
curl http://localhost:8000/api/v1/employees/NW-04821
```

### 5. Ingest policy documents

Parse the policy PDFs in `policies/`, chunk them, embed each chunk with OpenAI
`text-embedding-3-small`, and store the vectors in `policy_chunks`:

```bash
cd backend
python ingest_policies.py
```

Requires `OPENAI_API_KEY` in the project-root `.env`. The pipeline processes
**one PDF at a time** (bounded memory): extract text page-by-page → split into
overlapping token windows → detect a section heading → embed → store.

Expected output:

```
2025-06-01 12:00:00 [INFO] Found 8 PDF(s) in .../policies
2025-06-01 12:00:00 [INFO] Tokenizer: tiktoken cl100k_base
2025-06-01 12:00:00 [INFO] Processing policy1.pdf (document_id=policy1)
2025-06-01 12:00:00 [INFO]   14 page(s) → 18 chunk(s)
2025-06-01 12:00:00 [INFO]   embedded 18, stored 18 chunk(s)
...
2025-06-01 12:00:05 [INFO] Ingestion complete — PDFs processed: 8 | chunks created: 142 | embeddings stored: 142
```

(Chunk counts above are illustrative.)

**Flags**

| Flag | Effect |
|------|--------|
| `--dry-run` | Parse + chunk only; **no** OpenAI calls, **no** DB writes. Good for a cost-free check. |
| `--verbose` | Print a DEBUG line per chunk (page, index, detected section, token count) |
| `--chunk-size N` | Tokens per chunk (default **800**) |
| `--overlap N` | Token overlap between consecutive chunks (default **150**) |

**Design notes**

- **`document_id`** is the file stem (`policy1.pdf` → `policy1`), matching the
  `policy_documents` / `policy_chunks` schema. The pipeline is generic and makes
  no assumptions about a document's internal structure.
- **Chunking is per page**, so every chunk maps to exactly one `page_number`.
  Overlap is applied within a page.
- **Section detection is a regex placeholder** (`^N.N Heading`). The most recent
  heading is carried forward to chunks that don't start with one. A production
  version would parse real heading styles.
- **Re-running is safe** — `policy_documents` is upserted on `document_id`, and a
  document's existing `policy_chunks` are deleted and re-inserted each run.
- If `tiktoken` can't load its encoding (e.g. fully offline), the pipeline falls
  back to a whitespace token approximation and logs a warning.

## Policy search (retrieval)

Once policies are ingested, you can run semantic search over them. This is
**pure embedding retrieval — no LLM is called**. The query is embedded with the
same `text-embedding-3-small` model used at ingest, then ranked against
`policy_chunks` by pgvector cosine similarity.

**Endpoint:** `POST /api/v1/policy/search`

```bash
curl -X POST http://localhost:8000/api/v1/policy/search \
  -H "Content-Type: application/json" \
  -d '{"query": "Can directors fly business class?"}'
```

Request:

```json
{ "query": "Can directors fly business class?", "top_k": 5 }
```

`top_k` is optional (default **5**, max 20).

Response:

```json
{
  "query": "Can directors fly business class?",
  "confidence": "high",
  "results": [
    {
      "document_id": "policy2",
      "page_number": 1,
      "section": "2 Class of service",
      "chunk_text": "Business class is permitted only on international flight segments ...",
      "similarity": 0.61,
      "confidence": "high"
    }
  ]
}
```

**Confidence** is derived from cosine similarity (heuristics tuned for
`text-embedding-3-small`, see `services/retrieval.py`):

| Similarity | Confidence |
|------------|------------|
| ≥ 0.50 | `high` |
| 0.35 – 0.50 | `medium` |
| < 0.35 | `low` |

The top-level `confidence` reflects the best-matching chunk; each result also
carries its own per-chunk confidence. Requires `OPENAI_API_KEY` (returns `503`
if unset).

### 6. Run the backend (without Docker)

```bash
cd backend
python -m venv .venv
# Windows:  .venv\Scripts\activate     macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt

# DATABASE_URL must use the asyncpg driver, e.g.
#   postgresql+asyncpg://postgres:password@localhost:54322/postgres
uvicorn app.main:app --reload --port 8000
```

- API docs: http://localhost:8000/api/v1/docs
- Health:   http://localhost:8000/health

**Required environment variables** (read from the project-root `.env`):

| Variable | Required for | Notes |
|----------|--------------|-------|
| `DATABASE_URL` | everything | Must use `postgresql+asyncpg://…` |
| `ANTHROPIC_API_KEY` | review + image/field extraction | Optional to boot; review returns `503` without it |
| `OPENAI_API_KEY` | policy retrieval during review | Embeds the query for RAG; review still runs without it but returns `needs_review` for lack of context |
| `ANTHROPIC_MODEL` | optional | Defaults to `claude-sonnet-4-6` |

> Apply migrations through `004_review_vocabulary.sql` before reviewing — it
> aligns the verdict/status check constraints with the compliance vocabulary
> (`compliant | flagged | rejected | needs_review`).

## The expense review workflow

The end-to-end flow is: **create a submission → upload receipts → run review →
inspect verdicts → (optionally) override**.

### Create a submission

```bash
curl -X POST http://localhost:8000/api/v1/submissions \
  -H "Content-Type: application/json" \
  -d '{
    "employee_id": "NW-04821",
    "trip_purpose": "Quarterly client review in Denver",
    "trip_start_date": "2025-04-14",
    "trip_end_date": "2025-04-16"
  }'
# -> 201 { "id": "<submission_id>", "status": "pending", ... }
```

### Upload receipts

Accepts one or many files in a single multipart request. Supported types:
`.txt`, `.pdf`, `.jpg`, `.jpeg`, `.png`. Files are saved under
`backend/uploads/{submission_id}/` and the text/fields are extracted
immediately (PDF via `pypdf`, images via Claude vision, fields parsed by Claude
when `ANTHROPIC_API_KEY` is set).

```bash
curl -X POST http://localhost:8000/api/v1/submissions/<submission_id>/receipts \
  -F "files=@submissions/01_clean_denver/receipts/01_united_airlines.pdf" \
  -F "files=@submissions/01_clean_denver/receipts/04_dinner_mercantile.pdf"
# -> 201 { "submission_id": "...", "receipts": [ ... ], "warnings": [ ... ] }
```

Extraction is best-effort: a file that can't be parsed (e.g. an image uploaded
without an API key) is still saved and recorded, and the reason appears in
`warnings`.

```bash
# list receipts for a submission
curl http://localhost:8000/api/v1/submissions/<submission_id>/receipts
```

### Run the AI review

Reviews every receipt that doesn't yet have a verdict. For each receipt Claude
is given the employee + trip context, the receipt fields/text, and the top
policy chunks retrieved by pgvector, and returns a schema-constrained verdict.
Quotes and citations are validated against the retrieved chunks server-side, so
nothing is fabricated.

```bash
curl -X POST http://localhost:8000/api/v1/submissions/<submission_id>/review
```

```json
{
  "submission_id": "...",
  "status": "flagged",
  "reviewed": 2,
  "verdicts": [
    {
      "id": "...",
      "receipt_id": "...",
      "verdict": "flagged",
      "category": "meal",
      "reasoning": "Dinner exceeds the per-person meal cap...",
      "confidence": 0.82,
      "policy_citations": [
        {"document_id": "policy3", "page_number": 2, "section": "4.2", "reason": "Meal cap"}
      ],
      "quoted_policy_clauses": [
        {"document_id": "policy3", "quote": "Meals shall not exceed $75 per person per day"}
      ],
      "overrides": [],
      "effective_verdict": "flagged"
    }
  ]
}
```

The submission `status` is rolled up from the receipt verdicts using the
precedence **rejected > flagged > needs_review > compliant** (review returns
`503` if `ANTHROPIC_API_KEY` is missing).

### Inspect and override a verdict

Verdicts are append-only. A human override never mutates the AI verdict — it is
added to an audit trail and the **latest override wins** as `effective_verdict`.

```bash
# fetch the verdict (with override trail) for a receipt
curl http://localhost:8000/api/v1/receipts/<receipt_id>/verdict

# override a verdict
curl -X POST http://localhost:8000/api/v1/verdicts/<verdict_id>/override \
  -H "Content-Type: application/json" \
  -d '{
    "override_verdict": "compliant",
    "reviewer_name": "Jordan Lee",
    "comment": "Pre-approved by finance for the client dinner."
  }'
```

### Smoke test

With the backend running and an employee seeded, exercise the whole path:

```bash
cd backend
python smoke_test_backend.py --base-url http://localhost:8000
```

It checks `/health`, lists employees, creates a submission, uploads a TXT
receipt, runs the review, and applies an override — reporting `PASS`/`FAIL`/`SKIP`
per step (steps needing a key/DB that isn't configured are skipped, not failed).

## Database schema

Migration `003_northwind_schema.sql` defines the full domain model. All tables live in the `public` schema with RLS enabled.

```
employees
├── employee_id  TEXT UNIQUE       — natural key, e.g. "NW-04821"
├── name / grade / title / department / home_base
└── manager_id   TEXT → employees(employee_id)   — self-referencing org tree

submissions
├── employee_id  → employees(employee_id)
├── folder_name  TEXT              — matches the /submissions sub-directory name
├── trip_purpose / trip_start_date / trip_end_date
└── status       TEXT              — pending | under_review | compliant | flagged | rejected | needs_review

receipts
├── submission_id → submissions(id)
├── original_filename / file_path (relative from project root)
├── merchant / transaction_date / amount / currency
├── category     TEXT              — flight | hotel | transport | meal | registration | other
└── raw_extracted_text             — full Claude/OCR output for audit trail

verdicts  (1-to-1 with receipts, written by Claude)
├── receipt_id  → receipts(id)
├── verdict     TEXT              — compliant | flagged | rejected | needs_review
├── reasoning / confidence (0.000–1.000)
├── policy_citations   JSONB[]    — [{document_id, page_number, section, reason}]
└── quoted_policy_clauses JSONB[] — [{document_id, quote}] — verbatim excerpts from retrieved chunks

overrides  (many-to-1 with verdicts, written by human reviewers)
├── verdict_id → verdicts(id)
├── override_verdict / reviewer_name / comment
└── created_at                    — append-only audit log; latest row wins

policy_documents
├── document_id TEXT UNIQUE       — "policy1" … "policy8" (stem of filename)
└── filename / title

policy_chunks  (RAG index over policy PDFs)
├── document_id → policy_documents(document_id)
├── section / page_number / chunk_text
├── embedding   vector(1536)      — IVFFlat cosine index (lists=100)
└── metadata    JSONB             — chunking provenance (offsets, headings)
```

### Key design decisions

- **`employee_id` is a text natural key** (`NW-XXXXX`) rather than a UUID — it is the canonical identifier used in every `employee_info.json` and by the HR system.
- **`receipts.file_path` is relative** to the project root so the path survives container re-mounts without absolute-path coupling.
- **`verdicts` are append-only** per receipt (unique constraint on `receipt_id`). Human corrections go into `overrides` rather than mutating the original AI verdict, preserving the full audit trail.
- **`policy_chunks.embedding`** uses an IVFFlat index with `lists=100`, appropriate for up to ~1 million vectors. Switch to HNSW (`vector_hnsw_ops`) for higher recall at scale.

## Key API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness check (no DB) |
| GET | `/api/v1/employees` | List employees (optional `?department=`) |
| GET | `/api/v1/employees/{employee_id}` | Fetch one employee by business key |
| POST | `/api/v1/policy/search` | Semantic search over policy chunks (embedding retrieval, no LLM) |
| POST | `/api/v1/submissions` | Create a submission |
| GET | `/api/v1/submissions` | List submissions (`?employee_id=`, `?status=`, `?date_from=`, `?date_to=`) |
| GET | `/api/v1/submissions/{id}` | Submission detail with receipts, verdicts, overrides |
| POST | `/api/v1/submissions/{id}/receipts` | Upload one or more receipt files (multipart) |
| GET | `/api/v1/submissions/{id}/receipts` | List receipts for a submission |
| POST | `/api/v1/submissions/{id}/review` | Run AI review for all not-yet-reviewed receipts |
| GET | `/api/v1/receipts/{id}/verdict` | Fetch AI verdict (+ override trail) for a receipt |
| POST | `/api/v1/verdicts/{id}/override` | Human override of a verdict (append-only) |

## Environment variables reference

See `.env.example` for all required variables and their descriptions.

## Implemented vs. not implemented

**Implemented (backend)**

- Database schema + SQLAlchemy models for the full Northwind domain
- Employee seeding (`seed_employees.py`) and employee API
- Policy ingestion (`ingest_policies.py`) and semantic policy search (`POST /policy/search`)
- Receipt text/field extraction (`services/receipt_extractor.py`) — `.txt`, `.pdf` (pypdf),
  and `.jpg/.jpeg/.png` (Claude vision), with schema-constrained JSON
- Submissions API — create, list (filterable), and detail (with receipts/verdicts/overrides)
- Receipts API — multipart upload (saved to `backend/uploads/`) + list
- AI review engine (`services/ai_reviewer.py`) — per-receipt, retrieval-grounded,
  schema-constrained verdicts with server-side citation/quote validation
- Review API (`POST /submissions/{id}/review`) + submission status roll-up
- Verdict fetch and append-only human overrides (`effective_verdict` = latest override)
- `smoke_test_backend.py` end-to-end check
- `/health`

**Not implemented yet**

- **Frontend** — still the default Next.js landing page (no review UI)
- **Auth** — endpoints are unauthenticated; RLS policies are open for local dev
- **Async/background review** — review runs synchronously in the request
- **Receipt re-extraction endpoint** — files saved without a key (e.g. images)
  must currently be re-uploaded once `ANTHROPIC_API_KEY` is set
- **Automated test suite** — only the smoke script exists (no `pytest` cases yet)
