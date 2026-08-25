from dataclasses import dataclass
from datetime import datetime
from math import exp
from typing import Iterable

from .providers.identity import resolve_fixture_identity
from .replay import ReplayedFixture

FEATURE_VERSION = "football-pre-match-v1"


@dataclass(frozen=True)
class FeatureConfig:
    recent_matches: int = 10
    strength_matches: int = 30
    strength_prior_matches: float = 2.0
    decay_half_life_days: float | None = 365.0

    def __post_init__(self) -> None:
        if self.recent_matches <= 0:
            raise ValueError("recent_matches must be greater than zero")
        if self.strength_matches <= 0:
            raise ValueError("strength_matches must be greater than zero")
        if self.strength_prior_matches < 0:
            raise ValueError("strength_prior_matches cannot be negative")
        if self.decay_half_life_days is not None and self.decay_half_life_days <= 0:
            raise ValueError("decay_half_life_days must be greater than zero")


@dataclass(frozen=True)
class FixtureFeatures:
    feature_version: str
    fixture_id: str
    forecast_at: datetime
    kickoff: datetime
    home_team_id: str
    away_team_id: str
    matches_used: int
    home_matches_used: int
    away_matches_used: int
    home_goals_for_average: float | None
    home_goals_against_average: float | None
    away_goals_for_average: float | None
    away_goals_against_average: float | None
    home_home_goals_for_average: float | None
    home_home_goals_against_average: float | None
    away_away_goals_for_average: float | None
    away_away_goals_against_average: float | None
    home_points_average: float | None
    away_points_average: float | None
    home_attack_strength: float | None
    home_defense_strength: float | None
    away_attack_strength: float | None
    away_defense_strength: float | None
    home_rest_days: float | None
    away_rest_days: float | None
    data_completeness: float
    source_manifest_paths: tuple[str, ...]
    raw_snapshot_shas: tuple[str, ...]


@dataclass(frozen=True)
class TeamMatch:
    fixture: ReplayedFixture
    team_id: str
    opponent_id: str
    is_home: bool


def build_fixture_features(
    target: ReplayedFixture,
    history: Iterable[ReplayedFixture],
    forecast_at: datetime | None = None,
    config: FeatureConfig | None = None,
) -> FixtureFeatures:
    active_config = config or FeatureConfig()
    forecast = forecast_at or target.record.match_start_at
    _require_aware(forecast, "forecast_at")
    _require_aware(target.record.match_start_at, "kickoff")
    _require_aware(target.record.retrieved_at, "target record retrieval")
    _require_aware(target.manifest_retrieved_at, "target manifest retrieval")
    if forecast > target.record.match_start_at:
        raise ValueError("forecast_at must be before kickoff")
    if target.record.retrieved_at > forecast or target.manifest_retrieved_at > forecast:
        raise ValueError("target fixture must be available by forecast_at")
    target_identity = target.identity or resolve_fixture_identity(target.record, target.record.season)
    eligible = _eligible_history(target, history, forecast)
    home_matches = _team_matches(eligible, target_identity.canonical_home_team_id)
    away_matches = _team_matches(eligible, target_identity.canonical_away_team_id)
    home_recent = _recent(home_matches, active_config)
    away_recent = _recent(away_matches, active_config)
    home_home = [item for item in home_recent if item.is_home]
    away_away = [item for item in away_recent if not item.is_home]
    selected = _unique_records([item.fixture for item in (*home_recent, *away_recent)])
    provenance = _unique_records([target, *[item.fixture for item in (*home_recent, *away_recent)], *eligible])
    strengths = _opponent_adjusted_strengths(eligible, forecast, active_config)
    available_values = sum(
        value is not None
        for items in (home_recent, away_recent)
        for value in (_average_for(items, forecast, active_config), _average_against(items, forecast, active_config))
    )
    completeness = available_values / 4 if home_recent and away_recent else 0.0
    return FixtureFeatures(
        feature_version=FEATURE_VERSION,
        fixture_id=target_identity.canonical_fixture_id,
        forecast_at=forecast,
        kickoff=target.record.match_start_at,
        home_team_id=target_identity.canonical_home_team_id,
        away_team_id=target_identity.canonical_away_team_id,
        matches_used=len(selected),
        home_matches_used=len(home_recent),
        away_matches_used=len(away_recent),
        home_goals_for_average=_average_for(home_recent, forecast, active_config),
        home_goals_against_average=_average_against(home_recent, forecast, active_config),
        away_goals_for_average=_average_for(away_recent, forecast, active_config),
        away_goals_against_average=_average_against(away_recent, forecast, active_config),
        home_home_goals_for_average=_average_for(home_home, forecast, active_config),
        home_home_goals_against_average=_average_against(home_home, forecast, active_config),
        away_away_goals_for_average=_average_for(away_away, forecast, active_config),
        away_away_goals_against_average=_average_against(away_away, forecast, active_config),
        home_points_average=_average_points(home_recent, forecast, active_config),
        away_points_average=_average_points(away_recent, forecast, active_config),
        home_attack_strength=strengths.get(target_identity.canonical_home_team_id, (None, None))[0],
        home_defense_strength=strengths.get(target_identity.canonical_home_team_id, (None, None))[1],
        away_attack_strength=strengths.get(target_identity.canonical_away_team_id, (None, None))[0],
        away_defense_strength=strengths.get(target_identity.canonical_away_team_id, (None, None))[1],
        home_rest_days=_rest_days(home_recent, target.record.match_start_at),
        away_rest_days=_rest_days(away_recent, target.record.match_start_at),
        data_completeness=completeness,
        source_manifest_paths=tuple(sorted({item.manifest_path for item in provenance})),
        raw_snapshot_shas=tuple(sorted({item.raw_snapshot_sha256 for item in provenance})),
    )


