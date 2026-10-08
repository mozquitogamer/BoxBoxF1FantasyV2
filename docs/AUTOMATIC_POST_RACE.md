# Automatic race weekend updates

The GitHub Actions workflow **Automatic race weekend updates** runs the prediction pipelines when sessions make them due:

| Session | Run due | Pipeline |
| --- | --- | --- |
| FP1, FP2, FP3 (when scheduled) | 35 minutes after the recorded finish | post_fp |
| Sprint Qualifying (sprint weekends) | 35 minutes after SQ3 finishes | post_fp with the actual sprint grid |
| Grand Prix qualifying | 35 minutes after Q3 finishes | post_quali, with locked qualifying points for Final Fix |
| Grand Prix race | 24 hours after the recorded finish | post_race, then the next race's pre_fp_predict forecast |

A small schedule check runs every five minutes on GitHub. It does not install pipeline dependencies or run simulations when nothing is due. The owner's computer can be off. GitHub scheduling is best effort: queue delays and processing time can make publication later than the target. See [GitHub scheduling documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

The planner fetches the current [OpenF1 session schedule](https://api.openf1.org/v1/sessions?year=2026) and SessionStatus race-control messages. Actual SESSION FINISHED messages determine the delay, so red flags, postponed starts and overruns do not cause premature runs. Q1/Q2 finishes are ignored. Race sessions are matched to the seed calendar by local event date and meeting ID; cancelled rounds are skipped and external numbering is not assumed.

Each successful session is recorded in data/automation/weekend_state.json only after validation. Missing timing, telemetry, classification or official scoring is retried at the next schedule check. Missed older practice sessions are coalesced into the newest due update; completed sessions never downgrade to an older one. Practice updates stop when the race starts. Failures do not publish generated changes.

Qualifying updates require a complete classification and a simulation with qualifying locked. Practice/SQ updates require the new session's evidence in prediction metadata. Forecasts must contain all 22 drivers and 11 constructors, with fresh weather for the same round. After the race, official Fantasy totals must match for every asset before settlement and the next-round forecast are published.

The original phase holdouts remain frozen. Additional write-once post_fp_fp1, post_fp_fp2, post_fp_fp3 and post_fp_sq archives preserve each session version; timestamped audit snapshots retain every run. The Drivers and Constructors labels distinguish Post FP1/FP2/FP3, Post sprint qualifying and Post qualifying. Sprint qualifying does not lock Grand Prix qualifying points.

Verified files are committed to master, which deploys through the existing Vercel integration. The separate lightweight weather refresh follows the round of the live forecast, so it cannot jump ahead during the 24-hour wait.

## Manual runs

Open [Actions → Automatic race weekend updates → Run workflow](https://github.com/mozquitogamer/BoxBoxF1FantasyV2/actions/workflows/post-race.yml). Select post_race to settle immediately, or post_fp/post_quali to request those updates. Manual runs bypass the automatic delay but retain data checks. The round is an internal calendar number; blank uses the current forecast (or the latest recent race for post_race). For compatibility, entering a round with phase auto requests a manual post-race run.

Local commands remain available:

```sh
python pipeline/auto_weekend.py --plan
python pipeline/auto_weekend.py
python pipeline/auto_weekend.py --phase post_fp --round 19
python pipeline/auto_weekend.py --phase post_quali --round 19
python pipeline/auto_post_race.py --round 19
python pipeline/auto_post_race.py --dry-run
```

Exit 75 means data is pending. Other failures need inspection of the failed step. Post-race fingerprints remain in data/automation/post_race_state.json; unchanged results skip repeated settlement, and explicit manual runs can pick up official corrections. Disable/re-enable the schedule from the workflow's Actions menu. Review the seed calendar, roster and season settings when moving to a new season.
