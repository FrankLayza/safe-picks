import json
import os
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterable

from dotenv import load_dotenv

from .providers.identity import (
    FixtureIdentity,
    identity_to_dict,
    normalize_identity_label,
    resolve_fixture_identity,
    resolve_team_id,
)
from .providers.models import FixtureRecord, OddsEvent, OddsQuote, RawSnapshot
from .providers.odds_api import OddsApiAdapter, OddsApiPayloadError, ParsedOddsSnapshot
from .providers.quality import IngestionQualityPolicy, IngestionValidationError, validate_ingestion_quality
from .providers.raw_store import FileRawSnapshotStore
from .replay import HistoricalManifestReplay, ReplayedFixture

DEFAULT_ODDS_BASE_URL = "https://api.the-odds-api.com/v4"
DEFAULT_ODDS_SPORT = "soccer_epl"
DEFAULT_ODDS_REGIONS = "eu"
DEFAULT_ODDS_MARKETS = "h2h,totals"
DEFAULT_ODDS_FORMAT = "decimal"
DEFAULT_ODDS_INTERVAL_SECONDS = 300
DEFAULT_ODDS_MAX_AGE_MINUTES = 15


@dataclass(frozen=True)
class OddsIngestionPolicy:
    max_snapshot_age: timedelta = timedelta(minutes=15)
    max_quote_age: timedelta = timedelta(minutes=15)
    supported_markets: tuple[str, ...] = ("match result", "total")

    def __post_init__(self) -> None:
        if self.max_snapshot_age.total_seconds() < 0:
            raise ValueError("max_snapshot_age cannot be negative")
        if self.max_quote_age.total_seconds() < 0:
            raise ValueError("max_quote_age cannot be negative")


@dataclass(frozen=True)
class MatchedOddsEvent:
    event: OddsEvent
    identity: FixtureIdentity
    historical_home_matches: int
    historical_away_matches: int


def event_record(event: OddsEvent) -> FixtureRecord:
    return FixtureRecord(
        provider=event.provider,
        source_event_id=event.source_event_id,
        home_team=event.home_team,
        away_team=event.away_team,
        match_start_at=event.match_start_at,
        retrieved_at=event.retrieved_at,
        competition=event.competition,
        season=event.season,
    )


def match_events_to_history(
    events: Iterable[OddsEvent],
    quotes: Iterable[OddsQuote],
    history: Iterable[ReplayedFixture],
    reference_at: datetime,
    policy: OddsIngestionPolicy,
) -> tuple[list[MatchedOddsEvent], list[OddsQuote], list[dict[str, object]]]:
    historical_counts: dict[str, dict[str, int]] = {}
    for item in history:
        if item.record.home_goals is None or item.record.away_goals is None:
            continue
        competition = historical_counts.setdefault(item.identity.canonical_competition_id, {})
        for team_id in (
            item.identity.canonical_home_team_id,
            item.identity.canonical_away_team_id,
        ):
            competition[team_id] = competition.get(team_id, 0) + 1

    event_values = list(events)
    source_counts: dict[str, int] = {}
    fixture_sources: dict[str, list[str]] = {}
    for event in event_values:
        source_counts[event.source_event_id] = source_counts.get(event.source_event_id, 0) + 1
        identity = resolve_fixture_identity(event_record(event), event.season)
        fixture_sources.setdefault(identity.canonical_fixture_id, []).append(
            event.source_event_id
        )

    quotes_by_event: dict[str, list[OddsQuote]] = {}
    for quote in quotes:
        quotes_by_event.setdefault(quote.source_event_id, []).append(quote)

    matched: list[MatchedOddsEvent] = []
    accepted_quotes: list[OddsQuote] = []
    rejections: list[dict[str, object]] = []
    for event in event_values:
        identity = resolve_fixture_identity(event_record(event), event.season)
        details = {"source_event_id": event.source_event_id}
        if event.match_start_at <= reference_at:
            rejections.append(_reason("odds_event_already_started", details))
            continue
        if source_counts[event.source_event_id] > 1:
            rejections.append(
                _reason(
                    "duplicate_source_event_id",
                    {
                        **details,
                        "occurrences": source_counts[event.source_event_id],
                    },
                )
            )
            continue
        if len(fixture_sources[identity.canonical_fixture_id]) > 1:
            rejections.append(
                _reason(
                    "ambiguous_canonical_fixture",
                    {
                        **details,
                        "canonical_fixture_id": identity.canonical_fixture_id,
                        "source_event_ids": fixture_sources[identity.canonical_fixture_id],
                    },
                )
            )
            continue
        competition = historical_counts.get(identity.canonical_competition_id)
        if competition is None:
            rejections.append(
                _reason(
                    "historical_competition_not_found",
                    {
                        **details,
                        "canonical_competition_id": identity.canonical_competition_id,
                    },
                )
            )
            continue
        home_matches = competition.get(identity.canonical_home_team_id, 0)
        away_matches = competition.get(identity.canonical_away_team_id, 0)
        missing_teams = []
        if home_matches == 0:
            missing_teams.append("home")
        if away_matches == 0:
            missing_teams.append("away")
        if missing_teams:
            rejections.append(
                _reason(
                    "historical_team_not_found",
                    {
                        **details,
                        "missing_sides": missing_teams,
                        "home_team": event.home_team,
                        "away_team": event.away_team,
                    },
                )
            )
            continue
        event_quotes, quote_rejections = _eligible_quotes(
            event,
            identity,
            quotes_by_event.get(event.source_event_id, []),
            reference_at,
            policy,
        )
        rejections.extend(quote_rejections)
        if not event_quotes:
            rejections.append(_reason("no_complete_current_market", details))
            continue
        matched.append(MatchedOddsEvent(event, identity, home_matches, away_matches))
        accepted_quotes.extend(event_quotes)
    return matched, accepted_quotes, rejections


