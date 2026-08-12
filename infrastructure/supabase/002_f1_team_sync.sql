-- Official F1 Fantasy team linking and read-only snapshot history.
-- The importer uses a single organiser session. Members only choose one
-- visible team from the Box Box F1 Fantasy league; no F1 credentials are stored.

create table if not exists public.f1_team_links (
    user_id uuid primary key references public.member_profiles(user_id) on delete cascade,
    league_id integer not null default 160604,
    league_type text not null default 'public' check (league_type in ('public', 'private')),
    team_slot smallint not null check (team_slot between 1 and 3),
    official_team_id text not null check (char_length(official_team_id) between 1 and 100),
    official_team_name text not null check (char_length(official_team_name) between 1 and 100),
    manager_name text,
    status text not null default 'active' check (status in ('active', 'not_found', 'disconnected')),
    linked_at timestamptz not null default now(),
    last_synced_at timestamptz,
    last_error text,
    updated_at timestamptz not null default now(),
    unique (league_id, official_team_id, team_slot)
);

create table if not exists public.f1_team_snapshots (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references public.member_profiles(user_id) on delete cascade,
    official_team_id text not null,
    season smallint not null default 2026,
    round smallint not null check (round between 1 and 24),
    team_slot smallint not null check (team_slot between 1 and 3),
    official_team_name text not null,
    manager_name text,
    fantasy_points integer,
    overall_points integer,
    league_rank integer,
    overall_rank integer,
    budget_millions numeric(5,1),
    free_transfers smallint,
    chip_code text,
    assets jsonb not null default '[]'::jsonb,
    captured_at timestamptz not null default now(),
    unique (user_id, season, round)
);

create index if not exists f1_team_snapshots_user_round
    on public.f1_team_snapshots(user_id, season, round desc);

drop trigger if exists f1_team_links_set_updated_at on public.f1_team_links;
create trigger f1_team_links_set_updated_at before update on public.f1_team_links
for each row execute function public.set_updated_at();

alter table public.f1_team_links enable row level security;
alter table public.f1_team_snapshots enable row level security;

drop policy if exists "members read own f1 link" on public.f1_team_links;
create policy "members read own f1 link" on public.f1_team_links
for select to authenticated using ((select auth.uid()) = user_id);

drop policy if exists "members read own f1 snapshots" on public.f1_team_snapshots;
create policy "members read own f1 snapshots" on public.f1_team_snapshots
for select to authenticated using ((select auth.uid()) = user_id);

revoke all on public.f1_team_links from anon, authenticated;
revoke all on public.f1_team_snapshots from anon, authenticated;
grant select on public.f1_team_links to authenticated;
grant select on public.f1_team_snapshots to authenticated;

-- Link creation and syncing are intentionally service-role-only. This prevents
-- one member from claiming another entrant by writing directly through PostgREST.
