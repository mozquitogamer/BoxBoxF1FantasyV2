"""
Audit log — append-only history of every prediction event.

Two complementary outputs, both tracked in git so they survive across machines:

  data/audit/predictions_log.jsonl
    One JSON object per line, slim event summary. Grep-friendly:
      jq 'select(.round==3 and .phase=="post_fp")' data/audit/predictions_log.jsonl
    Includes timestamp, round, phase, model hash, MAE vs actuals (if known),
    git commit, and the path to the corresponding full snapshot.

  data/audit/snapshots/round{N}/{ISO-timestamp}_{phase}.json
    Full prediction JSON snapshot per event. Filename is timestamped so it
    is never overwritten. Use as a recovery source if a canonical archive
    is lost/corrupted.

Append semantics are enforced by:
  - JSONL log: open in append mode ('a'), never truncate
  - Snapshot files: unique timestamped filenames, never reused

This is INTENTIONALLY separate from web/public/data/predictions_round*.json.
The web archives are what the frontend reads; the audit log is the immutable
record of what the pipeline produced and when. They can diverge over time
(e.g. when a phase archive is overwritten by a later phase run) — the audit
log keeps both states.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Resolve project root relative to this file so the module works regardless
# of CWD when scripts call it.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
AUDIT_DIR = _PROJECT_ROOT / "data" / "audit"
LOG_PATH = AUDIT_DIR / "predictions_log.jsonl"
SNAPSHOTS_DIR = AUDIT_DIR / "snapshots"


def _git_head_sha() -> str | None:
    """Return current git HEAD short SHA, or None if unavailable."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(_PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def _safe_iso(dt: datetime | None = None) -> str:
    if dt is None:
        dt = datetime.now(timezone.utc)
    # Filename-safe ISO: replace ':' with '-' and drop microseconds for tidiness
    return dt.strftime("%Y-%m-%dT%H-%M-%SZ")


def _compute_pos_mae(predictions: dict[str, Any], actuals: dict[str, Any]) -> tuple[float | None, int]:
    """Compute race-position MAE between a predictions dict and an actuals dict.

    Returns (mae, n_compared). Returns (None, 0) if no comparisons possible.
    Used purely to attach a quick sanity check to each audit entry.
    """
    pred_map = {d.get("driver_id"): d for d in predictions.get("drivers", []) if d.get("driver_id")}
    act_map = {d.get("driver_id"): d for d in actuals.get("drivers", []) if d.get("driver_id")}
    errs: list[float] = []
    for abbrev, p in pred_map.items():
        a = act_map.get(abbrev)
        if not a:
            continue
        pr = p.get("predicted_finish")
        ar = a.get("race_position")
        if pr is None or ar is None:
            continue
        try:
            errs.append(abs(int(pr) - int(ar)))
        except (TypeError, ValueError):
            continue
    if not errs:
        return (None, 0)
    return (sum(errs) / len(errs), len(errs))


def record_prediction_event(
    *,
    round_num: int,
    phase: str,
    predictions_json: dict[str, Any],
    prediction_metadata: dict[str, Any] | None = None,
    actuals_json: dict[str, Any] | None = None,
    event_label: str | None = None,
) -> dict[str, str]:
    """Append a slim entry to predictions_log.jsonl AND write a full snapshot.

    Args:
        round_num: Race round number.
        phase: One of 'pre_fp' | 'post_fp' | 'post_quali'.
        predictions_json: The full predictions payload (as exported to web).
        prediction_metadata: The contents of prediction_metadata.json sidecar
            (model hashes, flags, etc.). Optional but recommended.
        actuals_json: Optional actual_round{N}.json contents. If provided,
            race-position MAE is computed and included in the log entry.
        event_label: Free-form note (e.g. 'recovery', 'manual_rerun'). Stored
            in the log; useful for filtering later.

    Returns:
        {'log_entry_ts': '...', 'snapshot_path': '/path/to/snapshot.json'}
    """
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    snapshot_dir = SNAPSHOTS_DIR / f"round{round_num}"
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    ts_iso = _safe_iso()
    ts_pretty = datetime.now(timezone.utc).isoformat()

    # 1) Full snapshot: timestamped filename, never overwritten
    snapshot_name = f"{ts_iso}_{phase}.json"
    snapshot_path = snapshot_dir / snapshot_name
    snapshot_payload = {
        "audit_timestamp": ts_pretty,
        "round": round_num,
        "phase": phase,
        "event_label": event_label,
        "prediction_metadata": prediction_metadata or {},
        "git_head": _git_head_sha(),
        "predictions": predictions_json,
    }
    # Defensive — if the file somehow already exists (clock skew?), suffix it.
    if snapshot_path.exists():
        snapshot_path = snapshot_dir / f"{ts_iso}_{phase}__dup-{datetime.now().microsecond}.json"
    with open(snapshot_path, "w") as f:
        json.dump(snapshot_payload, f, indent=2)

    # 2) Slim log entry: one line per event, append-only
    mae, n_compared = (None, 0)
    if actuals_json:
        mae, n_compared = _compute_pos_mae(predictions_json, actuals_json)

    log_entry = {
        "ts": ts_pretty,
        "round": round_num,
        "phase": phase,
        "event_label": event_label,
        "reconstructed": predictions_json.get("reconstructed", False),
        "n_drivers": len(predictions_json.get("drivers", [])),
        "n_constructors": len(predictions_json.get("constructors", [])),
        "race_pos_mae": round(mae, 3) if mae is not None else None,
        "race_pos_mae_n": n_compared,
        "git_head": _git_head_sha(),
        "model_hash_quali": (prediction_metadata or {}).get("quali_model_sha256_16"),
        "model_hash_race": (prediction_metadata or {}).get("race_model_sha256_16"),
        "race_model_used": (prediction_metadata or {}).get("race_model_used"),
        "snapshot": str(snapshot_path.relative_to(_PROJECT_ROOT)).replace("\\", "/"),
    }
    with open(LOG_PATH, "a") as f:
        f.write(json.dumps(log_entry) + "\n")

    return {
        "log_entry_ts": ts_pretty,
        "snapshot_path": str(snapshot_path),
    }


def load_prediction_metadata(round_num: int) -> dict[str, Any] | None:
    """Load the prediction_metadata.json sidecar for a round, if it exists."""
    path = _PROJECT_ROOT / "data" / "predictions" / f"round{round_num}" / "prediction_metadata.json"
    if not path.exists():
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def load_actuals(round_num: int) -> dict[str, Any] | None:
    """Load actual_round{N}.json from the web data dir, if present."""
    path = _PROJECT_ROOT / "web" / "public" / "data" / f"actual_round{round_num}.json"
    if not path.exists():
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None
