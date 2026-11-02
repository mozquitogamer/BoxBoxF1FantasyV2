"""Apply documented classification corrections while preserving raw API files."""
import copy
import json
from pathlib import Path

from config.settings import SEED_DIR


def load_result_json(path):
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    # Jolpica introduced a different ID for the reserve's race debut.
    # Keep the model identity used by his practice and qualifying evidence.
    def normalize(value):
        if isinstance(value, dict):
            return {key: ("hirakawa" if key == "driverId" and item == "ryo_hirakawa"
                          else normalize(item)) for key, item in value.items()}
        if isinstance(value, list):
            return [normalize(item) for item in value]
        return value
    data = normalize(data)
    if path.name == "qualifying.json" and path.parent.name.startswith("round"):
        from config.post_quali import load_post_quali_results
        for race in data.get("MRData", {}).get("RaceTable", {}).get("Races", []):
            official = load_post_quali_results(
                int(path.parent.name.removeprefix("round")), int(race["season"])
            ).get("drivers", {})
            if official:
                rows = race.get("QualifyingResults", [])
                if {row["Driver"]["driverId"] for row in rows} != set(official):
                    raise ValueError("Official qualifying correction must cover the full field")
                for row in rows:
                    result = official[row["Driver"]["driverId"]]
                    row["position"] = str(result["position"])
                    if result.get("status") == "DSQ":
                        for segment in ("Q1", "Q2", "Q3"):
                            row[segment] = ""
                rows.sort(key=lambda row: int(row["position"]))
    overrides_path = SEED_DIR / "race_result_overrides.json"
    if path.name != "results.json" or not overrides_path.exists():
        return data
    overrides = json.loads(overrides_path.read_text(encoding="utf-8"))
    for race in data.get("MRData", {}).get("RaceTable", {}).get("Races", []):
        key = f"{race.get('season')}:{path.parent.name.removeprefix('round')}"
        correction = overrides.get(key)
        if not correction:
            continue
        if race.get("date") != correction["date"]:
            raise ValueError("Official classification correction has the wrong event date")
        rows = {row["Driver"]["driverId"]: row for row in race["Results"]}
        if set(rows) != set(correction["order"]):
            raise ValueError("Official classification correction must cover exactly the full field")
        points = [25, 18, 15, 12, 10, 8, 6, 4, 2, 1]
        ordered = []
        for position, driver in enumerate(correction["order"], 1):
            row = copy.deepcopy(rows[driver])
            row["position"] = str(position)
            row["positionText"] = str(position) if row.get("status") == "Finished" else row.get("positionText")
            row["points"] = str(points[position - 1] if position <= 10 else 0)
            if driver in correction.get("times", {}):
                row["Time"] = {"time": correction["times"][driver]}
            ordered.append(row)
        race["Results"] = ordered
        race["classification_source"] = correction["source"]
    return data
