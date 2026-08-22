export type MarketType =
  | "goals_over_under"
  | "both_teams_to_score"
  | "match_result"
  | "double_chance"
  | "corners_over_under";

export type CandidateStatus = "eligible" | "rejected" | "abstain";

export type CandidateRejectionCode =
  | "INVALID_ODDS"
  | "STALE_ODDS"
  | "MISSING_MARKET_PEERS"
  | "LOW_DATA_COMPLETENESS"
  | "HIGH_UNCERTAINTY"
  | "UNCALIBRATED_MODEL"
  | "DISTRIBUTION_SHIFT"
  | "LOW_EDGE"
  | "CORRELATED_SELECTION"
  | "UNSUPPORTED_MARKET";

export interface CandidateDecision {
  status: CandidateStatus;
  rejectionCode?: CandidateRejectionCode;
  reason: string;
}

export interface MarketQuote {
  selection: string;
  odds: number;
}

export interface MarketCandidate {
  id: string;
  fixtureId: string;
  kickoff: string;
  homeTeam: string;
  awayTeam: string;
  market: MarketType;
  selection: string;
  line?: number;
  odds: number;
  marketQuotes?: MarketQuote[];
  modelProbability: number;
  impliedProbability: number;
  estimatedEdge: number;
  fairProbability?: number;
  fairOdds?: number;
  uncertainty: number;
  dataCompleteness: number;
  calibrationError?: number;
  distributionShift?: number;
  correlationGroup?: string;
  modelVersion: string;
  oddsObservedAt: string;
  status: CandidateStatus;
  reason: string;
  rejectionCode?: CandidateRejectionCode;
}

export interface TodayCandidatesResponse {
  generatedAt: string;
  source: "development-mock" | "forecasting-service";
  candidates: MarketCandidate[];
  warnings: string[];
}

export interface DraftSlip {
  targetOdds: number;
  maxLegs: number;
  candidates: MarketCandidate[];
  combinedOdds: number;
  estimatedJointProbability: number;
  status: "draft" | "abstain";
  warnings: string[];
}
