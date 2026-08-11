# Email, Membership, and Ads Roadmap

This foundation keeps the current public prediction pipeline static and fast while placing private subscriber, payment, and team data behind server-side boundaries.

## Recommended stack

- **Email delivery and list management:** Resend. It covers transactional confirmation messages, contact segments, broadcasts, automatic unsubscribe handling, and later personalized transactional emails. The free plans currently cover 3,000 transactional emails per month (100/day) and 1,000 marketing contacts.
- **Login and private data:** Supabase Auth + Postgres with row-level security. The free plan is enough for the initial launch; production can move to Pro when paid membership revenue justifies the fixed cost.
- **Recurring membership payments:** Ko-fi Memberships for the $5 Pit Wall launch. It already fits the channel's support model and pays directly through the creator's connected PayPal or Stripe account. Ko-fi's webhook reports successful payments but not ended memberships, so website access must be time-limited from the latest successful payment and reconciled against the member CSV.
- **Ads:** a dormant Google AdSense responsive unit and a mutually exclusive direct-sponsor fallback are scaffolded at the bottom of every page. AdSense activation still requires the real Google IDs, site approval, a certified consent message, and an explicit CSP decision; see `docs/ADSENSE_SETUP.md`.

Official references checked on 2026-07-21:

- Resend pricing: https://resend.com/docs/knowledge-base/what-is-resend-pricing
- Resend contacts: https://resend.com/docs/api-reference/contacts/create-contact
- Resend broadcasts: https://resend.com/docs/api-reference/broadcasts/create-broadcast
- Supabase pricing: https://supabase.com/pricing
- Ko-fi memberships: https://help.ko-fi.com/hc/en-us/articles/4402945994001-Ko-fi-Memberships-and-Membership-Tiers
- Ko-fi payment webhook: https://help.ko-fi.com/hc/en-us/articles/360004162298-Does-Ko-fi-have-an-API-or-webhook
- AdSense privacy policy requirement: https://support.google.com/adsense/answer/10961370

## What is scaffolded now

1. `web/public/index.html`, `engagement.css`, and `engagement.js` contain a compact email-alert panel, a responsive AdSense unit, and a direct-sponsor fallback.
2. `web/public/data/site_features.json` enables the email experience, while a server-side status check keeps the form hidden until delivery credentials are configured. Paid membership is introduced on the V13 page without removing any free tools.
3. `web/api/email/subscribe.js` sends a signed, expiring double-opt-in confirmation email. It does not store the address.
4. `web/api/email/confirm.js` verifies the signed link and only then adds the address to the Resend simulation-alert segment.
5. `pipeline/notify_subscribers.py` turns the current `predictions.json` into a branded Resend broadcast. Preview is the default; `--draft` is reviewable; only `--send` delivers.
6. `infrastructure/supabase/001_memberships.sql` defines the private member/team/chip/entitlement/recommendation tables and RLS policies. The schema is connected to the Pit Wall member panel and server-side notification worker.

## Phase 1 — simulation alerts

Do this after the race:

1. Create a Resend account and verify `boxboxf1fantasy.com` with SPF/DKIM. Use a sender such as `BoxBoxF1Fantasy Updates <updates@boxboxf1fantasy.com>`.
2. Create a Resend segment named `Simulation updates`.
3. Add the values listed in `web/.env.example` to the Vercel project's Production and Preview environments. Generate `SUBSCRIPTION_SIGNING_SECRET` with a cryptographically random value of at least 32 bytes.
   Configure `EMAIL_POSTAL_ADDRESS` in the local pipeline environment before creating a draft or send; the broadcaster refuses network delivery without sender-address footer data.
4. Deploy and call the subscribe/confirm endpoints directly with a test address. The public panel preflights `/api/email/status` and remains hidden until all delivery values are present, even though the feature flag is enabled.
5. Complete a real browser sign-up, confirmation, and unsubscribe check before promoting the list.
6. After a simulation update is live on Vercel, preview and then create a draft:

   ```powershell
   python pipeline/notify_subscribers.py
   python pipeline/notify_subscribers.py --draft
   ```

7. Review the draft in Resend. When satisfied, use `--send`. Do not wire automatic sending into `run_weekend.py` until deployment completion and idempotency are handled; otherwise an email can announce data before the new deployment is live or send twice on a rerun.

