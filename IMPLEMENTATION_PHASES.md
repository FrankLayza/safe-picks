# Safe Picks Implementation Phases

Status: In progress
Last updated: 2026-08-29

This plan is the implementation companion to [PRD.md](PRD.md). Every phase references PRD requirement IDs. A requirement is only complete when its acceptance criteria in the PRD are met and verified.

## Status Legend

- `[x]` Complete and verified for the current scope.
- `[~]` Partially implemented; scaffold or development-only behavior exists.
- `[ ]` Not implemented.

## Phase 0: Project Foundation

PRD coverage: FR-06, supporting infrastructure for FR-01 through FR-05

- [x] Create the pnpm TypeScript workspace.
- [x] Create the Telegram bot application boundary in `apps/bot`.
- [x] Create the Python FastAPI forecasting boundary in `services/forecasting`.
- [x] Create shared TypeScript contracts in `packages/contracts`.
- [x] Add environment template and ignore rules.
- [x] Add project context, architecture, agent instructions, and README.
- [x] Add health endpoint for the forecasting service.
- [x] Validate TypeScript typechecking and build.
- [x] Validate the Python service import and mock candidate response.

Exit criteria: The repository installs, builds, and exposes a testable service boundary. Complete.

## Phase 1: Telegram Command Slice

PRD coverage: FR-03, FR-04, FR-05, FR-06, partial FR-07

- [x] Add `/safe_bets <target odds> <max legs>` command.
- [x] Add `/trim` command.
- [x] Add `/slip` command.
- [x] Add `/help` command.
- [x] Validate target odds and maximum-leg input.
- [x] Display odds, model probability, edge, and warnings for mock candidates.
- [x] Implement one-selection-per-fixture behavior.
- [x] Implement basic edge-ranked draft construction.
- [x] Implement basic trimming behavior.
- [ ] Add persistent user drafts instead of in-memory drafts.
- [ ] Return structured rejection reasons from the forecasting service.
- [x] Add focused tests for command parsing and slip behavior.

Exit criteria: Core commands work against the development service contract and parsing/selection/trimming/abstention behavior has automated tests. Core slice complete; persistence and service-level rejection contracts remain.

## Phase 2: Candidate and Decision Contracts

PRD coverage: FR-01, FR-02, FR-07, FR-12

- [x] Define shared candidate, quote, decision, and slip types.
- [x] Return multiple development market candidates with decision metadata.
- [ ] Add market registry with market-specific settlement rules.
- [x] Add candidate eligibility gates for data completeness, freshness, calibration, and distribution shift.
- [x] Add explicit abstention and rejection reason codes.
- [x] Add value calculation using de-vigged market probabilities and a configurable minimum edge.
- [x] Add correlation groups and duplicate-market suppression.
- [ ] Add adapter interface for future bookmaker integrations.

Exit criteria: Candidates are evaluated by the shared decision layer and are either eligible with fair-price metadata or rejected with a machine-readable reason. Market settlement registry and bookmaker adapter remain open.

## Phase 3: Permitted Data Ingestion

PRD coverage: FR-09, FR-10

- [x] Select one permitted football results/fixtures source for research backfill: Football-Data.co.uk, subject to licence review.
- [x] Select one permitted odds source for current snapshots: The Odds API, subject to account and plan verification.
- [x] Define provider registry, license status, rate limits, and retention rules.
- [x] Normalize Football-Data CSV fixtures/results/stats in the first scheduled ingestion job.
- [x] Normalize scheduled The Odds API events and bookmaker quotes with event, retrieval, and bookmaker timestamps.
- [x] Save immutable Football-Data raw payloads to the local file snapshot store and write normalized manifests; PostgreSQL/object storage is not implemented.
- [x] Add canonical identity resolution for teams, competitions, fixtures, and markets.
- [x] Add exact duplicate detection and conflicting correction checks for normalized manifests.
- [x] Add freshness and broader missingness checks with machine-readable rejection reasons; identity and timestamp fields fail closed.
- [x] Expose ingestion quality rejection codes through the forecasting service API for downstream diagnostics.
- [x] Add historical replay so fixtures can be reconstructed as-of any forecast time from eligible normalized manifests.
- [x] Link current odds events to canonical historical competitions and teams, rejecting ambiguous, stale, incomplete, started, or unmatched events with machine-readable reasons.

Exit criteria: A historical fixture and odds record can be reproduced exactly from saved source snapshots and normalized into the canonical schema. Current adapter tests cover parsing and snapshots; provider licence/account verification and durable ingestion remain.

## Phase 4: Football Feature Pipeline

PRD coverage: FR-02, FR-09, FR-10

- [x] Build opponent-adjusted team strength features.
- [x] Build home/away and rest/congestion features.
- [x] Build exponentially weighted recent-form features.
- [ ] Add expected goals and shot-quality features where licensed data supports them.
- [ ] Add lineup, injury, suspension, and availability snapshots.
- [ ] Add corner features only after provider definitions are stable.
- [x] Store feature version, source IDs, and forecast timestamp.
- [x] Add leakage tests for post-match and future information.

Exit criteria: Features are reproducible using only pre-match information and pass leakage checks.

## Phase 5: Baseline Models and Calibration

PRD coverage: FR-01, FR-02, FR-10, FR-11

