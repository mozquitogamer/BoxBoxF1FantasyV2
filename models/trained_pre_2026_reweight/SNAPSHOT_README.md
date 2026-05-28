# Snapshot: pre-2026-reweight (2026-05-27)

Snapshot taken before the model retraining experiment campaign documented in
`docs/MODEL_RETRAINING_EXPERIMENT.md`. Used to restore production behaviour if
the new sweep produces worse models or no statistically significant improvement.

## What this snapshot contains

All artefacts from `models/trained/` as of commit `ffb30b8` (Scenarios Phase 2+3,
DNF classifier framework, MC widener calibration). Trained with the
**production weather + ramped 2026 weight** configuration:

- Qualifying model: XGBRanker, n=1200, lr=0.025, depth=3
- Race model:       XGBRanker, n=650,  lr=0.03,  depth=5
- Race-FP model:    XGBRanker, n=650,  lr=0.03,  depth=5 (walk-forward predicted quali)
- Sprint model:     XGBRanker, n=400,  lr=0.035, depth=4
- 2026 sample weight: ramped 2.0 → 2.5 (full multiplier at 10+ rounds)
- Wet-row weight boost: 6× (race-session label)

## Restore

```bash
# Restore models
cp -r models/trained_pre_2026_reweight/* models/trained/

# Restore code state (if needed)
git checkout backup/pre-2026-reweight
```

The git tag `backup/pre-2026-reweight` marks the exact commit + tree state.

## Walk-forward MAE (baseline reference)

Recorded by `pipeline/validate_model_config.py --config baseline` —
see `data/experiments/baseline_results.json` for fold-level numbers.
