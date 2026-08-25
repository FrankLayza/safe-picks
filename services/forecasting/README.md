# Forecasting Service

This FastAPI service exposes deterministic development candidates and offline football forecasting components. The statistical baseline is for chronological evaluation and paper-trading research; it is not a claim of profitable or calibrated betting performance.

Run locally:

```text
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Endpoints:

- `GET /health`
- `GET /v1/candidates/today`
- `POST /v1/ingestion/quality`

## Provider ingestion boundary

`app/providers` contains the Phase 3 provider-neutral ingestion boundary:

- `FootballDataCsvAdapter` parses historical Football-Data.co.uk CSV files.
- `OddsApiAdapter` parses The Odds API snapshots and can make authenticated requests when `ODDS_API_KEY` is set.
- `FileRawSnapshotStore` saves immutable payload bytes and checksum metadata.
- `ProviderRegistry` records coverage, licensing status, rate-limit policy, and retention policy.
- `FootballDataIngestionJob` downloads one configured league/season, stores the raw CSV, and writes a normalized JSON manifest.
- `identity.py` resolves canonical entity IDs and validates duplicate, completion, and correction behavior before a manifest is written.
- `HistoricalManifestReplay` reconstructs fixture records as of a forecast timestamp using only manifests already retrieved by that time.
- Ingestion quality validation rejects future or stale snapshots and missing required identity/timestamp fields, while auditing optional-statistic missingness. Configure `INGESTION_MAX_SNAPSHOT_AGE_DAYS` and optionally `INGESTION_MAX_OPTIONAL_MISSING_FRACTION`.
- `POST /v1/ingestion/quality` exposes the same quality gate to downstream services. Rejected payloads return HTTP 422 with `error.code`, `error.reasons[]`, and `error.audit`.
- `build_fixture_features` creates versioned, leakage-safe pre-match features from replayed fixtures, including recency weighting, home/away splits, rest, completeness, provenance, and opponent-adjusted strength.
- `PoissonGoalsModel` provides the first goals baseline with smoothed attack/defence rates, recency weighting, and a Dixon-Coles low-score correction. It emits full score probabilities plus totals, BTTS, and 1X2 probabilities.
- `evaluate_goals_walk_forward` runs chronological validation/test scoring and `isotonic-v1` calibration for each supported binary market. It reports Brier score, log loss, accuracy, reliability buckets, and explicit abstentions when training data is insufficient.

Run provider tests from this directory:

```text
..\\..\\.venv\\Scripts\\python.exe -m unittest discover -s tests -t .
```

The adapters do not imply that raw data may be redistributed. Keep snapshots private until the provider account and licence terms are confirmed.

Run one Football-Data ingestion job:

```text
python -m services.forecasting.app.ingest_football_data --once
```

The default is the England Premier League (`E0`, season `2526`). Override `FOOTBALL_DATA_LEAGUE`, `FOOTBALL_DATA_SEASON`, `FOOTBALL_DATA_BASE_URL`, and `RAW_DATA_ROOT` in `.env` or the process environment. The scheduled mode runs once per day by default:

```text
python -m services.forecasting.app.ingest_football_data --interval-seconds 86400
```

The mock response must not be presented as model performance or betting advice.
