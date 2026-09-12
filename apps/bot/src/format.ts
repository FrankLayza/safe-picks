import type { DraftSlip, MarketCandidate, PaperTrade } from "@safe-picks/contracts";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function pct(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

function sign(value: number): string {
  return value >= 0 ? `+${pct(value)}` : pct(value);
}

function marketEmoji(market: string): string {
  const map: Record<string, string> = {
    goals_over_under: "⚽",
    both_teams_to_score: "✅",
    match_result: "🔄",
    double_chance: "🔄",
    corners_over_under: "📐",
  };
  return map[market] ?? "🎯";
}

function marketLabel(market: string): string {
  const map: Record<string, string> = {
    goals_over_under: "Goals O/U",
    both_teams_to_score: "BTTS",
    match_result: "1X2",
    double_chance: "Dbl Chance",
    corners_over_under: "Corners O/U",
  };
  return map[market] ?? market;
}

/** Format a UTC ISO string as 'Today HH:MM UTC' or 'Mon DD HH:MM UTC' */
function kickoffTime(iso: string): string {
  try {
    const d = new Date(iso);
    const now = new Date();
    const isToday =
      d.getUTCFullYear() === now.getUTCFullYear() &&
      d.getUTCMonth() === now.getUTCMonth() &&
      d.getUTCDate() === now.getUTCDate();
    const hh = String(d.getUTCHours()).padStart(2, "0");
    const mm = String(d.getUTCMinutes()).padStart(2, "0");
    if (isToday) {
      return `Today ${hh}:${mm} UTC`;
    }
    const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    const month = months[d.getUTCMonth()];
    const day = d.getUTCDate();
    return `${month} ${day} ${hh}:${mm} UTC`;
  } catch {
    return iso;
  }
}

function escapeMarkdown(text: string): string {
  // Escape characters that break Telegram MarkdownV1
  return text.replace(/[_*[\]()~`>#+=|{}.!-]/g, (c) => `\\${c}`);
}

// ---------------------------------------------------------------------------
// Candidate block
// ---------------------------------------------------------------------------

export function formatCandidate(candidate: MarketCandidate, index?: number): string {
  const emoji = marketEmoji(candidate.market);
  const market = marketLabel(candidate.market);
  const line = candidate.line !== undefined && candidate.line !== null ? ` ${candidate.line}` : "";
  const prefix = index !== undefined ? `${index + 1}. ` : "";
  const kickoff = kickoffTime(candidate.kickoff);

  return [
    `${prefix}*${candidate.homeTeam} vs ${candidate.awayTeam}*  _(${kickoff})_`,
    `   ${emoji} ${market}${line}: *${candidate.selection}* @ \`${candidate.odds.toFixed(2)}\``,
    `   Model ${pct(candidate.modelProbability)} | Edge ${sign(candidate.estimatedEdge)} | EV ${sign(candidate.expectedValue ?? 0)} | Rank ${pct(candidate.rankingScore ?? 0)}`,
    `   _${candidate.reason.replace(/_/g, "\\_")}_`,
  ].join("\n");
}

// ---------------------------------------------------------------------------
// Slip block
// ---------------------------------------------------------------------------

export function formatSlip(draft: DraftSlip, pendingTrades?: PaperTrade[]): string {
  const isAbstain = draft.status === "abstain";
  const title = isAbstain ? "🚫 *No qualifying bet*" : "📋 *Filtered picks*";

  const legs = isAbstain
    ? ""
    : draft.candidates
        .map((candidate, i) => formatCandidate(candidate, i))
        .join("\n\n");

  const oddsLine = isAbstain
    ? ""
    : `\n\n*Combined odds:* \`${draft.combinedOdds.toFixed(2)}\`  |  *Est. joint P:* ${pct(draft.estimatedJointProbability)}`;

  const removalsSection =
    draft.removedLegs && draft.removedLegs.length > 0
      ? `\n\n✂️ *Removed fixtures*\n${draft.removedLegs.map((r) => `• ${r.reason} \`[${r.code}]\``).join("\n")}`
      : "";

  const abstentionSection = draft.abstention
    ? `\n\n🚫 *Abstention:* ${draft.abstention.reason} \`[${draft.abstention.code}]\`\n` +
      `Rejections: ${formatCounts(draft.abstention.rejectionCounts)}\n` +
      `Diagnostics: ${formatDiagnostics(draft.abstention.diagnosticCodes)}`
    : "";

  const pendingSection =
    pendingTrades && pendingTrades.length > 0
      ? `\n\n💰 *${pendingTrades.length} paper trade(s) open.*  Use /settle win|loss|void when results are known.`
      : "";

  const warnings =
    draft.warnings.length > 0
      ? `\n\n⚠️ ${draft.warnings.map((w) => w.replace(/_/g, "\\_")).join("\n⚠️ ")}`
      : "";

  const parts = [title];
  if (legs) parts.push(`\n\n${legs}`);
  if (oddsLine) parts.push(oddsLine);
  if (removalsSection) parts.push(removalsSection);
  if (abstentionSection) parts.push(abstentionSection);
  if (pendingSection) parts.push(pendingSection);
  if (warnings) parts.push(warnings);

  return parts.join("");
}

// ---------------------------------------------------------------------------
// Settlement confirmation
// ---------------------------------------------------------------------------

export function formatSettlement(settled: PaperTrade[], outcome: string): string {
  if (settled.length === 0) return "No pending trades found to settle.";
  const pl = settled.reduce((sum, t) => sum + (t.profitLoss ?? 0), 0);
  const sign = pl >= 0 ? "+" : "";
  const outcomeLabel = outcome === "settled_win" ? "✅ Won" : outcome === "settled_loss" ? "❌ Lost" : "⭕ Void";
  return [
    `${outcomeLabel} — ${settled.length} trade(s) settled`,
    `P&L: *${sign}${pl.toFixed(2)}u*`,
    settled.map((t) => `• ${t.homeTeam} vs ${t.awayTeam} — ${marketLabel(t.market)}: ${t.selection} @ ${t.odds.toFixed(2)}`).join("\n"),
  ].join("\n");
}

// ---------------------------------------------------------------------------
// Internal
// ---------------------------------------------------------------------------

function formatCounts(counts: Record<string, number>): string {
  const entries = Object.entries(counts).sort(([a], [b]) => a.localeCompare(b));
  return entries.length > 0 ? entries.map(([code, count]) => `\`${code}=${count}\``).join(", ") : "none";
}

function formatDiagnostics(codes: string[]): string {
  return codes.length > 0 ? codes.map((c) => `\`${c}\``).join(", ") : "none";
}
