from bisect import bisect_left
from dataclasses import dataclass
from datetime import datetime
from math import log
from typing import Iterable, Literal

from .goals import GoalsPrediction, PoissonGoalsModel, PoissonModelConfig
from .replay import ReplayedFixture

EVALUATION_VERSION = "goals-walk-forward-v1"
CALIBRATION_VERSION = "isotonic-v1"

GoalMarket = Literal[
    "home_win",
    "draw",
    "away_win",
    "over_1_5",
    "over_2_5",
    "btts",
]
MARKETS: tuple[GoalMarket, ...] = (
    "home_win",
    "draw",
    "away_win",
    "over_1_5",
    "over_2_5",
    "btts",
)


@dataclass(frozen=True)
class EvaluationConfig:
    validation_start: datetime
    validation_end: datetime
    test_end: datetime | None = None
    min_training_matches: int = 1
    min_calibration_samples: int = 100
    model_config: PoissonModelConfig = PoissonModelConfig()

    def __post_init__(self) -> None:
        _require_aware(self.validation_start, "validation_start")
        _require_aware(self.validation_end, "validation_end")
        if self.validation_end <= self.validation_start:
            raise ValueError("validation_end must be after validation_start")
        if self.test_end is not None:
            _require_aware(self.test_end, "test_end")
            if self.test_end <= self.validation_end:
                raise ValueError("test_end must be after validation_end")
        if self.min_training_matches <= 0:
            raise ValueError("min_training_matches must be greater than zero")
        if self.min_calibration_samples < 2:
            raise ValueError("min_calibration_samples must be at least two")


@dataclass(frozen=True)
class MarketObservation:
    fixture_id: str
    kickoff: datetime
    split: Literal["validation", "test"]
    market: GoalMarket
    probability: float
    outcome: int
    model_version: str | None
    training_matches: int
    training_as_of: datetime | None
    status: Literal["scored", "abstained"]
    rejection_code: str | None = None


@dataclass(frozen=True)
class MarketMetrics:
    sample_count: int
    brier_score: float | None
    log_loss: float | None
    accuracy: float | None
    calibration_curve: tuple[tuple[float, float, int], ...]


@dataclass(frozen=True)
class EvaluationReport:
    evaluation_version: str
    calibration_version: str
    validation_start: datetime
    validation_end: datetime
    test_end: datetime | None
    validation_observations: tuple[MarketObservation, ...]
    test_observations: tuple[MarketObservation, ...]
    validation_metrics: dict[GoalMarket, MarketMetrics]
    test_metrics: dict[GoalMarket, MarketMetrics]
    calibrated_test_metrics: dict[GoalMarket, MarketMetrics]
    calibrators: dict[GoalMarket, "IsotonicCalibrator"]

    def calibrated_test_observations(self) -> tuple[MarketObservation, ...]:
        return tuple(_calibrate_observations(self.test_observations, self.calibrators))

    def calibrated_test_probabilities(self) -> dict[str, tuple[float, ...]]:
        values: dict[str, list[float]] = {market: [] for market in self.calibrators}
        for observation in self.calibrated_test_observations():
            if observation.status != "scored":
                continue
            values[observation.market].append(observation.probability)
        return {market: tuple(probabilities) for market, probabilities in values.items()}


@dataclass(frozen=True)
class IsotonicCalibrator:
    version: str
    sample_count: int
    thresholds: tuple[float, ...]
    values: tuple[float, ...]

    @classmethod
    def fit(cls, probabilities: Iterable[float], outcomes: Iterable[int]) -> "IsotonicCalibrator":
        probability_values = list(probabilities)
        outcome_values = list(outcomes)
        if len(probability_values) != len(outcome_values):
            raise ValueError("calibration probabilities and outcomes must have equal length")
        if len(probability_values) < 2:
            raise ValueError("at least two observations are required for calibration")
        if any(outcome not in (0, 1) for outcome in outcome_values):
            raise ValueError("calibration outcomes must be zero or one")
        pairs = sorted(
            (_validate_probability(probability), int(outcome))
            for probability, outcome in zip(probability_values, outcome_values)
        )

        blocks: list[dict[str, float]] = []
        for probability, outcome in pairs:
            if blocks and blocks[-1]["max_probability"] == probability:
                blocks[-1]["sum_outcomes"] += outcome
                blocks[-1]["count"] += 1.0
            else:
                blocks.append(
                    {
                        "min_probability": probability,
                        "max_probability": probability,
                        "sum_outcomes": float(outcome),
                        "count": 1.0,
                    }
                )
            while len(blocks) >= 2 and _block_value(blocks[-2]) > _block_value(blocks[-1]):
                right = blocks.pop()
                left = blocks.pop()
                blocks.append(
                    {
                        "min_probability": left["min_probability"],
                        "max_probability": right["max_probability"],
                        "sum_outcomes": left["sum_outcomes"] + right["sum_outcomes"],
                        "count": left["count"] + right["count"],
                    }
                )
        return cls(
            CALIBRATION_VERSION,
            len(pairs),
            tuple(block["max_probability"] for block in blocks),
            tuple(_block_value(block) for block in blocks),
        )

    def predict(self, probability: float) -> float:
        value = _validate_probability(probability)
        index = bisect_left(self.thresholds, value)
        return self.values[min(index, len(self.values) - 1)]


