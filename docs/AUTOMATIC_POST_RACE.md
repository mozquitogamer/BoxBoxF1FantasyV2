# Automatic post-race updates

The GitHub Actions workflow **Automatic post-race update** runs at 00:17, 06:17, 12:17 and 18:17 UTC (02:17, 08:17, 14:17 and 20:17 South African time). It runs on GitHub; the owner's computer does not need to be on. GitHub may delay scheduled jobs.

The workflow detects the latest non-cancelled race from the last seven days, waits for complete results, official Fantasy points and next-round prices, then settles the race and prepares the next round's pre-practice forecast. Official totals must match for all drivers and constructors before anything is published. Saved race forecasts are preserved. Pending feeds are retried at the next scheduled run, and unchanged official sources skip repeated simulations.

Verified generated data is committed to `master`, which deploys through the existing Vercel integration. Failed checks do not publish generated changes. The job summary shows whether data is pending, unchanged, published or failed. Workflow changes also trigger a run so its configuration is checked immediately.

## Manual run and recovery

Open GitHub **Actions → Automatic post-race update → Run workflow**. Leave the round blank for automatic selection, or enter the internal calendar round (for example, Bahrain GP in Malaysia is 18; cancelled April rounds retain their numbers). The runner maps API round numbers itself.

For local operation:

```sh
python pipeline/auto_post_race.py --dry-run
python pipeline/auto_post_race.py
python pipeline/auto_post_race.py --round 18
```

Exit code 75 means official data or the provider is temporarily unavailable. Other failures need inspection of the failed step. Source fingerprints and successful completion times are stored in `data/automation/post_race_state.json`; they are saved only after the complete run validates.

Disable or re-enable the schedule through the workflow's GitHub Actions menu. A seat change, field-size change or new season requires reviewing the roster/calendar mapping before automatic publication can proceed. Keep `config/settings.py` and `data/seed/races.json` current when moving to a new season.
