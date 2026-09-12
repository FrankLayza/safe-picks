import { describe, expect, it } from "vitest";
import { buildReport, formatReport } from "../src/report.js";
import { parseSettleArgs } from "../src/commands.js";
import type { PaperTrade } from "@safe-picks/contracts";

function makeTrade(overrides: Partial<PaperTrade> = {}): PaperTrade {
  return {
    tradeId: crypto.randomUUID(),
    slipEventId: "slip-1",
    chatId: 1,
    fixtureId: "fix1",
    kickoff: "2026-09-13T15:00:00Z",
    homeTeam: "Arsenal",
    awayTeam: "Chelsea",
    market: "match_result",
    selection: "Arsenal",
    odds: 2.10,
    modelProbability: 0.55,
    estimatedEdge: 0.074,
    expectedValue: 0.155,
    rankingScore: 0.06,
    modelVersion: "poisson-v1",
    oddsObservedAt: "2026-09-13T09:00:00Z",
    stake: 1.0,
    status: "pending",
    openedAt: new Date().toISOString(),
    ...overrides,
  };
}

const NOW = new Date().toISOString();

describe("buildReport", () => {
  it("empty trades produce a zero report", () => {
    const report = buildReport([]);
    expect(report.totalBets).toBe(0);
    expect(report.settledBets).toBe(0);
    expect(report.winRate).toBeNull();
    expect(report.roi).toBeNull();
    expect(report.avgModelEdge).toBeNull();
  });

  it("pending trades count but do not affect settled metrics", () => {
    const report = buildReport([makeTrade(), makeTrade()]);
    expect(report.totalBets).toBe(2);
    expect(report.pendingBets).toBe(2);
    expect(report.settledBets).toBe(0);
    expect(report.winRate).toBeNull();
  });

  it("win P&L accumulates correctly", () => {
    const trade = makeTrade({ status: "settled_win", profitLoss: 1.10, settledAt: NOW });
    const report = buildReport([trade]);
    expect(report.wins).toBe(1);
    expect(report.losses).toBe(0);
    expect(report.profitLoss).toBeCloseTo(1.10);
  });

  it("loss P&L is negative", () => {
    const trade = makeTrade({ status: "settled_loss", profitLoss: -1.0, settledAt: NOW });
    const report = buildReport([trade]);
    expect(report.losses).toBe(1);
    expect(report.profitLoss).toBeCloseTo(-1.0);
  });

  it("win rate = wins / settled (including voids in denominator)", () => {
    const trades = [
      makeTrade({ status: "settled_win", profitLoss: 1.1, settledAt: NOW }),
      makeTrade({ status: "settled_win", profitLoss: 1.1, settledAt: NOW }),
      makeTrade({ status: "settled_loss", profitLoss: -1.0, settledAt: NOW }),
      makeTrade({ status: "void", profitLoss: 0, settledAt: NOW }),
    ];
    const report = buildReport(trades);
    expect(report.wins).toBe(2);
    expect(report.losses).toBe(1);
    expect(report.voids).toBe(1);
    expect(report.winRate).toBeCloseTo(0.5); // 2/4
  });

  it("ROI = profitLoss / totalStake", () => {
    const trades = [
      makeTrade({ status: "settled_win", profitLoss: 1.1, stake: 1.0, settledAt: NOW }),
      makeTrade({ status: "settled_loss", profitLoss: -1.0, stake: 1.0, settledAt: NOW }),
    ];
    const report = buildReport(trades);
    expect(report.roi).toBeCloseTo(0.05); // (1.1 - 1.0) / 2.0
  });

  it("byMarket groups wins and losses separately", () => {
    const trades = [
      makeTrade({ market: "match_result", status: "settled_win", profitLoss: 1.1, settledAt: NOW }),
      makeTrade({ market: "goals_over_under", status: "settled_loss", profitLoss: -1.0, settledAt: NOW }),
    ];
    const report = buildReport(trades);
    expect(report.byMarket["match_result"]?.wins).toBe(1);
    expect(report.byMarket["goals_over_under"]?.losses).toBe(1);
  });
});

describe("formatReport", () => {
  it("returns a non-empty string containing expected sections", () => {
    const trades = [makeTrade({ status: "settled_win", profitLoss: 1.1, settledAt: NOW })];
    const text = formatReport(buildReport(trades));
    expect(text.length).toBeGreaterThan(0);
    expect(text).toContain("Paper Trade Report");
  });

  it("shows 'No settled bets yet' for all-pending trades", () => {
    const text = formatReport(buildReport([makeTrade(), makeTrade()]));
    expect(text).toContain("No settled bets yet");
  });
});

describe("parseSettleArgs", () => {
  it("/settle win", () => {
    expect(parseSettleArgs("/settle win")).toEqual({ kind: "all", outcome: "settled_win" });
  });

  it("/settle won (alias)", () => {
    expect(parseSettleArgs("/settle won")).toEqual({ kind: "all", outcome: "settled_win" });
  });

  it("/settle loss", () => {
    expect(parseSettleArgs("/settle loss")).toEqual({ kind: "all", outcome: "settled_loss" });
  });

  it("/settle lost (alias)", () => {
    expect(parseSettleArgs("/settle lost")).toEqual({ kind: "all", outcome: "settled_loss" });
  });

  it("/settle void", () => {
    expect(parseSettleArgs("/settle void")).toEqual({ kind: "all", outcome: "void" });
  });

  it("/settle <id> win → per-trade form", () => {
    expect(parseSettleArgs("/settle abc-123 win")).toEqual({ kind: "id", tradeId: "abc-123", outcome: "settled_win" });
  });

  it("throws when no outcome supplied", () => {
    expect(() => parseSettleArgs("/settle")).toThrow("Usage");
  });

  it("throws on unknown outcome word", () => {
    expect(() => parseSettleArgs("/settle banana")).toThrow("Unknown outcome");
  });
});
