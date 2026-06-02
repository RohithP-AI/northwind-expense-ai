-- ─────────────────────────────────────────────────────────────────────────────
-- 005_policy_chunks_hnsw_index.sql
-- Replace the IVFFlat index on policy_chunks.embedding with an HNSW index.
--
-- Why: the IVFFlat index was created with lists=100, which is far too many for
-- the small policy corpus (~100 chunks). With the default ivfflat.probes=1 a
-- query scans a single, often-empty list and returns 0–2 rows regardless of the
-- LIMIT — surfacing as "No policy chunks retrieved" during reviews. HNSW needs
-- no lists/probes tuning and gives high recall across corpus sizes.
--
-- Idempotent and safe to re-run.
-- ─────────────────────────────────────────────────────────────────────────────

drop index if exists public.policy_chunks_embedding_idx;

create index if not exists policy_chunks_embedding_idx
    on public.policy_chunks
    using hnsw (embedding vector_cosine_ops);
