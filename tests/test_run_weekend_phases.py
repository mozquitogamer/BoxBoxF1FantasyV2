"""Regression tests for weekend-pipeline phase ordering and required CLI args."""

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "run_weekend", ROOT / "pipeline" / "run_weekend.py"
)
RUN_WEEKEND = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(RUN_WEEKEND)


def _step_names(phase: str) -> list[str]:
    return [step[0] for step in RUN_WEEKEND.PHASES[phase]["steps"]]


def test_pre_fp_supplies_required_all_flags():
    steps = RUN_WEEKEND.PHASES["pre_fp"]["steps"]
    args_by_script = {step[0]: step[1] for step in steps}

    assert args_by_script["03a_normalize_jolpica.py"] == ["--all"]
    assert args_by_script["03b_build_jolpica_features.py"] == ["--all"]


def test_post_race_canonical_data_is_final_before_actual_scoring():
    names = _step_names("post_race")

    assert names.index("12_count_overtakes.py") < names.index(
        "13_fetch_openf1_overtakes.py"
    )
    assert names.index("13_fetch_openf1_overtakes.py") < names.index(
        "13_fetch_pitstop_stationary.py"
    )
    assert names.index("13_fetch_pitstop_stationary.py") < names.index(
        "11_actual_fantasy_points.py"
    )
    assert names.index("11_actual_fantasy_points.py") < names.index(
        "08_export_website_json.py"
    )


def test_post_race_extracts_weather_for_next_retrain():
    steps = RUN_WEEKEND.PHASES["post_race"]["steps"]
    weather_step = next(
        step for step in steps if step[0] == "03c_extract_session_weather.py"
    )

    assert weather_step[1] == ["--year", "{year}", "--round", "{round}"]