def evaluate_goals_walk_forward(
    fixtures: Iterable[ReplayedFixture],
    config: EvaluationConfig,
) -> EvaluationReport:
    """Evaluate raw and calibrated goals probabilities in chronological windows."""
    values = list(fixtures)
    for item in values:
        _require_aware(item.record.match_start_at, "fixture kickoff")
    ordered = sorted(values, key=lambda item: item.record.match_start_at)
    validation = _score_window(
        ordered,
        config.validation_start,
        config.validation_end,
        "validation",
        config,
    )
    test = _score_window(ordered, config.validation_end, config.test_end, "test", config)
    calibrators: dict[GoalMarket, IsotonicCalibrator] = {}
    for market in MARKETS:
        observations = [item for item in validation if item.market == market and item.status == "scored"]
        if len(observations) < config.min_calibration_samples:
            continue
        if len({item.outcome for item in observations}) < 2:
            continue
        calibrators[market] = IsotonicCalibrator.fit(
            (item.probability for item in observations),
            (item.outcome for item in observations),
        )
    return EvaluationReport(
        EVALUATION_VERSION,
        CALIBRATION_VERSION,
        config.validation_start,
        config.validation_end,
        config.test_end,
        tuple(validation),
        tuple(test),
        _metrics(validation),
        _metrics(test),
        _calibrated_metrics(test, calibrators),
        calibrators,
    )


def _score_window(
    fixtures: list[ReplayedFixture],
    start: datetime,
    end: datetime | None,
    split: Literal["validation", "test"],
    config: EvaluationConfig,
) -> list[MarketObservation]:
    observations: list[MarketObservation] = []
    for target in fixtures:
        kickoff = target.record.match_start_at
        if kickoff < start or (end is not None and kickoff >= end):
            continue
        if target.record.home_goals is None or target.record.away_goals is None:
            continue
        try:
            model = PoissonGoalsModel.fit(fixtures, kickoff, config.model_config)
            if model.training_matches < config.min_training_matches:
                raise ValueError("insufficient_training_matches")
            prediction = model.predict(target.record.home_team, target.record.away_team)
        except ValueError as exc:
            if str(exc) not in (
                "at least one completed pre-match fixture is required",
                "insufficient_training_matches",
            ):
                raise
            code = (
                "INSUFFICIENT_TRAINING_MATCHES"
                if str(exc) == "insufficient_training_matches"
                else "MODEL_UNAVAILABLE"
            )
            observations.extend(_abstentions(target, split, code, model_version=None))
            continue
        observations.extend(_observations(target, split, prediction))
    return observations


def _observations(
    target: ReplayedFixture,
    split: Literal["validation", "test"],
    prediction: GoalsPrediction,
) -> list[MarketObservation]:
    if target.record.home_goals > target.record.away_goals:
        result = 0
    elif target.record.home_goals == target.record.away_goals:
        result = 1
    else:
        result = 2
    probabilities: dict[GoalMarket, float] = {
        "home_win": prediction.home_win_probability,
        "draw": prediction.draw_probability,
        "away_win": prediction.away_win_probability,
        "over_1_5": prediction.over_1_5_probability,
        "over_2_5": prediction.over_2_5_probability,
        "btts": prediction.btts_probability,
    }
    outcomes: dict[GoalMarket, int] = {
        "home_win": int(result == 0),
        "draw": int(result == 1),
        "away_win": int(result == 2),
        "over_1_5": int(target.record.home_goals + target.record.away_goals > 1),
        "over_2_5": int(target.record.home_goals + target.record.away_goals > 2),
        "btts": int(target.record.home_goals > 0 and target.record.away_goals > 0),
    }
    return [
        MarketObservation(
            target.identity.canonical_fixture_id,
            target.record.match_start_at,
            split,
            market,
            probabilities[market],
            outcomes[market],
            prediction.model_version,
            prediction.training_matches,
            prediction.training_as_of,
            "scored",
        )
        for market in MARKETS
    ]