- [ ] Implement class-frequency and home-advantage baselines.
- [ ] Implement Elo baseline.
- [x] Implement Poisson/Dixon-Coles goals baseline.
- [ ] Implement regularized logistic/Poisson models.
- [ ] Add one gradient-boosting comparison only after baseline data quality is proven.
- [x] Use chronological train, validation, and untouched future test windows.
- [x] Calibrate each supported baseline market on held-out temporal data.
- [x] Store model, feature, and calibration versions.

Exit criteria: Baselines and candidate models have comparable future-period reports and calibration curves.

## Phase 6: Multi-Market Selector and Slip Quality

PRD coverage: FR-01 through FR-07, FR-11

- [~] Generate model-backed candidates for goals, BTTS, and result from the latest accepted odds manifest; double chance and corners remain disabled pending validated market/model support.
- [x] Rank by de-vigged calibrated edge after explicit completeness, uncertainty, calibration-error, and distribution-shift penalties.
- [x] Reject short-price candidates unless they clear configurable stronger de-vigged edge and expected-value thresholds.
- [x] Apply one-leg-per-match defaults in draft construction and verify with automated tests.
- [x] Detect correlated legs across markets and fixtures using explicit fixture and canonical-team keys; reject weaker overlaps with an auditable reason.
- [ ] Estimate joint slip probability conservatively.
- [ ] Make `trim` explain every removed leg.
- [ ] Return `No qualifying bet` when no candidate passes gates.
- [ ] Add candidate and slip decision audit records.

Exit criteria: The selector chooses a market because it is the best validated opportunity, not because it has the highest raw probability or fills a target odds number.

## Phase 7: Paper-Trading and Evaluation

PRD coverage: FR-08, FR-11, success metrics

- [ ] Create paper-trade ledger for accepted and rejected candidates.
- [ ] Record decision timestamp, available odds, closing odds, model version, and settlement.
- [ ] Report log loss, Brier score, calibration, accuracy, and confusion matrices where applicable.
- [ ] Report by league, season/window, market, odds range, and confidence bucket.
- [ ] Plot risk-coverage curves for abstention.
- [ ] Simulate realistic slippage, costs, limits, and selection rules.
- [ ] Run unseen-time-window and unseen-competition checks.
- [ ] Define written go/no-go decision for the next release.

Exit criteria: Performance claims are reproducible, uncertainty is reported, and the system either earns a broader paper-trading pilot or remains an analytics prototype.

## Phase 8: Production Hardening

PRD coverage: quality requirements, FR-09, FR-12

- [ ] Add PostgreSQL persistence and migrations.
- [ ] Add authentication, rate limits, and durable Telegram user state.
- [ ] Add monitoring for source health, missingness, latency, drift, and calibration.
- [ ] Add model rollback and immutable model registry behavior.
- [ ] Add operational audit logs without secrets or unnecessary personal data.
- [ ] Complete data licensing and responsible-gambling review.
- [ ] Verify whether SportyBet provides an official permitted code/slip integration.
- [ ] Implement the bookmaker adapter only if approved and technically supported.

Exit criteria: The system is observable, recoverable, permissioned, and still able to abstain safely.

## Phase 9: Release Review

PRD coverage: release policy and all release-blocking requirements

- [ ] Confirm no unsupported market is presented to users.
- [ ] Confirm no “guaranteed” or “risk-free” claims appear in bot responses.
- [ ] Confirm paper-trading evidence is based on future data and includes rejected candidates.
- [ ] Confirm secrets, provider permissions, and retention rules.
- [ ] Confirm user-facing warnings and responsible-use guidance.
- [ ] Confirm rollback and no-qualifying-bet behavior.
- [ ] Approve or reject public release in a documented decision.

Exit criteria: Release approval is evidence-based and does not depend on a headline accuracy number.

## Traceability Matrix

| PRD requirement | Primary phase | Current status |
|---|---|---|
| FR-01 Multi-market candidates | Phase 2, Phase 6 | `[~]` model-backed goals/BTTS/result generation exists; selector and additional markets remain open |
| FR-02 Forecast metadata | Phase 2, Phase 5 | `[~]` contract and model provenance exist; production calibration artifacts remain operator-supplied |
| FR-03 Safe-bets draft | Phase 1 | `[x]` works with model-backed candidates and tested quality-adjusted selection behavior |
| FR-04 Risk trimming | Phase 1, Phase 6 | `[~]` basic scaffold only |
| FR-05 Slip inspection | Phase 1 | `[x]` works with in-memory draft and tested calculations |
| FR-06 Help and wording | Phase 1 | `[x]` command and warnings exist |
| FR-07 Abstention | Phase 1, Phase 2, Phase 6 | `[~]` empty-set and gate rejection exist; production calibration gates remain unvalidated |
| FR-08 Paper ledger | Phase 7 | `[ ]` |
| FR-09 Permitted ingestion | Phase 3 | `[~]` results and current-odds jobs, identity, replay, quality checks, and local manifests exist; account/licence verification and durable storage remain |
| FR-10 Leakage prevention | Phase 4, Phase 5 | `[~]` feature and walk-forward checks exist; broader market and provider coverage remain |
| FR-11 Model evaluation | Phase 5, Phase 7 | `[~]` baseline metrics/calibration report exists; comparative and paper-trading evaluation remain |
| FR-12 SportyBet boundary | Phase 8 | `[ ]` |
