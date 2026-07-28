"""Freeze and verify prospective prediction evidence by round and phase."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import CURRENT_SEASON, DATA_DIR, PROJECT_ROOT, WEB_DATA_DIR


HOLDOUT_DIR = DATA_DIR / "evaluation" / "prospective"
VALID_PHASES = ("pre_fp", "post_fp", "post_quali")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def manifest_path(round_num: int, phase: str, season: int) -> Path:
    return (
        HOLDOUT_DIR
        / f"year{season}"
        / f"round{round_num}"
        / f"{phase}_manifest.json"
    )


def freeze_phase_archive(
    archive_path: Path,
    round_num: int,
    phase: str,
    prediction_metadata: dict | None = None,
) -> Path:
    """Register a non-reconstructed frozen phase archive as a holdout."""
    if phase not in VALID_PHASES:
        raise ValueError(f"Invalid holdout phase: {phase!r}")
    with open(archive_path) as f:
        archive = json.load(f)
    if int(archive.get("round", -1)) != int(round_num):
        raise ValueError("Archive round does not match requested holdout")
    if archive.get("phase") != phase:
        raise ValueError("Archive phase does not match requested holdout")
    if archive.get("reconstructed", False):
        raise ValueError("Reconstructed forecasts cannot be prospective holdouts")

    season = int(archive.get("season", CURRENT_SEASON))
    path = manifest_path(round_num, phase, season)
    digest = _sha256(archive_path)
    if path.exists():
        with open(path) as f:
            existing = json.load(f)
        if existing.get("archive_sha256") != digest:
            raise RuntimeError(
                f"Frozen holdout changed after registration: {archive_path}"
            )
        return path

    metadata = prediction_metadata or {}
    weather = metadata.get("weather_features_used") or {}
    try:
        source = str(archive_path.relative_to(PROJECT_ROOT)).replace("\\", "/")
    except ValueError:
        source = str(archive_path)
    payload = {
        "schema_version": 1,
        "season": season,
        "round": int(round_num),
        "phase": phase,
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "archive_source": source,
        "archive_sha256": digest,
        "archive_exported_at": archive.get("exported_at"),
        "archive_generated_at": archive.get("generated_at"),
        "reconstructed": False,
        "model_identity": {
            "quali_model_sha256_16": metadata.get("quali_model_sha256_16"),
            "race_model_sha256_16": metadata.get("race_model_sha256_16"),
            "race_model_used": metadata.get("race_model_used"),
            "race_model_algorithm": metadata.get("race_model_algorithm"),
        },
        "weather_snapshot": {
            "snapshot_id": weather.get("forecast_snapshot_id"),
            "retrieved_at": weather.get("forecast_retrieved_at"),
            "archive_path": weather.get("forecast_archive_path"),
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "x") as f:
        json.dump(payload, f, indent=2)
    return path


def verify_phase_holdout(round_num: int, phase: str, season: int) -> bool:
    path = manifest_path(round_num, phase, season)
    if not path.exists():
        return False
    with open(path) as f:
        manifest = json.load(f)
    archive = PROJECT_ROOT / manifest["archive_source"]
    return archive.exists() and _sha256(archive) == manifest["archive_sha256"]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Freeze or verify a prospective prediction holdout"
    )
    parser.add_argument("--round", type=int, required=True)
    parser.add_argument("--phase", choices=VALID_PHASES, required=True)
    parser.add_argument("--season", type=int, default=CURRENT_SEASON)
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify an existing manifest instead of registering the archive",
    )
    args = parser.parse_args()

    if args.verify:
        ok = verify_phase_holdout(args.round, args.phase, args.season)
        print("OK" if ok else "MISSING OR CHANGED")
        raise SystemExit(0 if ok else 1)

    archive = (
        WEB_DATA_DIR
        / f"predictions_round{args.round}_{args.phase}.json"
    )
    metadata_path = (
        DATA_DIR
        / "predictions"
        / f"round{args.round}"
        / "prediction_metadata.json"
    )
    metadata = None
    if metadata_path.exists():
        with open(metadata_path) as f:
            metadata = json.load(f)
    path = freeze_phase_archive(
        archive,
        args.round,
        args.phase,
        prediction_metadata=metadata,
    )
    print(f"Frozen holdout -> {path}")


if __name__ == "__main__":
    main()
