"""
One-shot: write prediction_metadata.json sidecars for rounds whose parquets
predate the sidecar mechanism. Without a sidecar, 08_export_website_json
falls back to data-state inference for phase detection, which can mis-label
old predictions (e.g. labeling R6's pre-main-quali prediction as "post_quali"
just because quali data exists now).

This script inspects each round's predictions.parquet + raw data state and
writes a best-effort sidecar that captures the phase that prediction
represents. Mark as backfilled with a flag.

Usage:
    python pipeline/backfill_sidecars.py [--round N]
"""

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd

from config.settings import (
    PREDICTIONS_DIR,
    FEATURES_DIR,
    RAW_DIR,
    TRAINED_DIR,
    CURRENT_SEASON,
    CANCELLED_ROUNDS_2026,
)


def _file_sha256_16(p: Path) -> str | None:
    try:
        with open(p, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()[:16]
    except Exception:
        return None


def write_sidecar_for_round(round_num: int, year: int = CURRENT_SEASON) -> str | None:
    pred_dir = PREDICTIONS_DIR / f"round{round_num}"
    pred_path = pred_dir / "predictions.parquet"
    if not pred_path.exists():
        return None

    # Determine state at the time the prediction was last made. The simplest
    # signal is `predicted_quali_position` in the parquet vs jolpica actual
    # quali — but the model regenerates quali predictions every run regardless,
    # so that's not a reliable signal of "used actual quali at predict time".
    #
    # Instead: detect by file-existence (best-effort backfill). This can
    # mis-label edge cases but is correct for the common path:
    #   - FP features exist for round N AND jolpica quali exists -> post_quali
    #     UNLESS we know the prediction was made before quali. We can't tell
    #     that from current state alone, so we default to post_quali here.
    #   - FP features exist, no quali -> post_fp
    #   - No FP features -> pre_fp

    # Special-case overrides for rounds we know the truth about. These are
    # hand-curated from inspection of when the parquets were last written and
    # what the recovery script's last 06_run_predictions invocation did.
    KNOWN_PHASES = {
        # R1/R2/R3 had polluted archives that were rebuilt by recover_archives.py
        # on 2026-05-16. The script's LAST 06 run for each was --no-fp (pre_fp),
        # so the parquets currently on disk reflect pre_fp state.
        1: "pre_fp",
        2: "pre_fp",
        3: "pre_fp",
        # Round 6 (Miami sprint weekend, race May 3): fantasy_points.parquet
        # was written May 2 09:05 — after sprint qualifying but before main
        # qualifying (which was Sat afternoon). So phase=post_fp.
        6: "post_fp",
    }
    if round_num in KNOWN_PHASES:
        resolved_phase = KNOWN_PHASES[round_num]
    else:
        fp_features = FEATURES_DIR / f"round{round_num}" / "features.parquet"
        quali_path = RAW_DIR / "jolpica" / f"year{year}" / f"round{round_num}" / "qualifying.json"
        has_fp = fp_features.exists()

        has_actual_quali = False
        if quali_path.exists():
            try:
                with open(quali_path) as f:
                    qd = json.load(f)
                races = qd.get("MRData", {}).get("RaceTable", {}).get("Races", [])
                has_actual_quali = bool(races and races[0].get("QualifyingResults"))
            except Exception:
                pass

        if has_actual_quali and has_fp:
            resolved_phase = "post_quali"
        elif has_fp:
            resolved_phase = "post_fp"
        else:
            resolved_phase = "pre_fp"

    # Capture model hashes from the model files currently on disk. NOTE: these
    # are the CURRENT models, not necessarily the ones that produced the
    # parquet. Flag as backfilled so future readers understand.
    quali_model_path = TRAINED_DIR / "quali_model.json"
    race_model_path = TRAINED_DIR / "race_model.json"
    race_model_fp_path = TRAINED_DIR / "race_model_fp.json"
    race_model_used = race_model_fp_path if (resolved_phase != "post_quali" and race_model_fp_path.exists()) else race_model_path

    sidecar = {
        "round": round_num,
        "year": year,
        "phase": resolved_phase,
        "generated_at": None,  # unknown — pre-sidecar prediction
        "backfilled_at": datetime.now(timezone.utc).isoformat(),
        "backfilled": True,
        "is_post_quali": resolved_phase == "post_quali",
        "used_fp_features": resolved_phase in ("post_fp", "post_quali"),
        "skip_fp_flag": False,
        "force_flag": None,
        "race_model_used": race_model_used.name if race_model_used else None,
        "quali_model_sha256_16": _file_sha256_16(quali_model_path),
        "race_model_sha256_16": _file_sha256_16(race_model_used) if race_model_used else None,
        "note": "Backfilled sidecar — model hashes reflect models currently on disk, not necessarily the ones that produced predictions.parquet.",
    }

    out_path = pred_dir / "prediction_metadata.json"
    if out_path.exists():
        print(f"  R{round_num}: sidecar already exists, skipping")
        return None
    with open(out_path, "w") as f:
        json.dump(sidecar, f, indent=2)
    return resolved_phase


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill prediction_metadata.json sidecars")
    parser.add_argument("--round", type=int, default=None,
                        help="Single round to backfill. If omitted, backfills all rounds with predictions.")
    args = parser.parse_args()

    if args.round is not None:
        rounds = [args.round]
    else:
        rounds = []
        for d in sorted(PREDICTIONS_DIR.iterdir()):
            if not d.is_dir():
                continue
            m = d.name
            if m.startswith("round") and m[5:].isdigit():
                rn = int(m[5:])
                if rn not in CANCELLED_ROUNDS_2026:
                    rounds.append(rn)

    print(f"Backfilling sidecars for rounds: {rounds}")
    for rn in rounds:
        phase = write_sidecar_for_round(rn)
        if phase:
            print(f"  R{rn}: wrote sidecar (phase={phase})")
        else:
            print(f"  R{rn}: no sidecar written")


if __name__ == "__main__":
    main()
