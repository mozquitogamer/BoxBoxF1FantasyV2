"""Regression coverage for generic retirement and tyre-failure parsing."""

import importlib.util
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "jolpica_features_dnf_test", ROOT / "pipeline" / "03b_build_jolpica_features.py"
)
features = importlib.util.module_from_spec(spec)
spec.loader.exec_module(features)


def test_generic_retired_is_not_a_tire_failure():
    status = pd.Series(["Retired", "Tyre puncture", "Tire puncture", "Brakes", "Accident"])
    dnf = pd.Series([1] * len(status))
    dsq = pd.Series([0] * len(status))

    assert features.dnf_cause_bucket(status, dnf, dsq).tolist() == [
        "other", "mechanical", "mechanical", "mechanical", "collision"
    ]
