"use strict";
// Diagnostic-only discrete eight-substep comparator. No broker, orders, strategy or RNG.
// Does not replace the native M10 replay or claim liquidity/queue executability.
const { strict: assert } = require("node:assert");
const SCHEMA = "HARPOON_M11_EXECUTION_EQUIVALENCE_1";
const roundTick = (p, tick, up) => (up ? Math.ceil(p / tick - 1e-8) : Math.floor(p / tick + 1e-8)) * tick;
const near = (a, b) => Math.abs(a - b) <= 1e-9 * Math.max(1, Math.abs(a), Math.abs(b));

function checkGrid(bar, prices) {
  assert(Array.isArray(prices) && prices.length === 8, "EIGHT_SUBSTEPS_REQUIRED");
  assert([bar.t, bar.end, bar.availableAt].every(Number.isSafeInteger), "BAR_TIMESTAMPS");
  assert(bar.t < bar.end && bar.availableAt > bar.end, "PUBLICATION_AFTER_BAR");
  assert([bar.o, bar.h, bar.l, bar.c, ...prices].every(v => Number.isFinite(v) && v > 0), "FINITE_PRICES");
  assert(near(bar.c, prices[7]) && near(bar.h, Math.max(bar.o, ...prices)) &&
    near(bar.l, Math.min(bar.o, ...prices)), "SUBSTEP_OHLC_IDENTITY");
}

function validate(position, costs) {
  assert(Number.isSafeInteger(position.quantity) && position.quantity > 0, "POSITIVE_INTEGER_QUANTITY");
  assert([position.entry, position.stop, position.distance].every(x => Number.isFinite(x) && x > 0), "LONG_STOP_ARGUMENTS");
  assert(position.stop < position.entry && position.distance > 0, "LONG_SIDE_ONLY");
  assert(Array.isArray(position.targetsR) && position.targetsR.length === 2 &&
    position.targetsR.every(x => x === null || (Number.isFinite(x) && x > 0)), "TWO_TARGETS");
  assert(Number.isFinite(costs.friction) && costs.friction >= 0 && costs.friction < 1, "FRICTION");
  assert(Number.isFinite(costs.perSideUsd) && costs.perSideUsd >= 0 &&
    Number.isFinite(costs.tick) && costs.tick > 0, "EXISTING_COSTS");
}

function appendFill(fills, costs, {quantity, price, at, knownAt, reason, step}) {
  if (!quantity) return;
  const afterCostsPrice = roundTick(price * (1 - costs.friction), costs.tick, false);
  fills.push({ quantity, rawPrice: price, fillPrice: afterCostsPrice,
    commissionUsd: costs.perSideUsd * quantity, at, knownAt, reason, step });
}

function nativeBarExits(bar, prices, position, costs) {
  checkGrid(bar, prices);
  validate(position, costs);
  const { quantity, entry, stop, distance, targetsR } = position;
  const fills = [];
  if (bar.l <= stop) {
    appendFill(fills, costs, { quantity, price: Math.min(bar.o, stop),
      at: bar.end, knownAt: bar.availableAt, reason: "STOP", step: null });
  } else {
    for (let j = 0; j < 2; j++) {
      if (targetsR[j] === null) continue;
      const target = roundTick(entry + targetsR[j] * distance, costs.tick, true);
      if (bar.h >= target) {
        appendFill(fills, costs, { quantity: Math.floor(quantity / 4), price: target,
          at: bar.end, knownAt: bar.availableAt, reason: `TP${j + 1}`, step: null });
      }
    }
  }
  return { schema: SCHEMA, mode: "NATIVE_OHLC_BARRIER_ORDER", fills,
    remainingQuantity: quantity - fills.reduce((n, f) => n + f.quantity, 0) };
}