def _abstentions(
    target: ReplayedFixture,
    split: Literal["validation", "test"],
    rejection_code: str,
    model_version: str | None,
) -> list[MarketObservation]:
    return [
        MarketObservation(
            target.identity.canonical_fixture_id,
            target.record.match_start_at,
            split,
            market,
            0.0,
            0,
            model_version,
            0,
            None,
            "abstained",
            rejection_code,
        )
        for market in MARKETS
    ]


def _metrics(observations: Iterable[MarketObservation]) -> dict[GoalMarket, MarketMetrics]:
    result: dict[GoalMarket, MarketMetrics] = {}
    for market in MARKETS:
        scored = [item for item in observations if item.market == market and item.status == "scored"]
        if not scored:
            result[market] = MarketMetrics(0, None, None, None, ())
            continue
        brier = sum((item.probability - item.outcome) ** 2 for item in scored) / len(scored)
        loss = -sum(
            item.outcome * log(max(item.probability, 1e-15))
            + (1 - item.outcome) * log(max(1 - item.probability, 1e-15))
            for item in scored
        ) / len(scored)
        accuracy = sum(int((item.probability >= 0.5) == bool(item.outcome)) for item in scored) / len(scored)
        result[market] = MarketMetrics(len(scored), brier, loss, accuracy, _calibration_curve(scored))
    return result


def _calibrated_metrics(
    observations: Iterable[MarketObservation],
    calibrators: dict[GoalMarket, IsotonicCalibrator],
) -> dict[GoalMarket, MarketMetrics]:
    return _metrics(_calibrate_observations(observations, calibrators))


def _calibrate_observations(
    observations: Iterable[MarketObservation],
    calibrators: dict[GoalMarket, IsotonicCalibrator],
) -> list[MarketObservation]:
    calibrated: list[MarketObservation] = []
    for observation in observations:
        if observation.status != "scored":
            calibrated.append(observation)
            continue
        calibrator = calibrators.get(observation.market)
        if calibrator is None:
            calibrated.append(
                MarketObservation(
                    observation.fixture_id,
                    observation.kickoff,
                    observation.split,
                    observation.market,
                    0.0,
                    observation.outcome,
                    observation.model_version,
                    observation.training_matches,
                    observation.training_as_of,
                    "abstained",
                    "CALIBRATOR_UNAVAILABLE",
                )
            )
            continue
        calibrated.append(
            MarketObservation(
                observation.fixture_id,
                observation.kickoff,
                observation.split,
                observation.market,
                calibrator.predict(observation.probability),
                observation.outcome,
                observation.model_version,
                observation.training_matches,
                observation.training_as_of,
                observation.status,
                observation.rejection_code,
            )
        )
    _normalize_result_probabilities(calibrated)
    return calibrated


def _normalize_result_probabilities(observations: list[MarketObservation]) -> None:
    result_markets = {"home_win", "draw", "away_win"}
    by_fixture: dict[str, list[int]] = {}
    for index, observation in enumerate(observations):
        if observation.status == "scored" and observation.market in result_markets:
            by_fixture.setdefault(observation.fixture_id, []).append(index)
    for indexes in by_fixture.values():
        if len(indexes) != 3:
            continue
        total = sum(observations[index].probability for index in indexes)
        if total <= 0:
            for index in indexes:
                observations[index] = _replace_probability(observations[index], 1 / 3)
            continue
        for index in indexes:
            observations[index] = _replace_probability(
                observations[index],
                observations[index].probability / total,
            )


def _replace_probability(observation: MarketObservation, probability: float) -> MarketObservation:
    return MarketObservation(
        observation.fixture_id,
        observation.kickoff,
        observation.split,
        observation.market,
        probability,
        observation.outcome,
        observation.model_version,
        observation.training_matches,
        observation.training_as_of,
        observation.status,
        observation.rejection_code,
    )


def _calibration_curve(
    observations: list[MarketObservation],
    bins: int = 10,
) -> tuple[tuple[float, float, int], ...]:
    result: list[tuple[float, float, int]] = []
    for index in range(bins):
        lower, upper = index / bins, (index + 1) / bins
        selected = [
            item
            for item in observations
            if lower <= item.probability < upper
            or (index == bins - 1 and item.probability == upper)
        ]
        if selected:
            result.append(
                (
                    sum(item.probability for item in selected) / len(selected),
                    sum(item.outcome for item in selected) / len(selected),
                    len(selected),
                )
            )
    return tuple(result)


def _block_value(block: dict[str, float]) -> float:
    return block["sum_outcomes"] / block["count"]


def _validate_probability(value: float) -> float:
    if not 0.0 <= value <= 1.0:
        raise ValueError("probabilities must be between zero and one")
    return float(value)


def _require_aware(value: datetime, label: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must include a timezone")
