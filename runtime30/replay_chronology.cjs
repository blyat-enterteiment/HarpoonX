"use strict";

/** @typedef {{at:number, pnl:number}} Mark */
/**
 * Build the observable campaign timeline at a terminal receipt. A bar valuation
 * arriving after the exit receipt cannot re-open inventory or defer its release.
 * Does not modify executions, fees, prices, or receipt timestamps.
 * @param {Mark[]} raw
 * @param {number} exitKnownAt
 * @param {number} realized
 * @returns {{marks:Mark[], peak:number, lateNonterminalMarks:number}}
 */
function terminalTimeline(raw, exitKnownAt, realized) {
  if (!Number.isSafeInteger(exitKnownAt) || !Number.isFinite(realized) || !raw.length)
    throw Error("INVALID_TERMINAL_TIMELINE");
  for (const m of raw)
    if (!Number.isSafeInteger(m.at) || !Number.isFinite(m.pnl))
      throw Error("INVALID_CAMPAIGN_MARK");
  const marks = raw.filter(m => m.at < exitKnownAt).map(m => ({...m}));
  if (marks.some((m, i) => i > 0 && m.at < marks[i - 1].at))
    throw Error("NONTERMINAL_MARK_ORDER");
  marks.push({at: exitKnownAt, pnl: realized});
  return {marks, peak: Math.max(0, ...marks.map(m => m.pnl)),
    lateNonterminalMarks: raw.slice(0, -1).filter(m => m.at > exitKnownAt).length};
}
module.exports = {terminalTimeline};
