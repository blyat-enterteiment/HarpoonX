"use strict";
// SYNTHETIC HTTP/browser contract regression only. Coverage fault cases are injected
// telemetry, not evidence of live manager fairness, broker protection or profitability.
const fs = require("node:fs"),
  path = require("node:path"),
  assert = require("node:assert/strict"),
  { ready, signal, prepare } = require("./xxx_fixtures.cjs"),
  { server } = require("../runtime30/server.js");
(async () => {
  const qaDir = process.env.HARPOON_QA_OUTPUT_DIR ||
    path.join(__dirname, "../evidence/operational-30.3.1");
  fs.mkdirSync(qaDir, { recursive: true });
  const { chromium } = require(
      process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES
        ? process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES + "/playwright"
        : "playwright",
    ),
    html = fs.readFileSync(path.join(__dirname, "../deploy/dashboard30.html"), "utf8"),
    checks = [], errors = [];
  assert.equal(html, fs.readFileSync(path.join(__dirname, "../HARPOON_XXXUltimate.html"), "utf8"));
  checks.push("served dashboard exactly matches active HTML artifact");
  const { e } = await ready(), s = signal();
  prepare(e, s);
  await e.entries("equity");
  await e.reconcile();
  await e.manage();
  await e.reconcile();
  e.probe.start();
  const c = e.active()[0], now = Date.now(), oldCompletion = now - 1200;
  let coverage = {
    state: "WAITING", entrySafe: false, total: 2, completed: 1, fresh: 1,
    deadlineMs: 5000, lastCompletedAt: oldCompletion,
    positions: [
      { campaign: c.id, symbol: c.symbol, book: c.book,
        lastAttempt: oldCompletion, lastCompleted: oldCompletion, ageMs: 1200,
        outcome: "HOLD", detail: "SYNTHETIC completed position", state: "ALIVE",
        quoteAt: now, syncAt: now },
      { campaign: "SYNTHETIC-SECOND-CAMPAIGN", symbol: "SPXL", book: "etf",
        lastAttempt: now, lastCompleted: 0, ageMs: null,
        outcome: "NOT_EVALUATED", detail: "SYNTHETIC second position has not completed", state: "WAITING",
        quoteAt: now, syncAt: now },
    ],
    detail: "SYNTHETIC 1/2 positions covered; a recent lane cannot cover the other position",
  };
  // Narrow dependency injection verifies the public health/UI contract. Manager
  // behavior is independently tested by the operational unit regression suite.
  e.exitCoverage = () => structuredClone(coverage);
  e.exitCheckAt = Date.now();
  const lane = e.scheduler.lanes.find((l) => l.name === "positions-and-take-profit");
  lane.lastSuccess = Date.now(); lane.lastStart = Date.now(); lane.runs = 1;
  const password = "synthetic-" + "x".repeat(40), origin = "http://127.0.0.1:19132",
    app = server(e, password, html, origin);
  await new Promise((r) => app.listen(19132, "127.0.0.1", r));
  let browser;
  try {
    browser = await chromium.launch({ headless: true,
      executablePath: process.env.CHROMIUM_EXECUTABLE_PATH || undefined,
      args: ["--no-sandbox", "--disable-dev-shm-usage"],
    });
    const page = await browser.newPage({ httpCredentials: { username: "trader", password },
      viewport: { width: 1440, height: 1080 } });
    page.on("pageerror", (error) => errors.push(error.message));
    const check = async (name, fn) => { await fn(); checks.push(name); },
      refresh = () => page.evaluate(() => refresh()),
      tab = async (id) => {
        await page.locator('[data-tab="' + id + '"]').click();
        assert(await page.locator("#" + id).isVisible());
      };
    await page.goto(origin);
    await page.waitForFunction(() => document.querySelector("#connection").textContent.includes("PAPER"));
    await check("partial completion stays WAITING despite fresh global timestamp and healthy scheduler", async () => {
      const h = e.view().health, exit = h.components.find((x) => x.id === "exit-decisions");
      assert.equal(exit.state, "WAITING"); assert.equal(exit.fresh, 1);
      assert.equal(exit.lastSuccess, oldCompletion); assert.notEqual(h.status, "ALIVE");
      assert.match(await page.locator("#guardianStatus").textContent(), /WAITING.*1 \/ 2/);
      assert.equal(await page.locator("#guardianStatus .good").count(), 0);
      assert.match(await page.locator("#status").textContent(), /nuevas entradas bloqueadas/);
      assert(await page.locator("#resume").isDisabled());
    });
    await tab("health");
    await check("every position exposes completion, age, outcome and quote/reconciliation inputs", async () => {
      assert.equal(await page.locator("#exitCoverageRows tr").count(), 2);
      const pending = page.locator("#exitCoverageRows tr").nth(1);
      assert.match(await pending.textContent(), /SPXL.*WAITING.*Sin ejecución.*Sin muestra.*NOT_EVALUATED/);
      assert.match(await page.locator("#exitCoverageSummary").textContent(), /1 \/ 2 vigentes.*1 completadas/);
      assert.equal(await pending.locator(".good").count(), 0);
    });
    await check("complete fresh coverage is rendered ALIVE only from explicit per-position coverage", async () => {
      coverage.state = "ALIVE"; coverage.entrySafe = true; coverage.completed = 2; coverage.fresh = 2;
      Object.assign(coverage.positions[1], { state: "ALIVE", lastCompleted: now, ageMs: 100,
        outcome: "HOLD", detail: "SYNTHETIC second position completed" });
      await refresh();
      assert.match(await page.locator("#exitCoverageSummary").textContent(), /ALIVE.*2 \/ 2 vigentes/);
      assert.equal(await page.locator("#exitCoverageRows .good").count(), 2);
    });
    await check("stale position degrades aggregate coverage even when another completion is recent", async () => {
      coverage.state = "STALE"; coverage.entrySafe = false; coverage.fresh = 1; coverage.lastCompletedAt = Date.now();
      Object.assign(coverage.positions[1], { state: "STALE", ageMs: 7000,
        detail: "SYNTHETIC evaluation deadline exceeded" });
      await refresh();
      assert.match(await page.locator("#guardianStatus").textContent(), /STALE.*1 \/ 2/);
      assert.match(await page.locator("#exitCoverageRows tr").nth(1).textContent(), /STALE.*7 s/);
      assert.equal(e.view().health.status, "DEGRADED");
    });
    await check("failed evaluation preserves historical completion and exposes the error", async () => {
      coverage.state = "ERROR"; coverage.lastCompletedAt = oldCompletion;
      Object.assign(coverage.positions[1], { state: "ERROR", outcome: "ERROR",
        lastAttempt: Date.now(), detail: "SYNTHETIC_EXIT_FAILURE" });
      await refresh();
      assert.match(await page.locator("#exitCoverageRows").textContent(), /SYNTHETIC_EXIT_FAILURE/);
      assert.equal(e.view().health.components.find((x) => x.id === "exit-decisions").lastSuccess, oldCompletion);
      assert.equal(await page.locator("#guardianStatus .good").count(), 0);
    });
    await check("backoff remains a visible incomplete outcome without a fabricated completion", async () => {
      coverage.state = "DEGRADED"; coverage.completed = 1;
      Object.assign(coverage.positions[1], { state: "DEGRADED", outcome: "BACKOFF",
        lastCompleted: 0, ageMs: null, detail: "SYNTHETIC protection backoff; retry pending" });
      await refresh();
      const row = await page.locator("#exitCoverageRows tr").nth(1).textContent();
      assert.match(row, /Sin ejecución.*Sin muestra.*BACKOFF/);
      assert.equal(await page.locator("#guardianStatus .good").count(), 0);
    });
    await check("held native order is distinct from evaluated software coverage and never a green protection", async () => {
      const protect = e.pending(c).find((i) => i.kind === "protect"), status = protect.status;
      protect.status = "held";
      await refresh();
      assert.equal(e.view().health.protection.held, 1);
      assert.equal(e.view().health.components.find((x) => x.id === "native-stop-alignment").state, "DEGRADED");
      await tab("overview");
      assert.match(await page.locator("#positions").textContent(), /NATIVA HELD/);
      assert.equal(await page.locator("#positions tr td").nth(5).locator(".good").count(), 0);
      await tab("takeprofit");
      assert.match(await page.locator("#tpPlans").textContent(), /NATIVA HELD/);
      assert.equal(await page.locator("#tpPlans .good").count(), 0);
      protect.status = status;
    });
    await check("stale reconciliation invalidates native protection confidence", async () => {
      const syncAt = e.syncAt; e.syncAt = Date.now() - 20000;
      await refresh();
      assert.match(await page.locator("#tpPlans").textContent(), /SNAPSHOT VENCIDO/);
      assert.equal(e.view().health.components.find((x) => x.id === "native-stop-alignment").state, "STALE");
      e.syncAt = syncAt;
    });
    await check("missing coverage cannot fall back to scheduler success", async () => {
      const snapshot = e.view(); delete snapshot.operationalCoverage; delete snapshot.health.operationalCoverage;
      await page.evaluate((s) => render(s), snapshot);
      assert.match(await page.locator("#guardianStatus").textContent(), /WAITING.*0 \/ 1/);
      assert.equal(await page.locator("#guardianStatus .good").count(), 0);
      assert.match(await page.locator("#positions").textContent(), /NOT_EVALUATED/);
      await refresh();
    });
    await tab("futures");
    await check("futures explicitly remains demo/PAPER explicit-order separate from four autonomous books", async () => {
      const scope = await page.locator("#futuresScope").textContent();
      assert.match(scope, /demo\/PAPER/); assert.match(scope, /separado del gestor autónomo Alpaca/);
      assert.match(scope, /No hay gestión autónoma de futuros/);
      assert.match(scope, /confirmación explícitas/);
      assert.equal(await page.locator("#books .card").count(), 4);
      assert(await page.locator("#futuresPlan").isDisabled());
      assert.equal(await page.locator("#futuresHealth .good").count(), 0);
    });
    await check("repeated navigation and narrow layouts preserve all coverage rows without page overflow", async () => {
      for (const width of [1440, 420, 390]) {
        await page.setViewportSize({ width, height: 900 });
        for (const id of ["overview", "health", "takeprofit", "futures", "health", "overview"]) {
          await tab(id);
          assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 2), id + " " + width);
        }
      }
    });
    await tab("health");
    await page.screenshot({ path: path.join(qaDir, "operational-coverage-mobile.png"), fullPage: true });
    await page.setViewportSize({ width: 1440, height: 1080 });
    await page.screenshot({ path: path.join(qaDir, "operational-coverage-desktop.png"), fullPage: true });
    await check("disconnect invalidates aggregate and per-position confidence and disables actions", async () => {
      await page.route("**/v1/state", (r) => r.abort());
      await refresh();
      assert.match(await page.locator("#exitCoverageSummary").textContent(), /DISCONNECTED/);
      assert.match(await page.locator("#guardianStatus").textContent(), /DISCONNECTED/);
      assert.equal(await page.locator("#exitCoverageRows .good, #positions .good, #tpPlans .good").count(), 0);
      assert(await page.locator("#resume").isDisabled());
    });
    await check("browser runs without JavaScript exceptions", async () => assert.deepEqual(errors, []));
    const report = { source: "SYNTHETIC_TELEMETRY_LOCAL_HTTP_BROWSER", version: require("../package.json").version,
      generatedAt: new Date().toISOString(), passed: checks.length, checks,
      coverageScope: "Health/UI contract mapping with injected coverage, not manager execution evidence",
      viewports: [1440, 420, 390], errors, externalOrders: 0 };
    fs.writeFileSync(path.join(qaDir, "operational-browser.json"), JSON.stringify(report, null, 2) + "\n");
    console.log(JSON.stringify(report));
  } finally {
    if (browser) await browser.close();
    e.probe.close();
    await new Promise((r) => app.close(r));
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });
