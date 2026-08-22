from datetime import datetime, timezone
from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel, Field

app = FastAPI(title="Safe Picks Forecasting Service", version="0.1.0")


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
