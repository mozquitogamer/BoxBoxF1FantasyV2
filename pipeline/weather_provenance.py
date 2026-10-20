"""Fail before publishing a simulation that combines different weather inputs."""
from datetime import datetime


def validate_simulation_weather(metadata: dict, weather: dict) -> None:
    inference = metadata.get("weather_features_used") or {}
    inferred_source = inference.get("source")
    simulated_source = weather.get("source")
    if not inferred_source or not simulated_source or inferred_source != simulated_source:
        raise ValueError("Prediction and simulation weather versions do not match. Refresh weather, then rerun 06, 07 and 08 before exporting.")
    try:
        recorded_at = datetime.fromisoformat(inferred_source.replace("Z", "+00:00"))
        if recorded_at.tzinfo is None:
            raise ValueError("Weather timestamp must include its timezone.")
    except (ValueError, AttributeError) as exc:
        raise ValueError("Weather source timestamp is missing or invalid. Refresh weather and rerun predictions.") from exc
    inferred_snapshot = inference.get("forecast_snapshot_id")
    simulated_snapshot = weather.get("forecast_snapshot_id")
    if inferred_snapshot and simulated_snapshot and inferred_snapshot != simulated_snapshot:
        raise ValueError("Weather snapshot changed after prediction. Rerun 06, 07 and 08 before exporting.")
    inferred_round = inference.get("weather_round")
    simulated_round = weather.get("round")
    if inferred_round is not None and simulated_round is not None and int(inferred_round) != int(simulated_round):
        raise ValueError("Prediction and simulation weather rounds do not match.")
