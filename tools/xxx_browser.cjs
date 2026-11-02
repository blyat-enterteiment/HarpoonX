"use strict";
// Real local HTTP/UI, controlled synthetic broker. No external orders or market evidence.
const fs = require("node:fs"),
  assert = require("node:assert/strict"),
  path = require("node:path"),
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
    { e } = await ready(),
    s = signal(),
    coverage = [];
  const check = async (label, fn) => {
    await fn();
    coverage.push(label);
  };
  prepare(e, s);
  await e.entries("equity");
  await e.reconcile();
  await e.manage();
  await e.reconcile();
  e.probe.start();
  await e.scheduler.once(
    e.scheduler.lanes.find((l) => l.name === "positions-and-take-profit"),
  );
  const password = "fixture-" + "x".repeat(40),
    origin = "http://127.0.0.1:19130",
    app = server(
      e,
      password,
      fs.readFileSync(
        path.join(__dirname, "../deploy/dashboard30.html"),
        "utf8",
      ),
      origin,
    );
  await new Promise((r) => app.listen(19130, "127.0.0.1", r));
  const browser = await chromium.launch({
      headless: true,
      executablePath: process.env.CHROMIUM_EXECUTABLE_PATH || undefined,
      args: [
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--use-gl=angle",
        "--use-angle=swiftshader",
        "--enable-unsafe-swiftshader",
      ],
    }),
    context = await browser.newContext({
      httpCredentials: { username: "trader", password },
      viewport: { width: 1440, height: 1080 },
    }),
    page = await context.newPage(),
    errors = [];
  page.on("pageerror", (err) => errors.push(err.message));
  const tab = async (id) => {
    await page.locator('[data-tab="' + id + '"]').click();
    assert(await page.locator("#" + id).isVisible());
  };
  const fresh = () => page.evaluate(() => refresh());
  try {
    await page.goto(origin);
    await page.waitForFunction(() =>
      document.querySelector("#connection").textContent.includes("PAPER"),
    );
    await check("HTTP PAPER state and four book coverage", async () => {
      assert.equal(await page.locator("#books .card").count(), 4);
      assert.match(await page.locator("#connection").textContent(), /PAPER/);
    });
    await check(
      "position has calculated targets and broker-confirmed protection",
      async () => {
        assert.equal(await page.locator("#positions tr").count(), 1);
        assert.match(
          await page.locator("#positions").textContent(),
          /CONFIRMADA/,
        );
        assert.match(await page.locator("#positions").textContent(), /R \/ /);
      },
    );
    await check(
      "equity chart uses actual observed reconciliation history",
      async () =>
        assert.equal(
          await page.locator("#equityChart svg polyline").count(),
          1,
        ),
    );
    await check("pause inputs through actual control endpoint", async () => {
      await page.locator("#pause").click();
      await page.waitForFunction(() =>
        document
          .querySelector("#status")
          .textContent.includes("ENTRADAS PAUSADAS"),
      );
      assert.equal(e.state.paused, true);
    });
    await tab("takeprofit");
    await check(
      "take-profit dashboard renders actual confirmed floor and three registered research results",
      async () => {
        assert.match(await page.locator("#tpPlans").textContent(), /ALINEADA/);
        assert.equal(await page.locator("#wfRows tr").count(), 3);
        assert.match(
          await page.locator("#exitResearchStatus").textContent(),
          /SIN CANDIDATO VALIDADO/,
        );
        assert.match(
          await page.locator("#tpLatency").textContent(),
          /Sin muestra/,
        );
      },
    );
    await check(
      "experimental exit profile requires acknowledgement and changes only future entries",
      async () => {
        const old = structuredClone(e.active()[0].policy);
        await page.locator("#exitProfileSelect").selectOption("TREND_RUNNER");
        await page.locator("#applyExitProfile").click();
        await page.waitForFunction(() =>
          document
            .querySelector("#toast")
            .textContent.includes("acknowledgement"),
        );
        assert.equal(e.state.exitProfile, undefined);
        await page.locator("#exitProfileAck").check();
        await page.locator("#applyExitProfile").click();
        await page.waitForFunction(
          () =>
            document.querySelector("#exitProfileCurrent").textContent ===
            "TREND_RUNNER",
        );
        assert.deepEqual(e.active()[0].policy, old);
        await page.locator("#exitProfileSelect").selectOption("BASELINE_30_1");
        await page.locator("#applyExitProfile").click();
        await page.waitForFunction(
          () =>
            document.querySelector("#exitProfileCurrent").textContent ===
            "BASELINE_30_1",
        );
      },
    );
    await page.screenshot({
      path: path.join(qaDir, "browser-takeprofit.png"),
      fullPage: true,
    });
    await tab("health");
    await check(
      "runtime, SQLite, core validators and actual endpoint counters render",
      async () => {
        assert((await page.locator("#services .service").count()) > 20);
        assert((await page.locator("#validators tr").count()) >= 5);
        assert((await page.locator("#endpoints tr").count()) >= 4);
        assert.match(
          await page.locator("#healthHeadline").textContent(),
          /telemetría observada/,
        );
      },
    );
    await check(
      "fault injection changes scheduler health to ERROR without fabricating success",
      async () => {
        e.scheduler.add("controlled-fault", 1000, async () => {
          throw Error("CONTROLLED_BROWSER_FAULT");
        });
        await e.scheduler.once(e.scheduler.lanes.at(-1));
        await fresh();
        assert.match(
          await page.locator("#services").textContent(),
          /CONTROLLED_BROWSER_FAULT/,
        );
        assert.match(
          await page.locator("#healthHeadline").textContent(),
          /DEGRADED/,
        );
        assert.equal(e.scheduler.lanes.at(-1).lastSuccess, 0);
      },
    );
    await check("stalled guardian is visible as STALLED", async () => {
      const l = e.scheduler.lanes.find(
        (l) => l.name === "positions-and-take-profit",
      );
      l.running = true;
      l.lastStart = Date.now() - 5000;
      await fresh();
      assert.match(await page.locator("#services").textContent(), /STALLED/);
      l.running = false;
      await e.scheduler.once(l);
    });
    await tab("plugins");
    await check(
      "61 strategies and two connected selectors waiting for real models",
      async () => {
        assert.equal(await page.locator("#pluginRows tr").count(), 61);
        for (const id of ["equity-strategy-14", "etf-strategy-14"])
          assert.equal(
            await page.locator('[data-plugin="' + id + '"]').isDisabled(),
            false,
          );
        assert.match(
          await page.locator("#pluginCount").textContent(),
          /2 esperando modelo/,
        );
      },
    );
    await check("strategy filter and selection save persist", async () => {
      await page.locator("#pluginSearch").fill("options");
      assert.equal(await page.locator("#pluginRows tr").count(), 3);
      await page.locator('[data-plugin="options-call-breakout"]').uncheck();
      await page.locator("#savePlugins").click();
      await page.waitForFunction(
        () =>
          document.querySelector("#toast").textContent === "Selección guardada",
      );
      assert(!e.state.plugins.includes("options-call-breakout"));
    });
    await tab("overview");
    await check(
      "resume handler still uses reconciliation/risk authority",
      async () => {
        await e.sessions();
        prepare(e, s);
        await e.reconcile();
        await e.manage();
        await fresh();
        await page.locator("#resume").click();
        await page.waitForFunction(() =>
          document.querySelector("#status").textContent.includes("ACTIVAS"),
        );
        assert.equal(e.state.paused, false);
      },
    );
    await check("all eight navigation tabs are usable", async () => {
      for (const id of [
        "overview",
        "health",
        "plugins",
        "signals",
        "risk",
        "research",
        "journal",
        "takeprofit",
      ])
        await tab(id);
    });
    await tab("research");
    await check(
      "selector registration uses server policy and immutable identity",
      async () => {
        await page.locator("#costsConfirmed").check();
        await page.locator("#registerSelector").click();
        await page.waitForFunction(() =>
          document
            .querySelector("#selectorDetail")
            .textContent.includes("REGISTERED"),
        );
        assert.equal(e.selectors.state.trials.length, 1);
        assert.equal(
          e.selectors.state.trials[0].recipe.selection_filter,
          "ridge_lcb",
        );
        assert.equal(await page.locator("#installSelector").isDisabled(), true);
      },
    );
    await check(
      "malformed selector file is rejected by actual core contract",
      async () => {
        await page.locator("#selectorFile").setInputFiles({
          name: "bad-selector.json",
          mimeType: "application/json",
          buffer: Buffer.from(
            JSON.stringify({
              samples: [],
              events: [],
              sessions: { bad: {} },
            }),
          ),
        });
        await page.waitForFunction(() =>
          document
            .querySelector("#toast")
            .textContent.includes("invalid completed session"),
        );
        assert.equal(e.selectors.state.trials[0].datasetHash, null);
      },
    );
    await check(
      "selector worker completes honestly with insufficient evidence",
      async () => {
        await page.locator("#diagnoseSelector").click();
        await page.waitForFunction(() =>
          document
            .querySelector("#researchJson")
            .textContent.includes("QUEUED"),
        );
        await e.research();
        await fresh();
        assert.match(
          await page.locator("#selectorDetail").textContent(),
          /EVIDENCIA_INSUFICIENTE/,
        );
        assert.equal(await page.locator("#installSelector").isDisabled(), true);
        assert.equal(e.selectors.state.models.equity, undefined);
      },
    );
    await check(
      "selector observations export contains no manufactured samples",
      async () => {
        const pending = page.waitForEvent("download");
        await page.locator("#exportSelector").click();
        const d = await pending,
          x = JSON.parse(fs.readFileSync(await d.path(), "utf8"));
        assert.equal(x.samples.length, 0);
        assert.equal(x.prospectiveVerified, false);
      },
    );
    await check("research pause changes real scheduler gate", async () => {
      await page.locator("#pauseResearch").click();
      await page.waitForFunction(
        () =>
          JSON.parse(document.querySelector("#researchJson").textContent)
            .paused === true,
      );
      assert.equal(e.state.researchPaused, true);
    });
    await check(
      "War Room import/resume surfaces actual worker error",
      async () => {
        await page.locator("#researchFile").setInputFiles({
          name: "invalid-study.json",
          mimeType: "application/json",
          buffer: Buffer.from(
            JSON.stringify({ operation: "optimize", protocol: {}, data: {} }),
          ),
        });
        await page.waitForFunction(() =>
          document
            .querySelector("#researchJson")
            .textContent.includes("QUEUED"),
        );
        assert.equal(e.pendingResearch.operation, "optimize");
        await page.locator("#resumeResearch").click();
        await page.waitForFunction(
          () =>
            JSON.parse(document.querySelector("#researchJson").textContent)
              .paused === false,
        );
        await e.research();
        assert.equal(e.state.research.status, "ERROR");
        await fresh();
        assert.match(
          await page.locator("#researchJson").textContent(),
          /ERROR/,
        );
      },
    );
    await tab("overview");
    await fresh();
    await page.screenshot({
      path: path.join(qaDir, "browser-desktop.png"),
      fullPage: true,
    });
    await tab("health");
    await page.screenshot({
      path: path.join(qaDir, "browser-monitor.png"),
      fullPage: true,
    });
    await check(
      "responsive 420px layout has no page overflow in all tabs",
      async () => {
        await page.setViewportSize({ width: 420, height: 900 });
        for (const id of [
          "overview",
          "health",
          "plugins",
          "signals",
          "risk",
          "research",
          "journal",
          "takeprofit",
        ]) {
          await tab(id);
          assert.equal(
            await page.evaluate(
              () => document.documentElement.scrollWidth <= innerWidth,
            ),
            true,
            id,
          );
        }
        await tab("overview");
        await page.screenshot({
          path: path.join(qaDir, "browser-mobile.png"),
          fullPage: true,
        });
      },
    );
    await check(
      "flatten waits for actual controlled cancellation and broker fills",
      async () => {
        await e.sessions();
        page.once("dialog", (d) => d.accept());
        await page.locator("#flatten").click();
        await page.waitForFunction(() =>
          document.querySelector("#status").textContent.includes("PAUSADAS"),
        );
        assert(e.state.campaigns[0].flatten);
        await e.reconcile();
        await e.manage();
        await e.reconcile();
        await e.manage();
        await e.reconcile();
        assert.equal(e.active().length, 0);
      },
    );
    await tab("journal");
    await check(
      "evidence export retains closed campaigns and acknowledged fills",
      async () => {
        const pending = page.waitForEvent("download");
        await page.locator("#export").click();
        const d = await pending;
        assert.equal(d.suggestedFilename(), "HARPOON_XXX_evidencia.json");
        const x = JSON.parse(fs.readFileSync(await d.path(), "utf8"));
        assert(x.history.campaigns[0].closed);
        assert(
          x.history.intents.some(
            (i) => i.kind === "flatten" && Number(i.order.filled_qty) > 0,
          ),
        );
      },
    );
    await check(
      "network failure clears all ALIVE badges and disables mutations",
      async () => {
        await tab("health");
        await page.route("**/v1/state", (r) => r.abort());
        await page.waitForFunction(() =>
          document
            .querySelector("#status")
            .textContent.includes("SIN CONEXIÓN"),
        );
        for (const id of [
          "resume",
          "pause",
          "flatten",
          "registerSelector",
          "researchFile",
          "selectorFile",
        ])
          assert.equal(await page.locator("#" + id).isDisabled(), true);
        assert.match(
          await page.locator("#systemBadge").textContent(),
          /DISCONNECTED/,
        );
        assert.equal(
          await page
            .locator("#services .pill.good, #overview .pill.good")
            .count(),
          0,
        );
      },
    );
    await check("browser executes without JS exceptions", async () =>
      assert.deepEqual(errors, []),
    );
    fs.writeFileSync(
      path.join(qaDir, "xxx-browser.json"),
      JSON.stringify(
        {
          version: require("../package.json").version,
          generatedAt: new Date().toISOString(),
          source: "SYNTHETIC_LOCAL_BROWSER_FIXTURE",
          checks: coverage.length,
          passed: coverage.length,
          coverage,
          consoleErrors: errors,
          viewports: [1440, 420],
          externalOrders: 0,
        },
        null,
        2,
      ) + "\n",
    );
    console.log(
      "Browser: " +
        coverage.length +
        "/" +
        coverage.length +
        " checks; no JS exceptions",
    );
  } finally {
    e.probe.close();
    await browser.close();
    await new Promise((r) => app.close(r));
  }
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
