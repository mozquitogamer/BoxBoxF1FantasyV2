-- BoxBoxF1Fantasy member-data foundation for Supabase/Postgres.
-- Apply only after creating the Supabase project. Public prediction JSON stays
-- separate; these tables hold private user/team/payment state behind RLS.

create extension if not exists pgcrypto;

create table if not exists public.member_profiles (
    user_id uuid primary key references auth.users(id) on delete cascade,
    email text not null,
    display_name text,
    email_simulation_updates boolean not null default true,
    email_member_newsletter boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.saved_teams (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references public.member_profiles(user_id) on delete cascade,
    name text not null default 'My Team' check (char_length(name) between 1 and 60),
    budget_millions numeric(5,1) not null default 100.0 check (budget_millions between 0 and 999.9),
    free_transfers smallint not null default 2 check (free_transfers between 0 and 9),
    is_default boolean not null default false,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (user_id, name)
);

create unique index if not exists saved_teams_one_default_per_user
    on public.saved_teams(user_id) where is_default;

create table if not exists public.saved_team_assets (
    team_id uuid not null references public.saved_teams(id) on delete cascade,
    asset_type text not null check (asset_type in ('driver', 'constructor')),
    asset_id text not null check (char_length(asset_id) between 1 and 40),
    slot smallint not null,
    is_boosted boolean not null default false,
    primary key (team_id, asset_type, asset_id),
    unique (team_id, asset_type, slot),
    check (
        (asset_type = 'driver' and slot between 1 and 5)
        or (asset_type = 'constructor' and slot between 1 and 2)
    )
);

create table if not exists public.member_chips (
    team_id uuid not null references public.saved_teams(id) on delete cascade,
    chip_code text not null check (chip_code in (
        'limitless', '3x_boost', 'wild_card', 'no_negative', 'autopilot', 'final_fix'
    )),
    available boolean not null default true,
    used_round smallint check (used_round between 1 and 24),
    updated_at timestamptz not null default now(),
    primary key (team_id, chip_code),
    check ((available and used_round is null) or (not available))
);

create table if not exists public.member_entitlements (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references public.member_profiles(user_id) on delete cascade,
    provider text not null check (provider in ('paystack', 'youtube', 'manual')),
    external_customer_id text,
    external_subscription_id text,
    status text not null check (status in ('active', 'trialing', 'past_due', 'cancelled', 'expired')),
    current_period_end timestamptz,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create unique index if not exists member_entitlements_external_subscription
    on public.member_entitlements(provider, external_subscription_id)
    where external_subscription_id is not null;

create index if not exists member_entitlements_active_user
    on public.member_entitlements(user_id, status, current_period_end);

create table if not exists public.notification_events (
    id uuid primary key default gen_random_uuid(),
    event_key text not null unique,
    season smallint not null,
    round smallint not null,
    phase text not null check (phase in ('pre_fp', 'post_fp', 'post_quali')),
    predictions_generated_at timestamptz not null,
    status text not null default 'draft' check (status in ('draft', 'processing', 'sent', 'failed')),
    payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    sent_at timestamptz
);

create table if not exists public.member_recommendations (
    id uuid primary key default gen_random_uuid(),
    event_id uuid not null references public.notification_events(id) on delete cascade,
    user_id uuid not null references public.member_profiles(user_id) on delete cascade,
    team_id uuid not null references public.saved_teams(id) on delete cascade,
    recommendation jsonb not null,
    delivery_status text not null default 'pending' check (delivery_status in ('pending', 'sent', 'failed', 'skipped')),
    provider_message_id text,
    created_at timestamptz not null default now(),
    delivered_at timestamptz,
    unique (event_id, team_id)
);

create or replace function public.set_updated_at()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

drop trigger if exists member_profiles_set_updated_at on public.member_profiles;
create trigger member_profiles_set_updated_at before update on public.member_profiles
for each row execute function public.set_updated_at();

drop trigger if exists saved_teams_set_updated_at on public.saved_teams;
create trigger saved_teams_set_updated_at before update on public.saved_teams
for each row execute function public.set_updated_at();

drop trigger if exists member_chips_set_updated_at on public.member_chips;
create trigger member_chips_set_updated_at before update on public.member_chips
for each row execute function public.set_updated_at();

drop trigger if exists member_entitlements_set_updated_at on public.member_entitlements;
create trigger member_entitlements_set_updated_at before update on public.member_entitlements
for each row execute function public.set_updated_at();

create or replace function public.handle_new_member_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
    insert into public.member_profiles (user_id, email, display_name)
    values (new.id, coalesce(new.email, ''), new.raw_user_meta_data ->> 'display_name')
    on conflict (user_id) do nothing;
    return new;
end;
$$;

drop trigger if exists on_auth_user_created_boxbox on auth.users;
create trigger on_auth_user_created_boxbox
after insert on auth.users
for each row execute function public.handle_new_member_user();

alter table public.member_profiles enable row level security;
alter table public.saved_teams enable row level security;
alter table public.saved_team_assets enable row level security;
alter table public.member_chips enable row level security;
alter table public.member_entitlements enable row level security;
alter table public.notification_events enable row level security;
alter table public.member_recommendations enable row level security;

create policy "members read own profile" on public.member_profiles
for select to authenticated using ((select auth.uid()) = user_id);
create policy "members update own profile" on public.member_profiles
for update to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);

create policy "members manage own teams" on public.saved_teams
for all to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);

create policy "members manage assets for own teams" on public.saved_team_assets
for all to authenticated
using (exists (select 1 from public.saved_teams t where t.id = team_id and t.user_id = (select auth.uid())))
with check (exists (select 1 from public.saved_teams t where t.id = team_id and t.user_id = (select auth.uid())));

create policy "members manage chips for own teams" on public.member_chips
for all to authenticated
using (exists (select 1 from public.saved_teams t where t.id = team_id and t.user_id = (select auth.uid())))
with check (exists (select 1 from public.saved_teams t where t.id = team_id and t.user_id = (select auth.uid())));

create policy "members read own entitlements" on public.member_entitlements
for select to authenticated using ((select auth.uid()) = user_id);

create policy "members read own recommendations" on public.member_recommendations
for select to authenticated using ((select auth.uid()) = user_id);

-- Prevent clients from changing identity/payment/delivery fields. Service-role
-- requests bypass RLS and retain full access for webhooks and email workers.
revoke all on public.member_profiles from authenticated;
grant select on public.member_profiles to authenticated;
grant update (display_name, email_simulation_updates, email_member_newsletter) on public.member_profiles to authenticated;

grant select, insert, update, delete on public.saved_teams to authenticated;
grant select, insert, update, delete on public.saved_team_assets to authenticated;
grant select, insert, update, delete on public.member_chips to authenticated;
grant select on public.member_entitlements to authenticated;
grant select on public.member_recommendations to authenticated;
