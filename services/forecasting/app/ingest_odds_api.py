import argparse
import os

from .odds_ingestion import (
    DEFAULT_ODDS_INTERVAL_SECONDS,
    odds_job_from_environment,
    run_odds_scheduler,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest current football odds")
    parser.add_argument("--once", action="store_true", help="Run one download and exit")
    parser.add_argument(
        "--interval-seconds",
        type=int,
        default=int(
            os.getenv(
                "ODDS_API_INGESTION_INTERVAL_SECONDS",
                str(DEFAULT_ODDS_INTERVAL_SECONDS),
            )
        ),
    )
    args = parser.parse_args()
    job = odds_job_from_environment()
    if args.once:
        print(job.run_once())
        return
    run_odds_scheduler(job, args.interval_seconds)


if __name__ == "__main__":
    main()
