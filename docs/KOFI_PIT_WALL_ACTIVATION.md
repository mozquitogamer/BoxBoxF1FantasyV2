# Pit Wall activation

Pit Wall is the $5/month BoxBoxF1Fantasy convenience membership. It supports the channel without removing the public predictions, simulations, optimizers, V13 decision history, or Beat V13 entry route.

## Public promise

**Tier name:** Pit Wall

**Price:** US$5 per month

**Launch benefits:**

- concise member weekend briefings through Ko-fi;
- first access to new convenience features;
- recognition as a founding Pit Wall member.

**Features rolling out next:**

- save up to three named fantasy teams, each with its own lineup, finances, transfers, history, and remaining chips;
- receive personalized early-thoughts and post-FP alerts;
- receive a short "what changed" transfer/chip note;
- compare any saved-team combination with V13 without re-entering it.

The paid tier is for faster delivery, saved state, and personalization. It must not receive hidden contest data, a stronger private forecast, or an earlier team lock than the public V13 record.

## Ko-fi setup

1. In Ko-fi, switch Memberships to **Membership tiers**.
2. Add and enable the **Pit Wall** tier at **$5/month**.
3. Use the benefit wording above and state clearly which features are available now versus rolling out next.
4. Set the welcome message to thank the member and ask them to use the same email for their future BoxBox account. Do not opt them into marketing email automatically.
5. Set the page's default support tab to Memberships if monthly support is the primary call to action.
6. The public membership link is `https://ko-fi.com/boxboxf1fantasy/tiers`.

Ko-fi charges the member immediately and renews near the same calendar day each month. It provides a downloadable member CSV with email and membership status.

## Entitlement rule for the member dashboard

Ko-fi webhooks fire for successful payments, including membership payments, and may retry the same `message_id`. They do not report when a membership ends.

When the member dashboard is connected:

1. accept only a valid Ko-fi membership payment for the Pit Wall tier;
2. deduplicate using `message_id`;
3. match the member on a normalized lowercase email;
4. extend `paid_through` from the payment date by the paid monthly period plus a small processing grace window;
5. never grant permanent access from a historical payment;
6. reconcile the Ko-fi member CSV at least monthly and before any prize or paid-benefit eligibility decision;
7. keep an append-only payment event record for support and refunds.

Until the private database and magic-link accounts are live, Ko-fi itself is the source of truth for the member briefing. Website-only personalized tools should remain marked as rolling out.

## Pit Wall three-team workspace

Migration `005_pit_wall_three_team_workspace.sql` extends the existing membership schema after migrations `001_memberships.sql`, `002_f1_team_sync.sql`, `003_security_hardening.sql`, and `004_beat_v13_entries.sql`. It is additive: existing members keep their current default team as stable Team 1, and legacy save calls remain compatible.

Each member has three stable slots:

- Team 1, Team 2, and Team 3 can each have an independent name, lineup, source, finances, chip ledger, and weekly history.
- The first saved team becomes primary when no primary exists. A member can explicitly change the primary team; ordinary saves to another slot do not reclaim it.
- Personalized simulation emails are primary-team-only. Saving or linking Team 2 or Team 3 never creates additional personalized email recipients.

Financial fields must not be conflated:

- `squad_value_millions` is the current value of the selected drivers and constructors;
- `bank_millions` is the member's actual cash remaining;
- `spending_power_millions` is the usable total (`squad value + bank`) and is exposed as legacy `budget_millions` for existing recommendation code.

If a legacy record only has its old budget value, retain it as spending power and leave squad value and bank unknown until the member confirms them. An official F1 `teambal` sync represents bank only; it must not be treated as total spending power.

Team history is idempotent per team, season, and round. Re-saving a round updates that round's snapshot rather than creating a duplicate. Chip state is season-aware for the six supported chips (`limitless`, `3x_boost`, `wild_card`, `no_negative`, `autopilot`, and `final_fix`) and uses `unknown`, `available`, or `used`, with an optional `used_round` when known.

Official F1 links are independent per Team 1/2/3 slot. Refreshing a link is non-destructive: it stores the latest official lineup, bank, transfers, chips, and ranks as a slot-specific snapshot without overwriting the member's saved manual team. The member must use the explicit **Apply official** action to replace a saved lineup with that snapshot.

Expired members retain read-only access to their saved teams, snapshots, history, and chip state. Saves, renames, primary-team changes, official refreshes, and personalized recommendations remain entitlement-gated.

### Rollout, rollback, and verification

1. Apply migrations `001` through `005` in filename order in a staging Supabase project. Confirm the migration completes before deploying the API or frontend that sends slot-aware payloads.
2. Verify one legacy member has their former team as Team 1, retains legacy spending power, and has unknown squad/bank rather than fabricated values. Verify a member with no primary receives exactly one repaired primary (the lowest stable slot).
3. Save Team 2 and Team 3 independently, rename one, set the other primary, and confirm a normal Team 1 save does not change primary status. Record the current round twice and confirm one history row per team/season/round.
4. Link and refresh official Team 1/2/3 records. Confirm snapshots are slot-specific and that saved lineups remain unchanged until **Apply official**. Confirm personalized notification data selects only the primary slot.
5. Run `node web/tests/member-team-contract.test.js` and `node web/tests/f1-fantasy.test.js`, then perform a signed-in mobile smoke test covering save, rename, primary selection, chip edits, compare selection, official refresh, and inactive read-only behavior.

The migration is additive and has no destructive down migration. If rollout must be paused, first roll back the API/frontend deployment to the legacy-compatible contract, leave migration `005` in place, and investigate without deleting the new columns or history. Restore from the Supabase backup only if a database rollback is explicitly required and has been reviewed.

## Free Beat V13 registration and alerts

The free email list and Beat V13 entry are separate from Ko-fi membership. Registration is open now: a visitor explicitly registers through the website, confirms by email before the Round 22 Las Vegas F1 Fantasy team lock on 2026-11-21 at 04:00 UTC, and receives V13, simulation and competition updates. Entry is free, and every broadcast includes an unsubscribe route.

To expose the free sign-up form, configure these private values in Vercel:

- `RESEND_API_KEY`
- `RESEND_FROM`
- `RESEND_SIM_UPDATES_SEGMENT_ID`
- `SUBSCRIPTION_SIGNING_SECRET`
- `SITE_ORIGIN=https://boxboxf1fantasy.com`

The website checks `/api/email/status` before showing the form, so missing configuration produces no broken sign-up experience.

For broadcasts, use Resend's unsubscribe footer/URL handling. Preview first, create a draft, review it, then send only after the corresponding public simulation deployment is live.

## Monthly operations

- Export the Ko-fi member CSV and compare active/overdue/cancelled status with the entitlement table.
- Publish the member weekend briefing without revealing a different private V13 selection.
- After simulations deploy, send the free alert and any personalized member alerts with one idempotent event key.
- Review joins, conversion clicks, cancellations, and email unsubscribes; do not judge the tier on subscriber count alone.

## Provider fallback

Stay with Ko-fi for this launch. Gumroad is the strongest practical fallback if website entitlement automation becomes more important than fees because it exposes subscription and license status. Patreon is workable for South African payouts but its platform fee is difficult to justify for this convenience tier. Do not migrate payment providers until Ko-fi creates a concrete operational or conversion problem.
