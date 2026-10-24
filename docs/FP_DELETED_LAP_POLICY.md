# Deleted practice laps as pace evidence

From 24 October 2026, a lap-time deletion does not disqualify a real timed free-practice lap from pace analysis. The same population feeds qualifying features, long-run features, historical training, current-weekend prediction and the Monte Carlo raw scores.

Both `02_build_laps.py` (FastF1) and `import_openf1_fp.py` (OpenF1) preserve `lap_deleted` as provenance. A reinstated OpenF1 lap loses that flag. Pit in/out laps, missing/nonpositive times and SC/VSC/red-flag interruptions remain excluded. Long-run selection still trims cooldowns and isolated traffic spikes; accepting a deletion does not mean accepting every slow lap as race pace.

Official qualifying classifications, qualifying Fantasy points, actual sprint grids and confirmed penalised race grids are unchanged. A deleted practice best may be quicker than the published legal practice classification. The OpenF1 source-consistency check consequently compares the classification only with non-deleted laps.

## Consistency and recovery

The existing feature/model semantics version advances from 3 to 4. Processed practice laps carry `fp_lap_semantics_version=4`; feature extraction rejects stale or unstamped lap populations. Feature parquets and trained model manifests carry `fp_stint_semantics_version=4`, retaining the existing downstream compatibility guard.

`python pipeline/rebuild_fp_pace.py --output outputs/<review>/staged` rebuilds the existing event coverage from persisted raw FastF1 parquets or archived `data/audit/inputs/yearYYYY/roundN/openf1_fpN_KEY/` bundles. It writes staged features, current-season laps and a report. Any failed event prevents declaring the rebuild complete; `--only-events YEAR:ROUND` retries selected events and updates the report.

For the October 24 migration, all 109 feature sets were rebuilt. Austin FP1+FP2 recovers 145 deleted timed laps. Singapore FP1's raw, processed and FastF1-cache files were unreadable through OneDrive, so the public OpenF1 session 11378 was recovered and archived with URLs and content hashes. No lap times were invented.

Training uses only completed rounds strictly before Austin (`--exclude-after 2026:20`). Rebuilt features, new models and the Austin forecast are validated together before promotion. Completed-round prediction/accuracy archives are not regenerated. Historical Monte Carlo noise calibration is retained rather than being tuned to make one weekend look more plausible.

The investigation scripts, baseline copies, feature report, walk-forward results and before/after comparison are saved under `outputs/deleted_lap_pace_20261024/`. OneDrive also prevented copying the old Singapore feature parquet; the original immutable inference snapshots remain available separately in `data/audit/inputs/year2026/round19/`.
