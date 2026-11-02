"use strict";
// Hermetic synthetic causality/execution checks, never strategy fits or financial trials.
const test = require("node:test"), assert = require("node:assert/strict"), path = require("node:path");
const runtime = process.env.HARPOON_CAUSALITY_RUNTIME_ROOT || path.join(__dirname, "../runtime30");
const { opportunities, planSignalEntryAt, replayCampaign, UnobservedEntryError,
  UnresolvedHoldingExposureError } = require(path.join(runtime, "ultimate_replay.js"));
const BAR = 300000, DAY = 86400000;

function fixture(delay = 3000) {
  const start = Date.UTC(2025, 0, 1, 14, 30), sessions = [], bars = [];
  for (let d = 0; d < 21; d++) {
    const open = start + d * DAY, close = open + 10 * BAR;
    sessions.push({ date: new Date(open).toISOString().slice(0, 10), open, close });
    for (let j = 0; j < 10; j++) {
      const t = open + j * BAR, price = d === 20 && j >= 3 ? 102 : 100;
      bars.push({ t, end: t + BAR, availableAt: t + BAR + delay,
        o: price, h: price + .2, l: price - .2, c: price, v: d === 20 ? 100 : 10 });
    }
  }
  const series = { symbol: "SPY", root: "SPY", pointValue: 1, tick: .01, bars };
  const data = { schema: "HARPOON-ULTIMATE-DATA-1", kind: "ALPACA_PROXY", sessions,
    series: [series], splitEvents: [] };
  const protocol = { kind: "ALPACA_PROXY", costs: { spreadBps: 2, slippageBps: 2, perSideUsd: 0 } };
  const decision = sessions.at(-1).open + 4 * BAR + delay;
  return { data, protocol, series, decision };
}
function before(f) { return opportunities(f.data, f.protocol).signals.filter(s => s.at <= f.decision); }
function first(f) {
  const signals = before(f); assert.equal(signals.length, 1); return signals[0];
}
function replay(f, signal = first(f)) {
  return replayCampaign(signal, f.series, f.data, f.protocol, "BASELINE", 4);
}
function remove(f, at) { f.series.bars = f.series.bars.filter(b => b.t !== at); }

test("deleting the later last bar cannot erase an earlier signal", () => {
  const f = fixture(), expected = before(f);
  assert.equal(expected.length, 1);
  f.series.bars.pop();
  assert.deepEqual(before(f), expected);
  assert.equal(opportunities(f.data, f.protocol).funnel.incompleteSessions, 1);
});

test("future prices and future availability do not change an earlier signal", () => {
  const f = fixture(), expected = before(f);
  for (const b of f.series.bars) if (b.t > f.decision) {
    for (const key of ["o", "h", "l", "c"]) b[key] *= 2;
    b.v *= 100; b.availableAt = b.end + 60000;
  }
  assert.deepEqual(before(f), expected);
});

test("an observed prefix gap blocks dependent decisions without interpolation", () => {
  const f = fixture(), gapAt = f.data.sessions.at(-1).open + 2 * BAR;
  remove(f, gapAt);
  assert.equal(before(f).length, 0);
  assert.equal(opportunities(f.data, f.protocol).signals.filter(s => s.at >= gapAt).length, 0);
});

test("a future gap preserves past signals and blocks decisions after the observed gap", () => {
  const f = fixture(), expected = before(f), gapAt = f.data.sessions.at(-1).open + 7 * BAR;
  remove(f, gapAt);
  const result = opportunities(f.data, f.protocol);
  assert.deepEqual(result.signals.filter(s => s.at <= f.decision), expected);
  assert.equal(result.signals.filter(s => s.at >= gapAt + BAR).length, 0);
  assert(result.funnel.dataGap > 0);
});

test("entry plans use the declared grid for zero, three-second and sixty-second availability", () => {
  for (const [delay, expectedOffset] of [[0, 4], [3000, 5], [60000, 5]]) {
    const f = fixture(delay), signal = first(f), open = f.data.sessions.at(-1).open;
    assert.equal(signal.plannedEntryAt, open + expectedOffset * BAR);
    assert(signal.plannedEntryAt >= signal.at);
    assert.equal(planSignalEntryAt(signal.at, f.data.sessions), signal.plannedEntryAt);
  }
});

test("entry admission near session close depends on calendar, not future bars", () => {
  const f = fixture(), session = f.data.sessions.at(-1);
  assert.equal(planSignalEntryAt(session.close - 2 * BAR, f.data.sessions), session.close - 2 * BAR);
  assert.equal(planSignalEntryAt(session.close - 2 * BAR + 1, f.data.sessions), null);
  assert.equal(planSignalEntryAt(session.close, f.data.sessions), null);
});

