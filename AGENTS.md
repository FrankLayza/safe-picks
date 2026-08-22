# Safe Picks Agent Instructions

## Read First

Before changing this project, read:

1. `CONTEXT.md`
2. `ARCHITECTURE.md`
3. The relevant research and review notes in the HIOS `ideas` folder

## Project Status

This is a planning-stage football betting decision-support project. Do not describe planned components as implemented. The current approved scope is a paper-trading MVP with a Telegram interface.

## Product Rules

- Treat “safe bets” as a user-facing label only; never promise safety, certainty, or guaranteed profit.
- The system must evaluate multiple markets and may abstain.
- Never force a prediction or add a weak leg to reach target odds.
- Default to one selection per match and account for correlated legs.
- Show probability, odds timestamp, model/calibration version, uncertainty, and rejection reasons.
- Keep forecasting, candidate ranking, slip construction, and Telegram presentation as separate responsibilities.
- Do not automate wagers in the MVP.

## Data and Modeling Rules

- Use only information available before the prediction timestamp.
- Store raw source snapshots and retrieval/publication timestamps.
- Use chronological train/validation/test splits; never use random splits for match time series.
- Compare against frequency, Elo, and Poisson/Dixon-Coles baselines.
- Evaluate log loss, Brier score, calibration, risk-coverage, and realistic paper-trading returns. Accuracy alone is insufficient.
- Calibrate each market separately on held-out temporal data.
- Treat head-to-head and recent averages as testable features, not conclusions.

## Engineering Rules

- Prefer small, explicit modules over premature abstractions.
- Use simple, straightforward comments only when they clarify non-obvious logic. Avoid decorative, narrative, or redundant comments.
- Validate external payloads and user inputs at boundaries.
- Version schemas, features, models, and calibration artifacts.
- Fail closed on stale or incomplete critical data.
- Do not add provider integrations without checking licensing, rate limits, and permitted use.
- Keep SportyBet integration behind an adapter and verify official support before implementing it.
- Add tests for selection gates, trimming, correlation rules, odds math, and abstention.

## Change Workflow

1. Inspect current files and status.
2. Update context or architecture when a decision changes.
3. Implement the smallest vertical slice.
4. Add focused tests.
5. Run relevant checks.
6. Confirm the implementation is valid and the relevant checks pass.
7. Review `git diff` and `git status`.
8. Stage only the files changed for this task with `git add`.
9. Commit the validated implementation with a concise message.
10. Document unresolved risks and next actions.

Every implementation task should end with a commit after validation. Never stage or commit unrelated changes made by the user, another agent, or an external tool. If unrelated changes are present, leave them untouched and stage only the files owned by the current task.

## Prohibited Shortcuts

- No fabricated performance numbers.
- No leakage from final lineups, post-match statistics, revised ratings, or future odds.
- No cherry-picked backtests.
- No hidden filtering that reports only successful picks.
- No automated betting or credential collection without explicit, verified authorization.

## Communication

When reporting a prediction or system result, distinguish:

- Established evidence
- Observed experiment result
- Engineering recommendation
- Untested hypothesis

Use “No qualifying bet” when the evidence is insufficient.
