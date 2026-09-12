import json
import os
import time
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable
from urllib.request import Request, urlopen

from dotenv import load_dotenv

from .providers.football_data import FootballDataCsvAdapter
from .providers.identity import FixtureIdentity, identity_to_dict, resolve_fixture_identity, resolve_fixture_records
from .providers.models import FixtureRecord, RawSnapshot
from .providers.quality import IngestionQualityPolicy, validate_ingestion_quality
from .providers.raw_store import FileRawSnapshotStore

DEFAULT_BASE_URL = "https://www.football-data.co.uk"
DEFAULT_LEAGUE = "E0"
DEFAULT_SEASON = "2526"
DEFAULT_INTERVAL_SECONDS = 86_400
DEFAULT_MAX_SNAPSHOT_AGE_DAYS = 7


def football_data_url(base_url: str, league: str, season: str) -> str:
    clean_base = base_url.rstrip("/")
    clean_league = league.strip().upper()
    clean_season = season.strip()
    if not clean_league or not clean_season:
        raise ValueError("Football-Data league and season are required")
    if "/mmz" in clean_base:
        return f"{clean_base}/{clean_season}/{clean_league}.csv"
    return f"{clean_base}/mmz4281/{clean_season}/{clean_league}.csv"


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
    audit: dict[str, object] | None = None,
    identities: dict[str, FixtureIdentity] | None = None,
    quality_audit: dict[str, object] | None = None,
) -> Path:
    directory = Path(root) / "normalized" / "football-data.co.uk" / written_at.strftime("%Y-%m-%d")
    directory.mkdir(parents=True, exist_ok=True)
    manifest_path = directory / f"{written_at.strftime('%H%M%S')}-{snapshot.sha256[:16]}.json"
    fixture_payloads = []
    for record in records:
        serialized = asdict(record)
        serialized["match_start_at"] = record.match_start_at.isoformat()
        serialized["retrieved_at"] = record.retrieved_at.isoformat()
        serialized["observed_at"] = record.observed_at.isoformat() if record.observed_at else None
        fixture_id = resolve_fixture_identity(record, season).canonical_fixture_id
        identity = identities.get(fixture_id) if identities else None
        if identity is None:
            raise ValueError("Fixture identity is required before writing a normalized manifest")
        serialized.update(identity_to_dict(identity))
        fixture_payloads.append(serialized)
    payload = {
        "provider": "football-data.co.uk",
        "league": league,
        "season": season,
        "source_url": source_url,
        "retrieved_at": snapshot.retrieved_at.isoformat(),
        "raw_snapshot_sha256": snapshot.sha256,
        "raw_snapshot_path": snapshot.payload_path,
        "record_count": len(fixture_payloads),
        "fixtures": fixture_payloads,
        "identity_validation": audit or {},
        "quality_validation": quality_audit or {},
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
        quality_policy: IngestionQualityPolicy | None = None,
        quality_reference_clock: Callable[[], datetime] | None = None,
    ):
        self.raw_root = Path(raw_root)
        self.base_url = base_url
        self.league = league.strip().upper()
        self.season = season.strip()
        self.downloader = downloader
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.quality_policy = quality_policy or IngestionQualityPolicy()
        self.quality_reference_clock = quality_reference_clock

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
        records = FootballDataCsvAdapter().parse(payload, retrieved_at, self.league, self.season)
        if not records:
            raise ValueError("Football-Data payload contained no dated fixtures")
        quality_audit = validate_ingestion_quality(
            records,
            snapshot_retrieved_at=retrieved_at,
            reference_at=self.quality_reference_clock() if self.quality_reference_clock else retrieved_at,
            policy=self.quality_policy,
        )
        normalized_records, audit, identities = resolve_fixture_records(
            records,
            self.season,
            previous_manifests=self._existing_manifests(),
        )
        return write_normalized_manifest(
            self.raw_root,
            self.league,
            self.season,
            source_url,
            snapshot,
            normalized_records,
            retrieved_at,
            audit,
            identities,
            quality_audit,
        )

    def _existing_manifests(self) -> list[dict[str, object]]:
        directory = self.raw_root / "normalized" / "football-data.co.uk"
        if not directory.exists():
            return []
        manifests: list[dict[str, object]] = []
        for path in sorted(directory.rglob("*.json")):
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, ValueError) as exc:
                raise ValueError(f"Unable to read existing normalized manifest: {path}") from exc
            if not isinstance(value, dict) or not isinstance(value.get("fixtures", []), list):
                raise ValueError(f"Invalid normalized manifest shape: {path}")
            manifests.append(value)
        return manifests


def run_scheduler(job: FootballDataIngestionJob, interval_seconds: int = DEFAULT_INTERVAL_SECONDS) -> None:
    if interval_seconds <= 0:
        raise ValueError("Ingestion interval must be greater than zero")
    while True:
        job.run_once()
        time.sleep(interval_seconds)


def job_from_environment() -> FootballDataIngestionJob:
    load_dotenv()
    max_age_days = float(os.getenv("INGESTION_MAX_SNAPSHOT_AGE_DAYS", str(DEFAULT_MAX_SNAPSHOT_AGE_DAYS)))
    missing_fraction_value = os.getenv("INGESTION_MAX_OPTIONAL_MISSING_FRACTION", "").strip()
    missing_fraction = float(missing_fraction_value) if missing_fraction_value else None
    return FootballDataIngestionJob(
        raw_root=os.getenv("RAW_DATA_ROOT", "data/raw"),
        base_url=os.getenv("FOOTBALL_DATA_BASE_URL", DEFAULT_BASE_URL),
        league=os.getenv("FOOTBALL_DATA_LEAGUE", DEFAULT_LEAGUE),
        season=os.getenv("FOOTBALL_DATA_SEASON", DEFAULT_SEASON),
        quality_policy=IngestionQualityPolicy(
            max_snapshot_age=timedelta(days=max_age_days),
            max_optional_missing_fraction=missing_fraction,
        ),
    )
