# Safe Picks

Football betting decision-support bot. The Telegram workflow still uses deterministic development candidates, while historical results, current odds ingestion, and the first statistical model exist as offline service components.

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

Without a Telegram token, the bot intentionally exits with a configuration error. The forecasting health and mock candidate endpoints do not require credentials.

## Status

No configured production provider account, live model-backed candidate endpoint, database, SportyBet integration, or real-money wagering is included.
