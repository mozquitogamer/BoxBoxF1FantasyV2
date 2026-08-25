-- Pit Wall three-team workspace.
-- This migration is additive and keeps the legacy budget_millions field and
-- save_member_team RPC as compatibility aliases for older clients.

begin;

-- Stable saved-team slots. Existing members retain their default team as T1;
-- any other legacy teams are assigned the remaining slots by creation order.
alter table public.saved_teams add column if not exists team_slot smallint;
do $$
begin
    if exists (
        select 1
        from (
            select row_number() over (partition by user_id order by is_default desc, created_at asc, id asc) as slot_no
            from public.saved_teams
        ) ranked
        where ranked.slot_no > 3
    ) then
        raise exception 'A member has more than three saved teams; resolve before applying migration 005.';
    end if;
end;
$$;

with ranked as (
    select id,
           row_number() over (partition by user_id order by is_default desc, created_at asc, id asc)::smallint as slot_no
    from public.saved_teams
)
update public.saved_teams teams
set team_slot = ranked.slot_no
from ranked
where ranked.id = teams.id
  and teams.team_slot is null;

alter table public.saved_teams alter column team_slot set not null;
alter table public.saved_teams drop constraint if exists saved_teams_user_id_name_key;
alter table public.saved_teams drop constraint if exists saved_teams_team_slot_check;
alter table public.saved_teams add constraint saved_teams_team_slot_check check (team_slot between 1 and 3);

-- Repair only the legacy users who have no primary at all. Existing primary
-- selections are left untouched; the lowest stable slot wins for the repair.
with ranked as (
    select id, user_id,
           row_number() over (partition by user_id order by team_slot asc, created_at asc, id asc) as slot_rank
    from public.saved_teams
), repaired as (
    select ranked.id
    from ranked
    where ranked.slot_rank = 1
      and not exists (
          select 1 from public.saved_teams existing
          where existing.user_id = ranked.user_id and existing.is_default
      )
)
update public.saved_teams teams
set is_default = true
from repaired
where teams.id = repaired.id;

create unique index if not exists saved_teams_user_slot on public.saved_teams(user_id, team_slot);

alter table public.saved_teams add column if not exists source_type text not null default 'manual';
alter table public.saved_teams add column if not exists squad_value_millions numeric(5,1);
alter table public.saved_teams add column if not exists bank_millions numeric(5,1);
alter table public.saved_teams add column if not exists spending_power_millions numeric(5,1);
alter table public.saved_teams drop constraint if exists saved_teams_source_type_check;
alter table public.saved_teams add constraint saved_teams_source_type_check
    check (source_type in ('manual', 'official'));
alter table public.saved_teams drop constraint if exists saved_teams_squad_value_check;
alter table public.saved_teams add constraint saved_teams_squad_value_check
    check (squad_value_millions is null or squad_value_millions between 0 and 999.9);
alter table public.saved_teams drop constraint if exists saved_teams_bank_check;
alter table public.saved_teams add constraint saved_teams_bank_check
    check (bank_millions is null or bank_millions between 0 and 999.9);
alter table public.saved_teams drop constraint if exists saved_teams_spending_power_check;
alter table public.saved_teams add constraint saved_teams_spending_power_check
    check (spending_power_millions is null or spending_power_millions between 0 and 999.9);

-- A legacy budget was the only financial value available. Preserve it as
-- spending power only until the member supplies real squad/bank values.
-- The absent squad/bank columns intentionally remain NULL.
update public.saved_teams
set spending_power_millions = coalesce(spending_power_millions, budget_millions)
where spending_power_millions is null;

-- Chips become season-aware and can explicitly be unknown, available or used.
alter table public.member_chips add column if not exists season smallint;
alter table public.member_chips add column if not exists status text;
update public.member_chips
set season = coalesce(season, 2026),
    status = coalesce(status, case when available then 'available' else 'used' end);
alter table public.member_chips alter column season set not null;
alter table public.member_chips alter column status set not null;
alter table public.member_chips alter column available drop not null;
alter table public.member_chips alter column available drop default;
alter table public.member_chips drop constraint if exists member_chips_pkey;
alter table public.member_chips drop constraint if exists member_chips_check;
alter table public.member_chips drop constraint if exists member_chips_status_check;
alter table public.member_chips add constraint member_chips_status_check
    check (status in ('unknown', 'available', 'used'));
alter table public.member_chips drop constraint if exists member_chips_status_round_check;
alter table public.member_chips add constraint member_chips_status_round_check
    check ((status = 'used' and (used_round is null or used_round between 1 and 24)) or (status <> 'used' and used_round is null));
