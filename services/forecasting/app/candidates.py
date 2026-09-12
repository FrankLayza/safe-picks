"""Model-backed candidate generation from accepted current-odds manifests."""

import json
import os
from bisect import bisect_left
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from .goals import MODEL_VERSION, GoalsPrediction, PoissonGoalsModel, PoissonModelConfig
from .providers.identity import normalize_identity_label, resolve_team_id
from .providers.models import FixtureRecord, OddsQuote
from .replay import HistoricalManifestReplay, ReplayedFixture


@dataclass(frozen=True)
class CandidateGenerationResult:
    generated_at: datetime
    source_manifest: str | None
    candidates: tuple[dict[str, Any], ...]
    warnings: tuple[str, ...]
    diagnostics: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class CalibrationSpec:
    version: str
    thresholds: tuple[float, ...]
    values: tuple[float, ...]
    error: float

    def predict(self, probability: float) -> float:
        if not self.thresholds or len(self.thresholds) != len(self.values):
            raise ValueError("calibration artifact has invalid thresholds")
        index = bisect_left(self.thresholds, probability)
        return max(0.0, min(1.0, self.values[min(index, len(self.values) - 1)]))


def generate_candidates(
    raw_root: str | Path,
    *,
    now: datetime | None = None,
    historical_league: str | None = None,
    min_training_matches: int = 20,
    model_config: PoissonModelConfig | None = None,
    calibration_artifact: str | Path | None = None,
    max_kickoff_hours: float | None = None,
) -> CandidateGenerationResult:
    """Generate candidates using only data available at the odds snapshot time.

    The function is deliberately fail-closed: missing manifests, insufficient
    history, incomplete markets, and missing calibration produce diagnostics and
    abstentions rather than a development fallback.
    """
    generated_at = now or datetime.now(timezone.utc)
    _require_aware(generated_at, "candidate generation time")
    if min_training_matches <= 0:
        raise ValueError("min_training_matches must be greater than zero")

    root = Path(raw_root)
    manifest_path, manifest, manifest_diagnostics = _latest_accepted_manifest(root)
    if manifest is None:
        return CandidateGenerationResult(
            generated_at,
            None,
            (),
            ("No accepted current-odds manifest is available.",),
            tuple(manifest_diagnostics),
        )

    retrieved_at = _timestamp(manifest.get("retrieved_at"), "manifest.retrieved_at")
    if retrieved_at > generated_at:
        return CandidateGenerationResult(
            generated_at,
            str(manifest_path),
            (),
            ("The latest accepted odds manifest is future-dated.",),
            tuple(
                [
                    *manifest_diagnostics,
                    _reason(
                        "odds_manifest_timestamp_in_future",
                        {"manifest": str(manifest_path), "retrieved_at": retrieved_at.isoformat()},
                    ),
                ]
            ),
        )

    events = {
        str(value.get("source_event_id")): value
        for value in manifest.get("events", [])
        if isinstance(value, dict) and value.get("source_event_id")
    }
    if not events:
        return CandidateGenerationResult(
            generated_at,
            str(manifest_path),
            (),
            ("The accepted odds manifest contains no accepted events.",),
            tuple([*manifest_diagnostics, _reason("no_accepted_odds_events", {})]),
        )

    try:
        history = list(
            HistoricalManifestReplay(root, league=historical_league).replay(retrieved_at).fixtures
        )
    except ValueError as exc:
        return CandidateGenerationResult(
            generated_at,
            str(manifest_path),
            (),
            ("Historical replay failed; no forecast was produced.",),
            tuple(
                [
                    *manifest_diagnostics,
                    _reason("historical_replay_failed", {"message": str(exc)}),
                ]
            ),
        )

    calibrators, calibration_diagnostics = _load_calibration_artifact(calibration_artifact)
    candidates: list[dict[str, Any]] = []
    diagnostics = [*manifest_diagnostics, *calibration_diagnostics]
    quotes_by_event: dict[str, list[OddsQuote]] = {}
    for value in manifest.get("quotes", []):
        try:
            quote = _quote_from_manifest(value)
        except ValueError as exc:
            diagnostics.append(_reason("invalid_odds_manifest_quote", {"message": str(exc)}))
            continue
        if quote.source_event_id in events:
            quotes_by_event.setdefault(quote.source_event_id, []).append(quote)
        else:
            diagnostics.append(
                _reason("odds_quote_unknown_event", {"source_event_id": quote.source_event_id})
            )

    for source_event_id, event in events.items():
        event_candidates, event_diagnostics = _generate_event_candidates(
            event,
            quotes_by_event.get(source_event_id, []),
            history,
            retrieved_at,
            min_training_matches,
            model_config,
            calibrators,
            generated_at=generated_at,
            max_kickoff_hours=max_kickoff_hours,
        )
        candidates.extend(event_candidates)
        diagnostics.extend(event_diagnostics)

    warnings = [
        "Candidates are model-backed development outputs and are not guaranteed betting advice."
    ]
    if not candidates:
        warnings.append("No complete supported market could be generated from the accepted manifest.")
    if not calibrators:
        warnings.append("Calibration artifact unavailable; generated candidates abstain until calibration is supplied.")
    return CandidateGenerationResult(
        generated_at,
        str(manifest_path),
        tuple(sorted(candidates, key=lambda item: (-item["rankingScore"], item["id"]))),
        tuple(warnings),
        tuple(diagnostics),
    )


