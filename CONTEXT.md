# Safe Picks Project Context

Status: Scaffold implemented / paper-trading validation pending
Last updated: 2026-08-29

## Product

Safe Picks is a Telegram-based football betting decision-support bot. It evaluates multiple pre-match markets for the day's fixtures, ranks candidates by calibrated probability and price value, and helps a user build a filtered multi-match slip.

The product must not present outcomes as guaranteed or risk-free. “Safe bets” is a user-facing command name for a higher-confidence, quality-filtered selection tier. The system must be able to return **No qualifying bet**.

## Primary User

Football bettors who want a concise, evidence-based shortlist instead of manually comparing every available market. The first user flow assumes the user provides a target total odds and may specify a maximum number of selections.

## MVP Commands

```text
/safe_bets  -> collect target odds, evaluate the day's eligible matches, build a candidate slip
/trim       -> remove weak, uncertain, stale, or correlated legs from the current draft
/slip       -> display the current draft, odds, estimated joint probability, and warnings
/help       -> explain commands, limitations, and responsible use
```

The first MVP is paper-trading only. It should generate a clear manual slip. SportyBet code generation is a future adapter pending verification of an official, permitted integration mechanism.

## Initial Market Scope

Start with markets that can be supported by reliable, timestamped data:

- Full-match goals totals
- Both teams to score
- 1X2 and double chance
- Match corners only where provider coverage and calibration are adequate

Do not enable cards, player props, or broad multi-league coverage until separate market-specific evidence exists.

## Product Principles

- Forecast probabilities, not certainties.
- Separate forecasting from betting decisions.
- Compare calibrated probability with the actual price; do not rank by probability alone.
- Prefer one leg per match by default.
- Penalize correlation, stale odds, missing data, distribution shift, and model disagreement.
- Never add a weak leg merely to reach the user's target odds.
- Record accepted and rejected candidates for paper-trading evaluation.
- Show uncertainty, timestamps, model version, and reasons for rejection.
- Do not automate wagers in the MVP.

## Success Criteria

The project is not ready for real-money use until it demonstrates, on untouched future data:

1. Better log loss and Brier score than simple baselines.
2. Acceptable calibration by confidence and odds bucket.
3. Stable performance across multiple seasons or time windows.
4. A risk-coverage curve showing that abstention improves retained-pick quality.
5. Any simulated value surviving conservative odds slippage, costs, limits, and selection bias.

## Current State

- Research blueprint exists in the HIOS ideas folder.
- TypeScript Telegram bot scaffold exists with `/safe_bets`, `/trim`, `/slip`, and `/help`.
- Python FastAPI forecasting boundary generates model-backed 1X2 and totals candidates from accepted odds manifests, with BTTS support when those quotes are available.
- Candidate ranking uses de-vigged calibrated edge with explicit data-quality and uncertainty penalties.
- Shared contracts, environment template, and workspace tooling exist.
- Phase 3 provider boundary exists for Football-Data.co.uk historical CSVs, The Odds API snapshots, raw file snapshots, and provider metadata.
- Development ingestion resolves canonical team, competition, fixture, and market identities and audits duplicate/completion rows while rejecting conflicting corrections.
- Historical manifest replay can reconstruct the latest fixture observation available at a timezone-aware as-of timestamp and preserves source provenance.
- Ingestion quality validation rejects future/stale snapshots and missing required fields, while optional statistics produce field-level missingness audits and can be threshold-gated.
- The forecasting API exposes ingestion quality results and structured rejection diagnostics to downstream clients.
- The first leakage-safe feature pipeline and Poisson/Dixon-Coles goals baseline are implemented for offline evaluation; no performance claim has been established.
- A dependency-free chronological walk-forward evaluator and per-market isotonic calibration baseline are implemented; they report held-out metrics but do not establish profitability or production calibration.
- Scheduled The Odds API ingestion stores private raw snapshots, normalizes current events and quotes, links canonical teams and competitions to historical records, and retains event-level rejection diagnostics.
- No configured production provider account, durable database, calibration export job, decision ledger, or bookmaker integration has been implemented.

## Key Risks

- Accumulator probability falls rapidly as legs are added and independence is usually false.
- “Safe” wording can create false confidence and responsible-gambling risk.
- Historical averages and head-to-head results can be misleading without opponent, venue, lineup, and league adjustments.
- Sports-data licensing, odds history, and SportyBet integration are unresolved.
- Corners and cards may use inconsistent provider definitions.

## Related Research

- `C:/Users/sysadmin/Documents/projects/HIOS/ideas/sports-bet-prediction-engine-research.md`
- `C:/Users/sysadmin/Documents/projects/HIOS/ideas/HIOS-review-football-telegram-betting-bot.md`
