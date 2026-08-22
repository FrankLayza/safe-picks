from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class ProviderMetadata:
    provider: str
    role: str
    coverage: tuple[str, ...]
    license_status: str
    rate_limit_policy: str
    retention_policy: str
    permitted_for_public_redistribution: bool = False


@dataclass(frozen=True)
class RawSnapshot:
    provider: str
    source_uri: str
    retrieved_at: datetime
    payload: bytes
    content_type: str
    sha256: str
    payload_path: str | None = None
    metadata_path: str | None = None


@dataclass(frozen=True)
class FixtureRecord:
    provider: str
    source_event_id: str
    home_team: str
    away_team: str
    match_start_at: datetime
    retrieved_at: datetime
    observed_at: datetime | None = None
    competition: str | None = None
    season: str | None = None
    home_goals: int | None = None
    away_goals: int | None = None
    half_time_home_goals: int | None = None
    half_time_away_goals: int | None = None
    home_corners: int | None = None
    away_corners: int | None = None
    home_shots: int | None = None
    away_shots: int | None = None
    home_shots_on_target: int | None = None
    away_shots_on_target: int | None = None


@dataclass(frozen=True)
class OddsQuote:
    provider: str
    source_event_id: str
    bookmaker: str
    market: str
    selection: str
    odds: float
    match_start_at: datetime
    retrieved_at: datetime
    observed_at: datetime | None = None
    line: float | None = None
    canonical_market_id: str | None = None
    canonical_market: str | None = None
    canonical_selection: str | None = None
    canonical_line: str | None = None


def parse_datetime(value: str) -> datetime:
    normalized = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError("Timestamp must include a timezone")
    return parsed


def to_int(value: Any) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    return int(float(str(value).strip()))
