from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .providers.models import FixtureRecord
from .providers.quality import IngestionQualityPolicy, IngestionValidationError, validate_ingestion_quality

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
    candidates: list[MarketCandidate]
    warnings: list[str]


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


def mock_candidates() -> list[MarketCandidate]:
    observed = datetime.now(timezone.utc).isoformat()
    return [
        MarketCandidate(
            id="dev-001",
            fixtureId="fixture-dev-001",
            kickoff="2026-08-23T18:00:00Z",
            homeTeam="Development FC",
            awayTeam="Example United",
            market="goals_over_under",
            selection="Over 1.5 goals",
            line=1.5,
            odds=1.32,
            modelProbability=0.78,
            impliedProbability=1 / 1.32,
            estimatedEdge=0.022,
            uncertainty=0.12,
            dataCompleteness=0.92,
            calibrationError=0.04,
            distributionShift=0.02,
            correlationGroup="fixture-dev-001-goals",
            marketQuotes=[
                {"selection": "Over 1.5 goals", "odds": 1.32},
                {"selection": "Under 1.5 goals", "odds": 3.80},
            ],
            modelVersion="mock-v0",
            oddsObservedAt=observed,
            status="eligible",
            reason="Development-only deterministic candidate.",
        ),
        MarketCandidate(
            id="dev-002",
            fixtureId="fixture-dev-002",
            kickoff="2026-08-23T20:00:00Z",
            homeTeam="Sample Athletic",
            awayTeam="Test City",
            market="corners_over_under",
            selection="Over 8.5 corners",
            line=8.5,
            odds=1.72,
            modelProbability=0.64,
            impliedProbability=1 / 1.72,
            estimatedEdge=0.012,
            uncertainty=0.19,
            dataCompleteness=0.84,
            calibrationError=0.05,
            distributionShift=0.03,
            correlationGroup="fixture-dev-002-corners",
            marketQuotes=[
                {"selection": "Over 8.5 corners", "odds": 1.72},
                {"selection": "Under 8.5 corners", "odds": 1.95},
            ],
            modelVersion="mock-v0",
            oddsObservedAt=observed,
            status="eligible",
            reason="Development-only deterministic candidate.",
        ),
    ]


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
    return {"status": "ok", "service": "forecasting", "mode": "development-mock"}


@app.get("/v1/candidates/today", response_model=CandidatesResponse)
def today_candidates() -> CandidatesResponse:
    return CandidatesResponse(
        generatedAt=datetime.now(timezone.utc).isoformat(),
        source="development-mock",
        candidates=mock_candidates(),
        warnings=["This response uses deterministic mock data; it is not a forecast or betting advice."],
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
