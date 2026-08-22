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

The mock response must not be presented as model performance or betting advice.