Before enabling the form, add rate limiting or a Turnstile challenge if bot traffic reaches the endpoint. The current origin check, consent field, honeypot, signed confirmation, and no-storage-before-confirmation flow are appropriate for a small initial list but are not a substitute for durable rate limiting at scale.

## Phase 2 — discreet ads

The bottom inventory supports either Google AdSense or a direct placement, never both at once. For AdSense, follow `docs/ADSENSE_SETUP.md`; the configurator validates the Google IDs, creates `/ads.txt`, and synchronizes the literal account code across all static pages. For a direct placement instead, configure `bottom_banner` in `site_features.json` with a clear sponsor label, short copy, destination, and optional first-party-hosted logo.

Direct sponsorship is a good first test at low traffic because there is no network minimum, no third-party tracking, and one niche sponsor can outperform many low-volume display impressions. Keep these rules:

- one bottom banner only;
- never interrupt the optimizer or prediction cards;
- label paid placements clearly;
- use `rel="sponsored noopener"` (the scaffold does this for external links);
- never imply that a sponsor influences rankings or model outputs;
- track only aggregate clicks through the existing GA event unless the privacy policy is updated for another tracker.

Do not paste an AdSense script into the direct banner config. Keep display ads off until the Google review, CMP, and CSP activation gates in the dedicated setup guide are complete.

## Phase 3 — paid members and saved teams

Implementation status: live foundation completed on 2026-08-11. The remaining recurring operational task is the monthly Ko-fi member reconciliation described in step 5.

1. Create a Supabase project and run `infrastructure/supabase/001_memberships.sql` in the SQL editor.
2. Add magic-link login. Keep the existing optimizer and all public predictions free; membership pays for persistence, convenience, and personalized delivery.
3. Build a member settings page for:
   - five drivers and two constructors;
   - current budget and free transfers;
   - remaining chips;
   - email preferences;
   - one default team initially (the schema supports more).
4. Create the $5 Ko-fi Pit Wall tier and connect its payment webhook. Each verified monthly payment extends `member_entitlements` to the end of that paid period; the browser never decides whether a user is paid. Deduplicate retries with Ko-fi's `message_id`.
5. Reconcile Ko-fi's member CSV monthly because the payment webhook does not report ended memberships. Never interpret one historical payment as permanent access.
6. Port the Transfer Advisor calculation to a server-side recommendation worker and add parity fixtures against the browser results. On each notification event the worker should snapshot one recommendation per team in `member_recommendations` before sending it.
7. Use an idempotent event key such as `2026:r13:post_fp:<predictions_generated_at>` so pipeline reruns cannot double-email.

The live implementation uses same-origin, HttpOnly session cookies; verifies active entitlement before generating a passwordless link; stores complete teams transactionally; and triggers the recommendation worker only after a successful Production deployment. The worker skips non-actionable or stale predictions and snapshots each personalized recommendation before delivery.

Suggested product boundary: public users keep the full tools; paid users get saved teams, zero re-entry, personalized transfer/chip advice after every actionable simulation update, and the member newsletter. That is a strong convenience product without weakening the site's SEO or goodwill with a paywall.

## Phase 4 — paid newsletter and YouTube members

- Put the editorial newsletter in a separate Resend segment from free simulation alerts.
- Grant newsletter access from active `member_entitlements` only.
- Represent YouTube membership as another entitlement provider; do not mix YouTube identifiers into team tables.
- Initially allow manual YouTube-member verification. Automate it only after the channel is eligible and the membership API/OAuth workflow is available.
- Every send should record the source event, recipient, provider message ID, and delivery outcome without copying sensitive team data into logs.

## Privacy and operational rules

- Never put emails, teams, chips, payment status, or access tokens in `web/public/data`.
- Never expose Resend, Supabase service-role, or Ko-fi verification values to browser JavaScript.
- Use double opt-in for the free list and include an unsubscribe link in every marketing broadcast.
- Provide account export/deletion before paid profiles launch.
- Confirm the final privacy, email, tax, and subscription terms with an appropriate professional before charging users; the technical safeguards here are not legal advice.
- Back up member data before relying on a free database plan for paid customers.
- Keep simulation alerts and paid editorial mail as separate preferences.
