"use strict";
// SYNTHETIC rendering contract in a minimal DOM stub. This is NOT a browser,
// layout, user-interaction, external broker or live manager verification.
const fs = require("node:fs"), vm = require("node:vm"), path = require("node:path"),
  assert = require("node:assert/strict"), test = require("node:test"),
  { ready, signal, prepare } = require("./xxx_fixtures.cjs");
const html = fs.readFileSync(path.join(__dirname, "../HARPOON_XXXUltimate.html"), "utf8");
function renderer() {
  const elements = new Map([...html.matchAll(/\bid="([^"]+)"/g)].map(([, id]) => [id,
    { id, value: "", textContent: "", innerHTML: "", disabled: false, className: "", title: "" }]));
  const document = {
    getElementById(id) { assert(elements.has(id), "UI element exists: " + id); return elements.get(id); },
    querySelectorAll() { return []; },
  };
  // Evaluate unchanged rendering functions; omit only event binding/startup below them.
  const script = html.match(/<script>([\s\S]*?)<\/script>/)[1],
    boundary = script.indexOf('      for (const b of document.querySelectorAll("[data-tab]"))');
  assert(boundary > 0);
  const context = vm.createContext({ document, Date, console });
  vm.runInContext(script.slice(0, boundary), context);
  return { elements, render(snapshot) { context.snapshot = snapshot; vm.runInContext("render(snapshot)", context); } };
}
async function fixture() {
  const { e } = await ready(), s = signal(); prepare(e, s);
  await e.entries("equity"); await e.reconcile(); await e.manage(); await e.reconcile();
  const c = e.active()[0], now = Date.now(), coverage = {
    state: "WAITING", entrySafe: false, total: 2, completed: 1, fresh: 1, deadlineMs: 5000, lastCompletedAt: now - 1200,
    positions: [
      { campaign: c.id, symbol: c.symbol, book: c.book, lastAttempt: now - 1200, lastCompleted: now - 1200,
        ageMs: 1200, outcome: "EVALUATED", detail: "SYNTHETIC evaluated", state: "ALIVE", quoteAt: now, syncAt: now },
      { campaign: "SYNTHETIC-SECOND", symbol: "SPXL", book: "etf", lastAttempt: now, lastCompleted: 0,
        ageMs: null, outcome: "NOT_EVALUATED", detail: "SYNTHETIC not evaluated", state: "WAITING", quoteAt: now, syncAt: now },
    ], detail: "SYNTHETIC incomplete coverage",
  };
  e.exitCoverage = () => structuredClone(coverage);
  return { e, c, coverage, ...renderer() };
}
test("active and deployed HTML are byte-identical and explicitly separate futures demo/PAPER", () => {
  assert.equal(html, fs.readFileSync(path.join(__dirname, "../deploy/dashboard30.html"), "utf8"));
  assert.match(html, /Ironbeam demo\/PAPER: conector separado del gestor autónomo Alpaca/);
  assert.match(html, /No hay gestión autónoma de futuros/);
});
test("partial coverage never promotes healthy lane/global timestamp to exit ALIVE", async () => {
  const { e, coverage, render, elements } = await fixture();
  e.exitCheckAt = Date.now(); e.scheduler.lanes[0].lastSuccess = Date.now();
  const snapshot = e.view(), exit = snapshot.health.components.find((x) => x.id === "exit-decisions");
  assert.equal(exit.state, "WAITING"); assert.equal(exit.lastSuccess, coverage.lastCompletedAt);
  assert.equal(exit.total, 2); assert.equal(exit.fresh, 1); assert.notEqual(snapshot.health.status, "ALIVE");
  render(snapshot);
  assert.match(elements.get("guardianStatus").innerHTML, /WAITING.*1 \/ 2/);
  assert.doesNotMatch(elements.get("guardianStatus").innerHTML, /pill good/);
  assert.match(elements.get("exitCoverageSummary").textContent, /1 \/ 2 vigentes.*1 completadas/);
  assert.match(elements.get("exitCoverageRows").innerHTML, /SPXL[\s\S]*Sin ejecución[\s\S]*Sin muestra[\s\S]*NOT_EVALUATED/);
  assert.equal(elements.get("resume").disabled, true);
});
test("coverage states and per-position ages, outcomes and failure details render without freshening", async () => {
  const { e, coverage, render, elements } = await fixture(), initial = coverage.lastCompletedAt;
  for (const state of ["ALIVE", "STALE", "DEGRADED", "ERROR", "WAITING"]) {
    coverage.state = state;
    coverage.entrySafe = state === "ALIVE";
    Object.assign(coverage.positions[0], { state, ageMs: state === "STALE" ? 7000 : 1200,
      outcome: state === "ERROR" ? "ERROR" : state === "DEGRADED" ? "BACKOFF" : "EVALUATED",
      detail: "SYNTHETIC_" + state });
    render(e.view());
    assert.match(elements.get("guardianStatus").innerHTML, new RegExp(state));
    if (state !== "ALIVE") assert.doesNotMatch(elements.get("guardianStatus").innerHTML, /pill good/);
    assert.match(elements.get("positions").innerHTML, new RegExp("SYNTHETIC_" + state));
    if (state === "STALE") assert.match(elements.get("positions").innerHTML, /7 s/);
    assert.equal(e.view().health.components.find((x) => x.id === "exit-decisions").lastSuccess, initial);
  }
});
test("missing coverage falls back to WAITING without trusting campaign persisted evaluation", async () => {
  const { e, render, elements } = await fixture(), snapshot = e.view();
  delete snapshot.operationalCoverage; delete snapshot.health.operationalCoverage;
  snapshot.positions[0].evaluation = { state: "ALIVE", lastCompleted: Date.now(), ageMs: 0 };
  render(snapshot);
  assert.match(elements.get("guardianStatus").innerHTML, /WAITING.*0 \/ 1/);
  assert.match(elements.get("positions").innerHTML, /NOT_EVALUATED/);
  assert.doesNotMatch(elements.get("guardianStatus").innerHTML, /pill good/);
});
test("held native and stale/future reconciliation render separately without green protection confidence", async () => {
  const { e, c, render, elements } = await fixture(), protect = e.pending(c).find((i) => i.kind === "protect");
  protect.status = "held"; render(e.view());
  assert.equal(e.view().health.protection.held, 1);
  assert.equal(e.view().health.components.find((x) => x.id === "native-stop-alignment").state, "DEGRADED");
  assert.match(elements.get("positions").innerHTML, /NATIVA HELD/);
  assert.match(elements.get("tpPlans").innerHTML, /NATIVA HELD/);
  assert.doesNotMatch(elements.get("tpPlans").innerHTML, /pill good/);
  for (const offset of [-20000, 20000]) {
    e.syncAt = Date.now() + offset; render(e.view());
    assert.match(elements.get("positions").innerHTML, /SNAPSHOT VENCIDO/);
    assert.doesNotMatch(elements.get("tpPlans").innerHTML, /pill good/);
    assert.equal(e.view().health.components.find((x) => x.id === "native-stop-alignment").state, "STALE");
  }
});

