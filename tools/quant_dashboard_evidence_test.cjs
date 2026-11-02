"use strict";
// Synthetic snapshots only. This suite runs the actual dashboard rendering code
// in a minimal, local DOM surface; it does not prove layout, broker connectivity,
// account performance or order execution. No network or timers are provided.
const fs = require("node:fs"), path = require("node:path"), vm = require("node:vm");
const test = require("node:test"), assert = require("node:assert/strict");
const file = path.join(__dirname, "../deploy/dashboard30.html");
const html = fs.readFileSync(file, "utf8");
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
const prefix = script.slice(0, script.indexOf("      function exitCoverage(s)"));
const disconnectSource = script.slice(script.indexOf("      function disconnect(reason)"), script.indexOf("      function renderPlugins()"));
const bannerSource = script.slice(script.indexOf("        const stale = Date.now() + serverOffset"), script.indexOf("        const liveQuote = (c)"));
const ids = [...html.matchAll(/\bid="([^"]+)"/g)].map((m) => m[1]);

function dom() {
  const nodes = new Map(ids.map((id) => [id, {id, textContent: "", innerHTML: "", className: "", disabled: false}]));
  const badges = [{className: "pill good", textContent: "PASS"}];
  const queries = [];
  const document = {
    getElementById(id) { assert.ok(nodes.has(id), "missing DOM id: " + id); return nodes.get(id); },
    querySelectorAll(selector) { queries.push(selector); return badges; },
  };
  // The VM and its synthetic snapshots must share the same injected test clock.
  const context = vm.createContext({Date, document, commands() {}, toast() {}});
  vm.runInContext(prefix, context, {filename: file});
  vm.runInContext(disconnectSource, context, {filename: file});
  vm.runInContext("function renderEntryBannerForTest(s) {\n" + bannerSource + "\n}", context, {filename: file});
  context.exitCoverage = (s) => s.operationalCoverage || {entrySafe: true, state: "NO_OPEN_POSITIONS", fresh: 0, total: 0};
  return {nodes, context, badges, queries, node: (id) => nodes.get(id), render: (s) => context.renderOperationalEvidence(s)};
}

function syntheticSnapshot() {
  const at = Date.parse("2026-11-01T14:30:00.000Z");
  return {
    fixture_nature: "SYNTHETIC_TEST_SNAPSHOT_NO_BROKER_OR_ORDERS",
    version: "30.10.1-test", mode: "paper", paused: false, halt: null,
    reconciliation: "OK", syncAt: Date.now(),
    operationalCapabilities: {
      schema: "HARPOON_OPERATIONAL_CAPABILITIES_1", observed_at: at,
      state: "COLLECTING_OR_VALIDATING", operational_ready: false,
      full_autonomous_economic_cycle_verified: false,
      automatic_model_training_and_promotion_verified: false,
      position_management_independent_of_research: true,
      financial_profitability_demonstrated: false, net_candidate_bound_to_runtime: false,
      entry_additional_gate: {passes: true, failures: [], grants_order_authority: false},
      numerical_worker_budget: {max_active: 1, max_pending: 8},
      checks: [
        {id: "account_reconciliation", status: "PASS", evidence: {sync_at: at, error: null}},
        {id: "economic_net_costs_and_returns", status: "WAIT_DATA", evidence: {economic_complete: false, comparable_returns: false}},
        {id: "quant_planning", status: "WAIT_MODEL_OR_DECISION", evidence: {reason: "CALIBRATION_MISSING"}},
        {id: "net_economic_gate", status: "NOT_PROVEN", evidence: {dictamen: "VENTAJA_NO_DEMOSTRADA"}},
      ],
    },
    netAccountLedger: {
      status: "OBSERVED_ACCOUNT_NET", accountId: "SYNTHETIC-ACCOUNT-0001", reconciled: true,
      economicComplete: false, returnComplete: false, observations_count: 2,
      accountingPeriod: {from: at - 60000, through: at},
      evidence: {executionNature: "SYNTHETIC_TEST"},
      blockers: ["EXTERNAL_COST_COVERAGE_MISSING"],
      accounting: {initialEquityUsd: 20000, finalEquityUsd: 20125, accountNetPnlUsd: 125,
        externalCostsUsd: null, economicNetPnlUsd: null, totalReturnAccount: 0.00625,
        totalReturnEconomic: null, unreportedBrokerAccrualsUsd: null, unreportedBrokerAccrualsVerified: false,
        taxTreatment: "AFTER_REPORTED_ACCOUNT_WITHHOLDINGS_ONLY_OTHER_TAXES_NOT_CALCULATED"},
      costCoverage: null,
      costSource: {type:"LOCAL_COST_RECEIPT",status:"READ"},
      archive: {segments:2,archivedObservations:2000,verified:true},
    },
    prospectiveQuantObservations: {
      schema: "HARPOON_OBSERVATION_STATUS_1", status: "OBSERVED", persisted: true,
      lastSuccess: at, ageMs: 1000, intervalMs: 60000, error: null,
      frames: 10001, active_frames: 1, archived_segments: 1, maxFrames: 10000, maxArchives: 16,
      stored_bytes: 900000, committed_bytes: 890000, maxStoredBytes: 536870912, cursor: 400040,
      complete_opportunity_paths: false, financial_acceptance_allowed: false,
      latest: {accepted: 2, requested: 40, rejected: [{symbol: "SYNTHETIC", reason: "QUOTE_MISSING"}],
        coverage: {universe_complete: false, eligible: 500, sampled: 40}, phase: "OPEN_90"},
    },
  };
}

