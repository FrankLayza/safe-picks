# Safe Picks Architecture

Status: Proposed architecture
Last updated: 2026-08-29

## System Overview

Safe Picks consists of a Telegram interface, a TypeScript application layer, a Python forecasting service, timestamped football data pipelines, a historical database, and a paper-trading/evaluation layer.

The Telegram bot is a client of the prediction and slip APIs. It must not contain model logic, bookmaker credentials, or hidden selection rules.

## High-Level Flow

```text
Permitted football data and odds APIs
        -> ingestion jobs
        -> raw immutable snapshots
        -> validation and entity resolution
        -> PostgreSQL historical store
        -> timestamped feature generation
        -> market-specific forecasting models
        -> probability calibration and ensemble
        -> candidate scoring, value, uncertainty, and abstention
        -> slip builder and correlation controls
        -> TypeScript API
        -> Telegram bot
        -> paper-trading ledger and monitoring
```

## Planned Technology Stack

### Telegram and application layer

- TypeScript
- grammY or Telegraf for Telegram interactions
- Fastify or NestJS for the application API
- Zod for request and configuration validation

### Forecasting layer

- Python
- pandas or polars
- scikit-learn and statsmodels
- Elo, Poisson/Dixon-Coles, regularized GLMs, and gradient boosting
- MLflow for model and experiment versions

### Storage and operations

- PostgreSQL for normalized entities, forecasts, odds, slips, and paper trades
- Parquet/object storage for immutable raw payloads and reproducible training datasets
- Prefect or Dagster for scheduled ingestion and training jobs
- Prometheus/Grafana or a hosted equivalent for health and calibration monitoring

## Components

### Telegram Bot

Responsibilities:

- Parse `/safe_bets`, `/trim`, `/slip`, and `/help`.
- Maintain a user draft-slip reference.
- Ask for target odds and maximum legs.
- Display candidate explanations, warnings, and abstentions.

It must not calculate probabilities or silently change selections.

### Application API

Responsibilities:

- Authenticate and rate-limit bot requests.
- Expose match candidates and slip operations.
- Persist user inputs and decisions.
- Return stable, versioned response contracts.

### Data Ingestion

Responsibilities:

- Fetch fixtures, results, team/player data, event metrics, lineups, injuries, weather, and odds from permitted sources.
- Store raw payloads with provider, retrieval timestamp, event timestamp, and schema version.
- Detect duplicates, missingness, stale data, and provider corrections.

Current provider boundary:

- `FootballDataCsvAdapter` for private historical CSV backfills.
- `OddsApiAdapter` for authenticated current bookmaker snapshots.
- `OddsApiIngestionJob` for scheduled current-event and market snapshots, canonical historical matching, quote freshness checks, and normalized rejection manifests.
- `FileRawSnapshotStore` for immutable local payload/checksum storage during development.
- `ProviderRegistry` for coverage, licensing, rate-limit, and retention metadata.
- `identity.py` for deterministic canonical team, competition, fixture, and market IDs.
- Manifest validation for exact duplicate collapse, completion audit, and fail-closed correction detection.
- `HistoricalManifestReplay` for timestamp-bounded fixture reconstruction with source manifest and raw snapshot provenance.
- Ingestion quality validation for snapshot freshness, required-field completeness, timestamp integrity, and configurable optional-field missingness.

These adapters do not grant redistribution rights. Production ingestion still requires account verification, licensing review, freshness/missingness policy, and durable storage.

Current odds manifests contain only events whose competition and both teams resolve to historical records and whose supported bookmaker market groups are complete and fresh. Ambiguous fixtures, unknown teams or competitions, started events, stale quotes, incomplete markets, unsupported markets, and malformed payload rows remain in machine-readable `rejections[]` entries. Stored source URLs exclude the API key.

Historical replay only considers manifests whose provider retrieval timestamp is at or before the requested forecast timestamp. For each canonical fixture it selects the latest eligible observation and retains its manifest path and raw snapshot checksum so feature generation can be audited without using future data.

Quality validation uses a caller-supplied reference timestamp. This keeps historical backfills reproducible while allowing scheduled jobs to reject snapshots older than the configured freshness window. Required identity and timestamp fields fail closed; optional statistics are reported with field-level missing fractions and are rejecting only when an optional missingness threshold is configured.

### Feature Pipeline

Responsibilities:

- Build only as-of features available before each forecast timestamp.
- Resolve team, venue, competition, and player identities.
- Calculate opponent-adjusted strength, recent form, rest, travel, expected lineups, goals, and corners features.
- Preserve feature version and source snapshot IDs.

The first implementation is `build_fixture_features` (`football-pre-match-v1`). It rejects forecasts after kickoff and excludes incomplete, future, or post-forecast records. `PoissonGoalsModel` (`poisson-dixon-coles-v1`) consumes completed pre-match fixtures and retains training as-of and source provenance; it is a baseline, not calibrated betting performance. `evaluate_goals_walk_forward` (`goals-walk-forward-v1`) fits each forecast as-of its kickoff, keeps validation before test, and fits `isotonic-v1` calibrators only on validation observations.

### Forecasting Service

Responsibilities:

- Produce market-specific probabilities for each eligible fixture.
- Maintain separate models and calibration for goals, BTTS, 1X2/double chance, and corners.
- Generate uncertainty, model agreement, and data-completeness signals.

