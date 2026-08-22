# Safe Picks Architecture

Status: Proposed architecture
Last updated: 2026-08-23

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
- `FileRawSnapshotStore` for immutable local payload/checksum storage during development.
- `ProviderRegistry` for coverage, licensing, rate-limit, and retention metadata.
- `identity.py` for deterministic canonical team, competition, fixture, and market IDs.
- Manifest validation for exact duplicate collapse, completion audit, and fail-closed correction detection.

These adapters do not grant redistribution rights. Production ingestion still requires account verification, licensing review, freshness/missingness policy, and durable storage.

### Feature Pipeline

Responsibilities:

- Build only as-of features available before each forecast timestamp.
- Resolve team, venue, competition, and player identities.
- Calculate opponent-adjusted strength, recent form, rest, travel, expected lineups, goals, and corners features.
- Preserve feature version and source snapshot IDs.

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

### Slip Builder

Responsibilities:

- Build a draft from daily candidates under target odds and leg-count constraints.
- Default to one leg per match.
- Penalize or reject correlated selections.
- Explain every accepted or removed leg.
- Estimate joint probability conservatively; never assume independence without documenting it.

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
POST /v1/slips
POST /v1/slips/{slipId}/trim
GET  /v1/slips/{slipId}
GET  /v1/performance
```

The API must return timestamps, odds source, model version, calibration status, warnings, and abstention reasons with every candidate.

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

- Current architecture is unimplemented.
- Provider choices and licenses are not finalized.
- SportyBet code generation is not verified.
- Joint accumulator probability and correlation modeling require empirical validation.
