-- ─────────────────────────────────────────────────────────────────────────────
-- 003_northwind_schema.sql
-- Northwind Logistics – AI Expense Review System
-- ─────────────────────────────────────────────────────────────────────────────

-- Extensions are enabled in 001_enable_extensions.sql (uuid-ossp, pgcrypto, vector)

-- ─── 1. employees ─────────────────────────────────────────────────────────────
-- employee_id is the natural business key (e.g. "NW-04821") carried in every
-- employee_info.json.  manager_id is a self-referencing text FK so the org
-- tree can be reconstructed without a separate lookup.
create table if not exists public.employees (
    id              uuid        primary key default gen_random_uuid(),
    employee_id     text        not null unique,            -- e.g. "NW-04821"
    name            text        not null,
    grade           smallint    not null,                   -- 1-10 seniority band
    title           text        not null,
    department      text        not null,
    manager_id      text        references public.employees(employee_id)
                                on update cascade on delete set null,
    home_base       text        not null,
    created_at      timestamptz not null default now()
);

create index on public.employees (employee_id);
create index on public.employees (manager_id);
create index on public.employees (department);


-- ─── 2. submissions ───────────────────────────────────────────────────────────
-- One row per expense report folder (e.g. "01_clean_denver").
-- trip_start_date / trip_end_date are parsed from the "trip_dates" string in
-- employee_info.json ("2025-04-14 to 2025-04-16").
create table if not exists public.submissions (
    id              uuid        primary key default gen_random_uuid(),
    employee_id     text        not null
                                references public.employees(employee_id)
                                on update cascade on delete restrict,
    folder_name     text        not null,                   -- e.g. "01_clean_denver"
    trip_purpose    text        not null,
    trip_start_date date        not null,
    trip_end_date   date        not null,
    status          text        not null default 'pending'
                                check (status in (
                                    'pending',
                                    'under_review',
                                    'approved',
                                    'rejected',
                                    'flagged'
                                )),
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now()
);

create index on public.submissions (employee_id);
create index on public.submissions (status);
create index on public.submissions (trip_start_date desc);


-- ─── 3. receipts ──────────────────────────────────────────────────────────────
-- One row per PDF file inside a submission's /receipts folder.
-- file_path is relative to the project root, e.g.
--   "submissions/01_clean_denver/receipts/01_united_airlines.pdf"
-- raw_extracted_text holds the full Claude/OCR extraction for audit trail.
create table if not exists public.receipts (
    id                  uuid        primary key default gen_random_uuid(),
    submission_id       uuid        not null
                                    references public.submissions(id)
                                    on delete cascade,
    original_filename   text        not null,               -- "01_united_airlines.pdf"
    file_path           text        not null,               -- relative path from project root
    merchant            text,
    transaction_date    date,
    amount              numeric(12, 2),
    currency            char(3)     not null default 'USD',
    category            text        check (category in (
                                        'flight',
                                        'hotel',
                                        'transport',
                                        'meal',
                                        'registration',
                                        'other'
                                    )),
    raw_extracted_text  text,
    created_at          timestamptz not null default now()
);

create index on public.receipts (submission_id);
create index on public.receipts (category);
create index on public.receipts (transaction_date desc);