test("session-gated coverage remains WAITING while a separately safe entry gate allows unrelated books", async () => {
  const { e, coverage, render, elements } = await fixture();
  coverage.entrySafe = true; coverage.state = "WAITING"; coverage.fresh = 1;
  Object.assign(coverage.positions[1], { outcome: "MARKET_CLOSED", state: "WAITING",
    lastCompleted: 0, ageMs: null, detail: "SYNTHETIC fresh closed session; native protection aligned" });
  const snapshot = e.view(); snapshot.paused = true; render(snapshot);
  assert.equal(elements.get("resume").disabled, false);
  assert.match(elements.get("guardianStatus").innerHTML, /WAITING.*1 \/ 2/);
  assert.doesNotMatch(elements.get("guardianStatus").innerHTML, /pill good/);
  assert.match(elements.get("exitCoverageRows").innerHTML, /MARKET_CLOSED/);
  assert.match(elements.get("profitControl").innerHTML, /Permite evaluar otros filtros/);
});
test("acknowledged held OCO child stays distinct as contingent coverage when parent linkage is valid", async () => {
  const { e, c, render, elements } = await fixture(), protect = e.pending(c).find((i) => i.kind === "protect"),
    parent = structuredClone(protect);
  parent.id = "SYNTHETIC-VALID-OCO-PARENT";
  parent.status = "new";
  parent.payload.type = "limit";
  parent.payload.order_class = "oco";
  parent.order.type = "limit";
  e.state.intents.push(parent);
  protect.parentId = parent.id;
  protect.status = "held";
  const snapshot = e.view(); render(snapshot);
  assert.equal(snapshot.health.protection.protected, 1);
  assert.equal(snapshot.health.components.find((x) => x.id === "native-stop-alignment").state, "CONTINGENT");
  assert.match(elements.get("positions").innerHTML, /NATIVA CONDICIONAL/);
  assert.match(elements.get("tpPlans").innerHTML, /NATIVA CONDICIONAL/);
  assert.doesNotMatch(elements.get("tpPlans").innerHTML, /pill good/);
});
test("missing entry-safety contract fails closed even with no confirmed inventory", async () => {
  const { e, render, elements } = await fixture(), snapshot = e.view();
  delete snapshot.operationalCoverage; delete snapshot.health.operationalCoverage;
  snapshot.positions = []; snapshot.paused = true; render(snapshot);
  assert.equal(elements.get("resume").disabled, true);
  assert.match(elements.get("guardianStatus").innerHTML, /WAITING.*0 \/ 0/);
});
