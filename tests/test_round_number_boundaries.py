"""Internal calendar IDs must stay distinct from external API round numbers."""

import importlib
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from config.settings import (
    fastf1_round,
    internal_round_from_api,
    internal_rounds_for_year,
)


def test_2026_round_trip_skips_cancelled_calendar_slots():
    active_rounds = [r for r in range(1, 26) if r not in (4, 5)]
    assert internal_rounds_for_year(2026, 23) == active_rounds
    assert internal_rounds_for_year(2026, 4) == [1, 2, 3, 6]
    for api_round, internal_round in enumerate(active_rounds, start=1):
        assert internal_round_from_api(api_round, 2026) == internal_round
        assert fastf1_round(internal_round, 2026) == api_round


def test_sepang_insertion_preserves_history_and_aligns_future_sessions():
    from config.settings import SEED_DIR, SPRINT_ROUNDS_2026
    from config.track_classifications import get_circuit_id_from_race_name
    from config.circuit_coordinates import get_circuit_location

    calendar = json.loads((SEED_DIR / "races.json").read_text())
    active = [race for race in calendar["races"] if not race.get("cancelled")]
    assert len(active) == calendar["active_rounds"] == 23
    assert [race["date"] for race in active] == sorted(race["date"] for race in active)
    by_round = {race["round"]: race for race in active}
    assert by_round[17]["name"] == "Azerbaijan Grand Prix"
    assert by_round[18]["name"] == "Bahrain Grand Prix in Malaysia"
    assert by_round[18]["date"] == "2026-10-04"
    assert fastf1_round(17) == 15
    assert fastf1_round(18) == 16
    assert fastf1_round(19) == 17
    assert by_round[19]["name"] == "Singapore Grand Prix"
    assert by_round[25]["name"] == "Abu Dhabi Grand Prix"
    assert [race["round"] for race in active if race["sprint"]] == SPRINT_ROUNDS_2026
    assert get_circuit_id_from_race_name(by_round[18]["name"]) == "sepang"
    assert get_circuit_location(by_round[18]["circuit"])[2] == "Asia/Kuala_Lumpur"

    app = (Path(__file__).resolve().parents[1] / "web/public/app.js").read_text(encoding="utf-8")
    deadlines = re.findall(r"\{ round: (\d+),\s+race: '([^']+)',\s+lock: '([^']+)',\s+sprint: (true|false)", app)
    deadline_map = {int(number): (name, lock, sprint == "true") for number, name, lock, sprint in deadlines}
    for race in active:
        assert deadline_map[race["round"]][0] == race["name"]
        assert deadline_map[race["round"]][2] == race["sprint"]
    assert deadline_map[18][1] == "2026-10-03T08:00:00Z"


def test_other_seasons_keep_their_round_numbers():
    assert internal_rounds_for_year(2025, 4) == [1, 2, 3, 4]
    assert fastf1_round(4, 2025) == 4


@pytest.mark.parametrize("round_num", [0, 4, 5])
def test_invalid_2026_round_never_maps_to_a_different_race(round_num):
    with pytest.raises(ValueError):
        fastf1_round(round_num, 2026)


def test_bulk_jolpica_keeps_internal_directory_names(tmp_path, monkeypatch):
    download = importlib.import_module("pipeline.01_download_data")
    requests = []

    def fake_get(endpoint):
        requests.append(endpoint)
        if endpoint == "2026.json?limit=100":
            return {"MRData": {"RaceTable": {"Races": [{"round": "4"}]}}}
        if endpoint == "2026/4/results.json":
            return {"source": endpoint}
        return None

    monkeypatch.setattr(download, "JOLPICA_RAW_DIR", tmp_path)
    monkeypatch.setattr(download, "jolpica_get", fake_get)
    monkeypatch.setattr(download.time, "sleep", lambda _: None)
    monkeypatch.setattr(download, "tqdm", lambda rows, **_: rows)

    download.download_jolpica_year(2026)

    miami = tmp_path / "year2026" / "round6" / "results.json"
    assert json.loads(miami.read_text(encoding="utf-8"))["source"] == "2026/4/results.json"
    assert not (tmp_path / "year2026" / "round4").exists()
    assert "2026/4/results.json" in requests


def test_cancelled_single_round_does_not_create_raw_directory(tmp_path, monkeypatch):
    download = importlib.import_module("pipeline.01_download_data")
    monkeypatch.setattr(download, "JOLPICA_RAW_DIR", tmp_path)
    with pytest.raises(ValueError, match="cancelled"):
        download.download_jolpica_round(2026, 4)
    assert not (tmp_path / "year2026" / "round4").exists()


def test_historical_fastf1_helper_passes_internal_rounds(tmp_path, monkeypatch):
    helper = importlib.import_module("pipeline.download_helper")
    requested = []
    fake_download = SimpleNamespace(
        get_total_rounds_for_year=lambda year: 4,
        download_fastf1_round=lambda year, round_num: requested.append((year, round_num)),
    )
    monkeypatch.setattr(helper, "FASTF1_CACHE_DIR", tmp_path)
    monkeypatch.setattr(helper.fastf1.Cache, "enable_cache", lambda path: None)
    monkeypatch.setattr(helper, "load_download_module", lambda: fake_download)
    monkeypatch.setattr(sys, "argv", ["download_helper.py", "--mode", "fastf1_historical",
                                   "--start", "2026", "--end", "2026"])

    helper.main()

    assert requested == [(2026, 1), (2026, 2), (2026, 3), (2026, 6)]


def test_openf1_uses_original_calendar_position(monkeypatch):
    openf1 = importlib.import_module("pipeline.13_fetch_openf1_overtakes")
    sessions = [
        {
            "session_type": "Race", "session_name": "Race",
            "date_start": f"2026-0{round_num}-01", "meeting_key": round_num,
            "session_key": round_num * 100,
        }
        for round_num in range(1, 7)
    ]
    sessions.append({"session_type": "Race", "session_name": "Sprint",
                     "date_start": "2026-06-01", "meeting_key": 6, "session_key": 601})
    monkeypatch.setattr(openf1, "get_sessions", lambda year: sessions)

    assert openf1.get_session_key(2026, 6, "Race") == 600
    assert openf1.get_session_key(2026, 6, "Sprint") == 601