alter table public.member_chips drop constraint if exists member_chips_available_compat_check;
alter table public.member_chips add constraint member_chips_available_compat_check
    check (available is null or available = (status = 'available'));
alter table public.member_chips add primary key (team_id, season, chip_code);
update public.member_chips set available = case when status = 'available' then true when status = 'used' then false else null end;
create index if not exists member_chips_team_season on public.member_chips(team_id, season);

create table if not exists public.saved_team_history (
    team_id uuid not null references public.saved_teams(id) on delete cascade,
    season smallint not null,
    round smallint not null check (round between 1 and 24),
    squad_value_millions numeric(5,1) not null check (squad_value_millions between 0 and 999.9),
    bank_millions numeric(5,1) not null check (bank_millions between 0 and 999.9),
    spending_power_millions numeric(5,1) not null check (spending_power_millions between 0 and 999.9),
    budget_millions numeric(5,1) not null check (budget_millions between 0 and 999.9),
    free_transfers smallint not null check (free_transfers between 0 and 9),
    chips jsonb not null default '[]'::jsonb,
    assets jsonb not null default '[]'::jsonb,
    source_type text not null default 'manual' check (source_type in ('manual', 'official')),
    recorded_at timestamptz not null default now(),
    primary key (team_id, season, round)
);
create index if not exists saved_team_history_team_round on public.saved_team_history(team_id, season, round desc);
alter table public.saved_team_history alter column squad_value_millions drop not null;
alter table public.saved_team_history alter column bank_millions drop not null;
alter table public.saved_team_history drop constraint if exists saved_team_history_squad_value_millions_check;
alter table public.saved_team_history drop constraint if exists saved_team_history_bank_millions_check;
alter table public.saved_team_history drop constraint if exists saved_team_history_squad_value_check;
alter table public.saved_team_history add constraint saved_team_history_squad_value_check
    check (squad_value_millions is null or squad_value_millions between 0 and 999.9);
alter table public.saved_team_history drop constraint if exists saved_team_history_bank_value_check;
alter table public.saved_team_history add constraint saved_team_history_bank_value_check
    check (bank_millions is null or bank_millions between 0 and 999.9);

-- Official links and snapshots were previously one-per-member. Keep each
-- official T1/T2/T3 link and weekly snapshot independent.
alter table public.f1_team_links drop constraint if exists f1_team_links_pkey;
alter table public.f1_team_links add primary key (user_id, team_slot);
alter table public.f1_team_snapshots drop constraint if exists f1_team_snapshots_user_id_season_round_key;
alter table public.f1_team_snapshots add column if not exists squad_value_millions numeric(5,1);
alter table public.f1_team_snapshots add column if not exists bank_millions numeric(5,1);
alter table public.f1_team_snapshots add column if not exists spending_power_millions numeric(5,1);
alter table public.f1_team_snapshots drop constraint if exists f1_team_snapshots_finance_check;
alter table public.f1_team_snapshots add constraint f1_team_snapshots_finance_check
    check ((squad_value_millions is null or squad_value_millions between 0 and 999.9)
       and (bank_millions is null or bank_millions between 0 and 999.9)
       and (spending_power_millions is null or spending_power_millions between 0 and 999.9));
alter table public.f1_team_snapshots drop constraint if exists f1_team_snapshots_user_season_round_slot_key;
alter table public.f1_team_snapshots add constraint f1_team_snapshots_user_season_round_slot_key
    unique (user_id, season, round, team_slot);
create index if not exists f1_team_snapshots_user_slot_round
    on public.f1_team_snapshots(user_id, team_slot, season, round desc);

create or replace function public.save_member_team_v2(
    p_team_slot smallint,
    p_name text,
    p_source_type text,
    p_squad_value_millions numeric,
    p_bank_millions numeric,
    p_spending_power_millions numeric,
    p_free_transfers smallint,
    p_assets jsonb,
    p_chips jsonb,
    p_season smallint,
    p_round smallint,
    p_is_primary boolean default false
)
returns uuid
language plpgsql
security invoker
set search_path = ''
as $$
declare
    v_user_id uuid := auth.uid();
    v_team_id uuid;
    v_asset jsonb;
    v_chip jsonb;
    v_spending numeric := coalesce(p_spending_power_millions,
        case when p_squad_value_millions is not null and p_bank_millions is not null
             then p_squad_value_millions + p_bank_millions end);
    v_squad numeric := p_squad_value_millions;
    v_bank numeric := p_bank_millions;
    v_has_primary boolean;
    v_make_primary boolean;
    v_chip_code text;
    v_status text;
