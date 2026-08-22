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

Run provider tests from this directory:

```text
..\\..\\.venv\\Scripts\\python.exe -m unittest discover -s tests -t .
```

The adapters do not imply that raw data may be redistributed. Keep snapshots private until the provider account and licence terms are confirmed.

The mock response must not be presented as model performance or betting advice.
