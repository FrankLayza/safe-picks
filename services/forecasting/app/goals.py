from dataclasses import dataclass
from datetime import datetime
from math import exp, factorial, log
from typing import Iterable

from .replay import ReplayedFixture

MODEL_VERSION = "poisson-dixon-coles-v1"


@dataclass(frozen=True)
class PoissonModelConfig:
    prior_matches: float = 2.0
    decay_half_life_days: float | None = 365.0
    dixon_coles_rho: float | None = None
    max_goals: int = 10

    def __post_init__(self) -> None:
        if self.prior_matches < 0:
            raise ValueError("prior_matches cannot be negative")
        if self.decay_half_life_days is not None and self.decay_half_life_days <= 0:
            raise ValueError("decay_half_life_days must be greater than zero")
        if self.dixon_coles_rho is not None and not -0.25 <= self.dixon_coles_rho <= 0.25:
            raise ValueError("dixon_coles_rho must be between -0.25 and 0.25")
        if self.max_goals < 2:
            raise ValueError("max_goals must be at least two")


@dataclass(frozen=True)
class GoalsPrediction:
    model_version: str
    training_as_of: datetime
    training_matches: int
    home_team: str
    away_team: str
    expected_home_goals: float
    expected_away_goals: float
    dixon_coles_rho: float
    home_win_probability: float
    draw_probability: float
    away_win_probability: float
    over_1_5_probability: float
    over_2_5_probability: float
    btts_probability: float
    score_matrix: tuple[tuple[float, ...], ...]
    source_manifest_paths: tuple[str, ...]
    raw_snapshot_shas: tuple[str, ...]

    def score_probability(self, home_goals: int, away_goals: int) -> float:
        if home_goals < 0 or away_goals < 0:
            raise ValueError("goal counts cannot be negative")
        if home_goals >= len(self.score_matrix) or away_goals >= len(self.score_matrix[home_goals]):
            return 0.0
        return self.score_matrix[home_goals][away_goals]


class PoissonGoalsModel:
    def __init__(
        self,
        as_of: datetime,
        home_attack: dict[str, float],
        home_defense: dict[str, float],
        away_attack: dict[str, float],
        away_defense: dict[str, float],
        league_home_goals: float,
        league_away_goals: float,
        training_matches: int,
        rho: float,
        config: PoissonModelConfig,
        source_manifest_paths: tuple[str, ...],
        raw_snapshot_shas: tuple[str, ...],
    ):
        self.training_as_of = as_of
        self.home_attack = home_attack
        self.home_defense = home_defense
        self.away_attack = away_attack
        self.away_defense = away_defense
        self.league_home_goals = league_home_goals
        self.league_away_goals = league_away_goals
        self.training_matches = training_matches
        self.rho = rho
        self.config = config
        self.source_manifest_paths = source_manifest_paths
        self.raw_snapshot_shas = raw_snapshot_shas

    @classmethod
    def fit(
        cls,
        fixtures: Iterable[ReplayedFixture],
        as_of: datetime,
        config: PoissonModelConfig | None = None,
    ) -> "PoissonGoalsModel":
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("as_of must include a timezone")
        active_config = config or PoissonModelConfig()
        selected: dict[str, ReplayedFixture] = {}
        for item in fixtures:
            _require_aware(item.record.match_start_at, "fixture kickoff")
            _require_aware(item.record.retrieved_at, "record retrieval")
            _require_aware(item.manifest_retrieved_at, "manifest retrieval")
            if item.record.observed_at is not None:
                _require_aware(item.record.observed_at, "record observation")
            if item.record.home_goals is not None and item.record.away_goals is not None:
                if item.record.retrieved_at <= item.record.match_start_at:
                    raise ValueError("completed result retrieval must be after fixture kickoff")
            if (
                item.record.match_start_at < as_of
                and item.manifest_retrieved_at <= as_of
                and item.record.retrieved_at <= as_of
                and (item.record.observed_at is None or item.record.observed_at <= as_of)
                and item.record.home_goals is not None
                and item.record.away_goals is not None
            ):
                fixture_id = item.identity.canonical_fixture_id
                existing = selected.get(fixture_id)
                if existing is None or item.manifest_retrieved_at > existing.manifest_retrieved_at:
                    selected[fixture_id] = item
        records = list(selected.values())
        if not records:
            raise ValueError("at least one completed pre-match fixture is required")
        weights = [
            _time_weight(item.record.match_start_at, as_of, active_config.decay_half_life_days)
            for item in records
        ]
        total_weight = sum(weights)
        league_home = max(
            0.05,
            sum(item.record.home_goals * weight for item, weight in zip(records, weights))
            / total_weight,
        )
        league_away = max(
            0.05,
            sum(item.record.away_goals * weight for item, weight in zip(records, weights))
            / total_weight,
        )
        teams = sorted({item.record.home_team for item in records} | {item.record.away_team for item in records})
        home_attack: dict[str, float] = {}
        home_defense: dict[str, float] = {}
        away_attack: dict[str, float] = {}
        away_defense: dict[str, float] = {}
        for team in teams:
            home_rows = [
                (item, weight)
                for item, weight in zip(records, weights)
                if item.record.home_team == team
            ]
            away_rows = [
                (item, weight)
                for item, weight in zip(records, weights)
                if item.record.away_team == team
            ]
            home_attack[team] = _smoothed_strength(
                home_rows, "home_goals", league_home, active_config.prior_matches
            )
            home_defense[team] = _smoothed_strength(
                home_rows, "away_goals", league_away, active_config.prior_matches
            )
            away_attack[team] = _smoothed_strength(
                away_rows, "away_goals", league_away, active_config.prior_matches
            )
            away_defense[team] = _smoothed_strength(
                away_rows, "home_goals", league_home, active_config.prior_matches
            )
        rho = active_config.dixon_coles_rho
        if rho is None:
            rho = _fit_rho(
                records,
                weights,
                home_attack,
                home_defense,
                away_attack,
                away_defense,
                league_home,
                league_away,
            )
        return cls(
            as_of,
            home_attack,
            home_defense,
            away_attack,
            away_defense,
            league_home,
            league_away,
            len(records),
            rho,
            active_config,
            tuple(sorted({item.manifest_path for item in records})),
            tuple(sorted({item.raw_snapshot_sha256 for item in records})),
        )

    def predict(self, home_team: str, away_team: str) -> GoalsPrediction:
        expected_home = (
            self.league_home_goals
            * self.home_attack.get(home_team, 1.0)
            * self.away_defense.get(away_team, 1.0)
        )
        expected_away = (
            self.league_away_goals
            * self.away_attack.get(away_team, 1.0)
            * self.home_defense.get(home_team, 1.0)
        )
        expected_home, expected_away = max(0.01, expected_home), max(0.01, expected_away)
        matrix = self._score_matrix(expected_home, expected_away)
        size = len(matrix)
        home_win = sum(matrix[h][a] for h in range(size) for a in range(size) if h > a)
        draw = sum(matrix[h][h] for h in range(size))
        away_win = 1.0 - home_win - draw
        under_1_5 = sum(matrix[h][a] for h in range(size) for a in range(size) if h + a <= 1)
        under_2_5 = sum(matrix[h][a] for h in range(size) for a in range(size) if h + a <= 2)
        no_btts = sum(matrix[h][0] for h in range(size)) + sum(matrix[0][a] for a in range(1, size))
        return GoalsPrediction(
            MODEL_VERSION,
            self.training_as_of,
            self.training_matches,
            home_team,
            away_team,
            expected_home,
            expected_away,
            self.rho,
            home_win,
            draw,
            away_win,
            1.0 - under_1_5,
            1.0 - under_2_5,
            1.0 - no_btts,
            matrix,
            self.source_manifest_paths,
            self.raw_snapshot_shas,
        )

    def _score_matrix(self, home_goals: float, away_goals: float) -> tuple[tuple[float, ...], ...]:
        home = [_poisson_probability(home_goals, goals) for goals in range(self.config.max_goals + 1)]
        away = [_poisson_probability(away_goals, goals) for goals in range(self.config.max_goals + 1)]
        matrix = [
            [
                max(
                    0.0,
                    home[h]
                    * away[a]
                    * _dixon_coles_correction(
                        h, a, home_goals, away_goals, self.rho
                    ),
                )
                for a in range(len(away))
            ]
            for h in range(len(home))
        ]
        total = sum(sum(row) for row in matrix)
        return tuple(tuple(value / total for value in row) for row in matrix)


