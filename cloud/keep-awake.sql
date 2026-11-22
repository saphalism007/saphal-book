-- Keeping the free project from being paused.
--
-- Run this once, in the Supabase SQL Editor, on the saphal-book project.
-- Running it twice does no harm.
--
-- Supabase pauses a free project after about a week without enough activity.
-- A job on GitHub called the project twice a day for a month and it was still
-- marked inactive, because neither call made the database do anything: one
-- asked the sign in service if it was up, the other was turned away at the
-- door of the books table.
--
-- This gives the job something real to do. The function below writes one row,
-- the time of the last call, and reads it back. That is a genuine query and a
-- genuine write on every call.
--
-- What it opens up, plainly: anybody holding the public key, which is inside
-- the app and is meant to be public, can call this and move one timestamp.
-- It touches nothing else. It cannot read or write the books table, and it
-- takes no input.

create table if not exists public.heartbeat (
    id          int         primary key default 1 check (id = 1),
    last_call   timestamptz not null default now(),
    calls       bigint      not null default 0
);

-- Nobody reaches the table directly. Only through the function below.
alter table public.heartbeat enable row level security;
revoke all on public.heartbeat from anon, authenticated;

create or replace function public.keep_awake()
returns timestamptz
language sql
security definer
set search_path = ''
as $$
    insert into public.heartbeat (id, last_call, calls) values (1, now(), 1)
    on conflict (id) do update
        set last_call = now(), calls = public.heartbeat.calls + 1
    returning last_call;
$$;

revoke all on function public.keep_awake() from public;
grant execute on function public.keep_awake() to anon, authenticated;