def _eligible_history(
    target: ReplayedFixture,
    history: Iterable[ReplayedFixture],
    forecast_at: datetime,
) -> list[ReplayedFixture]:
    selected: dict[str, ReplayedFixture] = {}
    for item in history:
        record = item.record
        _require_aware(record.match_start_at, "historical kickoff")
        _require_aware(record.retrieved_at, "record retrieval")
        _require_aware(item.manifest_retrieved_at, "manifest retrieval")
        if record.observed_at is not None:
            _require_aware(record.observed_at, "record observation")
        if item.identity.canonical_fixture_id == target.identity.canonical_fixture_id:
            continue
        if record.home_goals is None or record.away_goals is None:
            continue
        if record.retrieved_at <= record.match_start_at:
            raise ValueError("completed result retrieval must be after historical kickoff")
        if (
            record.match_start_at >= forecast_at
            or item.manifest_retrieved_at > forecast_at
            or record.retrieved_at > forecast_at
            or (record.observed_at is not None and record.observed_at > forecast_at)
        ):
            continue
        existing = selected.get(item.identity.canonical_fixture_id)
        if existing is None or item.manifest_retrieved_at > existing.manifest_retrieved_at:
            selected[item.identity.canonical_fixture_id] = item
    return sorted(selected.values(), key=lambda item: item.record.match_start_at, reverse=True)


def _team_matches(history: list[ReplayedFixture], team_id: str) -> list[TeamMatch]:
    matches = []
    for item in history:
        if item.identity.canonical_home_team_id == team_id:
            matches.append(TeamMatch(item, team_id, item.identity.canonical_away_team_id, True))
        elif item.identity.canonical_away_team_id == team_id:
            matches.append(TeamMatch(item, team_id, item.identity.canonical_home_team_id, False))
    return matches


def _recent(matches: list[TeamMatch], config: FeatureConfig) -> list[TeamMatch]:
    return matches[: config.recent_matches]


def _unique_records(items: Iterable[ReplayedFixture]) -> list[ReplayedFixture]:
    unique: dict[str, ReplayedFixture] = {}
    for item in items:
        unique[item.identity.canonical_fixture_id] = item
    return list(unique.values())


def _average_for(matches: list[TeamMatch], reference: datetime, config: FeatureConfig) -> float | None:
    values = [_goals_for(item) for item in matches]
    return _weighted_average(values, matches, reference, config)


def _average_against(matches: list[TeamMatch], reference: datetime, config: FeatureConfig) -> float | None:
    values = [_goals_against(item) for item in matches]
    return _weighted_average(values, matches, reference, config)


def _average_points(matches: list[TeamMatch], reference: datetime, config: FeatureConfig) -> float | None:
    values = []
    for item in matches:
        scored, conceded = _goals_for(item), _goals_against(item)
        values.append(3.0 if scored > conceded else 1.0 if scored == conceded else 0.0)
    return _weighted_average(values, matches, reference, config)


