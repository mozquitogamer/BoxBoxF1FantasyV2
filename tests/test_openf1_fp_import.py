"""Backup practice data must preserve actual laps, tyre runs and deletions."""

import copy

import pytest

from pipeline.import_openf1_fp import build_practice_laps


@pytest.fixture
def inputs():
    session = {"session_key": 123, "session_name": "Practice 1", "location": "Austin",
               "year": 2026, "date_end": "2026-10-23T18:30:00Z"}
    def lap(number, duration, start, out=False):
        return {"session_key": 123, "driver_number": 1, "lap_number": number,
                "lap_duration": duration, "date_start": f"2026-10-23T{start}Z",
                "is_pit_out_lap": out, "duration_sector_1": None}
    bundle = {
        "drivers": [{"session_key": 123, "driver_number": 1, "name_acronym": "VER", "team_name": "Red Bull Racing"}],
        "laps": [lap(1, None, "17:30:00", True), lap(2, 90, "17:32:00"),
                 lap(3, 89, "17:34:00"), lap(4, 120, "17:36:00"),
                 lap(5, 200, "17:40:00", True), lap(6, 92, "17:44:00"),
                 lap(7, 93, "17:46:00")],
        "stints": [{"session_key": 123, "driver_number": 1, "stint_number": 1,
                    "lap_start": 1, "lap_end": 4, "compound": "MEDIUM", "tyre_age_at_start": 7},
                   {"session_key": 123, "driver_number": 1, "stint_number": 2,
                    "lap_start": 5, "lap_end": 7, "compound": "MEDIUM", "tyre_age_at_start": 0}],
        "race_control": [
            {"session_key": 123, "date": "2026-10-23T17:35:00Z", "message": "CAR 1 TIME 1:29.000 DELETED - TRACK LIMITS LAP 3"},
            {"session_key": 123, "date": "2026-10-23T17:46:30Z", "scope": "Track", "flag": "RED", "message": "RED FLAG"},
            {"session_key": 123, "date": "2026-10-23T17:49:00Z", "scope": "Track", "flag": "GREEN", "message": "GREEN FLAG"}],
        "weather": [{"session_key": 123, "track_temperature": 39, "air_temperature": 27, "rainfall": 0}],
        "session_result": [{"session_key": 123, "driver_number": 1, "duration": 90}],
    }
    return bundle, session


def test_retains_deleted_pace_but_filters_in_out_and_red_flag_laps(inputs):
    bundle, session = inputs
    before = copy.deepcopy(bundle)
    frame = build_practice_laps(bundle, session, 20)
    assert frame["lap_number"].tolist() == [2, 3, 6]
    assert frame["lap_time"].tolist() == [90, 89, 92]
    assert frame["stint_number"].tolist() == [1, 1, 2]
    assert frame["tyre_life"].tolist() == [9, 10, 2]
    assert frame["lap_deleted"].tolist() == [False, True, False]
    assert frame["sector_1"].isna().all()
    assert frame["fp_data_source"].unique().tolist() == ["openf1"]
    assert frame["session"].unique().tolist() == ["FP1"]
    assert bundle == before


def test_reinstated_lap_is_restored(inputs):
    bundle, session = inputs
    bundle["race_control"].append({"session_key": 123, "date": "2026-10-23T17:36:00Z",
                                   "message": "CAR 1 TIME 1:29.000 REINSTATED"})
    bundle["session_result"][0]["duration"] = 89
    assert 3 in build_practice_laps(bundle, session, 20)["lap_number"].tolist()
    assert not build_practice_laps(bundle, session, 20).set_index("lap_number").loc[3,"lap_deleted"]


def test_official_classification_rejects_an_unfiltered_invalid_fast_lap(inputs):
    bundle, session = inputs
    bundle["race_control"] = []
    with pytest.raises(ValueError, match="Unfiltered invalid best lap"):
        build_practice_laps(bundle, session, 20)


def test_mixed_sessions_and_non_practice_data_are_rejected(inputs):
    bundle, session = inputs
    bundle["laps"][0]["session_key"] = 999
    with pytest.raises(ValueError, match="mixes session keys"):
        build_practice_laps(bundle, session, 20)
    session["session_name"] = "Qualifying"
    with pytest.raises(ValueError, match="Only free-practice"):
        build_practice_laps(bundle, session, 20)