def _eligible_quotes(
    event: OddsEvent,
    identity: FixtureIdentity,
    quotes: list[OddsQuote],
    reference_at: datetime,
    policy: OddsIngestionPolicy,
) -> tuple[list[OddsQuote], list[dict[str, object]]]:
    eligible: list[OddsQuote] = []
    rejections: list[dict[str, object]] = []
    for quote in quotes:
        details = {
            "source_event_id": event.source_event_id,
            "bookmaker": quote.bookmaker,
            "market": quote.canonical_market or quote.market,
            "selection": quote.selection,
        }
        if quote.observed_at is None:
            rejections.append(_reason("odds_quote_missing_timestamp", details))
            continue
        if quote.observed_at > reference_at:
            rejections.append(_reason("odds_quote_timestamp_in_future", details))
            continue
        age = reference_at - quote.observed_at
        if age > policy.max_quote_age:
            rejections.append(
                _reason(
                    "stale_odds_quote",
                    {**details, "age_seconds": age.total_seconds()},
                )
            )
            continue
        if quote.match_start_at != event.match_start_at:
            rejections.append(_reason("odds_quote_kickoff_mismatch", details))
            continue
        if quote.canonical_market not in policy.supported_markets:
            rejections.append(_reason("unsupported_odds_market", details))
            continue
        eligible.append(quote)

    grouped: dict[tuple[str, str, str], list[OddsQuote]] = {}
    for quote in eligible:
        key = (
            quote.bookmaker,
            quote.canonical_market or quote.market,
            quote.canonical_line or "none",
        )
        grouped.setdefault(key, []).append(quote)
    complete: list[OddsQuote] = []
    for (bookmaker, market, line), values in grouped.items():
        expected = 3 if market == "match result" else 2
        selections_valid = _market_selections_valid(market, values, identity)
        if len(values) != expected or not selections_valid:
            rejections.append(
                _reason(
                    "incomplete_market_group",
                    {
                        "source_event_id": event.source_event_id,
                        "bookmaker": bookmaker,
                        "market": market,
                        "line": line,
                        "quote_count": len(values),
                        "expected_quote_count": expected,
                        "selections_valid": selections_valid,
                    },
                )
            )
            continue
        complete.extend(values)
    return complete, rejections


def _market_selections_valid(
    market: str,
    quotes: list[OddsQuote],
    identity: FixtureIdentity,
) -> bool:
    if market == "match result":
        selections: set[str] = set()
        for quote in quotes:
            normalized = normalize_identity_label(quote.selection, "selection")
            if normalized == "draw":
                selections.add("draw")
                continue
            team_id = resolve_team_id(quote.provider, quote.selection)
            if team_id == identity.canonical_home_team_id:
                selections.add("home")
            elif team_id == identity.canonical_away_team_id:
                selections.add("away")
            else:
                selections.add("unknown")
        return selections == {"home", "draw", "away"}
    if market == "total":
        selections = {
            normalize_identity_label(quote.selection, "selection")
            for quote in quotes
        }
        return selections == {"over", "under"}
    return False


