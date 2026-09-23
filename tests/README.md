# Tests

The Python suite covers scoring, prediction contracts, archives, weather,
pipeline ordering, and the manager and SEO tools. The JavaScript checks cover
the static site's load-time bindings and key user-facing calculations.

## Run the checks

```bash
python -m pytest tests/ -q
node tests/smoke_app_js.js
node tests/app_behavior_test.js
node tests/team_state_test.js
```

On Windows, use the project's virtual-environment Python if `python` is not
on `PATH` (for example, `.pipeline-venv/Scripts/python.exe`).

The GitHub publishing and scheduled-job workflows do not run this suite, so
run these checks before publishing a code change. Research sweeps are separate
experiments, listed in [the pipeline tool inventory](../docs/PIPELINE_TOOLS.md).

## JavaScript checks

- `smoke_app_js.js` loads the standalone scoring modules and `app.js` in a
  mocked browser and checks that their main bindings resolve. A syntax-only
  check cannot catch an undefined top-level reference.
- `app_behavior_test.js` exercises optimizer, Final Fix, Team Compare, price
  history, and other pure frontend behavior. It also retains a few shell and
  script-order checks that do not yet have browser-level coverage.
- `app_js_harness.js` is shared setup for those two checks; it is not a test
  command.
- `team_state_test.js` checks the standalone team-state store.

## Prediction export guard

`pipeline/prediction_sanity.py` runs inside `08_export_website_json.py` before
writing predictions. Problems print loudly; some warnings need judgment rather
than blocking an export. `test_prediction_sanity.py` checks the guard itself.

Tests that replay historical decisions should use frozen archive prices and
round-specific rosters. Tests must write generated files to temporary paths,
not into `web/public/data/`.
