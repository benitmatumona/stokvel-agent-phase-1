-- Run once in the Supabase SQL editor.
create table if not exists public.sessions (
  session_id text primary key,
  data       jsonb not null,
  updated_at timestamptz not null default now()
);

-- The server uses the service_role key, which bypasses RLS. Enabling RLS with
-- no policies blocks the public anon key from reading or writing sessions.
alter table public.sessions enable row level security;