### Candidate Selector

Responsibilities:

- Convert forecasts and odds into candidate value estimates.
- Apply minimum sample, calibration, freshness, uncertainty, and distribution-shift gates.
- Rank candidates by risk-adjusted value, not raw hit probability.
- Return “No qualifying bet” when gates fail.

The forecasting response exposes a top-level `abstain` status and `NO_ELIGIBLE_CANDIDATES` code when model-generation prerequisites fail. The slip layer independently aggregates candidate statuses, rejection codes, provider diagnostics, and source warnings so downstream abstention remains explicit after all TypeScript decision gates run.

The current candidate ranking score starts with positive calibrated edge against the de-vigged bookmaker probability. It multiplies that edge by data completeness and by the complements of uncertainty, calibration error, and distribution shift. Raw edge, total quality penalty, and final ranking score remain separate response fields so downstream selection is reproducible.

Short-priced selections receive an additional configurable value gate. The development defaults classify decimal odds at or below 1.40 as short-priced and require at least 0.04 de-vigged edge and 0.03 expected value. These are conservative engineering defaults, not empirically validated profitability thresholds.

### Slip Builder

Responsibilities:

- Build a draft from daily candidates under target odds and leg-count constraints.
- Default to one leg per match.
- Penalize or reject correlated selections.
- Explain every accepted or removed leg.
- Estimate joint probability conservatively; the current MVP uses the Frechet lower bound for unknown dependence and exposes the independence product only as a reference.

Candidates carry explicit correlation keys for their fixture and canonical home and away teams. The selector keeps the highest quality-adjusted rank for each occupied key and rejects weaker overlaps with `CORRELATED_SELECTION`. Competition-wide correlation is intentionally not inferred without validated evidence.

Each trim removes exactly one current lowest-ranked leg while retaining at least one leg. Removed-leg history stores the candidate identity, market, odds, rank, edge, uncertainty, completeness, machine-readable code, and user-readable explanation.

### Paper-Trading Ledger

Responsibilities:

- Record every candidate, selected leg, rejected leg, odds timestamp, model version, result, and settlement.
- Support future-period performance reports by market, league, odds range, and confidence bucket.

### Bookmaker Adapter Boundary

Responsibilities:

- Isolate any future SportyBet slip/code integration.
- Validate that an official permitted mechanism exists before implementation.
- Never require bookmaker automation for forecasting or paper trading.

## Core Data Entities

- `provider_source`: provider, license status, endpoint, rate limit, schema version
- `competition`: league/competition identity and provider mappings
- `team`: canonical team identity and provider mappings
- `fixture`: teams, venue, kickoff, competition, status
- `source_snapshot`: raw payload, provider, retrieved-at, published-at, checksum
- `odds_quote`: fixture, market, line, selection, odds, bookmaker, observed-at
- `feature_snapshot`: fixture, forecast timestamp, feature version, source IDs, values
- `model_version`: market, training window, code version, calibration version
- `forecast`: fixture, market, probabilities, uncertainty, agreement, created-at
- `candidate`: forecast, odds quote, edge/value, eligibility status, rejection reason
- `slip`: user, target odds, status, created-at, final probability estimate
- `slip_leg`: slip, candidate, rank, inclusion/removal reason
- `paper_trade`: candidate or slip, stake assumption, settlement, return, closing odds

## API Sketch

```text
GET  /v1/matches/today
POST /v1/ingestion/quality
POST /v1/slips
POST /v1/slips/{slipId}/trim
GET  /v1/slips/{slipId}
GET  /v1/performance
```

The API must return timestamps, odds source, model version, calibration status, warnings, and abstention reasons with every candidate.

Ingestion quality failures use a stable error envelope: HTTP 422 with `error.code`, `error.message`, `error.reasons`, and `error.audit`. The TypeScript client preserves this envelope in `ForecastingServiceError` for downstream diagnostics.

## Security and Reliability

- Store Telegram and provider secrets only in environment/managed secret storage.
- Validate all user-supplied odds, target totals, and IDs.
- Rate-limit commands and prevent duplicate request races.
- Log decisions without exposing secrets or unnecessary personal data.
- Use immutable raw data and model versions for auditability.
- Fail closed when odds, lineup, or critical market data is stale or missing.

## Deployment Plan

### MVP

- One deployable TypeScript bot/API service
- One scheduled Python worker
- PostgreSQL
- Local or managed object storage for raw snapshots
- Paper trading only

### Later

- Separate forecasting service deployment
- Queue-based ingestion
- MLflow registry and automated drift checks
- Web dashboard
- Verified bookmaker adapter, if legally and technically supported

## Architecture Decisions

1. Forecasting is separate from Telegram presentation so model decisions are testable and reusable.
2. PostgreSQL is sufficient for the first league and paper-trading volume.
3. Market-specific models are preferred over one universal classifier.
4. The bookmaker integration is optional and isolated behind an adapter.
5. No automatic wagering is part of the MVP.

## Known Limitations

- The architecture is partially implemented with local manifest storage rather than the planned durable database and object storage.
- Provider choices and licenses are not finalized.
- SportyBet code generation is not verified.
- Joint accumulator probability and correlation modeling require empirical validation.
