import hashlib
import re
import unicodedata
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

from .models import FixtureRecord, OddsQuote

IDENTITY_SCHEMA_VERSION = "identity-v1"

_TEAM_ALIASES = {
    "man utd": "manchester united",
    "manchester utd": "manchester united",
    "spurs": "tottenham hotspur",
    "wolves": "wolverhampton wanderers",
    "qpr": "queens park rangers",
}

_COMPETITION_ALIASES = {
    "e0": "england premier league",
    "premier league": "england premier league",
    "english premier league": "england premier league",
}

_MARKET_ALIASES = {
    "h2h": "match result",
    "moneyline": "match result",
    "1x2": "match result",
    "totals": "total",
    "over under": "total",
}

_FIXTURE_FACT_FIELDS = (
    "match_start_at",
    "home_goals",
    "away_goals",
    "half_time_home_goals",
    "half_time_away_goals",
    "home_corners",
    "away_corners",
    "home_shots",
    "away_shots",
    "home_shots_on_target",
    "away_shots_on_target",
)


class IdentityResolutionError(ValueError):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


class ManifestValidationError(ValueError):
    def __init__(self, code: str, message: str, details: list[dict[str, Any]] | None = None):
        super().__init__(message)
        self.code = code
        self.details = details or []


@dataclass(frozen=True)
class FixtureIdentity:
    canonical_competition_id: str
    canonical_competition: str
    canonical_home_team_id: str
    canonical_home_team: str
    canonical_away_team_id: str
    canonical_away_team: str
    canonical_fixture_id: str


@dataclass(frozen=True)
class MarketIdentity:
    canonical_market_id: str
    canonical_market: str
    canonical_selection: str
    canonical_line: str


def normalize_identity_label(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise IdentityResolutionError("missing_identity_field", f"{field} is required", {"field": field})
    decomposed = unicodedata.normalize("NFKD", value)
    ascii_value = decomposed.encode("ascii", "ignore").decode("ascii")
    ascii_value = ascii_value.replace(".", "")
    normalized = ascii_value.casefold().replace("&", " and ")
    normalized = re.sub(r"['`]+", "", normalized)
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    normalized = " ".join(normalized.split())
    if not normalized:
        raise IdentityResolutionError("invalid_identity_field", f"{field} has no usable value", {"field": field})
    return normalized


def _alias(value: str, aliases: dict[str, str]) -> str:
    return aliases.get(value, value)


def _stable_id(prefix: str, parts: Iterable[str]) -> str:
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:24]
    return f"{prefix}:{digest}"


def _canonical_team(provider: str, provider_name: str) -> str:
    normalize_identity_label(provider, "provider")
    return _alias(normalize_identity_label(provider_name, "team"), _TEAM_ALIASES)


def resolve_team_id(provider: str, provider_name: str) -> str:
    return _stable_id("team", (_canonical_team(provider, provider_name),))


def _canonical_competition(provider: str, provider_name: str) -> str:
    normalize_identity_label(provider, "provider")
    return _alias(normalize_identity_label(provider_name, "competition"), _COMPETITION_ALIASES)


def resolve_competition_id(provider: str, provider_name: str) -> str:
    return _stable_id("competition", (_canonical_competition(provider, provider_name),))


def _season_for(record: FixtureRecord, season: str | None) -> str:
    value = season or record.season
    if not value or not value.strip():
        raise IdentityResolutionError("missing_identity_field", "season is required", {"field": "season"})
    return value.strip().casefold()


def resolve_fixture_identity(record: FixtureRecord, season: str | None = None) -> FixtureIdentity:
    provider = normalize_identity_label(record.provider, "provider")
    normalize_identity_label(record.source_event_id, "source_event_id")
    if not record.competition:
        raise IdentityResolutionError("missing_identity_field", "competition is required", {"field": "competition"})
    competition = _canonical_competition(record.provider, record.competition)
    home_team = _canonical_team(record.provider, record.home_team)
    away_team = _canonical_team(record.provider, record.away_team)
    competition_id = _stable_id("competition", (competition,))
    home_id = _stable_id("team", (home_team,))
    away_id = _stable_id("team", (away_team,))
    if not isinstance(record.match_start_at, datetime) or record.match_start_at.tzinfo is None:
        raise IdentityResolutionError(
            "invalid_identity_field",
            "match_start_at must include a timezone",
            {"field": "match_start_at"},
        )
    kickoff = record.match_start_at.isoformat()
    season_value = _season_for(record, season)
    fixture_id = _stable_id(
        "fixture",
        (provider, competition_id, season_value, kickoff, home_id, away_id),
    )
    return FixtureIdentity(
        competition_id,
        competition,
        home_id,
        home_team,
        away_id,
        away_team,
        fixture_id,
    )


