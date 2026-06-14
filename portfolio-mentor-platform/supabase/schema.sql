-- Run in Supabase SQL Editor (https://supabase.com/dashboard → SQL)
-- Public read for proof links; writes use service role from Next.js API only.

create table if not exists public.lab_runs (
  id uuid primary key default gen_random_uuid(),
  lab_slug text not null,
  title text not null,
  summary text not null default '',
  bullets jsonb not null default '[]'::jsonb,
  metrics jsonb not null default '{}'::jsonb,
  provider text,
  model text,
  created_at timestamptz not null default now()
);

create index if not exists lab_runs_lab_slug_idx on public.lab_runs (lab_slug);
create index if not exists lab_runs_created_at_idx on public.lab_runs (created_at desc);

alter table public.lab_runs enable row level security;

drop policy if exists "Public read lab proofs" on public.lab_runs;
create policy "Public read lab proofs"
  on public.lab_runs for select
  using (true);

-- No insert/update for anon/authenticated — API uses service role key.
