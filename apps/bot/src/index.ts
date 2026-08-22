import "dotenv/config";
import { Bot } from "grammy";
import type { DraftSlip } from "@safe-picks/contracts";
import { config, telegramToken } from "./config.js";
import { parseSafeBetsArgs } from "./commands.js";
import { getTodayCandidates } from "./forecasting-client.js";
import { buildDraft, trimDraft } from "./slip.js";
import { formatCandidate, formatSlip } from "./format.js";

const drafts = new Map<number, DraftSlip>();

function authorized(userId: number | undefined): boolean {
  return !userId || config.allowedUserIds.size === 0 || config.allowedUserIds.has(userId);
}

async function main(): Promise<void> {
  const token = telegramToken();
  const bot = new Bot(token);

  bot.use(async (ctx, next) => {
    if (!authorized(ctx.from?.id)) return ctx.reply("This bot is not enabled for this account.");
    await next();
  });

  bot.command("help", (ctx) => ctx.reply("/safe_bets <target odds> <max legs>\n/trim\n/slip\n/help\n\nSelections are filtered forecasts, not guaranteed outcomes."));
  bot.command("safe_bets", async (ctx) => {
    try {
      const { targetOdds, maxLegs } = parseSafeBetsArgs(ctx.message?.text);
      const response = await getTodayCandidates(config.forecastingServiceUrl);
      const draft = buildDraft(response.candidates, targetOdds, maxLegs);
      drafts.set(ctx.chat.id, draft);
      await ctx.reply(formatSlip(draft));
    } catch (error) {
      await ctx.reply(error instanceof Error ? error.message : "Unable to build picks.");
    }
  });
  bot.command("trim", async (ctx) => {
    const draft = drafts.get(ctx.chat.id);
    if (!draft) return ctx.reply("No draft slip. Start with /safe_bets 3.00 3");
    const trimmed = trimDraft(draft);
    drafts.set(ctx.chat.id, trimmed);
    await ctx.reply(formatSlip(trimmed));
  });
  bot.command("slip", (ctx) => {
    const draft = drafts.get(ctx.chat.id);
    return ctx.reply(draft ? formatSlip(draft) : "No draft slip. Start with /safe_bets 3.00 3");
  });
  bot.catch((error) => console.error("Telegram bot error", error));
  await bot.start();
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