def _line_key(line: float | None) -> str:
    if line is None:
        return "none"
    try:
        value = Decimal(str(line)).normalize()
    except (InvalidOperation, ValueError) as exc:
        raise IdentityResolutionError("invalid_market_line", "market line must be numeric", {"line": line}) from exc
    return format(value, "f")


def resolve_market_identity(quote: OddsQuote) -> MarketIdentity:
    provider = normalize_identity_label(quote.provider, "provider")
    event_id = normalize_identity_label(quote.source_event_id, "source_event_id")
    bookmaker = normalize_identity_label(quote.bookmaker, "bookmaker")
    market = _alias(normalize_identity_label(quote.market, "market"), _MARKET_ALIASES)
    selection = normalize_identity_label(quote.selection, "selection")
    market_id = _stable_id(
        "market",
        (provider, event_id, bookmaker, market, selection, _line_key(quote.line)),
    )
    line = _line_key(quote.line)
    return MarketIdentity(market_id, market, selection, line)


def resolve_market_quotes(quotes: Iterable[OddsQuote]) -> tuple[list[OddsQuote], dict[str, Any]]:
    unique: dict[str, OddsQuote] = {}
    duplicates: list[dict[str, str]] = []
    for quote in quotes:
        market_id = resolve_market_identity(quote).canonical_market_id
        identity = resolve_market_identity(quote)
        normalized = replace(
            quote,
            canonical_market_id=market_id,
            canonical_market=identity.canonical_market,
            canonical_selection=identity.canonical_selection,
            canonical_line=identity.canonical_line,
        )
        existing = unique.get(market_id)
        if existing is None:
            unique[market_id] = normalized
            continue
        conflicting_fields = [
            field
            for field in ("odds", "match_start_at", "line")
            if getattr(existing, field) != getattr(normalized, field)
        ]
        if conflicting_fields:
            raise ManifestValidationError(
                "conflicting_correction",
                "market rows with the same canonical identity contain conflicting facts",
                [{"market_id": market_id, "fields": conflicting_fields}],
            )
        duplicates.append({"market_id": market_id})
    return list(unique.values()), {
        "identity_schema_version": IDENTITY_SCHEMA_VERSION,
        "duplicate_count": len(duplicates),
        "duplicates": duplicates,
        "correction_count": 0,
    }


def _fact_value(record: FixtureRecord, field: str) -> Any:
    value = getattr(record, field)
    return value.isoformat() if isinstance(value, datetime) else value


def _fact_conflicts(left: FixtureRecord, right: FixtureRecord) -> list[str]:
    conflicts: list[str] = []
    for field in _FIXTURE_FACT_FIELDS:
        left_value = _fact_value(left, field)
        right_value = _fact_value(right, field)
        if left_value is not None and right_value is not None and left_value != right_value:
            conflicts.append(field)
    return conflicts


def _facts_equal(left: FixtureRecord, right: FixtureRecord) -> bool:
    return all(_fact_value(left, field) == _fact_value(right, field) for field in _FIXTURE_FACT_FIELDS)


def _fact_regressions(left: FixtureRecord, right: FixtureRecord) -> list[str]:
    return [
        field
        for field in _FIXTURE_FACT_FIELDS
        if _fact_value(left, field) is not None and _fact_value(right, field) is None
    ]


def _merge_records(left: FixtureRecord, right: FixtureRecord, fixture_id: str) -> FixtureRecord:
    conflicts = _fact_conflicts(left, right)
    if conflicts:
        raise ManifestValidationError(
            "conflicting_correction",
            "records with the same canonical fixture identity contain conflicting facts",
            [{"fixture_id": fixture_id, "fields": conflicts}],
        )
    values: dict[str, Any] = {}
    for field in _FIXTURE_FACT_FIELDS:
        values[field] = getattr(left, field) if getattr(left, field) is not None else getattr(right, field)
    return replace(
        left,
        **values,
        retrieved_at=max(left.retrieved_at, right.retrieved_at),
        observed_at=right.observed_at or left.observed_at,
    )


