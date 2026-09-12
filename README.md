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

The Odds API ingestion variables are active development settings. Persistent drafts (`DRAFT_STORE_PATH`) and paper trading (`PAPER_TRADE_PATH`, `PAPER_TRADE_DEFAULT_STAKE`) are active local settings. Database, object storage, and model-registry variables remain placeholders until those integrations are implemented and approved.

The Telegram bot supports the following commands:
- `/safe_bets <target odds> <max legs>`: Evaluate today's matches, create a draft slip, and auto-open paper trades for eligible selections.
- `/trim`: Remove the weakest or most correlated leg from the current draft.
- `/slip`: View the current draft slip, combined odds, and open trade count.
- `/settle win|loss|void` or `/settle <tradeId> win|loss|void`: Record match outcomes for paper trades.
- `/report`: View aggregate paper-trading performance (P&L, win rate, ROI, market breakdown).
- `/help`: Display commands and responsible-use reminders.

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

When model prerequisites or decision gates reject every candidate, the API and Telegram response return `No qualifying bet` with structured rejection counts and diagnostic codes rather than filling the slip with weaker selections. The bot also appends candidate and slip decision provenance to `AUDIT_LOG_PATH` as versioned JSONL records.

## Status

No configured production provider account, database, calibration export job, SportyBet integration, or real-money wagering is included. Local per-user draft persistence, JSONL decision audit logging, and paper-trade settlement ledger are implemented.