begin
    if v_user_id is null then raise exception 'Sign in is required.'; end if;
    if not public.member_has_active_entitlement(v_user_id) then raise exception 'An active Pit Wall membership is required.'; end if;
    if p_team_slot is null or p_team_slot not between 1 and 3 then raise exception 'Team slot is invalid.'; end if;
    if p_name is null or char_length(trim(p_name)) not between 1 and 60 then raise exception 'Team name is invalid.'; end if;
    if coalesce(p_source_type, 'manual') not in ('manual', 'official') then raise exception 'Team source is invalid.'; end if;
    if v_spending is null
       or (v_squad is not null and (v_squad < 0 or v_squad > 999.9))
       or (v_bank is not null and (v_bank < 0 or v_bank > 999.9))
       or v_spending < 0 or v_spending > 999.9 then
        raise exception 'Team finances are invalid.';
    end if;
    if p_free_transfers is null or p_free_transfers not between 0 and 9 then raise exception 'Free transfers are invalid.'; end if;
    if jsonb_typeof(p_assets) <> 'array' or jsonb_array_length(p_assets) <> 7 then raise exception 'A complete team must contain five drivers and two constructors.'; end if;
    if (select count(*) from jsonb_array_elements(p_assets) item where item ->> 'asset_type' = 'driver') <> 5
       or (select count(*) from jsonb_array_elements(p_assets) item where item ->> 'asset_type' = 'constructor') <> 2
       or (select count(distinct (item ->> 'asset_id')) from jsonb_array_elements(p_assets) item) <> 7
       or (select count(distinct ((item ->> 'asset_type') || ':' || (item ->> 'slot'))) from jsonb_array_elements(p_assets) item) <> 7 then
        raise exception 'A complete team must contain five unique drivers and two unique constructors.';
    end if;
    if p_round is not null and (p_season is null or p_round not between 1 and 24) then raise exception 'History round is invalid.'; end if;

    select exists(select 1 from public.saved_teams where user_id = v_user_id and is_default) into v_has_primary;
    -- The first saved team becomes primary regardless of its slot. After a
    -- primary exists, ordinary slot saves cannot steal it.
    v_make_primary := coalesce(p_is_primary, false) or not v_has_primary;
    if v_make_primary then
        update public.saved_teams set is_default = false where user_id = v_user_id and is_default;
    end if;
    insert into public.saved_teams (
        user_id, team_slot, name, source_type, squad_value_millions, bank_millions,
        spending_power_millions, budget_millions, free_transfers, is_default
    ) values (
        v_user_id, p_team_slot, trim(p_name), coalesce(p_source_type, 'manual'), v_squad, v_bank,
        v_spending, v_spending, p_free_transfers, v_make_primary
    )
    on conflict (user_id, team_slot) do update set
        name = excluded.name,
        source_type = excluded.source_type,
        squad_value_millions = excluded.squad_value_millions,
        bank_millions = excluded.bank_millions,
        spending_power_millions = excluded.spending_power_millions,
        budget_millions = excluded.budget_millions,
        free_transfers = excluded.free_transfers,
        is_default = case when v_make_primary then true else public.saved_teams.is_default end
    returning id into v_team_id;

    delete from public.saved_team_assets where team_id = v_team_id;
    for v_asset in select value from jsonb_array_elements(p_assets) loop
        insert into public.saved_team_assets(team_id, asset_type, asset_id, slot, is_boosted)
        values (v_team_id, v_asset ->> 'asset_type', v_asset ->> 'asset_id', (v_asset ->> 'slot')::smallint, coalesce((v_asset ->> 'is_boosted')::boolean, false));
    end loop;

    if p_chips is not null and jsonb_typeof(p_chips) <> 'array' then raise exception 'Chip state is invalid.'; end if;
    -- Always keep one row per known chip so the dashboard can render unknown
    -- state explicitly until a member confirms what remains.
    if p_chips is not null then
      if exists (select 1 from jsonb_array_elements(p_chips) item where item ->> 'chip_code' not in ('limitless','3x_boost','wild_card','no_negative','autopilot','final_fix'))
         or (select count(*) from jsonb_array_elements(p_chips)) <> (select count(distinct item ->> 'chip_code') from jsonb_array_elements(p_chips)) then
          raise exception 'Chip code is invalid.';
      end if;
      if exists (select 1 from jsonb_array_elements(p_chips) item where coalesce(item ->> 'status', '') not in ('unknown', 'available', 'used')) then
          raise exception 'Chip status is invalid.';
      end if;
      for v_chip_code in select unnest(array['limitless','3x_boost','wild_card','no_negative','autopilot','final_fix']) loop
        v_status := 'unknown';
        for v_chip in select value from jsonb_array_elements(p_chips) where value ->> 'chip_code' = v_chip_code loop
            v_status := coalesce(v_chip ->> 'status', case when (v_chip ->> 'available')::boolean then 'available' else 'used' end);
            if v_status not in ('unknown', 'available', 'used') then raise exception 'Chip status is invalid.'; end if;
            if v_status = 'used' and (v_chip ->> 'used_round') is not null and ((v_chip ->> 'used_round')::smallint not between 1 and 24) then raise exception 'Used chip round is invalid.'; end if;
        end loop;
        insert into public.member_chips(team_id, season, chip_code, status, available, used_round)
        values (v_team_id, coalesce(p_season, 2026), v_chip_code, v_status, case when v_status = 'available' then true when v_status = 'used' then false else null end,
                case when v_status = 'used' then ((select value ->> 'used_round' from jsonb_array_elements(p_chips) where value ->> 'chip_code' = v_chip_code limit 1)::smallint) else null end)
        on conflict (team_id, season, chip_code) do update set status = excluded.status, available = excluded.available, used_round = excluded.used_round, updated_at = now();
      end loop;
    end if;

    if p_round is not null then
        insert into public.saved_team_history(team_id, season, round, squad_value_millions, bank_millions, spending_power_millions, budget_millions, free_transfers, chips, assets, source_type)
        values (v_team_id, coalesce(p_season, 2026), p_round, v_squad, v_bank, v_spending, v_spending, p_free_transfers,
                coalesce(p_chips, coalesce((select jsonb_agg(jsonb_build_object('chip_code', chip_code, 'status', status, 'used_round', used_round) order by chip_code)
                                           from public.member_chips where team_id = v_team_id and season = coalesce(p_season, 2026)), '[]'::jsonb)),
                p_assets, coalesce(p_source_type, 'manual'))
        on conflict (team_id, season, round) do update set
            squad_value_millions = excluded.squad_value_millions,
            bank_millions = excluded.bank_millions,
            spending_power_millions = excluded.spending_power_millions,
            budget_millions = excluded.budget_millions,
            free_transfers = excluded.free_transfers,
            chips = excluded.chips,
            assets = excluded.assets,
            source_type = excluded.source_type,
            recorded_at = now();
    end if;
    return v_team_id;