def _record_from_manifest(value: dict[str, Any]) -> FixtureRecord:
    try:
        return FixtureRecord(
            provider=str(value["provider"]),
            source_event_id=str(value["source_event_id"]),
            home_team=str(value["home_team"]),
            away_team=str(value["away_team"]),
            match_start_at=datetime.fromisoformat(str(value["match_start_at"])),
            retrieved_at=datetime.fromisoformat(str(value["retrieved_at"])),
            observed_at=datetime.fromisoformat(value["observed_at"]) if value.get("observed_at") else None,
            competition=value.get("competition"),
            season=value.get("season"),
            home_goals=value.get("home_goals"),
            away_goals=value.get("away_goals"),
            half_time_home_goals=value.get("half_time_home_goals"),
            half_time_away_goals=value.get("half_time_away_goals"),
            home_corners=value.get("home_corners"),
            away_corners=value.get("away_corners"),
            home_shots=value.get("home_shots"),
            away_shots=value.get("away_shots"),
            home_shots_on_target=value.get("home_shots_on_target"),
            away_shots_on_target=value.get("away_shots_on_target"),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ManifestValidationError("invalid_existing_manifest", "existing manifest has invalid fixture data") from exc


def resolve_fixture_records(
    records: Iterable[FixtureRecord],
    season: str | None = None,
    previous_manifests: Iterable[dict[str, Any]] = (),
) -> tuple[list[FixtureRecord], dict[str, Any], dict[str, FixtureIdentity]]:
    unique: dict[str, FixtureRecord] = {}
    identities: dict[str, FixtureIdentity] = {}
    duplicates: list[dict[str, Any]] = []
    completion_count = 0
    for record in records:
        identity = resolve_fixture_identity(record, season)
        fixture_id = identity.canonical_fixture_id
        identities[fixture_id] = identity
        if fixture_id not in unique:
            unique[fixture_id] = record
            continue
        before = unique[fixture_id]
        merged = _merge_records(before, record, fixture_id)
        if not _facts_equal(before, record):
            completion_count += 1
        unique[fixture_id] = merged
        duplicates.append({"scope": "manifest", "fixture_id": fixture_id, "source_event_id": record.source_event_id})

    previous_by_id: dict[str, FixtureRecord] = {}
    snapshot_duplicates: list[dict[str, Any]] = []
    for manifest in previous_manifests:
        for value in manifest.get("fixtures", []):
            previous = _record_from_manifest(value)
            identity = resolve_fixture_identity(previous, season)
            existing = previous_by_id.get(identity.canonical_fixture_id)
            if existing is not None and (_fact_conflicts(existing, previous) or _fact_regressions(existing, previous)):
                raise ManifestValidationError("invalid_existing_manifest", "existing manifests conflict with each other")
            previous_by_id[identity.canonical_fixture_id] = previous

    for fixture_id, record in unique.items():
        previous = previous_by_id.get(fixture_id)
        if previous is None:
            continue
        conflicts = _fact_conflicts(previous, record)
        regressions = _fact_regressions(previous, record)
        if conflicts or regressions:
            raise ManifestValidationError(
                "conflicting_correction",
                "new manifest conflicts with a previously ingested fixture",
                [{"fixture_id": fixture_id, "fields": conflicts + regressions}],
            )
        if _facts_equal(previous, record):
            snapshot_duplicates.append({"scope": "previous_snapshot", "fixture_id": fixture_id})
        else:
            snapshot_duplicates.append({"scope": "previous_snapshot", "fixture_id": fixture_id, "type": "completion"})

    audit = {
        "identity_schema_version": IDENTITY_SCHEMA_VERSION,
        "duplicate_count": len(duplicates),
        "duplicates": duplicates,
        "previous_snapshot_duplicate_count": len(snapshot_duplicates),
        "previous_snapshot_duplicates": snapshot_duplicates,
        "completion_count": completion_count + sum(item.get("type") == "completion" for item in snapshot_duplicates),
        "correction_count": 0,
    }
    return list(unique.values()), audit, identities


def identity_to_dict(identity: FixtureIdentity) -> dict[str, str]:
    return {
        "canonical_competition_id": identity.canonical_competition_id,
        "canonical_competition": identity.canonical_competition,
        "canonical_home_team_id": identity.canonical_home_team_id,
        "canonical_home_team": identity.canonical_home_team,
        "canonical_away_team_id": identity.canonical_away_team_id,
        "canonical_away_team": identity.canonical_away_team,
        "canonical_fixture_id": identity.canonical_fixture_id,
    }
