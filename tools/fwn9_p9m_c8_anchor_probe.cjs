"use strict";
// FWN9-C8: deterministic structural tests; never trades or samples market paths.
// Native reservation API is read-only; this module does not modify M9 semantics.
const {
  emptyFundedReservationBook,
  reserveFundedEntry,
  recordFundedReservationObservation,
  snapshotFundedReservations,
} = require("../runtime30/ultimate_reservations");

const CONTRACT = Object.freeze({
  capital: 20000, fraction: 0.12, risk: 0.0025,
  commission: 0.005, nominalFriction: 0.0003,
  maxHoldingHours: 72,
});

function need(x, why) { if (!x) throw new Error(why); }
function capacity(equity) {
  return {
    equity, cashAvailableUsd: 20000,
    riskFraction: CONTRACT.risk, openRiskFraction: CONTRACT.risk,
    grossFraction: CONTRACT.fraction, assetFraction: CONTRACT.fraction,
  };
}
function receipt(book, id, kind, at, remaining) {
  return recordFundedReservationObservation(book, {
    id, kind, at, knownAt: at, remainingQuantity: remaining, pendingQuantity: 0,
  });
}

/** Exact reservation snapshot (no repricing) versus the additional conservative
 * mark overlay computed by profit8_replay.js before planning a NEW order.
 * Marks are explicit values known at the simulated decision; they are not
 * fetched with future price data.
 */
function conservativeOverlay(snapshot, knownMarks) {
  const gross = snapshot.reservations.reduce((sum, row) => {
    if (row.state === "PENDING") return sum + row.notionalUsd;
    const price = knownMarks[row.symbol];
    need(Number.isFinite(price) && price > 0, "missing causal open mark");
    return sum + Math.max(row.notionalUsd, row.quantity * price);
  }, 0);
  return gross;
}

function rawVsRepricedAnchor({ firstMark = 220, noFill = false, partial = false } = {}) {
  need(firstMark >= 200 && Number.isFinite(firstMark), "positive finite reprice");
  // Two distinct original symbols. Quantity/risk below original nominal gates;
  // this demonstrates an admissible reservation API event sequence, not a
  // particular native signal generated from the 126-session market.
  let book = emptyFundedReservationBook();
  const first = reserveFundedEntry(book, {
    id: "C8-A", symbol: "SYNA", decisionAt: 100,
    quantity: 10, notionalUsd: 2000.30, cashUsd: 2000.35, riskUsd: 48,
  }, capacity(20000));
  need(first.status === "RESERVED", "first reservation rejected");
  book = receipt(first.book, "C8-A", "OPENED", 200, 10);
  const decisionAt = 301;
  const equityAtDecision = 20000 + 10 * (firstMark - 200) - 10 * CONTRACT.commission;
  const before = snapshotFundedReservations(book, decisionAt);
  const markedPrior = conservativeOverlay(before, { SYNA: firstMark });
  const newCeiling = 100.03; // unfilled B uses price ceiling, not future open
  const riskB = 1.07;
  const rawBefore = before.notionalUsd;
  const correctedAtDecision = markedPrior + newCeiling;
  const plannedBudgetUsd = CONTRACT.fraction * equityAtDecision - markedPrior;
  const plannerAllowsB = newCeiling <= plannedBudgetUsd + 1e-8
    && before.riskUsd + riskB <= CONTRACT.risk * equityAtDecision + 1e-8;
  const second = reserveFundedEntry(book, {
    id: "C8-B", symbol: "SYNB", decisionAt,
    quantity: 1, notionalUsd: newCeiling,
    cashUsd: newCeiling + CONTRACT.commission, riskUsd: riskB,
  }, capacity(equityAtDecision));
  need(second.status === "RESERVED", "second native reservation refused");
  book = second.book;
  const snapshotAtDecision = snapshotFundedReservations(book, decisionAt);
  const rawAnchorUsd = snapshotAtDecision.notionalUsd;
  const correctedAnchorUsd = conservativeOverlay(snapshotAtDecision, {
    SYNA: firstMark, SYNB: 100,
  });
  need(Math.abs(correctedAtDecision - correctedAnchorUsd) < 1e-7, "overlay mismatch");
  book = noFill ? receipt(book, "C8-B", "NO_FILL", 400, 0)
    : receipt(book, "C8-B", "OPENED", 400, 1);
  // Market is flat from decision to fill: max of admissible price ratios is 1.
  const prebarSharesA = 10;
  const prebarSharesB = noFill ? 0 : 1;
  let cash = 20000 - 10 * (200 + CONTRACT.commission);
  if (!noFill) cash -= 100 + CONTRACT.commission;
  let laterSharesA = prebarSharesA;
  if (partial) {
    // Causal sale of three A at a rounded nominal sell price, with fee.
    cash += 3 * (219.93 - CONTRACT.commission);
    laterSharesA -= 3;
    book = receipt(book, "C8-A", "OPENED", 450, laterSharesA);
  }
  const exposureAtPrebarUsd = prebarSharesA * firstMark + prebarSharesB * 100;
  const equityAfter = cash + laterSharesA * firstMark + prebarSharesB * 100;
  const laterSnapshot = snapshotFundedReservations(book, partial ? 450 : 400);
  return {
    schema: "HARPOON_FWN9_C8_NATIVE_RESERVATION_ANCHOR_WITNESS_1",
    firstMark, noFill, partial, equityAtDecision, markedPrior,
    rawBefore, plannedBudgetUsd, plannerAllowsB, riskBudgetB: riskB,
    nativeSecondReservationStatus: second.status,
    rawAnchorUsd, correctedAnchorUsd,
    rawSnapshotAfterUsd: laterSnapshot.notionalUsd,
    exposureAtPrebarUsd, maxPriceRatioFromDecision: 1,
    rawAnchorPasses: exposureAtPrebarUsd <= rawAnchorUsd + 1e-8,
    correctedAnchorPasses: exposureAtPrebarUsd <= correctedAnchorUsd + 1e-8,
    correctedWithinGrossGate: correctedAnchorUsd <= CONTRACT.fraction * equityAtDecision + 1e-8,
    cashAfterEvents: cash, equityAfterEvents: equityAfter,
    remainingA: laterSharesA, BOpened: !noFill,
    noFuturePriceUsedForDecision: true,
    economicAccounts: 0, finalM10Opened: 0,
  };
}

