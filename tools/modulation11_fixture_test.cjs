"use strict";
const test = require("node:test"), assert = require("node:assert/strict");
const E = require("../runtime30/modulation11_execution_equivalence.cjs");
const costs = { friction: .0003, perSideUsd: .005, tick: .01 };
const position = { entry: 100.03, stop: 99.03, distance: 1, quantity: 8,
  targetsR: [1.5, 3] };
const makeBar = prices => ({ t: 1000000, end: 1300000, availableAt: 1301000,
  o: 100, h: Math.max(100, ...prices), l: Math.min(100, ...prices), c: prices[7] });
const close = (x, y) => assert(Math.abs(x - y) < 1e-8, `${x} != ${y}`);
const reservation = (id, decisionAt = 1000) => ({ id, symbol: "SYNA", decisionAt,
  quantity: 10, riskUsd: 20, notionalUsd: 1000, cashUsd: 1000.05 });
const capacity = { equity: 20000, cashAvailableUsd: 20000, riskFraction: .0025,
  openRiskFraction: .0025, grossFraction: .12, assetFraction: .12 };

test("family1: a reserved IOC is NOT a contemporaneous 12% exposure cap", () => {
  const a = E.inspectReserveAnchor({ equityAtDecision: 20000, shadowEquityAtDecision: 20000,
    reservedNotional: 2300, pendingAcquisitionCeiling: 500, observedExistingValue: 1800,
    contemporaryExistingValue: 2250, equityAtFill: 20450, contemporaryNewValue: 500 });
  assert.equal(a.admissionWithinCap, true);
  assert.equal(a.conservativePending, true);
  assert.equal(a.shadowDominatesObserved, true);
  assert.equal(a.observedPositionCovered, false);
  assert.equal(a.continuousCapAtFill, false);
  close(a.actualFillRatio, 2750 / 20450);
});

test("family2: native reservation persists through delayed no-fill receipts", () => {
  const R = require("../runtime30/ultimate_reservations.js");
  const a = R.reserveFundedEntry(R.emptyFundedReservationBook(), reservation("IOC"), capacity);
  assert.equal(a.status, "RESERVED");
  assert.equal(R.snapshotFundedReservations(a.book, 1299).cashUsd, 1000.05);
  const rejected = R.recordFundedReservationObservation(a.book, {
    id: "IOC", kind: "NO_FILL", at: 1299, knownAt: 1300,
    remainingQuantity: 0, pendingQuantity: 0 });
  assert.equal(R.snapshotFundedReservations(rejected, 1299).pending, 1);
  assert.equal(R.snapshotFundedReservations(rejected, 1300).cashUsd, 0);
  const b = R.reserveFundedEntry(R.emptyFundedReservationBook(), reservation("PARTIAL"), capacity);
  const opened = R.recordFundedReservationObservation(b.book, {
    id: "PARTIAL", kind: "OPENED", at: 1200, knownAt: 1300,
    remainingQuantity: 4, pendingQuantity: 6 });
  assert.equal(R.snapshotFundedReservations(opened, 1301).notionalUsd, 1000);
  assert.equal(R.snapshotFundedReservations(opened, 1301).opened, 1);
  assert.equal(R.snapshotFundedReservations(opened, 1301).reservations[0].observedRemainingQuantity, 4);
});

test("family3: native stop interpolation overpays by .23/share with unchanged costs", () => {
  const prices = [100.02, 100.01, 99.9, 98.8, 98.9, 99.1, 99.2, 99.4];
  const bar = makeBar(prices);
  const a = E.nativeBarExits(bar, prices, position, costs);
  const b = E.substepBarExits(bar, prices, position, costs);
  close(a.fills[0].fillPrice, 99);
  close(b.fills[0].fillPrice, 98.77);
  close(a.fills[0].fillPrice - b.fills[0].fillPrice, .23);
  assert.equal(b.fills[0].knownAt, bar.availableAt);
  assert(b.fills[0].at < b.fills[0].knownAt);
  close(E.incrementalCashLedger(position, a.fills, costs).inventory, 0);
  close(E.incrementalCashLedger(position, b.fills, costs).inventory, 0);
});

test("family3: target interpolation underpays by .27/share with unchanged costs", () => {
  const prices = [100.1, 101.8, 101.2, 100.8, 100.9, 101, 101.1, 101.2];
  const bar = makeBar(prices);
  const a = E.nativeBarExits(bar, prices, position, costs);
  const b = E.substepBarExits(bar, prices, position, costs);
  assert.equal(a.fills[0].reason, "TP1");
  close(a.fills[0].fillPrice, 101.49);
  close(b.fills[0].fillPrice, 101.76);
  close(b.fills[0].fillPrice - a.fills[0].fillPrice, .27);
  close(E.incrementalCashLedger(position, a.fills, costs).inventory, 6);
});

test("family4: identical OHLC with reversed chronology changes inventory/payoff", () => {
  const firstTarget = [100.5, 101.8, 100.5, 98.8, 99.1, 100.2, 100.3, 99.4];
  const firstStop = [100.5, 98.8, 100.5, 101.8, 100.3, 99.1, 100.2, 99.4];
  const x = makeBar(firstTarget), y = makeBar(firstStop);
  assert.deepEqual([x.o, x.h, x.l, x.c], [y.o, y.h, y.l, y.c]);
  const nativeX = E.nativeBarExits(x, firstTarget, position, costs);
  const nativeY = E.nativeBarExits(y, firstStop, position, costs);
  assert.deepEqual(nativeX.fills, nativeY.fills);
  const subX = E.substepBarExits(x, firstTarget, position, costs);
  const subY = E.substepBarExits(y, firstStop, position, costs);
  assert.deepEqual(subX.fills.map(f => f.reason), ["TP1", "STOP"]);
  assert.deepEqual(subY.fills.map(f => f.reason), ["STOP"]);
  assert.notEqual(E.incrementalCashLedger(position, subX.fills, costs).markedPnlUsd,
    E.incrementalCashLedger(position, subY.fills, costs).markedPnlUsd);
});

test("fail-closed: mismatched synthetic substeps are refused", () => {
  const p = [100.02, 100.01, 99.9, 98.8, 98.9, 99.1, 99.2, 99.4];
  const bar = makeBar(p);
  assert.throws(() => E.substepBarExits(bar, [...p.slice(0, 7), 99.5], position, costs),
    /SUBSTEP_OHLC_IDENTITY/);
});
