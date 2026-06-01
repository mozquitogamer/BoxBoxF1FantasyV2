# Tests

A lightweight safety net. Not exhaustive — it targets the bug classes that have
actually bitten this project: silent scoring errors, undefined frontend
references, and grossly-broken prediction exports.

## Run everything

```bash
# Python tests (scoring rules + prediction sanity guard)
python -m pytest tests/ -q

# Frontend smoke test (catches undefined-reference crashes node --check misses)
node tests/smoke_app_js.js
```

## What each test covers

| File | Catches |
|------|---------|
| `test_fantasy_scoring.py` | Wrong point values, sign flips, off-by-one pitstop brackets, DOTD leaking into constructor totals. Every prediction flows through these functions. |
| `test_prediction_sanity.py` | The pre-export guard itself — all-zeros, NaNs, gross point suppression (the bias-nerf class), ranking collapse. |
| `smoke_app_js.js` | `app.js` failing to load, `TA_TUNABLES`/`MW_TUNABLES` undefined, key functions missing. `node --check` only validates syntax and would NOT catch these. |

## The pre-export guard

`pipeline/prediction_sanity.py` runs automatically inside
`08_export_website_json.py` before predictions are written to the live site. It
prints `[OK]`, `[X] problem`, or `- warning` lines. Problems don't block the
export (model output is a judgement call), but they print loudly so a regression
can't ship silently the way the MC bias-nerf did.

## Before pushing frontend or scoring changes

```bash
python -m pytest tests/ -q && node tests/smoke_app_js.js && echo "safe to push"
```
