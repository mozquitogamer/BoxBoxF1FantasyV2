"""
One-shot script: backfill the audit log with all existing prediction archives
in web/public/data/. Run once after introducing the audit system so we have
historical entries for rounds that were predicted before the audit hook existed.

Usage:
    python pipeline/backfill_audit.py
"""

import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.audit import record_prediction_event, load_actuals


WEB_DATA_DIR = PROJECT_ROOT / "web" / "public" / "data"


def main() -> None:
    # Find all per-round archives. Two patterns:
    #   predictions_round{N}.json          (canonical)
    #   predictions_round{N}_{phase}.json  (phase-tagged)
    canonical_re = re.compile(r"^predictions_round(\d+)\.json$")
    phase_re = re.compile(r"^predictions_round(\d+)_(pre_fp|post_fp|post_quali)\.json$")

    entries: list[tuple[int, str, Path, str]] = []  # (round, phase, path, kind)

    for p in sorted(WEB_DATA_DIR.iterdir()):
        if not p.is_file() or not p.name.endswith(".json"):
            continue
        m_phase = phase_re.match(p.name)
        if m_phase:
            entries.append((int(m_phase.group(1)), m_phase.group(2), p, "phase"))
            continue
        m_canon = canonical_re.match(p.name)
        if m_canon:
            entries.append((int(m_canon.group(1)), "unknown", p, "canonical"))
            continue

    print(f"Found {len(entries)} archive files to backfill")

    # Order: phase archives first (more specific), canonical last per round.
    entries.sort(key=lambda t: (t[0], 0 if t[3] == "phase" else 1))

    backfilled = 0
    for round_num, phase, path, kind in entries:
        try:
            with open(path) as f:
                predictions = json.load(f)
        except Exception as e:
            print(f"  SKIP {path.name}: parse error {e}")
            continue

        # If canonical archive has a phase tag in its JSON, use it; else mark as 'canonical'
        if kind == "canonical":
            tag = predictions.get("phase") or "canonical_untagged"
        else:
            tag = phase

        actuals = load_actuals(round_num)

        result = record_prediction_event(
            round_num=round_num,
            phase=tag,
            predictions_json=predictions,
            prediction_metadata=None,  # No sidecar history available for backfill
            actuals_json=actuals,
            event_label=f"backfill:{path.name}",
        )
        mae_note = ""
        if actuals:
            from pipeline.audit import _compute_pos_mae
            mae, n = _compute_pos_mae(predictions, actuals)
            if mae is not None:
                mae_note = f" | MAE {mae:.2f} ({n} drivers)"
        rec = " [recon]" if predictions.get("reconstructed") else ""
        print(f"  R{round_num} {tag:<24}  -> {Path(result['snapshot_path']).name}{rec}{mae_note}")
        backfilled += 1

    print(f"\nBackfilled {backfilled} archive(s)")


if __name__ == "__main__":
    main()