def write_odds_manifest(
    root: str | Path,
    source_url: str,
    snapshot: RawSnapshot,
    parsed: ParsedOddsSnapshot,
    matched_events: list[MatchedOddsEvent],
    quotes: list[OddsQuote],
    rejections: list[dict[str, object]],
    quality_audit: dict[str, object],
    response_headers: dict[str, str],
) -> Path:
    written_at = snapshot.retrieved_at
    directory = Path(root) / "normalized" / "the-odds-api" / written_at.strftime("%Y-%m-%d")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{written_at.strftime('%H%M%S')}-{snapshot.sha256[:16]}.json"
    event_by_source = {item.event.source_event_id: item for item in matched_events}
    event_payloads: list[dict[str, object]] = []
    for item in matched_events:
        payload = asdict(item.event)
        payload["match_start_at"] = item.event.match_start_at.isoformat()
        payload["retrieved_at"] = item.event.retrieved_at.isoformat()
        payload.update(identity_to_dict(item.identity))
        payload["historical_home_matches"] = item.historical_home_matches
        payload["historical_away_matches"] = item.historical_away_matches
        event_payloads.append(payload)

    quote_payloads: list[dict[str, object]] = []
    for quote in quotes:
        payload = asdict(quote)
        payload["match_start_at"] = quote.match_start_at.isoformat()
        payload["retrieved_at"] = quote.retrieved_at.isoformat()
        payload["observed_at"] = quote.observed_at.isoformat() if quote.observed_at else None
        payload["canonical_fixture_id"] = event_by_source[
            quote.source_event_id
        ].identity.canonical_fixture_id
        quote_payloads.append(payload)

    quota_headers = {
        key.lower(): value
        for key, value in response_headers.items()
        if key.lower() in {"x-requests-remaining", "x-requests-used", "x-requests-last"}
    }
    status = "pass" if not rejections else "partial" if matched_events else "rejected"
    manifest = {
        "provider": "the-odds-api",
        "source_url": source_url,
        "retrieved_at": snapshot.retrieved_at.isoformat(),
        "raw_snapshot_sha256": snapshot.sha256,
        "raw_snapshot_path": snapshot.payload_path,
        "status": status,
        "raw_event_count": len(parsed.events),
        "event_count": len(event_payloads),
        "quote_count": len(quote_payloads),
        "events": event_payloads,
        "quotes": quote_payloads,
        "rejection_count": len(rejections),
        "rejections": rejections,
        "identity_validation": parsed.identity_audit,
        "quality_validation": quality_audit,
        "request_usage": quota_headers,
    }
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return path


