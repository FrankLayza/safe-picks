import json
import os
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from urllib.request import Request, urlopen

from dotenv import load_dotenv

from .providers.football_data import FootballDataCsvAdapter
from .providers.models import FixtureRecord, RawSnapshot
from .providers.raw_store import FileRawSnapshotStore

DEFAULT_BASE_URL = "https://www.football-data.co.uk"
DEFAULT_LEAGUE = "E0"
DEFAULT_SEASON = "2526"
DEFAULT_INTERVAL_SECONDS = 86_400


def football_data_url(base_url: str, league: str, season: str) -> str:
    clean_base = base_url.rstrip("/")
    clean_league = league.strip().upper()
    clean_season = season.strip()
    if not clean_league or not clean_season:
        raise ValueError("Football-Data league and season are required")
    return f"{clean_base}/mmz{clean_season}/{clean_season}/{clean_league}.csv"


def download_csv(url: str, timeout_seconds: int = 30) -> tuple[bytes, str]:
    request = Request(url, headers={"Accept": "text/csv", "User-Agent": "Safe-Picks/0.1"})
    with urlopen(request, timeout=timeout_seconds) as response:
        status = getattr(response, "status", 200)
        if status != 200:
            raise RuntimeError(f"Football-Data download failed with HTTP {status}")
        content_type = response.headers.get_content_type() if response.headers else "text/csv"
        return response.read(), content_type


def write_normalized_manifest(
    root: str | Path,
    league: str,
    season: str,
    source_url: str,
    snapshot: RawSnapshot,
    records: list[FixtureRecord],
    written_at: datetime,
) -> Path:
    directory = Path(root) / "normalized" / "football-data.co.uk" / written_at.strftime("%Y-%m-%d")
    directory.mkdir(parents=True, exist_ok=True)
    manifest_path = directory / f"{written_at.strftime('%H%M%S')}-{snapshot.sha256[:16]}.json"
    payload = {
        "provider": "football-data.co.uk",
        "league": league,
        "season": season,
        "source_url": source_url,
        "retrieved_at": snapshot.retrieved_at.isoformat(),
        "raw_snapshot_sha256": snapshot.sha256,
        "raw_snapshot_path": snapshot.payload_path,
        "record_count": len(records),
        "fixtures": [
            {
                **asdict(record),
                "match_start_at": record.match_start_at.isoformat(),
                "retrieved_at": record.retrieved_at.isoformat(),
                "observed_at": record.observed_at.isoformat() if record.observed_at else None,
            }
            for record in records
        ],
    }
    manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return manifest_path


class FootballDataIngestionJob:
    def __init__(
        self,
        raw_root: str | Path,
        base_url: str = DEFAULT_BASE_URL,
        league: str = DEFAULT_LEAGUE,
        season: str = DEFAULT_SEASON,
        downloader: Callable[[str], tuple[bytes, str]] = download_csv,
        clock: Callable[[], datetime] | None = None,
    ):
        self.raw_root = Path(raw_root)
        self.base_url = base_url
        self.league = league.strip().upper()
        self.season = season.strip()
        self.downloader = downloader
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def run_once(self) -> Path:
        retrieved_at = self.clock()
        source_url = football_data_url(self.base_url, self.league, self.season)
        payload, content_type = self.downloader(source_url)
        if not payload:
            raise ValueError("Football-Data returned an empty CSV payload")
        snapshot = FileRawSnapshotStore(self.raw_root).save(
            "football-data.co.uk",
            source_url,
            payload,
            content_type,
            retrieved_at,
        )
        records = FootballDataCsvAdapter().parse(payload, retrieved_at, self.league)
        if not records:
            raise ValueError("Football-Data payload contained no dated fixtures")
        return write_normalized_manifest(self.raw_root, self.league, self.season, source_url, snapshot, records, retrieved_at)


def run_scheduler(job: FootballDataIngestionJob, interval_seconds: int = DEFAULT_INTERVAL_SECONDS) -> None:
    if interval_seconds <= 0:
        raise ValueError("Ingestion interval must be greater than zero")
    while True:
        job.run_once()
        time.sleep(interval_seconds)


def job_from_environment() -> FootballDataIngestionJob:
    load_dotenv()
    return FootballDataIngestionJob(
        raw_root=os.getenv("RAW_DATA_ROOT", "data/raw"),
        base_url=os.getenv("FOOTBALL_DATA_BASE_URL", DEFAULT_BASE_URL),
        league=os.getenv("FOOTBALL_DATA_LEAGUE", DEFAULT_LEAGUE),
        season=os.getenv("FOOTBALL_DATA_SEASON", DEFAULT_SEASON),
    )
