import "dotenv/config";
import { Bot } from "grammy";
import type { DraftSlip } from "@safe-picks/contracts";
import { config, telegramToken } from "./config.js";
import { parseSafeBetsArgs, parseSettleArgs } from "./commands.js";
import { getTodayCandidates } from "./forecasting-client.js";
import { buildDraft, trimDraft } from "./slip.js";
import { formatSlip, formatSettlement } from "./format.js";
import { candidateAuditRecord, JsonlDecisionAuditStore, newAuditRequestId, slipAuditRecord } from "./audit.js";
import { DraftStore } from "./draft-store.js";
import { PaperTradeStore } from "./paper-trade-store.js";
import { buildReport, formatReport } from "./report.js";

function authorized(userId: number | undefined): boolean {
  return !userId || config.allowedUserIds.size === 0 || config.allowedUserIds.has(userId);
}

const HELP_TEXT = [
  "*Safe Picks commands*",
  "",
  "/safe\\_bets \\<target odds\\> \\<max legs\\>",
  "  Evaluate today's fixtures and build a ranked draft slip.",
  "  Example: `/safe_bets 3.00 3`",
  "",
  "/trim",
  "  Remove the weakest leg from the current draft.",
  "",
  "/slip",
  "  Show the current draft slip.",
  "",
  "/settle win|loss|void",
  "  Record the outcome of your current pending paper trades.",
  "  Example: `/settle win`  or  `/settle loss`",
  "",
  "/report",
  "  View your paper-trading performance summary.",
  "",
  "/help",
  "  Show this message.",
  "",
  "⚠️ _Selections are filtered model outputs, not guaranteed outcomes._",
  "_This bot does not place bets. Paper trading only._",
].join("\n");

async function main(): Promise<void> {
  const token = telegramToken();
  const bot = new Bot(token);

  const auditStore = new JsonlDecisionAuditStore(config.auditLogPath);
  const draftStore = new DraftStore(config.draftStorePath);
  const tradeStore = new PaperTradeStore(config.paperTradePath);

  // Authorization middleware
  bot.use(async (ctx, next) => {
    if (!authorized(ctx.from?.id)) return ctx.reply("This bot is not enabled for this account.");
    await next();
  });

  // /help
  bot.command("help", (ctx) =>
    ctx.reply(HELP_TEXT, { parse_mode: "Markdown" }),
  );

  // /safe_bets <target_odds> <max_legs>
  bot.command("safe_bets", async (ctx) => {
    try {
      const { targetOdds, maxLegs } = parseSafeBetsArgs(ctx.message?.text);
      const response = await getTodayCandidates(config.forecastingServiceUrl);
      const requestId = newAuditRequestId();
      const auditContext = {
        requestId,
        source: response.source,
        generatedAt: response.generatedAt,
        sourceManifest: response.sourceManifest,
      } as const;

      await auditStore.append(
        response.candidates.map((candidate) => candidateAuditRecord(candidate, auditContext)),
      );

      const draft = buildDraft(response.candidates, targetOdds, maxLegs, {
        sourceWarnings: response.warnings,
        diagnosticCodes: response.diagnostics?.map(({ code }) => code),
        sourceManifest: response.sourceManifest,
        sourceGeneratedAt: response.generatedAt,
        source: response.source,
      });

      const slipRecord = slipAuditRecord(draft, auditContext, "build", response.candidates.length);
      await auditStore.append([slipRecord]);
      await draftStore.set(ctx.chat.id, draft);

      // Auto-open paper trades for each eligible leg
      let pendingTrades: Awaited<ReturnType<typeof tradeStore.loadPending>> = [];
      if (draft.status !== "abstain" && draft.candidates.length > 0) {
        const opened = await tradeStore.openFromSlip(draft, ctx.chat.id, slipRecord.eventId, config.defaultStake);
        pendingTrades = opened;
      }

      await ctx.reply(formatSlip(draft, pendingTrades), { parse_mode: "Markdown" });
    } catch (error) {
      await ctx.reply(error instanceof Error ? error.message : "Unable to build picks.");
    }
  });

  // /trim
  bot.command("trim", async (ctx) => {
    const draft = await draftStore.get(ctx.chat.id);
    if (!draft) return ctx.reply("No draft slip. Start with /safe_bets 3.00 3");
    const trimmed = trimDraft(draft);
    const requestId = newAuditRequestId();
    await auditStore.append([
      slipAuditRecord(trimmed, {
        requestId,
        source: trimmed.source ?? "forecasting-service",
        generatedAt: trimmed.sourceGeneratedAt,
        sourceManifest: trimmed.sourceManifest,
      }, "trim", draft.candidates.length),
    ]);
    await draftStore.set(ctx.chat.id, trimmed);
    const pending = await tradeStore.loadPending(ctx.chat.id);
    await ctx.reply(formatSlip(trimmed, pending), { parse_mode: "Markdown" });
  });

  // /slip
  bot.command("slip", async (ctx) => {
    const draft = await draftStore.get(ctx.chat.id);
    if (!draft) return ctx.reply("No draft slip. Start with /safe_bets 3.00 3");
    const pending = await tradeStore.loadPending(ctx.chat.id);
    return ctx.reply(formatSlip(draft, pending), { parse_mode: "Markdown" });
  });

  // /settle win|loss|void  or  /settle <tradeId> win|loss|void
  bot.command("settle", async (ctx) => {
    try {
      const scope = parseSettleArgs(ctx.message?.text);
      let settled: Awaited<ReturnType<typeof tradeStore.settleByChat>>;
      if (scope.kind === "all") {
        settled = await tradeStore.settleByChat(ctx.chat.id, scope.outcome);
      } else {
        const trade = await tradeStore.settleById(scope.tradeId, scope.outcome);
        settled = trade ? [trade] : [];
      }
      await ctx.reply(formatSettlement(settled, scope.outcome), { parse_mode: "Markdown" });
    } catch (error) {
      await ctx.reply(error instanceof Error ? error.message : "Settlement failed.");
    }
  });

  // /report
  bot.command("report", async (ctx) => {
    const trades = await tradeStore.loadAll(ctx.chat.id);
    const report = buildReport(trades);
    await ctx.reply(formatReport(report), { parse_mode: "Markdown" });
  });

  bot.catch((error) => console.error("Telegram bot error", error));
  await bot.start();
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
