-- Private Beat V13 registration state.
--
-- This table is intentionally service-role-only. The public site never reads
-- it through PostgREST and the normalized email is not suitable for public
-- leaderboard output. Serverless routes use the Supabase service-role key to
-- create/update rows and to atomically claim the one reminder slot.

create extension if not exists pgcrypto;

create table if not exists public.beat_v13_entries (
    id uuid primary key default gen_random_uuid(),
    email_normalized text not null unique
        check (email_normalized = lower(email_normalized)),
    status text not null default 'pending'
        check (status in ('pending', 'confirmed', 'withdrawn')),
    confirmation_sent_at timestamptz,
    confirmation_provider_id text,
    confirmed_at timestamptz,
    reminder_claimed_at timestamptz,
    reminder_scheduled_at timestamptz,
    reminder_provider_id text,
    reminder_sent_at timestamptz,
    withdrawn_at timestamptz,
    -- Reserved for the post-season official-team verification workstream.
    official_team_id text,
    official_team_name text,
    official_team_slot smallint check (official_team_slot between 1 and 3),
    official_league_id integer,
    official_league_code text,
    official_team_linked_at timestamptz,
    -- Aliases used by the live official-team sync workstream.
    team_link_status text check (team_link_status in ('pending', 'active', 'not_found', 'disconnected')),
    team_linked_at timestamptz,
    last_synced_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    check (char_length(email_normalized) between 3 and 254)
);

-- Safe for an already-created staging table from the initial registration
-- rollout; linked teams must retain their exact public-league slot.
alter table public.beat_v13_entries
    add column if not exists official_team_slot smallint
    check (official_team_slot between 1 and 3);

alter table public.beat_v13_entries
    add column if not exists official_league_code text;
alter table public.beat_v13_entries
    add column if not exists team_link_status text
    check (team_link_status in ('pending', 'active', 'not_found', 'disconnected'));
alter table public.beat_v13_entries
    add column if not exists team_linked_at timestamptz;
alter table public.beat_v13_entries
    add column if not exists last_synced_at timestamptz;

create unique index if not exists beat_v13_entries_active_official_team_idx
    on public.beat_v13_entries(official_team_id, official_team_slot)
    where official_team_id is not null
      and official_team_slot is not null
      and coalesce(team_link_status, 'active') = 'active';

create index if not exists beat_v13_entries_status_idx
    on public.beat_v13_entries(status, created_at);

drop trigger if exists beat_v13_entries_set_updated_at on public.beat_v13_entries;
create trigger beat_v13_entries_set_updated_at before update on public.beat_v13_entries
for each row execute function public.set_updated_at();

alter table public.beat_v13_entries enable row level security;

-- There are deliberately no anon/authenticated policies. Explicit grants make
-- the intended boundary clear; service_role bypasses RLS and is the only role
-- that may access registration state.
revoke all on public.beat_v13_entries from public, anon, authenticated;
grant all on public.beat_v13_entries to service_role;
