import argparse

from .ingestion import DEFAULT_INTERVAL_SECONDS, job_from_environment, run_scheduler


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest one Football-Data.co.uk league CSV")
    parser.add_argument("--once", action="store_true", help="Run one download and exit")
    parser.add_argument("--interval-seconds", type=int, default=DEFAULT_INTERVAL_SECONDS)
    args = parser.parse_args()
    job = job_from_environment()
    if args.once:
        print(job.run_once())
        return
    run_scheduler(job, args.interval_seconds)


if __name__ == "__main__":
    main()
