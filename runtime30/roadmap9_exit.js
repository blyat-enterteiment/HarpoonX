"use strict";
/** Pure causal exit decision. Entry costs are sunk and are not charged again. */
function exitAction(signal, at, remaining, reduced, decisions) {
  const mode = signal.metadata?.roadmapExit;
  if (!mode || at <= signal.plannedEntryAt) return null;
  if (!["VALUE_TOTAL", "VALUE_PARTIAL"].includes(mode)) throw Error("ROADMAP_EXIT_MODE");
  if (!Number.isInteger(remaining) || remaining < 0) throw Error("ROADMAP_EXIT_QUANTITY");
  const row = decisions?.[`${signal.symbol}:${at}`];
  // No forecast is an abstention; native protective stop/deadline still applies.
  if (!row) return null;
  if (!(row.available_at <= row.decision_at && row.decision_at < at &&
        row.execution_at === at && row.model_asof <= row.decision_at &&
        row.latest_label_at <= row.model_asof &&
        row.decision_at - row.model_asof <= 168 * 3600000 &&
        row.decision_at - row.latest_label_at <= 168 * 3600000)) throw Error("ROADMAP_EXIT_CAUSALITY");
  if (row.decision_at <= signal.at) return null;
  if (!Number.isInteger(signal.metadata.roadmapOriginalDeadline) ||
      !Number.isInteger(row.deadline_at) || row.deadline_at > signal.metadata.roadmapOriginalDeadline ||
      row.deadline_at <= at) return null;
  if (![row.mean, row.mean_se, row.lower].every(Number.isFinite) || row.mean_se < 0 ||
      Math.abs(row.lower - (row.mean - 1.645 * row.mean_se)) > 1e-10) throw Error("ROADMAP_EXIT_FORECAST");
  if (mode === "VALUE_TOTAL" && row.lower <= 0)
    return {quantity: remaining, reason: "CONTINUATION_VALUE_TOTAL"};
  if (mode === "VALUE_PARTIAL") {
    if (row.mean < -1.645 * row.mean_se)
      return {quantity: remaining, reason: "CONTINUATION_VALUE_NEGATIVE"};
    if (!reduced && row.lower <= 0 && remaining >= 2)
      return {quantity: Math.floor(remaining / 2), reason: "CONTINUATION_VALUE_HALF"};
  }
  return null;
}
module.exports = {exitAction};
