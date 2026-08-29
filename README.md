# Safe Picks

Football betting decision-support bot. The forecasting API now generates model-backed development candidates from accepted, timestamped odds manifests and leakage-safe historical results. Outputs remain research/paper-trading candidates, not betting advice.

## Repository layout

```text
apps/bot/                 Telegram bot and slip workflow
packages/contracts/       Shared TypeScript response types
services/forecasting/     Python FastAPI forecasting boundary
CONTEXT.md                Product memory and current scope
ARCHITECTURE.md           System design and responsibilities
AGENTS.md                 Durable instructions for coding agents
```

## Setup

Copy `.env.example` to `.env`. For the current Telegram bot, `TELEGRAM_BOT_TOKEN` is required and `FORECASTING_SERVICE_URL` should point to the running forecasting service. `ALLOWED_TELEGRAM_USER_IDS` is optional for a local allowlist. The bot loads `.env` automatically; never commit the populated file.

The Odds API ingestion variables are active development settings. Database, object storage, model-registry, and paper-trading variables remain placeholders until those integrations are implemented and approved.

Start the forecasting service first, then run the bot:

```text
cd services/forecasting
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

In another terminal:

```text
pnpm install
pnpm --filter @safe-picks/bot dev
```

Without a Telegram token, the bot intentionally exits with a configuration error. The forecasting health and model-backed candidate endpoints do not require credentials, but candidate generation requires accepted local manifests and an optional calibration artifact for actionable status.

Short-price eligibility can be configured with `SHORT_PRICE_MAX_ODDS`, `SHORT_PRICE_MIN_EDGE`, and `SHORT_PRICE_MIN_EXPECTED_VALUE`. The defaults are development safeguards and still require future-data validation.

## Status

No configured production provider account, database, calibration export job, SportyBet integration, or real-money wagering is included.