function substepBarExits(bar, prices, position, costs) {
  checkGrid(bar, prices);
  validate(position, costs);
  const { quantity, entry, stop, distance, targetsR } = position;
  let remainingQuantity = quantity;
  const done = [false, false], fills = [];
  // An opening gap is observed before any intrabar substep. Do not backfill stops.
  const points = [{ price: bar.o, step: -1, at: bar.t },
    ...prices.map((price, step) => ({ price, step,
      at: bar.t + Math.floor((step + 1) * (bar.end - bar.t) / 8) }))];
  for (const point of points) {
    if (remainingQuantity === 0) break;
    if (point.price <= stop) {
      appendFill(fills, costs, { quantity: remainingQuantity, price: point.price,
        at: point.at, knownAt: bar.availableAt, reason: "STOP", step: point.step });
      remainingQuantity = 0;
      break;
    }
    for (let j = 0; j < 2; j++) {
      if (remainingQuantity === 0 || done[j] || targetsR[j] === null) continue;
      const target = roundTick(entry + targetsR[j] * distance, costs.tick, true);
      if (point.price >= target) {
        const sell = Math.min(remainingQuantity, Math.floor(quantity / 4));
        appendFill(fills, costs, { quantity: sell, price: point.price,
          at: point.at, knownAt: bar.availableAt, reason: `TP${j + 1}`, step: point.step });
        remainingQuantity -= sell;
        done[j] = true;
      }
    }
  }
  return { schema: SCHEMA, mode: "FIRST_OBSERVED_SUBSTEP_CROSS", fills, remainingQuantity };
}

function incrementalCashLedger(position, fills, costs) {
  validate(position, costs);
  let cash = -(position.quantity * position.entry + position.quantity * costs.perSideUsd);
  let inventory = position.quantity;
  for (const fill of fills) {
    assert(fill.quantity <= inventory && fill.quantity >= 0, "NO_SHORT_INVENTORY");
    cash += fill.quantity * fill.fillPrice - fill.commissionUsd;
    inventory -= fill.quantity;
  }
  const realizedFromFills = fills.reduce((sum, fill) => sum +
    (fill.fillPrice - position.entry) * fill.quantity - fill.commissionUsd, 0);
  const markedPnl = cash + inventory * position.entry;
  assert(near(markedPnl, realizedFromFills - position.quantity * costs.perSideUsd),
    "INDEPENDENT_CASH_RECONCILIATION");
  return { cashUsd: cash, inventory, markedPnlUsd: markedPnl,
    realizedFromFillsUsd: realizedFromFills };
}

// A necessary-condition inspector, NOT a proof for every past state of the native engine.
function inspectReserveAnchor({ equityAtDecision, shadowEquityAtDecision, reservedNotional,
  pendingAcquisitionCeiling, observedExistingValue, contemporaryExistingValue,
  equityAtFill, contemporaryNewValue, cap = .12 }) {
  const nums = [equityAtDecision, shadowEquityAtDecision, reservedNotional,
    pendingAcquisitionCeiling, observedExistingValue, contemporaryExistingValue,
    equityAtFill, contemporaryNewValue, cap];
  assert(nums.every(x => Number.isFinite(x) && x >= 0), "FINITE_RESERVE_LEDGER");
  assert(equityAtDecision > 0 && shadowEquityAtDecision > 0 && equityAtFill > 0 && cap > 0 && cap <= 1,
    "POSITIVE_EQUITY");
  return {
    admissionRatio: reservedNotional / equityAtDecision,
    actualFillRatio: (contemporaryExistingValue + contemporaryNewValue) / equityAtFill,
    conservativePending: pendingAcquisitionCeiling >= contemporaryNewValue,
    observedPositionCovered: observedExistingValue >= contemporaryExistingValue,
    shadowDominatesObserved: equityAtDecision <= shadowEquityAtDecision,
    admissionWithinCap: reservedNotional <= cap * equityAtDecision + 1e-8,
    continuousCapAtFill: (contemporaryExistingValue + contemporaryNewValue) <= cap * equityAtFill + 1e-8,
    semantics: "CAP_IS_RESERVATION_ADMISSION_NOT_CONTINUOUS_LIMIT"
  };
}

module.exports = { checkGrid, nativeBarExits, substepBarExits,
  incrementalCashLedger, inspectReserveAnchor };
