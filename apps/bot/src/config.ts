function required(name: string): string {
  const value = process.env[name];
  if (!value) throw new Error(`${name} is required`);
  return value;
}

function envNumber(name: string, fallback: number): number {
  const value = Number(process.env[name]);
  return Number.isFinite(value) ? value : fallback;
}

export const config = {
  token: process.env.TELEGRAM_BOT_TOKEN,
  forecastingServiceUrl: process.env.FORECASTING_SERVICE_URL ?? "http://localhost:8000",
  auditLogPath: process.env.AUDIT_LOG_PATH ?? "data/audit/decisions.jsonl",
  draftStorePath: process.env.DRAFT_STORE_PATH ?? "data/drafts",
  paperTradePath: process.env.PAPER_TRADE_PATH ?? "data/paper-trades",
  defaultStake: envNumber("PAPER_TRADE_DEFAULT_STAKE", 1.0),
  allowedUserIds: new Set(
    (process.env.ALLOWED_TELEGRAM_USER_IDS ?? "")
      .split(",")
      .map((value) => value.trim())
      .filter(Boolean)
      .map(Number),
  ),
};

export function telegramToken(): string {
  return required("TELEGRAM_BOT_TOKEN");
}
