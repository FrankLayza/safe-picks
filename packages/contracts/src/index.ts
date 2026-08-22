export type MarketType =
  | "goals_over_under"
  | "both_teams_to_score"
  | "match_result"
  | "double_chance"
  | "corners_over_under";

export type CandidateStatus = "eligible" | "rejected" | "abstain";

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
  modelProbability: number;
  impliedProbability: number;
  estimatedEdge: number;
  uncertainty: number;
  dataCompleteness: number;
  modelVersion: string;
  oddsObservedAt: string;
  status: CandidateStatus;
  reason: string;
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
