from __future__ import annotations

import argparse
import logging

from app.services.review_task_worker import run_worker_forever


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SmartReview review task worker")
    parser.add_argument("--poll-interval", type=float, default=2.0, help="Pending queue polling interval (seconds)")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    run_worker_forever(
        poll_interval_seconds=args.poll_interval,
    )


if __name__ == "__main__":
    main()
