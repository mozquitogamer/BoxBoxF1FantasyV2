# Beat V13 — operating plan

## What V13 is

V13 is the Budget Builder / medium-risk manager selected from the twelve 2026
virtual-manager experiments. Its normal lineup objective values projected
fantasy points, forecast price movement, and negative-P5 exposure. It does not
read qualifying results when choosing its normal team.

Qualifying-locked data is reserved for Final Fix. The R1–R13 research replay
used the first trustworthy post-qualifying opportunity at R13, moving Leclerc
to Norris for a realised four-point improvement. Final Fix is therefore no
longer available to the live 2026 manager.

The displayed R1–R13 total is a full-season counterfactual research replay:
2,541 points after Final Fix. R1–R3 use reconstructed forecasts; later rounds
use preserved archives. This distinction must remain visible anywhere the
replay score is promoted.

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

1. After R22 is complete and before the R23 lock, the entrant submits their
   exact official F1 Fantasy team name/identifier, display name, contact email,
   and the Ko-fi identity used for eligibility checks.
2. The registration form records timestamp, rules version, consent, country,
   age confirmation, and acceptance of the privacy notice.
3. After R24, a potential winner submits an official full-season score
   screenshot. The registered team identifier must match.
4. A private F1 Fantasy league can be used as the primary verification source
   if it reliably exposes the registered team's full-season total; screenshots
   remain the fallback.

Locking registration between R22 and R23 prevents entrants from choosing among
multiple teams after seeing the final two rounds. A screenshot alone at season
end would not prove which team they intended to enter.

## Standings and prizes

- Ranking metric: entrant's official full-2026 total minus V13's official
  full-2026 total.
- Only positive margins qualify.
- Planned prizes: $100, $50, and $30 for the three largest positive margins.
- Recommended tie rule: tied entrants split the combined prize positions they
  occupy. This avoids a subjective or retrofitted tiebreaker.
- Publish V13's final audit record before verifying winners.

## Eligibility and payments launch gate

Keep the challenge in `rules_pending` status until written official rules are
published. The fact that Ko-fi payments support the channel and contest entry
is described as a bonus does not, by itself, establish that the arrangement is
outside payment-processor contest restrictions. Before opening registration:

- obtain a rules/compliance review for the countries being allowed;
- confirm PayPal and Ko-fi permit the final promotion structure or provide a
  compliant alternative entry route;
- define minimum age, excluded locations, eligibility date, membership status
  test, winner verification window, payout method, taxes, disputes, and what
  happens if fewer than three entrants beat V13;
- state that the promotion is not sponsored or administered by Formula 1,
  F1 Fantasy, Ko-fi, or PayPal;
- publish a privacy notice and retention period for registration evidence.

Until those items are closed, the site may introduce V13 and show the research
record, but it should not claim that paid-member contest registration is open.

## Minimal data model for registration

Use a private table with these fields:

- generated entry ID;
- submitted timestamp and rules version;
- entrant display name and email;
- country and age confirmation;
- Ko-fi supporter email or immutable supporter reference;
- exact F1 Fantasy team name/identifier;
- eligibility snapshot after R22 and before the R23 lock;
- optional private-league identity;
- final screenshot location, verified score, verification status, and notes.

Never expose emails, Ko-fi identities, or screenshots in the public leaderboard.
Publish a display name, verified score, margin over V13, and verification state
only after consent.
