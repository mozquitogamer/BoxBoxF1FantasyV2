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

- save one fantasy team, exact budget, free transfers, and remaining chips;
- receive personalized early-thoughts and post-FP alerts;
- receive a short "what changed" transfer/chip note;
- compare the saved team with V13 without re-entering it.

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
