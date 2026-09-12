import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { PaperTradeStore } from "../src/paper-trade-store.js";
import type { DraftSlip, MarketCandidate } from "@safe-picks/contracts";

function makeCandidate(overrides: Partial<MarketCandidate> = {}): MarketCandidate {
  return {
    id: "fix1:match_result:home:none:bk1",
    fixtureId: "fix1",
    kickoff: "2026-09-13T15:00:00Z",
    homeTeam: "Arsenal",
    awayTeam: "Chelsea",
    market: "match_result",
    selection: "Arsenal",
    odds: 2.10,
    marketQuotes: [{ selection: "Arsenal", odds: 2.10 }, { selection: "Draw", odds: 3.20 }, { selection: "Chelsea", odds: 3.50 }],
    modelProbability: 0.55,
    impliedProbability: 0.476,
    estimatedEdge: 0.074,
    expectedValue: 0.155,
    rankingScore: 0.06,
    qualityPenalty: 0.014,
    uncertainty: 0.12,
    dataCompleteness: 0.95,
    calibrationError: 0.04,
    distributionShift: 0.0,
    correlationGroup: "fix1",
    correlationGroups: ["fix1", "team:ars", "team:che"],
    modelVersion: "poisson-dixon-coles-v1+calibrated",
    oddsObservedAt: "2026-09-13T09:00:00Z",
    status: "eligible",
    reason: "Passed eligibility gates.",
    ...overrides,
  };
}

function makeDraft(candidates: MarketCandidate[] = [makeCandidate()]): DraftSlip {
  return {
    targetOdds: 3.0,
    maxLegs: 3,
    candidates,
    combinedOdds: candidates.reduce((p, c) => p * c.odds, 1),
    estimatedJointProbability: 0.45,
    status: candidates.length > 0 ? "draft" : "abstain",
    warnings: [],
  };
}

let tmpDir = "";

beforeAll(async () => { tmpDir = await mkdtemp(join(tmpdir(), "paper-trade-test-")); });
afterAll(async () => { await rm(tmpDir, { recursive: true, force: true }); });

describe("PaperTradeStore", () => {
  it("openFromSlip creates one pending trade per candidate", async () => {
    const store = new PaperTradeStore(join(tmpDir, "t1"));
    const draft = makeDraft([
      makeCandidate(),
      makeCandidate({ id: "fix2:match_result:home:none:bk1", fixtureId: "fix2" }),
    ]);
    const trades = await store.openFromSlip(draft, 100, "slip-event-1", 1.0);
    expect(trades).toHaveLength(2);
    expect(trades.every((t) => t.status === "pending")).toBe(true);
    expect(trades.every((t) => t.chatId === 100)).toBe(true);
    expect(trades.every((t) => t.stake === 1.0)).toBe(true);
    expect(trades.every((t) => t.slipEventId === "slip-event-1")).toBe(true);
  });

  it("loadPending returns only pending trades for the given chat", async () => {
    const store = new PaperTradeStore(join(tmpDir, "t2"));
    await store.openFromSlip(makeDraft(), 200, "se-200", 1.0);
    await store.openFromSlip(makeDraft(), 201, "se-201", 1.0);
    const pending = await store.loadPending(200);
    expect(pending).toHaveLength(1);
    expect(pending.every((t) => t.chatId === 200)).toBe(true);
  });

  it("settleByChat with win applies correct P&L", async () => {
    const store = new PaperTradeStore(join(tmpDir, "t3"));
    await store.openFromSlip(makeDraft(), 300, "se-300", 2.0);
    const settled = await store.settleByChat(300, "settled_win");
    expect(settled).toHaveLength(1);
    expect(settled[0].status).toBe("settled_win");
    // P&L = 2 * (2.10 - 1) = 2.20
    expect(settled[0].profitLoss).toBeCloseTo(2.20);
    const all = await store.loadAll(300);
    expect(all.every((t) => t.status === "settled_win")).toBe(true);
  });

  it("settleByChat with loss applies negative P&L", async () => {
    const store = new PaperTradeStore(join(tmpDir, "t4"));
    await store.openFromSlip(makeDraft(), 301, "se-301", 1.0);
    const settled = await store.settleByChat(301, "settled_loss");
    expect(settled[0].profitLoss).toBe(-1.0);
  });

  it("settleByChat with void applies zero P&L", async () => {
    const store = new PaperTradeStore(join(tmpDir, "t5"));
    await store.openFromSlip(makeDraft(), 302, "se-302", 1.0);
    const settled = await store.settleByChat(302, "void");
    expect(settled[0].profitLoss).toBe(0);
    expect(settled[0].status).toBe("void");
  });

  it("settleById settles only the specified trade", async () => {
    const store = new PaperTradeStore(join(tmpDir, "t6"));
    const [t1] = await store.openFromSlip(makeDraft([
      makeCandidate(),
      makeCandidate({ id: "fix3:match_result:home:none:bk1", fixtureId: "fix3" }),
    ]), 400, "se-400", 1.0);
    await store.settleById(t1.tradeId, "settled_win");
    const all = await store.loadAll(400);
    const other = all.find((t) => t.tradeId !== t1.tradeId);
    expect(other?.status).toBe("pending");
  });

  it("openFromSlip with empty candidates returns empty array", async () => {
    const store = new PaperTradeStore(join(tmpDir, "t7"));
    const trades = await store.openFromSlip(makeDraft([]), 500, "se-500", 1.0);
    expect(trades).toHaveLength(0);
  });

  it("already-settled trades are not re-settled by settleByChat", async () => {
    const store = new PaperTradeStore(join(tmpDir, "t8"));
    await store.openFromSlip(makeDraft(), 600, "se-600", 1.0);
    await store.settleByChat(600, "settled_win");
    const second = await store.settleByChat(600, "settled_loss");
    expect(second).toHaveLength(0);
  });
});