def _smoothed_strength(
    rows: list[tuple[ReplayedFixture, float]],
    field: str,
    league_rate: float,
    prior_matches: float,
) -> float:
    weighted_matches = sum(weight for _, weight in rows)
    weighted_goals = sum(getattr(item.record, field) * weight for item, weight in rows)
    return max(
        0.05,
        (
            (weighted_goals + prior_matches * league_rate)
            / (weighted_matches + prior_matches)
        )
        / league_rate,
    )


def _time_weight(match_start: datetime, as_of: datetime, half_life_days: float | None) -> float:
    if half_life_days is None:
        return 1.0
    age_days = max(0.0, (as_of - match_start).total_seconds() / 86_400)
    return exp(-log(2) * age_days / half_life_days)


def _fit_rho(
    records: list[ReplayedFixture],
    weights: list[float],
    home_attack: dict[str, float],
    home_defense: dict[str, float],
    away_attack: dict[str, float],
    away_defense: dict[str, float],
    league_home: float,
    league_away: float,
) -> float:
    best_rho, best_score = 0.0, float("-inf")
    for step in range(-20, 21):
        rho, score, valid = step / 100, 0.0, True
        for item, weight in zip(records, weights):
            home_rate = max(
                0.01,
                league_home
                * home_attack[item.record.home_team]
                * away_defense[item.record.away_team],
            )
            away_rate = max(
                0.01,
                league_away
                * away_attack[item.record.away_team]
                * home_defense[item.record.home_team],
            )
            correction = _dixon_coles_correction(
                item.record.home_goals,
                item.record.away_goals,
                home_rate,
                away_rate,
                rho,
            )
            probability = (
                _poisson_probability(home_rate, item.record.home_goals)
                * _poisson_probability(away_rate, item.record.away_goals)
                * correction
            )
            if correction <= 0 or probability <= 0:
                valid = False
                break
            score += weight * log(probability)
        if valid and score > best_score:
            best_rho, best_score = rho, score
    return best_rho


def _poisson_probability(rate: float, goals: int) -> float:
    return exp(-rate) * rate**goals / factorial(goals)


def _dixon_coles_correction(home: int, away: int, home_rate: float, away_rate: float, rho: float) -> float:
    if (home, away) == (0, 0):
        return 1 - home_rate * away_rate * rho
    if (home, away) == (0, 1):
        return 1 + home_rate * rho
    if (home, away) == (1, 0):
        return 1 + away_rate * rho
    if (home, away) == (1, 1):
        return 1 - rho
    return 1.0


def _require_aware(value: datetime, label: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must include a timezone")