class OddsApiIngestionJob:
    def __init__(
        self,
        raw_root: str | Path,
        api_key: str,
        season: str,
        base_url: str = DEFAULT_ODDS_BASE_URL,
        sport: str = DEFAULT_ODDS_SPORT,
        regions: str = DEFAULT_ODDS_REGIONS,
        markets: str = DEFAULT_ODDS_MARKETS,
        odds_format: str = DEFAULT_ODDS_FORMAT,
        competition: str | None = None,
        historical_league: str | None = None,
        fetcher: Callable[[], tuple[bytes, dict[str, str]]] | None = None,
        clock: Callable[[], datetime] | None = None,
        quality_reference_clock: Callable[[], datetime] | None = None,
        history_loader: Callable[[datetime], Iterable[ReplayedFixture]] | None = None,
        policy: OddsIngestionPolicy | None = None,
    ):
        if not season.strip():
            raise ValueError("ODDS_API_SEASON is required")
        self.raw_root = Path(raw_root)
        self.adapter = OddsApiAdapter(api_key, base_url)
        self.sport = sport
        self.regions = regions
        self.markets = markets
        self.odds_format = odds_format
        self.competition = competition
        self.season = season.strip()
        self.historical_league = historical_league
        self.fetcher = fetcher or (
            lambda: self.adapter.fetch_odds(
                self.sport,
                self.regions,
                self.markets,
                self.odds_format,
            )
        )
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.quality_reference_clock = quality_reference_clock
        self.history_loader = history_loader or self._load_history
        self.policy = policy or OddsIngestionPolicy()

    def run_once(self) -> Path:
        retrieved_at = self.clock()
        _require_aware(retrieved_at, "odds snapshot retrieval")
        source_url = self.adapter.odds_source_url(
            self.sport,
            self.regions,
            self.markets,
            self.odds_format,
        )
        payload, headers = self.fetcher()
        snapshot = FileRawSnapshotStore(self.raw_root).save(
            "the-odds-api",
            source_url,
            payload,
            "application/json",
            retrieved_at,
        )
        if not payload:
            raise IngestionValidationError(
                "odds_payload_rejected",
                "The Odds API returned an empty payload",
                [_reason("empty_payload", {"payload_bytes": 0})],
                {"status": "rejected"},
            )
        try:
            parsed = self.adapter.parse_snapshot(
                payload,
                retrieved_at,
                self.season,
                self.competition,
            )
        except OddsApiPayloadError as exc:
            raise IngestionValidationError(
                exc.code,
                str(exc),
                exc.reasons,
                {"status": "rejected", "reasons": exc.reasons},
            ) from exc
        reference_at = (
            self.quality_reference_clock()
            if self.quality_reference_clock is not None
            else retrieved_at
        )
        _require_aware(reference_at, "odds quality reference")
        if not parsed.events:
            quality_audit = {
                "status": "rejected",
                "freshness": {
                    "snapshot_retrieved_at": retrieved_at.isoformat(),
                    "reference_at": reference_at.isoformat(),
                },
                "reasons": list(parsed.rejections),
            }
            return write_odds_manifest(
                self.raw_root,
                source_url,
                snapshot,
                parsed,
                [],
                [],
                list(parsed.rejections),
                quality_audit,
                headers,
            )
        quality_audit = validate_ingestion_quality(
            [event_record(event) for event in parsed.events],
            snapshot_retrieved_at=retrieved_at,
            reference_at=reference_at,
            policy=IngestionQualityPolicy(max_snapshot_age=self.policy.max_snapshot_age),
        )
        matched, quotes, matching_rejections = match_events_to_history(
            parsed.events,
            parsed.quotes,
            self.history_loader(retrieved_at),
            reference_at,
            self.policy,
        )
        rejections = [*parsed.rejections, *matching_rejections]
        return write_odds_manifest(
            self.raw_root,
            source_url,
            snapshot,
            parsed,
            matched,
            quotes,
            rejections,
            quality_audit,
            headers,
        )

    def _load_history(self, as_of: datetime) -> Iterable[ReplayedFixture]:
        return HistoricalManifestReplay(
            self.raw_root,
            league=self.historical_league,
        ).replay(as_of).fixtures


def run_odds_scheduler(
    job: OddsApiIngestionJob,
    interval_seconds: int = DEFAULT_ODDS_INTERVAL_SECONDS,
) -> None:
    if interval_seconds <= 0:
        raise ValueError("Odds ingestion interval must be greater than zero")
    while True:
        job.run_once()
        time.sleep(interval_seconds)


def odds_job_from_environment() -> OddsApiIngestionJob:
    load_dotenv()
    max_age_minutes = float(
        os.getenv("ODDS_MAX_AGE_MINUTES", str(DEFAULT_ODDS_MAX_AGE_MINUTES))
    )
    return OddsApiIngestionJob(
        raw_root=os.getenv("RAW_DATA_ROOT", "data/raw"),
        api_key=os.getenv("ODDS_API_KEY", ""),
        base_url=os.getenv("ODDS_API_BASE_URL", DEFAULT_ODDS_BASE_URL),
        sport=os.getenv("ODDS_API_SPORT", DEFAULT_ODDS_SPORT),
        regions=os.getenv("ODDS_API_REGIONS", DEFAULT_ODDS_REGIONS),
        markets=os.getenv("ODDS_API_MARKETS", DEFAULT_ODDS_MARKETS),
        odds_format=os.getenv("ODDS_API_FORMAT", DEFAULT_ODDS_FORMAT),
        competition=os.getenv("ODDS_API_COMPETITION") or None,
        season=os.getenv("ODDS_API_SEASON", ""),
        historical_league=os.getenv("FOOTBALL_DATA_LEAGUE") or None,
        policy=OddsIngestionPolicy(
            max_snapshot_age=timedelta(minutes=max_age_minutes),
            max_quote_age=timedelta(minutes=max_age_minutes),
        ),
    )


def _reason(code: str, details: dict[str, object]) -> dict[str, object]:
    return {"code": code, "details": details}


def _require_aware(value: datetime, label: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must include a timezone")
