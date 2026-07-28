"""Report circuit-vector similarity saturation without changing model inputs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.track_similarity import similarity_diagnostics


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit track-vector cosine similarity saturation"
    )
    parser.add_argument("--threshold", type=float, default=0.95)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    result = similarity_diagnostics(args.threshold)
    print(json.dumps(result, indent=2))
    if result["is_saturated"]:
        print(
            "\nWARNING: circuit vectors are saturated; validate a redesigned "
            "transform by prequential ablation before replacing production."
        )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
