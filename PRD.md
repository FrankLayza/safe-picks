# Safe Picks Product Requirements Document

Status: Approved product direction, implementation in progress
Version: 0.1
Last updated: 2026-08-23

## 1. Product Definition

Safe Picks is a Telegram-based football betting decision-support assistant. It evaluates multiple pre-match markets, compares calibrated model probabilities with timestamped odds, filters weak or unreliable candidates, and helps the user assemble a paper-trading slip.

The product does not guarantee outcomes, place bets, or claim that any selection is risk-free. `safe_bets` is a user-facing command name for a filtered, higher-confidence selection workflow.

## 2. Problem

Football bettors must manually compare many matches, markets, prices, and information sources. Generic tipsters often hide uncertainty, select only favorable historical results, and treat high probability as proof of value. Safe Picks should make the evidence, uncertainty, price, and rejection reasons visible.

## 3. Target User

The initial user is a football bettor who wants a concise daily shortlist and a way to remove weak legs from a multi-match slip. The first workflow accepts a target total odds and an optional maximum number of selections.

## 4. Goals

- Evaluate multiple eligible football markets for each fixture.
- Select the strongest qualifying opportunity by calibrated value and reliability.
- Allow the user to request a daily filtered slip.
- Allow the user to trim risky, stale, uncertain, or correlated selections.
- Support paper-trading measurement before any real-money use.
- Preserve timestamps, model versions, odds, warnings, and rejection reasons.
- Return `No qualifying bet` when evidence is insufficient.

## 5. Non-Goals

- Guaranteeing wins or profit.
- Calling any selection “safe” in the literal sense.
- Automatic wagering or bookmaker-account control in the MVP.
- SportyBet code generation before an official permitted integration is verified.
- Supporting every league and market at launch.
- Using post-match information or future data in a forecast.

## 6. Initial Market Scope

The first supported market families are:

1. Full-match goals totals.
2. Both teams to score.
3. Match result and double chance.
4. Match corners only where provider coverage and market calibration are sufficient.

Cards, player props, handicaps, first-half markets, and additional leagues require separate evidence and are out of the initial release unless explicitly approved.

## 7. User Experience

### `/safe_bets`

The bot asks for target combined decimal odds and a maximum number of legs. It evaluates the day's eligible fixtures, ranks market candidates, and creates a draft slip without adding weak legs solely to reach the requested odds.

Example:

```text
/safe_bets 3.00 3
```

The response must show each selected fixture, market, selection, odds, model probability, estimated edge, data freshness, model version, and warnings.

### `/trim`

The bot reviews the current draft and removes or flags legs with weak edge, high uncertainty, stale odds, incomplete critical data, poor market reliability, or excessive correlation. Each removal must have a reason.

### `/slip`

The bot displays the current draft, combined odds, estimated joint probability, selected legs, and warnings. It must communicate that accumulator probability is not simply guaranteed by individual leg confidence.

### `/help`

The bot explains the commands, paper-trading status, limitations, and responsible-use language.

## 8. Functional Requirements

| ID | Requirement | Acceptance criteria |
|---|---|---|
| FR-01 | Multi-market candidate generation | A fixture can return candidates from more than one supported market, each with a market-specific status and reason. |
| FR-02 | Forecast metadata | Every candidate includes probability, uncertainty, data completeness, model version, odds, and odds timestamp. |
| FR-03 | Safe-bets draft creation | A user can provide target odds and maximum legs and receive a draft ranked by eligible candidate value. |
| FR-04 | Risk trimming | The system can remove weak or correlated legs and explain each removal. |
| FR-05 | Slip inspection | The user can inspect combined odds, estimated joint probability, selected legs, and warnings. |
| FR-06 | Help and responsible wording | Commands explain limitations and do not promise guaranteed outcomes. |
| FR-07 | Abstention | The system can return `No qualifying bet` when gates fail or data is insufficient. |
| FR-08 | Paper-trading ledger | Accepted and rejected candidates can be recorded with timestamp, odds, model version, and settlement outcome. |
| FR-09 | Permitted data ingestion | Fixtures, results, odds, and advanced metrics are ingested with source and publication/retrieval timestamps. |
| FR-10 | Leakage prevention | Features are reconstructed from information available before the forecast timestamp and validated with chronological splits. |
| FR-11 | Model evaluation | Baselines and candidate models are compared using log loss, Brier score, calibration, and risk-coverage metrics. |
| FR-12 | SportyBet adapter boundary | Any future code-generation integration is isolated, permission-checked, and optional to the forecasting workflow. |

## 9. Quality Requirements

- The bot must fail closed when critical odds, lineup, or market data is missing or stale.
- User inputs must be validated at the command boundary.
- The bot must default to no more than one selection per fixture.
- Related legs must be detected or conservatively penalized.
- Raw source payloads, feature snapshots, model versions, and forecast timestamps must be auditable.
- Accuracy must not be reported without sample size, time range, selection rule, and uncertainty interval.
- Paper-trading results must include rejected candidates to avoid selection bias.
- Secrets must not be logged or committed.

## 10. Success Metrics

The product is ready for a broader paper-trading pilot only when it:

1. Beats frequency, Elo, and Poisson/Dixon-Coles baselines on untouched future data for the chosen market.
2. Demonstrates acceptable calibration by confidence and odds bucket.
3. Shows stable performance across multiple time windows.
4. Shows improved retained-pick quality when abstention is enabled.
5. Retains any simulated value after conservative price slippage, costs, limits, and selection bias.

No fixed 90% accuracy target is part of this PRD.

## 11. Dependencies and Risks

- Legal and contractual permission for sports data, odds storage, redistribution, and bookmaker integration.
- Reliable provider coverage for corners and other event markets.
- Accurate team, fixture, and market entity resolution.
- Lineup and injury information available at the actual decision time.
- Correlation and joint-probability estimation for multi-leg slips.
- Responsible-gambling and jurisdiction-specific product review.

## 12. Release Policy

### Development

Deterministic mock candidates are allowed for integration testing, but must be labeled as development data.

### Paper trading

Real provider data and timestamped odds may be used to create hypothetical selections. No wager is placed.

### Public release

Requires data licensing review, future-period evaluation, calibration evidence, monitoring, user-facing risk language, and a documented abstention policy.

### Real-money automation

Out of scope until separately approved after legal, security, provider, and bookmaker-integration review.