function row(d, id, label) {
  const match = d.node(id).innerHTML.match(new RegExp("<tr><td>" + label + "</td><td class=\"mono\">([^<]*)"));
  assert.ok(match, "expected table row: " + label); return match[1];
}

test("dashboard compiles; the read-only renderer is wired to real snapshot fields and all DOM IDs exist", () => {
  assert.doesNotThrow(() => new vm.Script(script, {filename: file}));
  assert.equal(new Set(ids).size, ids.length, "duplicate DOM IDs");
  assert.match(script, /renderOperationalEvidence\(s\);/);
  assert.doesNotMatch(html, /30\.3\.1/);
  const renderer = prefix.slice(prefix.indexOf("function renderOperationalEvidence"));
  assert.doesNotMatch(renderer, /\b(fetch|api|action|download|setTimeout|setInterval)\s*\(/);
  dom().render(syntheticSnapshot());
});

test("version labels come from runtime and missing version clears the previous label", () => {
  const d = dom(), s = syntheticSnapshot();
  d.render(s);
  assert.equal(d.node("runtimeVersion").textContent, s.version);
  assert.equal(d.node("runtimeVersionFooter").textContent, s.version);
  d.render({});
  assert.equal(d.node("runtimeVersion").textContent, "Versión sin lectura");
  assert.equal(d.node("runtimeVersionFooter").textContent, "Versión sin lectura");
});

test("missing account, costs and observations remain null instead of zero or ready", () => {
  const d = dom(); d.render({});
  assert.match(d.node("ledgerScope").textContent, /Cuenta: null/);
  assert.equal(row(d, "ledgerRows", "Patrimonio informado"), "null · sin dato observado");
  assert.equal(row(d, "ledgerRows", "Costes operativos externos"), "null · sin dato observado");
  assert.equal(row(d, "observationRows", "Capturas totales"), "null · sin dato observado");
  assert.doesNotMatch(d.node("ledgerRows").innerHTML, /\$0\.00/);
  assert.notEqual(d.node("operationalHeadline").className, "good");
  assert.equal(d.node("observationDetails").textContent, "null");
});

test("known zero costs differ from missing costs, and incomplete economic result stays null", () => {
  const d = dom(), s = syntheticSnapshot(); d.render(s);
  assert.equal(row(d, "ledgerRows", "Costes operativos externos"), "null · sin dato observado");
  assert.equal(row(d, "ledgerRows", "Resultado económico neto"), "null · sin dato observado");
  s.netAccountLedger.accounting.externalCostsUsd = 0; d.render(s);
  assert.equal(row(d, "ledgerRows", "Costes operativos externos"), "$0.00");
  assert.equal(row(d, "ledgerRows", "Resultado económico neto"), "null · sin dato observado");
});

test("positive account PnL does not turn financial proof or complete autonomy green", () => {
  const d = dom(), s = syntheticSnapshot();
  s.operationalCapabilities.state = "OPERATIONALLY_READY";
  s.operationalCapabilities.operational_ready = true; d.render(s);
  assert.equal(row(d, "ledgerRows", "Resultado neto de la cuenta"), "$125.00");
  assert.equal(d.node("operationalHeadline").className, "good");
  assert.equal(d.node("financialEvidenceStatus").textContent, "VENTAJA NO DEMOSTRADA");
  assert.equal(d.node("financialEvidenceStatus").className, "wait");
  assert.equal(d.node("autonomousEconomicStatus").textContent, "NO VERIFICADA");
  assert.equal(d.node("autonomousEconomicStatus").className, "wait");
  assert.match(d.node("autonomousTrainingDetail").textContent, /false$/);
});

test("candidate for forward validation is explicitly narrower than demonstrated profit", () => {
  const d = dom(), s = syntheticSnapshot();
  s.operationalCapabilities.net_candidate_bound_to_runtime = true;
  s.operationalCapabilities.checks.at(-1).status = "CANDIDATE_FOR_FORWARD_ONLY"; d.render(s);
  assert.match(d.node("financialCandidateDetail").textContent, /CANDIDATO PARA VALIDACIÓN FORWARD/);
  assert.match(d.node("operationalChecks").innerHTML, /class="pill wait">CANDIDATE_FOR_FORWARD_ONLY/);
  assert.equal(d.node("financialEvidenceStatus").textContent, "VENTAJA NO DEMOSTRADA");
  assert.notEqual(d.node("financialEvidenceStatus").className, "good");
});

test("reported blockers, reasons and evidence are escaped before entering HTML", () => {
  const d = dom(), s = syntheticSnapshot();
  s.operationalCapabilities.state = "HALT_NEW_RISK";
  s.operationalCapabilities.entry_additional_gate.failures = ['BROKER_<img src=x onerror="alert(1)">'];
  s.operationalCapabilities.checks[0].evidence.error = "</pre><script>bad()</script>";
  s.prospectiveQuantObservations.error = "OBSERVATION_BYTE_LIMIT"; d.render(s);
  const value = d.node("operationalBlockers").innerHTML + d.node("operationalChecks").innerHTML;
  assert.match(value, /&lt;img/); assert.match(value, /&lt;script&gt;/);
  assert.doesNotMatch(value, /<img|<script>/);
  assert.match(value, /EXTERNAL_COST_COVERAGE_MISSING/);
  assert.match(value, /CALIBRATION_MISSING/);
  assert.match(value, /OBSERVATION_BYTE_LIMIT/);
  assert.equal(d.node("operationalHeadline").className, "bad");
});

test("capture reports continuous totals, actual storage reservations and partial universe scope", () => {
  const d = dom(), s = syntheticSnapshot(); d.render(s);
  assert.equal(row(d, "observationRows", "Capturas totales"), (10001).toLocaleString("es-MX"));
  assert.equal(row(d, "observationRows", "Capturas del segmento activo"), "1");
  assert.equal(row(d, "observationRows", "Segmentos archivados"), "1");
  assert.equal(row(d, "observationRows", "Bytes reservados"), (900000).toLocaleString("es-MX"));
  assert.match(d.node("observationFinancialScope").textContent, /Trayectorias completas: false/);
  assert.match(d.node("observationFinancialScope").textContent, /aceptación financiera permitida por la captura: false/);
  assert.equal(JSON.parse(d.node("observationDetails").textContent).coverage.universe_complete, false);
  assert.match(d.node("observationRows").innerHTML, /no representa operaciones ejecutadas/);
  assert.equal(row(d, "ledgerRows", "Observaciones contables archivadas"), (2000).toLocaleString("es-MX"));
  assert.equal(row(d, "ledgerRows", "Segmentos contables verificados"), "2");
  assert.match(d.node("ledgerCompleteness").textContent, /fuente de costes: LOCAL_COST_RECEIPT/);
});

test("stale ledger and failed capture preserve last values with explicit unverified current status", () => {
  const d = dom(), s = syntheticSnapshot();
  s.netAccountLedger.status = "STALE"; s.netAccountLedger.reconciled = false;
  s.netAccountLedger.blockers.push("LEDGER_RECEIPT_STALE");
  s.prospectiveQuantObservations.status = "ERROR";
  s.prospectiveQuantObservations.persisted = false;
  s.prospectiveQuantObservations.error = "OBSERVATION_STORAGE_BUDGET_EXHAUSTED"; d.render(s);
  assert.equal(d.node("ledgerStatus").textContent, "STALE");
  assert.equal(d.node("ledgerStatus").className, "bad");
  assert.match(d.node("ledgerCompleteness").textContent, /no se reclasifican como actuales/);
  assert.equal(d.node("observationStatus").className, "bad");
  assert.match(d.node("observationScope").textContent, /persistida: false/);
  assert.match(d.node("operationalBlockers").innerHTML, /LEDGER_RECEIPT_STALE/);
});

test("disconnection removes operational green and invalidates check badges without inventing new values", () => {
  const d = dom(), s = syntheticSnapshot();
  s.operationalCapabilities.state = "OPERATIONALLY_READY";
  s.operationalCapabilities.operational_ready = true; d.render(s);
  d.context.disconnect("synthetic disconnected snapshot");
  for (const id of ["operationalHeadline", "ledgerStatus", "observationStatus"]) {
    assert.equal(d.node(id).className, "bad");
    assert.match(d.node(id).textContent, /DISCONNECTED/);
  }
  assert.match(d.node("operationalFreshness").textContent, /última lectura sin vigencia/);
  assert.ok(d.queries.some((q) => q.includes("#operationalChecks .pill")));
  assert.equal(d.badges[0].className, "pill bad");
  assert.equal(d.badges[0].textContent, "NO VERIFICADO");
});

test("global entry banner never claims active when readiness is missing, false or contradictory", () => {
  const d = dom(), s = syntheticSnapshot();
  for (const cap of [undefined, {operational_ready: false, state: "COLLECTING_OR_VALIDATING"},
    {operational_ready: true, state: "HALT_NEW_RISK"}, {operational_ready: false, state: "STOPPING"}]) {
    s.operationalCapabilities = cap; d.context.renderEntryBannerForTest(s);
    assert.match(d.node("status").textContent, /PREPARACIÓN PENDIENTE/);
    assert.equal(d.node("status").className, "banner wait");
  }
  s.operationalCapabilities = {operational_ready: true, state: "OPERATIONALLY_READY"};
  d.context.renderEntryBannerForTest(s);
  assert.match(d.node("status").textContent, /ENTRADAS PAPER ACTIVAS/);
  s.paused = true; d.context.renderEntryBannerForTest(s);
  assert.match(d.node("status").textContent, /ENTRADAS PAUSADAS/);
  assert.equal(d.node("status").className, "banner wait");
});

test("invalid numeric and boolean types remain unknown instead of coercing into observations", () => {
  const d = dom(), s = syntheticSnapshot();
  s.netAccountLedger.accounting.externalCostsUsd = "0";
  s.netAccountLedger.accounting.totalReturnEconomic = false;
  s.prospectiveQuantObservations.frames = "10000";
  s.operationalCapabilities.full_autonomous_economic_cycle_verified = "true"; d.render(s);
  assert.equal(row(d, "ledgerRows", "Costes operativos externos"), "null · sin dato observado");
  assert.equal(row(d, "ledgerRows", "Rendimiento económico"), "null · sin dato observado");
  assert.equal(row(d, "observationRows", "Capturas totales"), "null · sin dato observado");
  assert.equal(d.node("autonomousEconomicStatus").textContent, "null · sin dato observado");
});
