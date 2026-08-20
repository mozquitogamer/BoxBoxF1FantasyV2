# Beat V13 — operating plan

## What V13 is

V13 is the Budget Builder / medium-risk manager selected from the twelve 2026
virtual-manager experiments. Its normal lineup objective values projected
fantasy points, forecast price movement, and negative-P5 exposure. It does not
read qualifying results when choosing its normal team.

Qualifying-locked data is reserved for Final Fix. The R1–R13 research replay
used the first trustworthy post-qualifying opportunity at R13, moving Hamilton
to Norris with the 2x boost for a realised 22-point improvement. Final Fix is therefore no
longer available to the live 2026 manager.

The displayed R1–R13 total is a full-season counterfactual research replay:
2,594 points after Final Fix. R1–R3 use reconstructed forecasts; later rounds
use preserved archives. This distinction must remain visible anywhere the
replay score is promoted.

The replay uses the corrected 2026 transfer bank: two free transfers are
available every round after R1, one unused transfer can roll over, the minimum
available at a new round is two, and the maximum is three. Wild Card and
Limitless reset the following round to two. Correcting the
earlier one-per-round/max-five implementation changed the full lineup path,
penalties, chip timing, final budget and score. The original R14 pre-FP record
and revisions 1–3 remain unchanged; revision 4 appends the audited seat-
availability correction and points to a separate corrected pre-lock snapshot.

## R14 Dutch GP seat correction

R14 is a Sprint weekend, so the pre-FP snapshot is priors-only and the
post-FP refresh consumes actual FP1. For R14 only, the active Fantasy assets
are `LAW_RED_BULL` (Liam Lawson, Red Bull, £14.5M) and `TSU_RACING_BULLS`
(Yuki Tsunoda, Racing Bulls, £10.3M). `HAD` and the old Racing Bulls `LAW`
asset are inactive for R14; the canonical seed roster and all R1–R13 history
remain unchanged, and R15 falls back to that canonical roster unless a new
overlay is added.

The prediction rows retain the personal model identities (`lawson` and
`tsunoda`) while applying the new constructor context. Both substitute assets
carry a 0.68 confidence multiplier and 1.35 Monte Carlo noise multiplier. The
constructor pairs are therefore Red Bull = VER + `LAW_RED_BULL` and Racing
Bulls = LIN + `TSU_RACING_BULLS`.