def _generate_event_candidates(
    event: dict[str, Any],
    quotes: list[OddsQuote],
    history: list[ReplayedFixture],
    as_of: datetime,
    min_training_matches: int,
    model_config: PoissonModelConfig | None,
    calibrators: dict[str, CalibrationSpec],
    generated_at: datetime | None = None,
    max_kickoff_hours: float | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    diagnostics: list[dict[str, Any]] = []
    source_event_id = str(event.get("source_event_id", ""))
    fixture_id = str(event.get("canonical_fixture_id", ""))
    home_team = str(event.get("home_team", ""))
    away_team = str(event.get("away_team", ""))
    canonical_home = str(event.get("canonical_home_team") or normalize_identity_label(home_team, "home_team"))
    canonical_away = str(event.get("canonical_away_team") or normalize_identity_label(away_team, "away_team"))
    competition_id = str(event.get("canonical_competition_id", ""))
    kickoff = _timestamp(event.get("match_start_at"), "event.match_start_at")
    if not fixture_id or not competition_id:
        return [], [_reason("missing_canonical_fixture_identity", {"source_event_id": source_event_id})]

    if generated_at is not None and kickoff <= generated_at:
        return [], [
            _reason(
                "odds_event_already_started",
                {
                    "source_event_id": source_event_id,
                    "canonical_fixture_id": fixture_id,
                    "kickoff": kickoff.isoformat(),
                    "generated_at": generated_at.isoformat(),
                },
            )
        ]

    if (
        generated_at is not None
        and max_kickoff_hours is not None
        and kickoff > generated_at + timedelta(hours=max_kickoff_hours)
    ):
        return [], [
            _reason(
                "fixture_outside_kickoff_horizon",
                {
                    "source_event_id": source_event_id,
                    "canonical_fixture_id": fixture_id,
                    "kickoff": kickoff.isoformat(),
                    "max_kickoff_hours": max_kickoff_hours,
                },
            )
        ]

    competition_history = [
        _canonicalize_fixture(item)
        for item in history
        if item.identity.canonical_competition_id == competition_id
    ]
    try:
        model = PoissonGoalsModel.fit(competition_history, as_of, model_config)
    except ValueError as exc:
        return [], [
            _reason(
                "model_unavailable",
                {"source_event_id": source_event_id, "message": str(exc)},
            )
        ]
    home_matches = int(event.get("historical_home_matches", 0) or 0)
    away_matches = int(event.get("historical_away_matches", 0) or 0)
    if model.training_matches < min_training_matches or min(home_matches, away_matches) < 1:
        return [], [
            _reason(
                "insufficient_training_matches",
                {
                    "source_event_id": source_event_id,
                    "training_matches": model.training_matches,
                    "min_training_matches": min_training_matches,
                    "historical_home_matches": home_matches,
                    "historical_away_matches": away_matches,
                },
            )
        ]

    prediction = model.predict(canonical_home, canonical_away)
    completeness = min(1.0, min(home_matches, away_matches) / max(1, min_training_matches))
    uncertainty = min(1.0, 1.0 / (model.training_matches**0.5))
    grouped = _group_quotes(quotes)
    output: list[dict[str, Any]] = []
    for (bookmaker, market, line), group in grouped.items():
        probabilities = _market_probabilities(market, line, group, event, prediction)
        if probabilities is None:
            diagnostics.append(
                _reason(
                    "unsupported_or_incomplete_market",
                    {
                        "source_event_id": source_event_id,
                        "bookmaker": bookmaker,
                        "market": market,
                        "line": line,
                    },
                )
            )
            continue
        calibrated = _calibrate_market_probabilities(market, probabilities, calibrators)
        for quote, model_probability, calibration_error in calibrated:
            status = "eligible" if calibration_error is not None else "abstain"
            reason = (
                "Generated from the accepted odds manifest and leakage-safe goals model."
                if status == "eligible"
                else "Calibration artifact unavailable; abstaining from actionable selection."
            )
            output.append(
                _candidate_payload(
                    event,
                    quote,
                    fixture_id,
                    kickoff,
                    market,
                    line,
                    group,
                    model_probability,
                    uncertainty,
                    completeness,
                    calibration_error,
                    status,
                    reason,
                    model,
                )
            )
    return output, diagnostics


def _candidate_payload(
    event: dict[str, Any],
    quote: OddsQuote,
    fixture_id: str,
    kickoff: datetime,
    market: str,
    line: float | None,
    group: list[OddsQuote],
    model_probability: float,
    uncertainty: float,
    completeness: float,
    calibration_error: float | None,
    status: str,
    reason: str,
    model: PoissonGoalsModel,
) -> dict[str, Any]:
    market_name = _api_market_name(market)
    market_line = line if market == "total" else None
    implied = 1.0 / quote.odds
    fair_probability = _fair_probability(quote, group)
    edge = model_probability - fair_probability
    quality_penalty, ranking_score = _ranking_values(
        edge,
        uncertainty,
        completeness,
        calibration_error,
        0.0,
        status == "eligible",
    )
    return {
        "id": ":".join(
            [fixture_id, market_name, normalize_identity_label(quote.selection, "selection"), str(line or "none"), quote.bookmaker]
        ),
        "fixtureId": fixture_id,
        "kickoff": kickoff.isoformat(),
        "homeTeam": str(event.get("home_team", "")),
        "awayTeam": str(event.get("away_team", "")),
        "market": market_name,
        "selection": quote.selection,
        "line": market_line,
        "odds": quote.odds,
        "marketQuotes": [{"selection": item.selection, "odds": item.odds} for item in group],
        "modelProbability": model_probability,
        "impliedProbability": implied,
        "estimatedEdge": edge,
        "expectedValue": model_probability * quote.odds - 1.0,
        "qualityPenalty": quality_penalty,
        "rankingScore": ranking_score,
        "fairProbability": fair_probability,
        "fairOdds": 1.0 / fair_probability,
        "uncertainty": uncertainty,
        "dataCompleteness": completeness,
        "calibrationError": calibration_error,
        "distributionShift": 0.0,
        "correlationGroup": fixture_id,
        "correlationGroups": [
            fixture_id,
            f"team:{event.get('canonical_home_team_id', '')}",
            f"team:{event.get('canonical_away_team_id', '')}",
        ],
        "modelVersion": model_version(model, calibration_error is not None),
        "oddsObservedAt": (quote.observed_at or quote.retrieved_at).isoformat(),
        "status": status,
        "reason": reason,
    }


def model_version(model: PoissonGoalsModel, calibrated: bool) -> str:
    return f"{MODEL_VERSION}+{'calibrated' if calibrated else 'raw'}"


def _fair_probability(quote: OddsQuote, group: list[OddsQuote]) -> float:
    total = sum(1.0 / item.odds for item in group)
    if total <= 0:
        raise ValueError("market group has no valid implied probability")
    return (1.0 / quote.odds) / total


def _ranking_values(
    edge: float,
    uncertainty: float,
    completeness: float,
    calibration_error: float | None,
    distribution_shift: float,
    eligible: bool,
) -> tuple[float, float]:
    positive_edge = max(0.0, edge)
    if not eligible or calibration_error is None:
        return positive_edge, 0.0
    reliability = (
        _unit_interval(completeness)
        * (1.0 - _unit_interval(uncertainty))
        * (1.0 - _unit_interval(calibration_error))
        * (1.0 - _unit_interval(distribution_shift))
    )
    score = positive_edge * reliability
    return positive_edge - score, score


def _unit_interval(value: float) -> float:
    return max(0.0, min(1.0, value))


def _calibrate_market_probabilities(
    market: str,
    probabilities: list[tuple[OddsQuote, float, str]],
    calibrators: dict[str, CalibrationSpec],
) -> list[tuple[OddsQuote, float, float | None]]:
    available = [calibrators.get(key) for _, _, key in probabilities]
    if market == "match result":
        if any(spec is None for spec in available):
            return [(quote, probability, None) for quote, probability, _ in probabilities]
        values = [
            spec.predict(probability)
            for (_, probability, _), spec in zip(probabilities, available)
            if spec is not None
        ]
        total = sum(values)
        if total <= 0:
            return [(quote, probability, None) for quote, probability, _ in probabilities]
        return [
            (quote, value / total, spec.error if spec is not None else None)
            for (quote, _, _), value, spec in zip(probabilities, values, available)
        ]

    if len(probabilities) == 2:
        direct = [index for index, spec in enumerate(available) if spec is not None]
        if not direct:
            return [(quote, probability, None) for quote, probability, _ in probabilities]
        if len(direct) == 1:
            index = direct[0]
            spec = available[index]
            if spec is None:
                return [(quote, probability, None) for quote, probability, _ in probabilities]
            calibrated = spec.predict(probabilities[index][1])
            values = [1.0 - calibrated, 1.0 - calibrated]
            values[index] = calibrated
            values[1 - index] = 1.0 - calibrated
            return [
                (quote, values[item_index], spec.error)
                for item_index, (quote, _, _) in enumerate(probabilities)
            ]
        values = [
            spec.predict(probability)
            for (_, probability, _), spec in zip(probabilities, available)
            if spec is not None
        ]
        total = sum(values)
        if total <= 0:
            return [(quote, probability, None) for quote, probability, _ in probabilities]
        return [
            (quote, value / total, max(spec.error for spec in available if spec is not None))
            for (quote, _, _), value in zip(probabilities, values)
        ]

    return [(quote, probability, None) for quote, probability, _ in probabilities]


def _market_probabilities(
    market: str,
    line: float | None,
    group: list[OddsQuote],
    event: dict[str, Any],
    prediction: GoalsPrediction,
) -> list[tuple[OddsQuote, float, str]] | None:
    if market == "match result":
        result: list[tuple[OddsQuote, float, str]] = []
        home_id = str(event.get("canonical_home_team_id", ""))
        away_id = str(event.get("canonical_away_team_id", ""))
        seen: set[str] = set()
        for quote in group:
            selection = normalize_identity_label(quote.selection, "selection")
            if selection == "draw":
                key, probability, calibration_key = "draw", prediction.draw_probability, "draw"
            else:
                team_id = resolve_team_id(quote.provider, quote.selection)
                if team_id == home_id:
                    key, probability, calibration_key = "home", prediction.home_win_probability, "home_win"
                elif team_id == away_id:
                    key, probability, calibration_key = "away", prediction.away_win_probability, "away_win"
                else:
                    return None
            if key in seen:
                return None
            seen.add(key)
            result.append((quote, probability, calibration_key))
        return result if seen == {"home", "draw", "away"} else None
    if market == "total" and line is not None:
        if len(group) != 2:
            return None
        result: list[tuple[OddsQuote, float, str]] = []
        for quote in group:
            selection = normalize_identity_label(quote.selection, "selection")
            if selection == "over":
                probability = _total_probability(prediction, line, True)
                calibration_key = f"over_{line:g}"
            elif selection == "under":
                probability = _total_probability(prediction, line, False)
                calibration_key = f"under_{line:g}"
            else:
                return None
            result.append((quote, probability, calibration_key))
        return result
    if market == "both teams to score" and len(group) == 2:
        result: list[tuple[OddsQuote, float, str]] = []
        for quote in group:
            selection = normalize_identity_label(quote.selection, "selection")
            if selection in {"yes", "btts", "both teams to score"}:
                probability = prediction.btts_probability
                calibration_key = "btts"
            elif selection in {"no", "not btts", "no btts"}:
                probability = 1.0 - prediction.btts_probability
                calibration_key = "no_btts"
            else:
                return None
            result.append((quote, probability, calibration_key))
        return result
    return None


def _total_probability(prediction: GoalsPrediction, line: float, over: bool) -> float:
    return sum(
        prediction.score_matrix[home][away]
        for home in range(len(prediction.score_matrix))
        for away in range(len(prediction.score_matrix[home]))
        if (home + away > line) == over
    )


def _group_quotes(quotes: Iterable[OddsQuote]) -> dict[tuple[str, str, float | None], list[OddsQuote]]:
    grouped: dict[tuple[str, str, float | None], list[OddsQuote]] = {}
    for quote in quotes:
        market = quote.canonical_market or quote.market
        grouped.setdefault((quote.bookmaker, market, quote.line), []).append(quote)
    return grouped


def _canonicalize_fixture(item: ReplayedFixture) -> ReplayedFixture:
    record = replace(
        item.record,
        home_team=item.identity.canonical_home_team,
        away_team=item.identity.canonical_away_team,
        competition=item.identity.canonical_competition,
    )
    return replace(item, record=record)


def _quote_from_manifest(value: object) -> OddsQuote:
    if not isinstance(value, dict):
        raise ValueError("quote must be an object")
    try:
        observed = value.get("observed_at")
        return OddsQuote(
            provider=str(value["provider"]),
            source_event_id=str(value["source_event_id"]),
            bookmaker=str(value["bookmaker"]),
            market=str(value.get("canonical_market") or value["market"]),
            selection=str(value["selection"]),
            odds=float(value["odds"]),
            match_start_at=_timestamp(value["match_start_at"], "quote.match_start_at"),
            retrieved_at=_timestamp(value["retrieved_at"], "quote.retrieved_at"),
            observed_at=_timestamp(observed, "quote.observed_at") if observed else None,
            line=float(value["line"]) if value.get("line") is not None else None,
            canonical_market=str(value.get("canonical_market") or "") or None,
            canonical_selection=str(value.get("canonical_selection") or "") or None,
            canonical_line=str(value.get("canonical_line") or "") or None,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("quote is missing a valid field") from exc


def _latest_accepted_manifest(root: Path) -> tuple[Path | None, dict[str, Any] | None, list[dict[str, Any]]]:
    directory = root / "normalized" / "the-odds-api"
    diagnostics: list[dict[str, Any]] = []
    accepted: list[tuple[datetime, Path, dict[str, Any]]] = []
    if not directory.exists():
        diagnostics.append(_reason("odds_manifest_directory_missing", {"directory": str(directory)}))
        return None, None, diagnostics
    for path in sorted(directory.rglob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("manifest must be an object")
            retrieved = _timestamp(payload.get("retrieved_at"), "manifest.retrieved_at")
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            diagnostics.append(_reason("invalid_odds_manifest", {"path": str(path), "message": str(exc)}))
            continue
        if payload.get("status") not in {"pass", "partial"} or int(payload.get("event_count", 0) or 0) <= 0:
            continue
        accepted.append((retrieved, path, payload))
    if not accepted:
        diagnostics.append(_reason("no_accepted_odds_manifest", {"directory": str(directory)}))
        return None, None, diagnostics
    retrieved, path, payload = max(accepted, key=lambda value: (value[0], str(value[1])))
    diagnostics.append(_reason("odds_manifest_selected", {"path": str(path), "retrieved_at": retrieved.isoformat()}))
    return path, payload, diagnostics


def _load_calibration_artifact(path: str | Path | None) -> tuple[dict[str, CalibrationSpec], list[dict[str, Any]]]:
    if path is None:
        path = os.getenv("CALIBRATION_ARTIFACT_PATH") or None
    if not path:
        return {}, [_reason("calibration_artifact_unavailable", {})]
    artifact_path = Path(path)
    if not artifact_path.exists():
        return {}, [_reason("calibration_artifact_unavailable", {"path": str(artifact_path)})]
    try:
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
        markets = payload.get("markets", {})
        if not isinstance(markets, dict):
            raise ValueError("markets must be an object")
        result: dict[str, CalibrationSpec] = {}
        for market, value in markets.items():
            if not isinstance(value, dict):
                continue
            result[str(market)] = CalibrationSpec(
                str(payload.get("version", "isotonic-v1")),
                tuple(float(item) for item in value["thresholds"]),
                tuple(float(item) for item in value["values"]),
                float(value.get("calibration_error", 0.0)),
            )
        if not result:
            raise ValueError("artifact contains no market calibrators")
        return result, []
    except (OSError, UnicodeDecodeError, KeyError, TypeError, ValueError) as exc:
        return {}, [_reason("invalid_calibration_artifact", {"path": str(artifact_path), "message": str(exc)})]


def _api_market_name(market: str) -> str:
    return {
        "match result": "match_result",
        "total": "goals_over_under",
        "both teams to score": "both_teams_to_score",
    }.get(market, market)


def _timestamp(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO timestamp") from exc
    _require_aware(parsed, field)
    return parsed


def _require_aware(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must include a timezone")


def _reason(code: str, details: dict[str, Any]) -> dict[str, Any]:
    return {"code": code, "details": details}
