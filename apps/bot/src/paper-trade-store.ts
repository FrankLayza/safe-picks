import { randomUUID } from "node:crypto";
import { appendFile, mkdir, readFile, rename, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import type { DraftSlip, MarketCandidate, PaperTrade, PaperTradeStatus } from "@safe-picks/contracts";

const TRADES_FILE = "trades.jsonl";
const INDEX_FILE = "index.json";

/**
 * Append-only JSONL paper-trade ledger with a companion index for O(1)
 * settlement lookups. Stored under the configured directory:
 *   <dir>/trades.jsonl  — one JSON record per line
 *   <dir>/index.json    — { [tradeId]: lineNumber }
 *
 * Settlement rewrites the specific line in place (same length padding is NOT
 * used — we read all lines, patch the target, and rewrite the whole file).
 * This keeps the implementation simple while the file is small.
 */
export class PaperTradeStore {
  constructor(private readonly dir: string) {}

  /** Open paper trades for every eligible leg of a draft slip. */
  async openFromSlip(slip: DraftSlip, chatId: number, slipEventId: string, stake: number): Promise<PaperTrade[]> {
    if (slip.candidates.length === 0) return [];
    const now = new Date().toISOString();
    const trades: PaperTrade[] = slip.candidates.map((candidate) => candidateToTrade(candidate, slipEventId, chatId, stake, now));
    await this._append(trades);
    return trades;
  }

  /**
   * Settle all pending trades for a chat by outcome.
   * Returns the settled trades.
   */
  async settleByChat(chatId: number, outcome: PaperTradeStatus): Promise<PaperTrade[]> {
    const all = await this._readAll();
    const now = new Date().toISOString();
    const settled: PaperTrade[] = [];
    const updated = all.map((trade) => {
      if (trade.chatId !== chatId || trade.status !== "pending") return trade;
      const profitLoss = settleProfitLoss(trade, outcome);
      const patched: PaperTrade = { ...trade, status: outcome, settledAt: now, profitLoss };
      settled.push(patched);
      return patched;
    });
    if (settled.length > 0) await this._rewrite(updated);
    return settled;
  }

  /**
   * Settle a single trade by ID.
   */
  async settleById(tradeId: string, outcome: PaperTradeStatus): Promise<PaperTrade | undefined> {
    const all = await this._readAll();
    const now = new Date().toISOString();
    let target: PaperTrade | undefined;
    const updated = all.map((trade) => {
      if (trade.tradeId !== tradeId) return trade;
      const profitLoss = settleProfitLoss(trade, outcome);
      target = { ...trade, status: outcome, settledAt: now, profitLoss };
      return target;
    });
    if (target) await this._rewrite(updated);
    return target;
  }

  /** Load all trades, optionally filtered by chat ID. */
  async loadAll(chatId?: number): Promise<PaperTrade[]> {
    const all = await this._readAll();
    return chatId === undefined ? all : all.filter((trade) => trade.chatId === chatId);
  }

  /** Load only pending trades for a chat (for the /slip command). */
  async loadPending(chatId: number): Promise<PaperTrade[]> {
    const all = await this._readAll();
    return all.filter((trade) => trade.chatId === chatId && trade.status === "pending");
  }

  private async _append(trades: PaperTrade[]): Promise<void> {
    if (trades.length === 0) return;
    await mkdir(this.dir, { recursive: true });
    const content = `${trades.map((t) => JSON.stringify(t)).join("\n")}\n`;
    await appendFile(join(this.dir, TRADES_FILE), content, "utf8");
    await this._rebuildIndex();
  }

  private async _rewrite(trades: PaperTrade[]): Promise<void> {
    await mkdir(this.dir, { recursive: true });
    const content = `${trades.map((t) => JSON.stringify(t)).join("\n")}\n`;
    const tmp = join(this.dir, `${TRADES_FILE}.tmp`);
    await writeFile(tmp, content, "utf8");
    await rename(tmp, join(this.dir, TRADES_FILE));
    await this._rebuildIndex();
  }

  private async _readAll(): Promise<PaperTrade[]> {
    try {
      const raw = await readFile(join(this.dir, TRADES_FILE), "utf8");
      return raw
        .split("\n")
        .filter(Boolean)
        .map((line) => JSON.parse(line) as PaperTrade);
    } catch {
      return [];
    }
  }

  private async _rebuildIndex(): Promise<void> {
    const trades = await this._readAll();
    const index: Record<string, number> = {};
    trades.forEach((trade, i) => { index[trade.tradeId] = i; });
    const tmp = join(this.dir, `${INDEX_FILE}.tmp`);
    const dest = join(this.dir, INDEX_FILE);
    await mkdir(dirname(dest), { recursive: true });
    await writeFile(tmp, JSON.stringify(index, null, 2), "utf8");
    await rename(tmp, dest);
  }
}

function candidateToTrade(
  candidate: MarketCandidate,
  slipEventId: string,
  chatId: number,
  stake: number,
  openedAt: string,
): PaperTrade {
  return {
    tradeId: randomUUID(),
    slipEventId,
    chatId,
    fixtureId: candidate.fixtureId,
    kickoff: candidate.kickoff,
    homeTeam: candidate.homeTeam,
    awayTeam: candidate.awayTeam,
    market: candidate.market,
    selection: candidate.selection,
    odds: candidate.odds,
    modelProbability: candidate.modelProbability,
    estimatedEdge: candidate.estimatedEdge,
    expectedValue: candidate.expectedValue,
    rankingScore: candidate.rankingScore,
    modelVersion: candidate.modelVersion,
    oddsObservedAt: candidate.oddsObservedAt,
    stake,
    status: "pending",
    openedAt,
  };
}

function settleProfitLoss(trade: PaperTrade, outcome: PaperTradeStatus): number {
  if (outcome === "settled_win") return trade.stake * (trade.odds - 1);
  if (outcome === "settled_loss") return -trade.stake;
  return 0; // void
}
