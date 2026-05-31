-- ─────────────────────────────────────────────────────────────────────────────
-- 004_review_vocabulary.sql
-- Align verdict / submission status vocabulary with the AI review API contract.
--
-- The original schema (003) used HR-style words ("approved", "needs_clarification").
-- The review engine and API speak in compliance terms instead:
--     verdict / override_verdict : compliant | flagged | rejected | needs_review
--     submission status          : pending | under_review
--                                  | compliant | flagged | rejected | needs_review
--
-- This migration is idempotent and can be re-run safely.
-- ─────────────────────────────────────────────────────────────────────────────

-- ─── verdicts.verdict ─────────────────────────────────────────────────────────
alter table public.verdicts
    drop constraint if exists verdicts_verdict_check;
alter table public.verdicts
    add constraint verdicts_verdict_check
    check (verdict in ('compliant', 'flagged', 'rejected', 'needs_review'));

-- ─── overrides.override_verdict ───────────────────────────────────────────────
alter table public.overrides
    drop constraint if exists overrides_override_verdict_check;
alter table public.overrides
    add constraint overrides_override_verdict_check
    check (override_verdict in ('compliant', 'flagged', 'rejected', 'needs_review'));

-- ─── submissions.status ───────────────────────────────────────────────────────
-- 'pending' (just created) and 'under_review' (review in flight) are retained;
-- the terminal states now mirror the verdict vocabulary.
alter table public.submissions
    drop constraint if exists submissions_status_check;
alter table public.submissions
    add constraint submissions_status_check
    check (status in (
        'pending',
        'under_review',
        'compliant',
        'flagged',
        'rejected',
        'needs_review'
    ));
