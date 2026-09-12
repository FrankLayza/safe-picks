import type { PaperTrade, PaperTradeReport } from "@safe-picks/contracts";

export function buildReport(trades: PaperTrade[]): PaperTradeReport {
  const settled = trades.filter((t) => t.status !== "pending");
  const wins = settled.filter((t) => t.status === "settled_win");
  const losses = settled.filter((t) => t.status === "settled_loss");
  const voids = settled.filter((t) => t.status === "void");
  const pending = trades.filter((t) => t.status === "pending");

  const totalStake = settled.reduce((sum, t) => sum + t.stake, 0);
  const profitLoss = settled.reduce((sum, t) => sum + (t.profitLoss ?? 0), 0);
  const totalReturn = totalStake + profitLoss;
  const winRate = settled.length > 0 ? wins.length / settled.length : null;
  const roi = totalStake > 0 ? profitLoss / totalStake : null;

  const allEdges = trades.filter((t) => Number.isFinite(t.estimatedEdge)).map((t) => t.estimatedEdge);
  const avgModelEdge = allEdges.length > 0 ? allEdges.reduce((sum, e) => sum + e, 0) / allEdges.length : null;

  const byMarket: PaperTradeReport["byMarket"] = {};
  for (const trade of trades) {
    const key = trade.market;
    if (!byMarket[key]) byMarket[key] = { bets: 0, wins: 0, losses: 0, voids: 0, profitLoss: 0 };
    const bucket = byMarket[key];
    bucket.bets += 1;
    if (trade.status === "settled_win") { bucket.wins += 1; bucket.profitLoss += trade.profitLoss ?? 0; }
    else if (trade.status === "settled_loss") { bucket.losses += 1; bucket.profitLoss += trade.profitLoss ?? 0; }
    else if (trade.status === "void") { bucket.voids += 1; }
  }

  return {
    generatedAt: new Date().toISOString(),
    totalBets: trades.length,
    pendingBets: pending.length,
    settledBets: settled.length,
    wins: wins.length,
    losses: losses.length,
    voids: voids.length,
    winRate,
    totalStake,
    totalReturn,
    profitLoss,
    roi,
    avgModelEdge,
    byMarket,
  };
}

export function formatReport(report: PaperTradeReport, chatId?: number): string {
  const settledLine = report.settledBets === 0
    ? "No settled bets yet."
    : [
        `Bets:       ${report.settledBets} settled  |  ${report.pendingBets} pending`,
        `Record:     ${report.wins}W / ${report.losses}L / ${report.voids}V`,
        `Win rate:   ${report.winRate !== null ? pct(report.winRate) : "—"}`,
        `P&L:        ${report.profitLoss >= 0 ? "+" : ""}${report.profitLoss.toFixed(2)}u  (ROI ${report.roi !== null ? pct(report.roi) : "—"})`,
        `Avg edge:   ${report.avgModelEdge !== null ? pct(report.avgModelEdge) : "—"} model`,
      ].join("\n");

  const marketLines = Object.entries(report.byMarket)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([market, bucket]) => {
      const name = marketLabel(market);
      const wr = bucket.wins + bucket.losses > 0
        ? ` ${pct(bucket.wins / (bucket.wins + bucket.losses))} WR`
        : "";
      const pl = bucket.profitLoss >= 0 ? `+${bucket.profitLoss.toFixed(2)}u` : `${bucket.profitLoss.toFixed(2)}u`;
      return `  ${name.padEnd(20)} ${String(bucket.bets).padStart(3)} bets${wr}  ${pl}`;
    })
    .join("\n");

  const byMarketSection = Object.keys(report.byMarket).length > 0
    ? `\n\nBy market:\n${marketLines}`
    : "";

  return `📊 *Paper Trade Report*\n${"─".repeat(30)}\n${settledLine}${byMarketSection}\n\n_Not betting advice. Paper trading only._`;
}

function pct(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

function marketLabel(market: string): string {
  const labels: Record<string, string> = {
    goals_over_under: "Goals O/U",
    both_teams_to_score: "BTTS",
    match_result: "1X2",
    double_chance: "Dbl Chance",
    corners_over_under: "Corners O/U",
  };
  return labels[market] ?? market;
}
