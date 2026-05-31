-- ─── Users ───────────────────────────────────────────────────────────────────
create table if not exists public.users (
    id          uuid primary key default gen_random_uuid(),
    email       text not null unique,
    full_name   text not null,
    role        text not null default 'employee'
                    check (role in ('employee', 'manager', 'finance', 'admin')),
    is_active   boolean not null default true,
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now()
);

-- ─── Expenses ─────────────────────────────────────────────────────────────────
create table if not exists public.expenses (
    id              uuid primary key default gen_random_uuid(),
    submitted_by    uuid not null references public.users(id) on delete restrict,
    title           text not null,
    description     text,
    amount          numeric(12, 2) not null check (amount > 0),
    currency        char(3) not null default 'USD',
    category        text not null,
    expense_date    timestamptz not null,
    receipt_url     text,
    status          text not null default 'pending'
                        check (status in ('pending', 'under_review', 'approved', 'rejected')),
    metadata        jsonb,
    embedding       vector(1536),          -- text-embedding-3-small dimension
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now()
);

create index on public.expenses (submitted_by);
create index on public.expenses (status);
create index on public.expenses (expense_date desc);
create index on public.expenses using ivfflat (embedding vector_cosine_ops)
    with (lists = 100);

-- ─── Expense Reviews ──────────────────────────────────────────────────────────
create table if not exists public.expense_reviews (
    id              uuid primary key default gen_random_uuid(),
    expense_id      uuid not null unique references public.expenses(id) on delete cascade,
    risk_score      smallint not null check (risk_score between 0 and 100),
    flags           jsonb,
    ai_summary      text,
    recommendation  text not null
                        check (recommendation in ('approve', 'reject', 'manual_review')),
    raw_response    jsonb,
    reviewed_at     timestamptz not null default now()
);

-- ─── Updated-at trigger ───────────────────────────────────────────────────────
create or replace function public.set_updated_at()
returns trigger language plpgsql as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

create trigger trg_users_updated_at
    before update on public.users
    for each row execute function public.set_updated_at();

create trigger trg_expenses_updated_at
    before update on public.expenses
    for each row execute function public.set_updated_at();

-- ─── Row-Level Security ───────────────────────────────────────────────────────
alter table public.users        enable row level security;
alter table public.expenses     enable row level security;
alter table public.expense_reviews enable row level security;

-- Policies are intentionally left open for local dev; restrict per env.
create policy "service_role_all_users"    on public.users            using (true);
create policy "service_role_all_expenses" on public.expenses         using (true);
create policy "service_role_all_reviews"  on public.expense_reviews  using (true);