-- ─── 4. verdicts ──────────────────────────────────────────────────────────────
-- Claude's per-receipt AI decision.
-- policy_citations: [{"document_id": "policy3", "section": "4.2", "title": "..."}]
-- quoted_policy_clauses: ["Meals shall not exceed $75 per person per day ..."]
-- confidence is 0.000–1.000 (model's self-assessed certainty).
create table if not exists public.verdicts (
    id                      uuid            primary key default gen_random_uuid(),
    receipt_id              uuid            not null unique
                                            references public.receipts(id)
                                            on delete cascade,
    verdict                 text            not null
                                            check (verdict in (
                                                'approved',
                                                'rejected',
                                                'flagged',
                                                'needs_clarification'
                                            )),
    reasoning               text            not null,
    confidence              numeric(4, 3)   not null
                                            check (confidence between 0 and 1),
    policy_citations        jsonb           not null default '[]',
    quoted_policy_clauses   jsonb           not null default '[]',
    created_at              timestamptz     not null default now()
);

create index on public.verdicts (receipt_id);
create index on public.verdicts (verdict);


-- ─── 5. overrides ─────────────────────────────────────────────────────────────
-- Human reviewer manually overrides an AI verdict.
-- A verdict can be overridden more than once (audit log); latest row wins.
create table if not exists public.overrides (
    id                  uuid        primary key default gen_random_uuid(),
    verdict_id          uuid        not null
                                    references public.verdicts(id)
                                    on delete cascade,
    override_verdict    text        not null
                                    check (override_verdict in (
                                        'approved',
                                        'rejected',
                                        'flagged',
                                        'needs_clarification'
                                    )),
    reviewer_name       text        not null,
    comment             text,
    created_at          timestamptz not null default now()
);

create index on public.overrides (verdict_id);
create index on public.overrides (created_at desc);


-- ─── 6. policy_documents ──────────────────────────────────────────────────────
-- Metadata row for each PDF in /policies (policy1.pdf … policy8.pdf).
-- document_id matches the stem of the filename ("policy1", "policy2", …).
create table if not exists public.policy_documents (
    id          uuid        primary key default gen_random_uuid(),
    document_id text        not null unique,    -- "policy1" … "policy8"
    filename    text        not null,           -- "policy1.pdf"
    title       text        not null,
    created_at  timestamptz not null default now()
);

create index on public.policy_documents (document_id);


-- ─── 7. policy_chunks ─────────────────────────────────────────────────────────
-- Each policy PDF is split into chunks for RAG retrieval.
-- embedding is a 1536-dim vector (text-embedding-3-small).
-- metadata stores arbitrary chunking provenance (char offsets, headings, etc.).
create table if not exists public.policy_chunks (
    id          uuid        primary key default gen_random_uuid(),
    document_id text        not null
                            references public.policy_documents(document_id)
                            on update cascade on delete cascade,
    section     text,                           -- e.g. "4.2 Meal Allowances"
    page_number smallint,
    chunk_text  text        not null,
    embedding   vector(1536),
    metadata    jsonb       not null default '{}',
    created_at  timestamptz not null default now()
);

create index on public.policy_chunks (document_id);
-- IVFFlat index for fast approximate cosine similarity search.
-- lists=100 is appropriate for up to ~1 million vectors.
create index on public.policy_chunks
    using ivfflat (embedding vector_cosine_ops)
    with (lists = 100);


-- ─── updated_at trigger (reuse function from 002 if present) ─────────────────
create or replace function public.set_updated_at()
returns trigger language plpgsql as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

drop trigger if exists trg_submissions_updated_at on public.submissions;
create trigger trg_submissions_updated_at
    before update on public.submissions
    for each row execute function public.set_updated_at();


-- ─── Row-Level Security ───────────────────────────────────────────────────────
alter table public.employees         enable row level security;
alter table public.submissions       enable row level security;
alter table public.receipts          enable row level security;
alter table public.verdicts          enable row level security;
alter table public.overrides         enable row level security;
alter table public.policy_documents  enable row level security;
alter table public.policy_chunks     enable row level security;

-- Open policies for local dev / service-role access.
-- Tighten per-role in a later migration before deploying to prod.
create policy "service_all_employees"        on public.employees        using (true);
create policy "service_all_submissions"      on public.submissions      using (true);
create policy "service_all_receipts"         on public.receipts         using (true);
create policy "service_all_verdicts"         on public.verdicts         using (true);
create policy "service_all_overrides"        on public.overrides        using (true);
create policy "service_all_policy_documents" on public.policy_documents using (true);
create policy "service_all_policy_chunks"    on public.policy_chunks    using (true);