end;
$$;

create or replace function public.save_member_team(
    p_name text,
    p_budget_millions numeric,
    p_free_transfers smallint,
    p_assets jsonb
)
returns uuid
language sql
security invoker
set search_path = ''
as $$
    select public.save_member_team_v2(1, p_name, 'manual', null, null, p_budget_millions, p_free_transfers, p_assets, null, 2026, null, true);
$$;

create or replace function public.rename_member_team(p_team_slot smallint, p_name text)
returns uuid
language plpgsql
security invoker
set search_path = ''
as $$
declare
    v_user_id uuid := auth.uid();
    v_team_id uuid;
begin
    if v_user_id is null or not public.member_has_active_entitlement(v_user_id) then raise exception 'An active Pit Wall membership is required.'; end if;
    if p_team_slot is null or p_team_slot not between 1 and 3 then raise exception 'Team slot is invalid.'; end if;
    if p_name is null or char_length(trim(p_name)) not between 1 and 60 then raise exception 'Team name is invalid.'; end if;
    update public.saved_teams set name = trim(p_name)
    where user_id = v_user_id and team_slot = p_team_slot
    returning id into v_team_id;
    if v_team_id is null then raise exception 'Saved team was not found.'; end if;
    return v_team_id;
end;
$$;

create or replace function public.set_member_team_primary(p_team_slot smallint)
returns uuid
language plpgsql
security invoker
set search_path = ''
as $$
declare
    v_user_id uuid := auth.uid();
    v_team_id uuid;
begin
    if v_user_id is null or not public.member_has_active_entitlement(v_user_id) then raise exception 'An active Pit Wall membership is required.'; end if;
    if p_team_slot is null or p_team_slot not between 1 and 3 then raise exception 'Team slot is invalid.'; end if;
    select id into v_team_id from public.saved_teams where user_id = v_user_id and team_slot = p_team_slot;
    if v_team_id is null then raise exception 'Saved team was not found.'; end if;
    update public.saved_teams set is_default = false where user_id = v_user_id and is_default;
    update public.saved_teams set is_default = true where id = v_team_id;
    return v_team_id;