def _goals_for(item: TeamMatch) -> int:
    return item.fixture.record.home_goals if item.is_home else item.fixture.record.away_goals  # type: ignore[return-value]


def _goals_against(item: TeamMatch) -> int:
    return item.fixture.record.away_goals if item.is_home else item.fixture.record.home_goals  # type: ignore[return-value]


def _average(values: list[int | float]) -> float | None:
    return sum(values) / len(values) if values else None


def _weighted_average(
    values: list[int | float],
    matches: list[TeamMatch],
    reference: datetime,
    config: FeatureConfig,
) -> float | None:
    if not values:
        return None
    if config.decay_half_life_days is None:
        return _average(values)
    weights = [
        _time_weight(item.fixture.record.match_start_at, reference, config.decay_half_life_days)
        for item in matches
    ]
    return sum(value * weight for value, weight in zip(values, weights)) / sum(weights)


def _opponent_adjusted_strengths(
    history: list[ReplayedFixture],
    reference: datetime,
    config: FeatureConfig,
) -> dict[str, tuple[float, float]]:
    team_ids = sorted(
        {
            team_id
            for item in history
            for team_id in (
                item.identity.canonical_home_team_id,
                item.identity.canonical_away_team_id,
            )
        }
    )
    all_matches = {
        team_id: _team_matches(history, team_id)[: config.strength_matches]
        for team_id in team_ids
    }
    weights = {
        item.identity.canonical_fixture_id: _time_weight(item.record.match_start_at, reference, config.decay_half_life_days)
        for item in history
    }
    total_weight = sum(weights.values())
    total_goals = sum(
        (item.record.home_goals + item.record.away_goals) * weights[item.identity.canonical_fixture_id]
        for item in history
    )  # type: ignore[operator]
    league_rate = max(0.05, total_goals / (2 * total_weight)) if total_weight else 1.0
    raw: dict[str, tuple[float, float]] = {}
    for team_id, matches in all_matches.items():
        attack = _weighted_average([_goals_for(item) for item in matches], matches, reference, config)
        defense = _weighted_average([_goals_against(item) for item in matches], matches, reference, config)
        raw[team_id] = (
            _smooth_ratio(attack, league_rate, len(matches), config.strength_prior_matches),
            _smooth_ratio(defense, league_rate, len(matches), config.strength_prior_matches),
        )
    adjusted: dict[str, tuple[float, float]] = {}
    for team_id, matches in all_matches.items():
        attack_values = [
            _goals_for(item) / (league_rate * max(0.25, raw[item.opponent_id][1]))
            for item in matches
        ]
        defense_values = [
            _goals_against(item) / (league_rate * max(0.25, raw[item.opponent_id][0]))
            for item in matches
        ]
        attack = _weighted_average(attack_values, matches, reference, config)
        defense = _weighted_average(defense_values, matches, reference, config)
        adjusted[team_id] = (
            _smooth_strength(attack, len(matches), config.strength_prior_matches),
            _smooth_strength(defense, len(matches), config.strength_prior_matches),
        )
    return adjusted


def _smooth_ratio(
    value: float | None,
    league_rate: float,
    matches: int,
    prior_matches: float,
) -> float:
    observed = value / league_rate if value is not None else 1.0
    return (observed * matches + prior_matches) / (matches + prior_matches) if matches + prior_matches else 1.0


def _smooth_strength(value: float | None, matches: int, prior_matches: float) -> float:
    observed = value if value is not None else 1.0
    return (observed * matches + prior_matches) / (matches + prior_matches) if matches + prior_matches else 1.0


def _rest_days(matches: list[TeamMatch], kickoff: datetime) -> float | None:
    if not matches:
        return None
    return (kickoff - matches[0].fixture.record.match_start_at).total_seconds() / 86_400


def _require_aware(value: datetime, label: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must include a timezone")


def _time_weight(
    match_start: datetime,
    reference: datetime,
    half_life_days: float | None,
) -> float:
    if half_life_days is None:
        return 1.0
    age_days = max(0.0, (reference - match_start).total_seconds() / 86_400)
    return exp(-0.6931471805599453 * age_days / half_life_days)
