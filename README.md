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

Copy `.env.example` to `.env` and set `TELEGRAM_BOT_TOKEN` only when running the Telegram process. Start the forecasting service first, then run the bot:

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
