function required(name: string): string {
  const value = process.env[name];
  if (!value) throw new Error(`${name} is required`);
  return value;
}

export const config = {
  token: process.env.TELEGRAM_BOT_TOKEN,
  forecastingServiceUrl: process.env.FORECASTING_SERVICE_URL ?? "http://localhost:8000",
  auditLogPath: process.env.AUDIT_LOG_PATH ?? "data/audit/decisions.jsonl",
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
