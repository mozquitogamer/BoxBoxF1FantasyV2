"""Compatibility entry point for the phase-aware weekend pipeline.

Running this script without a phase keeps its historical post-FP behavior.
New commands should call pipeline/run_weekend.py directly.
"""

import sys

from pipeline.run_weekend import main as run_weekend


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if not any(arg == "--phase" or arg.startswith("--phase=") for arg in args):
        args = ["--phase", "post_fp", *args]
    return run_weekend(args)


if __name__ == "__main__":
    sys.exit(main())
