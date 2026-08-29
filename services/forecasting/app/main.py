from datetime import datetime, timedelta, timezone
import os
from typing import Any, Literal

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .providers.models import FixtureRecord
from .providers.quality import IngestionQualityPolicy, IngestionValidationError, validate_ingestion_quality
from .candidates import generate_candidates

app = FastAPI(title="Safe Picks Forecasting Service", version="0.1.0")


@app.exception_handler(IngestionValidationError)
async def ingestion_validation_error_handler(_: Request, error: IngestionValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": error.code,
                "message": str(error),
                "reasons": error.reasons,
                "audit": error.audit,
            }
        },
    )


class MarketCandidate(BaseModel):
    id: str
    fixtureId: str
    kickoff: str
    homeTeam: str
    awayTeam: str
    market: Literal[
        "goals_over_under",
        "both_teams_to_score",
        "match_result",
        "double_chance",
        "corners_over_under",
    ]
    selection: str
    line: float | None = None
    odds: float = Field(gt=1)
    marketQuotes: list[dict[str, float | str]] = Field(default_factory=list)
    modelProbability: float = Field(ge=0, le=1)
    impliedProbability: float = Field(ge=0, le=1)
    estimatedEdge: float
    fairProbability: float | None = None
    fairOdds: float | None = None
    uncertainty: float = Field(ge=0, le=1)
    dataCompleteness: float = Field(ge=0, le=1)
    calibrationError: float | None = Field(default=None, ge=0, le=1)
    distributionShift: float | None = Field(default=None, ge=0, le=1)
    correlationGroup: str | None = None
    modelVersion: str
    oddsObservedAt: str
    status: Literal["eligible", "rejected", "abstain"]
    reason: str


class CandidatesResponse(BaseModel):
    generatedAt: str
    source: Literal["development-mock", "forecasting-service"]
    sourceManifest: str | None = None
    candidates: list[MarketCandidate]
    warnings: list[str]
    diagnostics: list[dict[str, object]] = Field(default_factory=list)


class IngestionFixturePayload(BaseModel):
    provider: str | None = None
    source_event_id: str | None = None
    home_team: str | None = None
    away_team: str | None = None
    match_start_at: Any = None
    retrieved_at: Any = None
    observed_at: Any = None
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


class IngestionQualityRequest(BaseModel):
    snapshot_retrieved_at: Any = None
    reference_at: Any = None
    max_snapshot_age_seconds: float | None = Field(default=604800, ge=0)
    max_optional_missing_fraction: float | None = Field(default=None, ge=0, le=1)
    records: list[IngestionFixturePayload] = Field(default_factory=list)


class IngestionQualityResponse(BaseModel):
    status: Literal["pass", "rejected"]
    code: str | None = None
    message: str | None = None
    reasons: list[dict[str, object]]
    audit: dict[str, object]


def parse_api_timestamp(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value


def fixture_from_api(payload: IngestionFixturePayload) -> FixtureRecord:
    return FixtureRecord(
        provider=payload.provider,  # type: ignore[arg-type]
        source_event_id=payload.source_event_id,  # type: ignore[arg-type]
        home_team=payload.home_team,  # type: ignore[arg-type]
        away_team=payload.away_team,  # type: ignore[arg-type]
        match_start_at=parse_api_timestamp(payload.match_start_at),  # type: ignore[arg-type]
        retrieved_at=parse_api_timestamp(payload.retrieved_at),  # type: ignore[arg-type]
        observed_at=parse_api_timestamp(payload.observed_at),
        competition=payload.competition,
        season=payload.season,
        home_goals=payload.home_goals,
        away_goals=payload.away_goals,
        half_time_home_goals=payload.half_time_home_goals,
        half_time_away_goals=payload.half_time_away_goals,
        home_corners=payload.home_corners,
        away_corners=payload.away_corners,
        home_shots=payload.home_shots,
        away_shots=payload.away_shots,
        home_shots_on_target=payload.home_shots_on_target,
        away_shots_on_target=payload.away_shots_on_target,
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "forecasting", "mode": "model-backed"}


@app.get("/v1/candidates/today", response_model=CandidatesResponse)
def today_candidates() -> CandidatesResponse:
    result = generate_candidates(
        os.getenv("RAW_DATA_ROOT", "data/raw"),
        historical_league=os.getenv("FOOTBALL_DATA_LEAGUE") or None,
        min_training_matches=int(os.getenv("MODEL_MIN_TRAINING_MATCHES", "20")),
        calibration_artifact=os.getenv("CALIBRATION_ARTIFACT_PATH") or None,
    )
    return CandidatesResponse(
        generatedAt=result.generated_at.isoformat(),
        source="forecasting-service",
        sourceManifest=result.source_manifest,
        candidates=[MarketCandidate.model_validate(candidate) for candidate in result.candidates],
        warnings=list(result.warnings),
        diagnostics=list(result.diagnostics),
    )


@app.post("/v1/ingestion/quality", response_model=IngestionQualityResponse)
def ingestion_quality(payload: IngestionQualityRequest) -> IngestionQualityResponse:
    max_age = timedelta(seconds=payload.max_snapshot_age_seconds) if payload.max_snapshot_age_seconds is not None else None
    audit = validate_ingestion_quality(
        [fixture_from_api(record) for record in payload.records],
        snapshot_retrieved_at=parse_api_timestamp(payload.snapshot_retrieved_at),
        reference_at=parse_api_timestamp(payload.reference_at) if payload.reference_at is not None else None,
        policy=IngestionQualityPolicy(
            max_snapshot_age=max_age,
            max_optional_missing_fraction=payload.max_optional_missing_fraction,
        ),
    )
    return IngestionQualityResponse(
        status="pass",
        reasons=[],
        audit=audit,
    )