/** WEAK 72h maximum price-ratio moments (not wealth moments).
 * For any deterministic t, conditional compensated log-Gaussian increments and
 * bounded activity give an L^q Doob envelope. q=4 controls E[M^2],
 * q=8 controls E[M^4] via Lyapunov. Four sessions/overnights are
 * deliberately conservative, as in MODULATION10_FEASIBILITY.
 */
function weak72hPriceMomentUpper(targetPower, doobPower) {
  need((targetPower === 2 || targetPower === 4)
    && doobPower > targetPower, "invalid moment powers");
  const q = doobPower;
  const cb = q * (q - 1) / 2;
  const sigmaB = 0.00085 * 1.25 * 1.20 * Math.exp(0.7);
  const sigmaN = 0.0035 * 1.20 * Math.exp(0.7);
  const drift = 2.5e-5 * 1.10;
  const logBar = Math.log(0.996 * Math.exp(cb * sigmaB ** 2)
    + 0.004 * Math.exp(16 * cb * sigmaB ** 2));
  const logNight = cb * sigmaN ** 2;
  const logJump = Math.log(0.994 + 0.003 * 0.97 ** q + 0.003 * 1.03 ** q);
  const logMq = q * Math.log(q / (q - 1)) + Math.log(2)
    + 312 * (q * drift + logBar) + 4 * (logNight + logJump);
  const upper = Math.exp((targetPower / q) * logMq);
  need(Number.isFinite(upper) && upper >= 1, "invalid finite price moment upper");
  return { targetPower, doobPower, upper, logMq,
    sigmaB, sigmaN, bars: 312, overnightEvents: 4,
    hypothesis: "WEAK fixed-date two-symbol ratio max; finite price moments ONLY" };
}

function evidence() {
  return {
    schema: "HARPOON_FWN9_C8_STRUCTURAL_BOUND_PROBE_1",
    raw_counterexample: rawVsRepricedAnchor(),
    no_fill: rawVsRepricedAnchor({ noFill: true }),
    partial: rawVsRepricedAnchor({ partial: true }),
    planner_negative_control: rawVsRepricedAnchor({ firstMark: 260 }),
    finite_price_moments: [
      weak72hPriceMomentUpper(2, 4),
      weak72hPriceMomentUpper(4, 8),
    ],
    native_population_wealth_bound_certified: false,
    corrected_anchor_all_native_events_certified: false,
    new_market_seeds: 0, economic_accounts: 0, prospective_alpha_spent: 0,
    unopened_M10_final_accounts: 3200,
  };
}
module.exports = {
  CONTRACT, conservativeOverlay, rawVsRepricedAnchor,
  weak72hPriceMomentUpper, evidence,
};
if (require.main === module) process.stdout.write(JSON.stringify(evidence(), null, 2) + "\n");
