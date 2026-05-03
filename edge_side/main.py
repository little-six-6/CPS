"""Entry point for the edge-side application."""

from __future__ import annotations

import argparse
from typing import Optional

from core.pipeline import EdgePipeline
from utils.constants import DEFAULT_INTERVAL_SECONDS, DEFAULT_MAX_ITERATIONS


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the edge-side pipeline.")
    parser.add_argument(
        "--iterations",
        type=int,
        default=DEFAULT_MAX_ITERATIONS,
        help="Number of cycles to run. Use 0 for infinite loop.",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=DEFAULT_INTERVAL_SECONDS,
        help="Sleep interval between pipeline steps.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pipeline = EdgePipeline()
    iterations: Optional[int] = None if args.iterations == 0 else args.iterations
    stats = pipeline.run(iterations=iterations, interval=args.interval)
    print(
        f"edge pipeline finished: frames={stats.frames}, alerts={stats.alerts}, errors={stats.errors}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
