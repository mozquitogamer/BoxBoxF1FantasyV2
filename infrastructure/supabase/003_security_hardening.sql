-- Security hardening applied after the initial Pit Wall launch.
-- Keeps private helpers from being callable by public/anonymous PostgREST users
-- and prevents entitlement probing for arbitrary user UUIDs.

create or replace function public.member_has_active_entitlement(subject uuid default auth.uid())
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
    select subject is not null
       and subject = auth.uid()
       and exists (
            select 1
            from public.member_entitlements entitlement
            where entitlement.user_id = subject
              and entitlement.status in ('active', 'trialing')
              and (
                  entitlement.current_period_end is null
                  or entitlement.current_period_end > now()
              )
       );
$$;

revoke all on function public.set_updated_at() from public, anon, authenticated;
revoke all on function public.handle_member_user_change() from public, anon, authenticated;
revoke all on function public.member_has_active_entitlement(uuid) from public, anon;
revoke all on function public.save_member_team(text, numeric, smallint, jsonb) from public, anon;

grant execute on function public.member_has_active_entitlement(uuid) to authenticated;
grant execute on function public.save_member_team(text, numeric, smallint, jsonb) to authenticated;

revoke all on public.member_profiles from public, anon;
revoke all on public.saved_teams from public, anon;
revoke all on public.saved_team_assets from public, anon;
revoke all on public.member_chips from public, anon;
revoke all on public.member_entitlements from public, anon;
revoke all on public.kofi_webhook_events from public, anon, authenticated;
revoke all on public.notification_events from public, anon, authenticated;
revoke all on public.member_recommendations from public, anon;
revoke all on public.f1_team_links from public, anon;
revoke all on public.f1_team_snapshots from public, anon;

-- Older webhook rows may contain optional donor fields we do not need. Retain
-- only the payment metadata used for support and deduplication.
update public.kofi_webhook_events
set payload = jsonb_strip_nulls(jsonb_build_object(
    'timestamp', payload -> 'timestamp',
    'amount', payload -> 'amount',
    'currency', payload -> 'currency',
    'is_first_subscription_payment', payload -> 'is_first_subscription_payment',
    'kofi_transaction_id', payload -> 'kofi_transaction_id'
));