test("a missing planned fill retains signal, quantity and unknown exposure with null PnL", () => {
  const f = fixture(), signal = first(f); remove(f, signal.plannedEntryAt);
  assert.deepEqual(first(f), signal);
  assert.throws(() => replay(f, signal), error => {
    assert(error instanceof UnobservedEntryError);
    assert.equal(error.code, "UNOBSERVED_ENTRY");
    assert.equal(error.details.reason, "MISSING_PLANNED_ENTRY_BAR");
    assert.equal(error.details.plannedEntryAt, signal.plannedEntryAt);
    assert.equal(error.details.plannedQuantity, 4);
    assert.equal(error.details.positionOpened, null);
    assert.equal(error.details.exposureUnknown, true);
    assert.equal(error.details.economicPnlUsd, null);
    const transported = JSON.parse(error.message.slice(error.message.indexOf(": ") + 2));
    assert.deepEqual(transported, error.details);
    return true;
  });
});

test("execution resolves the exact planned timestamp when an earlier unavailable bar shifts the array", () => {
  const f = fixture(), signal = first(f), expected = replay(f, signal);
  // This bar is still unfinished at signal.at and is not an observed feature.
  remove(f, signal.plannedEntryAt - BAR);
  assert.deepEqual(first(f), signal);
  assert.notEqual(f.series.bars[signal.index].t, signal.plannedEntryAt);
  const actual = replay(f, signal);
  assert.equal(actual.opened, signal.plannedEntryAt);
  assert.equal(actual.entry, expected.entry);
  assert.equal(actual.netUsd, expected.netUsd);
});

test("a caller cannot substitute a later existing fill for the causal entry plan", () => {
  const f = fixture(), signal = first(f); signal.plannedEntryAt += BAR;
  assert.throws(() => replay(f, signal), /entry plan differs from causal calendar grid/);
});

test("a gap after an opening-breakout fill retains the already opened position", () => {
  const f = fixture(), signal = first(f); remove(f, signal.plannedEntryAt + 2 * BAR);
  assert.throws(() => replay(f, signal), error => {
    assert(error instanceof UnresolvedHoldingExposureError);
    assert.equal(error.details.reason, "MISSING_BAR_WITH_OPEN_EXPOSURE");
    assert.equal(error.details.openedAt, signal.plannedEntryAt);
    assert.equal(error.details.remainingQuantity, 4);
    assert.equal(error.details.economicPnlUsd, null);
    return true;
  });
});

test("truncated data after an observed fill cannot silently remove the campaign", () => {
  const f = fixture(), signal = first(f);
  f.series.bars = f.series.bars.filter(b => b.t <= signal.plannedEntryAt);
  assert.throws(() => replay(f, signal), error => {
    assert(error instanceof UnresolvedHoldingExposureError);
    assert.equal(error.details.reason, "DATA_ENDED_WITH_OPEN_EXPOSURE");
    assert.equal(error.details.remainingQuantity, 4);
    assert.equal(error.details.economicPnlUsd, null);
    return true;
  });
});

test("an unsupported future corporate action is an incident, not a hindsight no-entry filter", () => {
  const f = fixture(), signal = first(f);
  f.data.splitEvents.push({ symbol: "SPY", at: signal.plannedEntryAt + BAR, ratio: 2 });
  assert.throws(() => replay(f, signal), error => {
    assert(error instanceof UnobservedEntryError);
    assert.equal(error.details.reason, "CORPORATE_ACTION_PATH_UNMODELED");
    assert.equal(error.details.economicPnlUsd, null);
    assert.equal(error.details.exposureUnknown, true);
    return true;
  });
});

test("legacy signals retain valid explicit index timing but cannot enter before their decision", () => {
  const f = fixture(), signal = first(f); delete signal.plannedEntryAt;
  const actual = replay(f, signal);
  assert.equal(actual.opened, f.series.bars[signal.index].t);
  const invalid = { ...signal, at: actual.opened + 1 };
  assert.throws(() => replay(f, invalid), /entry precedes signal decision/);
});

test("legacy missing execution observations also cannot become a flat result", () => {
  const f = fixture(), signal = first(f); delete signal.plannedEntryAt;
  signal.index = f.series.bars.length;
  assert.throws(() => replay(f, signal), error => {
    assert(error instanceof UnobservedEntryError);
    assert.equal(error.details.reason, "MISSING_LEGACY_ENTRY_OBSERVATION");
    assert.equal(error.details.plannedEntryAt, null);
    assert.equal(error.details.economicPnlUsd, null);
    return true;
  });
});
