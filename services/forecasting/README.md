# Forecasting Service

This FastAPI service currently exposes deterministic development candidates so the Telegram contract can be tested before real data ingestion and model training exist.

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

## Provider ingestion boundary

`app/providers` contains the Phase 3 provider-neutral ingestion boundary:

- `FootballDataCsvAdapter` parses historical Football-Data.co.uk CSV files.
- `OddsApiAdapter` parses The Odds API snapshots and can make authenticated requests when `ODDS_API_KEY` is set.
- `FileRawSnapshotStore` saves immutable payload bytes and checksum metadata.
- `ProviderRegistry` records coverage, licensing status, rate-limit policy, and retention policy.
- `FootballDataIngestionJob` downloads one configured league/season, stores the raw CSV, and writes a normalized JSON manifest.
- `identity.py` resolves canonical entity IDs and validates duplicate, completion, and correction behavior before a manifest is written.
- `HistoricalManifestReplay` reconstructs fixture records as of a forecast timestamp using only manifests already retrieved by that time.

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
