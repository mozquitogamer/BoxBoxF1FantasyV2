# Automatic race weekend updates

The GitHub Actions workflow **Automatic race weekend updates** runs the prediction pipelines when sessions make them due:

| Session | Run due | Pipeline |
| --- | --- | --- |
| FP1, FP2, FP3 (when scheduled) | 35 minutes after the recorded finish | post_fp |
| Sprint Qualifying (sprint weekends) | 35 minutes after SQ3 finishes | post_fp with the actual sprint grid |
| Grand Prix qualifying | 35 minutes after Q3 finishes | post_quali, with locked qualifying points for Final Fix |
| Grand Prix race | 24 hours after the recorded finish | post_race, then the next race's pre_fp_predict forecast |

A lightweight GitHub check is scheduled every five minutes. Pipeline dependencies and simulations run only when an update is due. The owner's computer can be off. GitHub queue delays and processing time can make publication later than the target. [GitHub scheduling documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)

The planner fetches the current [OpenF1 session schedule](https://api.openf1.org/v1/sessions?year=2026) and SessionStatus race-control messages. Actual SESSION FINISHED messages determine the delay, so red flags, postponed starts and overruns do not cause premature runs. Q1/Q2 finishes are ignored. Race sessions are matched to the seed calendar by local event date and meeting ID; cancelled rounds are skipped and external numbering is not assumed.

Each successful session is recorded in data/automation/weekend_state.json only after validation. Missing timing, telemetry, classification or official scoring is retried at the next schedule check. Missed older practice sessions are coalesced into the newest due update; completed sessions never downgrade to an older one. Practice updates stop when the race starts. Failures do not publish generated changes.

Qualifying updates require a complete classification and a simulation with qualifying locked. Practice updates require all applicable practice sessions through the selected session in the model output. The runner tries FastF1 first and imports completed OpenF1 laps, stints, weather and classification when FastF1 is unavailable. OpenF1 lap counts must cover the published classification, and a late session finish keeps the valid laps recorded after the scheduled end. Sprint Qualifying also requires the actual sprint grid. Forecasts must contain 22 drivers and 11 constructors, with fresh weather for the same round. After the race, official Fantasy totals must match for every asset before settlement and the next-round forecast are published.

The original phase holdouts remain frozen. Additional write-once post_fp_fp1, post_fp_fp2, post_fp_fp3 and post_fp_sq archives preserve each session version; timestamped audit snapshots retain every run. The Drivers and Constructors labels distinguish Post FP1/FP2/FP3, Post sprint qualifying and Post qualifying. Sprint qualifying does not lock Grand Prix qualifying points.

Verified files are committed to master, which deploys through the existing Vercel integration. The separate lightweight weather refresh follows the round of the live forecast, so it cannot jump ahead during the 24-hour wait.

## Manual runs

Open [Actions → Automatic race weekend updates → Run workflow](https://github.com/mozquitogamer/BoxBoxF1FantasyV2/actions/workflows/post-race.yml) on `master`. Select `post_fp`, `post_quali` or `post_race` and enter the internal round from `data/seed/races.json`. With a blank round, explicit prediction phases use the live forecast's round and `post_race` uses the latest recent race. The combination of `auto` and a round requests manual settlement for that round.

A manual prediction run skips the 35-minute delay and waits for a confirmed finish and complete inputs. For `post_fp` it chooses the latest started practice or sprint qualifying session. If that session is still running or its finish is missing, the run reports pending. For `post_quali` it waits for Q3 to finish and accepts either the audited qualifying seed or the complete FastF1 classification. Session forecasts close at race start.

Local commands use the same checks. Run them from the repository root with the project Python environment. Replace `24` with the internal round for the weekend:

```sh
python pipeline/auto_weekend.py --plan
python pipeline/auto_weekend.py --phase post_fp --round 24 --plan
python pipeline/run_weekend.py --phase post_fp --round 24
python pipeline/run_weekend.py --phase post_quali --round 24
python pipeline/auto_weekend.py --phase post_race --round 24
```

`auto_weekend.py --plan` checks timing feeds without generating files. `run_weekend.py --dry-run` prints the phase's commands without checking timing feeds. Exit code 75 means a session or data is still pending. In GitHub Actions the job summary identifies the pending step and a later scheduled check can retry it. For any other failure, inspect the failed step before publishing. Local runs save files in the checkout. Use the [deployment checklist](OPERATIONS_GUIDE.md#manual-publishing-checklist) to commit them and verify production.

Post-race fingerprints are stored in `data/automation/post_race_state.json`. Unchanged results skip repeated settlement. A manual settlement can pick up official corrections. Disable or re-enable the schedule from the workflow's Actions menu. Review the seed calendar, roster and season settings when moving to a new season.