end;
$$;

alter table public.saved_team_history enable row level security;
drop policy if exists "paid members manage own teams" on public.saved_teams;
drop policy if exists "members read own teams" on public.saved_teams;
drop policy if exists "paid members insert own teams" on public.saved_teams;
drop policy if exists "paid members update own teams" on public.saved_teams;
drop policy if exists "paid members delete own teams" on public.saved_teams;
create policy "members read own teams" on public.saved_teams for select to authenticated using ((select auth.uid()) = user_id);
create policy "paid members insert own teams" on public.saved_teams for insert to authenticated with check ((select auth.uid()) = user_id and public.member_has_active_entitlement(user_id));
create policy "paid members update own teams" on public.saved_teams for update to authenticated using ((select auth.uid()) = user_id and public.member_has_active_entitlement(user_id)) with check ((select auth.uid()) = user_id and public.member_has_active_entitlement(user_id));
create policy "paid members delete own teams" on public.saved_teams for delete to authenticated using ((select auth.uid()) = user_id and public.member_has_active_entitlement(user_id));

drop policy if exists "paid members manage assets for own teams" on public.saved_team_assets;
drop policy if exists "members read own team assets" on public.saved_team_assets;
drop policy if exists "paid members write own team assets" on public.saved_team_assets;
create policy "members read own team assets" on public.saved_team_assets for select to authenticated using (exists (select 1 from public.saved_teams team where team.id = team_id and team.user_id = (select auth.uid())));
create policy "paid members write own team assets" on public.saved_team_assets for all to authenticated using (exists (select 1 from public.saved_teams team where team.id = team_id and team.user_id = (select auth.uid()) and public.member_has_active_entitlement(team.user_id))) with check (exists (select 1 from public.saved_teams team where team.id = team_id and team.user_id = (select auth.uid()) and public.member_has_active_entitlement(team.user_id)));

drop policy if exists "paid members manage chips for own teams" on public.member_chips;
drop policy if exists "members read own team chips" on public.member_chips;
drop policy if exists "paid members write own team chips" on public.member_chips;
create policy "members read own team chips" on public.member_chips for select to authenticated using (exists (select 1 from public.saved_teams team where team.id = team_id and team.user_id = (select auth.uid())));
create policy "paid members write own team chips" on public.member_chips for all to authenticated using (exists (select 1 from public.saved_teams team where team.id = team_id and team.user_id = (select auth.uid()) and public.member_has_active_entitlement(team.user_id))) with check (exists (select 1 from public.saved_teams team where team.id = team_id and team.user_id = (select auth.uid()) and public.member_has_active_entitlement(team.user_id)));

drop policy if exists "members read own team history" on public.saved_team_history;
drop policy if exists "paid members insert own team history" on public.saved_team_history;
drop policy if exists "paid members update own team history" on public.saved_team_history;
create policy "members read own team history" on public.saved_team_history for select to authenticated using (exists (select 1 from public.saved_teams team where team.id = team_id and team.user_id = (select auth.uid())));
create policy "paid members insert own team history" on public.saved_team_history for insert to authenticated with check (exists (select 1 from public.saved_teams team where team.id = team_id and team.user_id = (select auth.uid()) and public.member_has_active_entitlement(team.user_id)));
create policy "paid members update own team history" on public.saved_team_history for update to authenticated using (exists (select 1 from public.saved_teams team where team.id = team_id and team.user_id = (select auth.uid()) and public.member_has_active_entitlement(team.user_id))) with check (exists (select 1 from public.saved_teams team where team.id = team_id and team.user_id = (select auth.uid()) and public.member_has_active_entitlement(team.user_id)));

grant select, insert, update on public.saved_team_history to authenticated;
grant execute on function public.save_member_team_v2(smallint, text, text, numeric, numeric, numeric, smallint, jsonb, jsonb, smallint, smallint, boolean) to authenticated;
grant execute on function public.rename_member_team(smallint, text) to authenticated;
grant execute on function public.set_member_team_primary(smallint) to authenticated;

revoke all on function public.save_member_team_v2(smallint, text, text, numeric, numeric, numeric, smallint, jsonb, jsonb, smallint, smallint, boolean) from public, anon;
revoke all on function public.rename_member_team(smallint, text) from public, anon;
revoke all on function public.set_member_team_primary(smallint) from public, anon;

commit;
