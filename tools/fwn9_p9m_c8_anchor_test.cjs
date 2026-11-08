"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
const { performance } = require("node:perf_hooks");
const {
  CONTRACT, conservativeOverlay, rawVsRepricedAnchor,
  weak72hPriceMomentUpper, evidence,
} = require("./fwn9_p9m_c8_anchor_probe.cjs");

const cases = [];
function test(name, f) { cases.push([name, f]); }
test("original M9 nominal constants and no cap-continuous assumption", () => {
  assert.equal(CONTRACT.capital, 20000);
  assert.equal(CONTRACT.fraction, 0.12);
  assert.equal(CONTRACT.risk, 0.0025);
  assert.equal(CONTRACT.commission, 0.005);
  assert.equal(CONTRACT.nominalFriction, 0.0003);
  assert.equal(CONTRACT.maxHoldingHours, 72);
});
test("the actual native reservation snapshot is not marked to current prices", () => {
  const f = rawVsRepricedAnchor();
  assert.equal(f.nativeSecondReservationStatus, "RESERVED");
  assert.equal(f.plannerAllowsB, true);
  assert.equal(f.maxPriceRatioFromDecision, 1);
  assert.equal(f.rawAnchorPasses, false);
  assert(f.exposureAtPrebarUsd > f.rawAnchorUsd);
  assert(f.rawAnchorUsd < f.correctedAnchorUsd);
});
test("conservative full-original-quantity repricing repairs this fixture", () => {
  const f = rawVsRepricedAnchor();
  assert.equal(f.correctedAnchorPasses, true);
  assert.equal(f.correctedWithinGrossGate, true);
  assert(f.cashAfterEvents > 0);
  assert(f.equityAfterEvents > 0);
});
test("IOC NO_FILL releases B only upon observed NO_FILL and adds zero shares", () => {
  const f = rawVsRepricedAnchor({ noFill: true });
  assert.equal(f.BOpened, false);
  assert.equal(f.exposureAtPrebarUsd, 2200);
  assert.equal(f.rawSnapshotAfterUsd, 2000.30);
});
test("partial sale does not proportionally release native reservation quantity", () => {
  const a = rawVsRepricedAnchor();
  const p = rawVsRepricedAnchor({ partial: true });
  assert.equal(p.remainingA, 7);
  assert.equal(p.rawSnapshotAfterUsd, a.rawSnapshotAfterUsd);
  assert(p.equityAfterEvents < a.equityAfterEvents);
  assert(p.cashAfterEvents > a.cashAfterEvents);
});
test("native reservation library alone is not a repriced eligibility gate", () => {
  const f = rawVsRepricedAnchor({ firstMark: 260 });
  assert.equal(f.nativeSecondReservationStatus, "RESERVED");
  assert.equal(f.plannerAllowsB, false);
  assert.equal(f.correctedWithinGrossGate, false);
  // This is NOT a native full-replay admission: the caller omitted the
  // separate planProfit8FundedEntry conservative mark check.
});
test("invalid quotes/missing causal marks fail closed", () => {
  assert.throws(() => rawVsRepricedAnchor({ firstMark: NaN }), /positive finite/);
  assert.throws(() => conservativeOverlay({
    reservations: [{ state: "OPENED", notionalUsd: 100, quantity: 1, symbol: "SYNA" }],
  }, {}), /missing causal/);
});
test("finite WEAK max-price-ratio second/fourth moments (no wealth moments)", () => {
  for (const [r, q] of [[2, 4], [4, 8]]) {
    const env = weak72hPriceMomentUpper(r, q);
    assert.equal(env.targetPower, r);
    assert(Number.isFinite(env.upper) && env.upper > 1);
    assert.equal(env.bars, 312);
    assert.equal(env.overnightEvents, 4);
  }
});
test("no accidental evaluation of final M10 or prospective statistical spending", () => {
  const ev = evidence();
  assert.equal(ev.economic_accounts, 0);
  assert.equal(ev.prospective_alpha_spent, 0);
  assert.equal(ev.unopened_M10_final_accounts, 3200);
  assert.equal(ev.native_population_wealth_bound_certified, false);
});
test("reproduce bitwise stable deterministic JSON", () => {
  assert.equal(JSON.stringify(evidence()), JSON.stringify(evidence()));
});
test("locked M9 core and reservation files match immutable registration", () => {
  const root = path.join(__dirname, "..");
  const registration = JSON.parse(fs.readFileSync(path.join(root,
    "research/modulation9/registration.json"), "utf8"));
  for (const file of [
    "runtime30/ultimate_reservations.js",
    "runtime30/profit8_replay.js",
    "quant/harpoon_quant/modulation9.py",
  ]) {
    const current = crypto.createHash("sha256").update(
      fs.readFileSync(path.join(root, file))).digest("hex");
    assert.equal(current, registration.sources_sha256[file], file);
  }
});
let count = 0;
for (const [name, run] of cases) {
  run();
  count++;
  process.stdout.write("PASS C8 " + name + "\n");
}
const start = performance.now();
for (let j = 0; j < 1000; j++) evidence();
const ms = performance.now() - start;
assert(Number.isFinite(ms) && ms < 60000);
process.stdout.write(JSON.stringify({
  schema: "FWN9_C8_NATIVE_TESTS_1", passed: count,
  benchmark_1000_runs_ms: ms, economic_accounts: 0,
  independent_review: "PYTHON_DECIMAL_CHECK_SEPARATELY",
}) + "\n");
