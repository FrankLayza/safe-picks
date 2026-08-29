# Forecasting Service

This FastAPI service exposes model-backed football candidates from accepted odds manifests and offline forecasting components. The statistical baseline is for chronological evaluation and paper-trading research; it is not a claim of profitable or calibrated betting performance.

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
- `OddsApiIngestionJob` schedules private current-event and odds snapshots, matches canonical competitions and teams against historical records, and writes normalized accepted events plus machine-readable rejection reasons.
- `FileRawSnapshotStore` saves immutable payload bytes and checksum metadata.
- `ProviderRegistry` records coverage, licensing status, rate-limit policy, and retention policy.
- `FootballDataIngestionJob` downloads one configured league/season, stores the raw CSV, and writes a normalized JSON manifest.
- `identity.py` resolves canonical entity IDs and validates duplicate, completion, and correction behavior before a manifest is written.
- `HistoricalManifestReplay` reconstructs fixture records as of a forecast timestamp using only manifests already retrieved by that time.
- Ingestion quality validation rejects future or stale snapshots and missing required identity/timestamp fields, while auditing optional-statistic missingness. Configure `INGESTION_MAX_SNAPSHOT_AGE_DAYS` and optionally `INGESTION_MAX_OPTIONAL_MISSING_FRACTION`.
- `POST /v1/ingestion/quality` exposes the same quality gate to downstream services. Rejected payloads return HTTP 422 with `error.code`, `error.reasons[]`, and `error.audit`.
- `build_fixture_features` creates versioned, leakage-safe pre-match features from replayed fixtures, including recency weighting, home/away splits, rest, completeness, provenance, and opponent-adjusted strength.
- `PoissonGoalsModel` provides the first goals baseline with smoothed attack/defence rates, recency weighting, and a Dixon-Coles low-score correction. It emits full score probabilities plus totals, BTTS, and 1X2 probabilities.
- `generate_candidates` selects the latest accepted The Odds API manifest, replays historical fixtures as of its retrieval time, and emits bookmaker-specific 1X2, totals, and BTTS candidates. It ranks positive de-vigged edge after explicit completeness, uncertainty, calibration-error, and distribution-shift penalties. The endpoint returns machine-readable diagnostics and abstains when training or calibration prerequisites are not met.
- Candidates include fixture and canonical-team correlation keys; the TypeScript selector rejects weaker overlaps across related markets or fixtures with `CORRELATED_SELECTION`.
- Candidate responses expose `status: abstain` and `abstentionCode: NO_ELIGIBLE_CANDIDATES` when no generated candidate is eligible. Downstream slips preserve source warnings and diagnostic codes when later decision gates also reject every candidate.
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

Run one current-odds ingestion after a historical manifest exists:

```text
python -m services.forecasting.app.ingest_odds_api --once
```

Set `ODDS_API_KEY`, `ODDS_API_SEASON`, and the existing `ODDS_API_*` market settings first. Scheduled mode defaults to every five minutes and can be changed with `ODDS_API_INGESTION_INTERVAL_SECONDS` or `--interval-seconds`. Raw snapshots and normalized manifests are private; stored source URLs never contain the API key.

The mock response must not be presented as model performance or betting advice.
