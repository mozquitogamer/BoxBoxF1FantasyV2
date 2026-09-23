# Pipeline tool inventory

Use `pipeline/run_weekend.py --phase PHASE --round N` for a race weekend. Its
`PHASES` map is the source of step order. Run it with `--dry-run` to see the
current commands. The [operations guide](OPERATIONS_GUIDE.md) covers timing and
seed updates. This inventory separates routine code from tools kept for
specific maintenance or reproducible research.

| Status | Tools | Inputs and purpose |
|---|---|---|
| Weekend runner | `run_weekend.py`; numbered `01`–`14` scripts used by its `PHASES`; `predict_horizon.py`, `publish_v13_decision.py`, `build_v13_manager.py` | Raw API/cache data, seed files, models, and current-round artifacts. Produces predictions, actuals, web JSON, and generated pages. The runner chooses the order. |
| Production helpers | `audit.py`, `feature_engineering.py`, `fp_long_runs.py`, `prediction_sanity.py`, `prospective_holdout.py`, `16_build_seo_charts.py` | Imported by prediction, export, FP analysis, or SEO generation. Keep beside those callers. |
| Scheduled jobs | `weather_forecast.py`, `youtube_videos.py`, `15_submit_indexnow.py` | Forecast API, YouTube RSS, and generated sitemap respectively. Called by `.github/workflows/`; IndexNow runs after a relevant publish. |
| Operator tools | `12_official_fantasy_points.py`, `reconcile_official_points.py`, `calibrate_confidence.py`, `build_articles.py`, `apply_upgrades.py`, `pit_wall_weekly_preview.py`, `notify_subscribers.py`, `configure_adsense.py` | Official/seed data, completed-round actuals, article Markdown, dashboard upgrade settings, or public prediction JSON. Run for the corresponding update, audit, preview, or account setup. `apply_upgrades.py` also has dashboard callers. |
| Recovery and data repair | `recover_archives.py`, `backfill_audit.py`, `backfill_sidecars.py`, `backfill_fp_history.py`, `download_fp_missing.py`, `download_helper.py` | Historical archives, cached raw FP, or missing metadata. These can change archives, training data, or model state; run only for a known repair. The two download helpers may also be called by external local automation, so they stay at their current paths. |
| Model evaluation | `validate_model_config.py`, `validate_race_fp.py`, `validate_weather_features.py`, `validate_alt_algorithm.py`, `validate_alt_algo_v2.py`, `sweep_fp_blend.py`, `evaluate_prequential_2026.py`, `evaluate_post_fp_overlays.py`, `backtest_forecast.py` | Training rows and frozen prediction/actual archives. Run when assessing a proposed model or inference change; these are outside weekend publishing. The two alternative-algorithm validators test different learners. |
| Historical research | `analyze_multiple_testing.py`, `analyze_budget_point_value.py`, `audit_track_similarity.py`, `calibrate_weather_widener.py`, `train_dnf_classifier.py`, `simulate_fantasy_risk_profiles.py`, `simulate_fantasy_season_strategies.py`, `build_risk_team_evolution_report.py`, `pipeline/research/run_oat_sweep.py`, `pipeline/research/run_combined_grid.py`, `pipeline/research/run_race_fp_sweep.py` | Saved experiments, training rows, and historical fantasy results. Keep for reproducibility; they do not participate in a live phase. |

The three `pipeline/research/` launchers run their unchanged sweep candidate
lists through `pipeline/validate_model_config.py` or
`pipeline/validate_race_fp.py`. They read and write `data/experiments/`; the
recorded results remain there. For example, to inspect an existing sweep
without retraining:

```bash
python pipeline/research/run_oat_sweep.py weight --summary-only
```

`publish_weekend.py` at the project root is a compatibility entry point for
older operator commands. New commands should name the phase explicitly through
`pipeline/run_weekend.py`.
