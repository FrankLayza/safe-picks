# Safe Picks

Football betting decision-support bot. The current scaffold is paper-trading only and uses deterministic development candidates.

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

The remaining provider, database, storage, model-registry, and paper-trading variables are placeholders for later implementation phases and should remain empty until those integrations are approved.

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

No live provider, trained model, database, SportyBet integration, or real-money wagering is included.