Authoritative roster checks were made on 2026-08-20 (UTC): the [official F1
driver roster](https://www.formula1.com/en/drivers) still showed the canonical
Hadjar/Lawson seats, while the [public F1 Fantasy driver feed](https://fantasy.formula1.com/feeds/drivers/14_en.json)
was unavailable in the restricted runtime and did not expose a stable TSU
asset to mirror. The deterministic internal IDs and their `model_driver_id`
underlay are documented in `config/driver_assets.py`. A future official-feed
refresh can replace the fallback IDs without rewriting prior rounds. The
corrected V13 source is kept at
`web/public/data/predictions_round14_pre_fp_availability_corrected.json`; the
original frozen phase archive remains intact.

## Public record

The website reads `web/public/data/v13_manager.json`. It contains:

- V13's fixed policy and competition configuration;
- every replay round, team, captain, chip, score, budget, and forecast hash;
- the current owned team, bank, transfers, and remaining chip;
- the current round's early-thoughts and post-FP snapshots.

Live decisions are append-only records in `data/v13/decisions`. Each includes
the input forecast's SHA-256 hash and generation time, the published F1 Fantasy
lock time, and the hash of the previous V13 decision. An existing record is
never regenerated or overwritten by the publishing command.

## Weekly workflow

### 1. Early thoughts

Run the normal priors-only pipeline, then freeze the public early team:

```text
python pipeline/run_weekend.py --phase pre_fp_predict --round N
python pipeline/publish_v13_decision.py --round N --phase pre_fp
```

This snapshot is provisional. It can be discussed in videos and remains
visible after the post-FP final is published.

### 2. Post-FP final

After the actionable practice sessions are complete, run the post-FP pipeline
and freeze V13's official team:

```text
python pipeline/run_weekend.py --phase post_fp --round N
python pipeline/publish_v13_decision.py --round N --phase post_fp
```

The publisher refuses an archive whose generation timestamp is at or after the
configured lock deadline. The final record is immutable once written.

V13 has only 3x Boost remaining. At each post-FP deadline, it compares the
extra 3x value of its selected top two drivers with the largest remaining
priors-only top-two forecast already on file. It plays the chip only when the
current evidence meets or beats that future benchmark; otherwise it saves it.

### 3. Post-race settlement

First complete the normal official-points and reconciliation checklist. V13's
round must not be settled until official driver and constructor points and the
closing price snapshot are present and reconciled. Settlement then adds the
round score to the public history, revalues the persistent team, carries the
banked transfer state forward, and advances `next_round`.

The settlement command is the remaining operations item before R14 finishes;
it cannot be meaningfully exercised until R14 official scores and closing
prices exist. Do not update V13's score manually in the public JSON.

## Recommended entry proof

Do not ask people to submit a lineup every week. Use one registration and one
final proof:

1. Registration is open now. The entrant submits and confirms an email address
   before the R22 Las Vegas F1 Fantasy team lock on 2026-11-21 at 04:00 UTC.
2. The confirmation event and timestamp are the entry record. Entry is free
   and Ko-fi membership is not required.
3. After R24, the entrant submits one exact official F1 Fantasy team
   name/identifier and its official full-season score screenshot.
4. A private F1 Fantasy league can be used as the primary verification source
   if it reliably exposes the submitted team's full-season total; screenshots
   remain the fallback.

Closing registration at the R22 lock prevents people from waiting for the final
two rounds before deciding whether to enter. The chosen team is submitted after
the season, as approved for the simplified 2026 challenge flow.

## Standings and prizes

- Ranking metric: entrant's official full-2026 total minus V13's official
  full-2026 total.
- Only positive margins qualify.
- Planned prizes: $100, $50, and $30 for the three largest positive margins.
- Recommended tie rule: tied entrants split the combined prize positions they
  occupy. This avoids a subjective or retrofitted tiebreaker.
- Publish V13's final audit record before verifying winners.

## Eligibility and payments

The challenge is `registration_open` with a free entry route. Ko-fi payments
support the channel and do not determine challenge eligibility. Before winner
verification and payout, publish and confirm the remaining official terms:

- obtain a rules/compliance review for the countries being allowed;
- confirm PayPal and Ko-fi permit the final promotion structure or provide a
  compliant alternative entry route;
- define minimum age, excluded locations, eligibility date, membership status
  test, winner verification window, payout method, taxes, disputes, and what
  happens if fewer than three entrants beat V13;
- state that the promotion is not sponsored or administered by Formula 1,
  F1 Fantasy, Ko-fi, or PayPal;
- publish a privacy notice and retention period for registration evidence.

## Minimal data model for registration

For the simple launch, the confirmed Resend contact and its confirmation event
are the entry record. Before end-of-season score submission opens, use a private
table with these fields:

- generated entry ID;
- submitted timestamp and rules version;
- entrant display name and email;
- country and age confirmation;
- exact F1 Fantasy team name/identifier;
- confirmation evidence from before the R22 lock;
- optional private-league identity;
- final screenshot location, verified score, verification status, and notes.

Never expose emails, Ko-fi identities, or screenshots in the public leaderboard.
Publish a display name, verified score, margin over V13, and verification state
only after consent.

## Registration delivery deployment checklist

Before enabling the public registration form, run
`infrastructure/supabase/004_beat_v13_entries.sql` in the private Supabase
project. The table has RLS enabled with no anon/authenticated policies; only
the server-side Supabase service-role key may access it. Set the existing
Resend and `SUBSCRIPTION_SIGNING_SECRET` values, plus
`SUPABASE_SERVICE_ROLE_KEY` (or `SUPABASE_SECRET_KEY`) and
`NEXT_PUBLIC_SUPABASE_URL`. `BEAT_V13_SESSION_SECRET` is recommended for the
HttpOnly entrant session and falls back to `SUBSCRIPTION_SIGNING_SECRET` when
omitted. Do not run the migration from the browser or expose any of these
values in public JavaScript.
