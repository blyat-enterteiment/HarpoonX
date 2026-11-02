"use strict";
// Real HTTP/browser with SYNTHETIC broker and dataset, not account or performance evidence.
const fs = require("node:fs"),
  path = require("node:path"),
  assert = require("node:assert/strict");
const { ready } = require("./xxx_fixtures.cjs"),
  { dataset } = require("./ultimate_fixtures.cjs"),
  { server } = require("../runtime30/server.js");
(async () => {
  const qaDir = process.env.HARPOON_QA_OUTPUT_DIR ||
    path.join(__dirname, "../evidence/operational-30.3.1");
  fs.mkdirSync(qaDir, { recursive: true });
  const { chromium } = require(
    process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES
      ? process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES + "/playwright"
      : "playwright",
  );
  const origin = "http://127.0.0.1:19131";
  const { e } = await ready(),
    password = "x".repeat(40),
    app = server(
      e,
      password,
      fs.readFileSync(
        path.join(__dirname, "../deploy/dashboard30.html"),
        "utf8",
      ),
      origin,
    );
  await new Promise((r) => app.listen(19131, "127.0.0.1", r));
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.CHROMIUM_EXECUTABLE_PATH || undefined,
    args: ["--no-sandbox", "--disable-dev-shm-usage"],
  });
  const page = await browser.newPage({
      httpCredentials: { username: "trader", password },
      viewport: { width: 1440, height: 1000 },
    }),
    errors = [],
    checks = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const check = async (name, run) => {
    await run();
    checks.push(name);
  };
  try {
    await page.goto(origin);
    await page.waitForFunction(() =>
      document.querySelector("#connection").textContent.includes("PAPER"),
    );
    await check("autopilot state is supplied by the core", async () =>
      assert.match(
        await page.locator("#connection").textContent(),
        /SCANNING|WAIT_DATA|STARTING/,
      ),
    );
    await page.locator('[data-tab="ultimate"]').click();
    await check(
      "Ultimate has computed bundled research with scope and no promotion",
      async () => {
        assert.equal(await page.locator("#ultimateResults tr").count(), 9);
        assert.match(
          await page.locator("#ultimateReportScope").textContent(),
          /no retorno de cuenta/,
        );
      },
    );
    await check(
      "server rejects invalid protocol instead of registering a fictitious experiment",
      async () => {
        await page.locator("#ultimateProtocol").fill("{}");
        await page.locator("#ultimateRegister").click();
        await page.waitForFunction(() =>
          document.querySelector("#toast").textContent.includes("schema"),
        );
        assert.equal(e.ultimateLab.state.trials.length, 0);
      },
    );
    const fixture = dataset();
    await check(
      "user registers immutable protocol through the UI",
      async () => {
        await page
          .locator("#ultimateProtocol")
          .fill(JSON.stringify(fixture.protocol));
        await page.locator("#ultimateRegister").click();
        await page.waitForFunction(() =>
          document
            .querySelector("#ultimateDetail")
            .textContent.includes("REGISTERED"),
        );
        assert.equal(e.ultimateLab.state.trials.length, 1);
      },
    );
    await check(
      "observed-file import validates and locks dataset",
      async () => {
        await page
          .locator("#ultimateData")
          .setInputFiles({
            name: "SYNTHETIC_TEST_ONLY.json",
            mimeType: "application/json",
            buffer: Buffer.from(JSON.stringify(fixture.data)),
          });
        await page.waitForFunction(() =>
          document
            .querySelector("#ultimateDetail")
            .textContent.includes("READY"),
        );
        assert.equal(await page.locator("#ultimateData").isDisabled(), true);
      },
    );
    await check(
      "run button queues actual worker and returns nine evaluated policies",
      async () => {
        await page.locator("#ultimateRun").click();
        await page.waitForFunction(() =>
          document
            .querySelector("#ultimateDetail")
            .textContent.includes("QUEUED"),
        );
        await e.ultimateLab.tick();
        await page.evaluate(() => refresh());
        await page.waitForFunction(() =>
          document
            .querySelector("#ultimateDetail")
            .textContent.includes("COMPLETE"),
        );
        assert.equal(await page.locator("#ultimateResults tr").count(), 9);
        assert.equal(e.ultimateLab.state.trials[0].result.promotion, "NONE");
      },
    );
    await check("export downloads frozen protocol and hash chain", async () => {
      const [file] = await Promise.all([
        page.waitForEvent("download"),
        page.locator("#ultimateExport").click(),
      ]);
      const bytes = fs.readFileSync(await file.path()),
        data = JSON.parse(bytes);
      assert(data.chain.length >= 5);
      assert.equal(data.trial.status, "COMPLETE");
    });
    await page.locator('[data-tab="futures"]').click();
    await check(
      "unconfigured futures never display ALIVE or accept a plan",
      async () => {
        assert.match(
          await page.locator("#futuresHeadline").textContent(),
          /NOT_CONFIGURED/,
        );
        assert.equal(await page.locator("#futuresPlan").isDisabled(), true);
        assert.equal(
          await page.locator("#futuresHealth .pill.good").count(),
          0,
        );
      },
    );
    await check("all ten navigation tabs remain accessible", async () => {
      assert.equal(await page.locator("[data-tab]").count(), 10);
      for (const id of [
        "overview",
        "health",
        "plugins",
        "signals",
        "risk",
        "research",
        "journal",
        "takeprofit",
        "ultimate",
        "futures",
      ]) {
        await page.locator('[data-tab="' + id + '"]').click();
        assert(await page.locator("#" + id).isVisible());
      }
    });
    await check("mobile viewport contains the new panels", async () => {
      await page.setViewportSize({ width: 390, height: 844 });
      for (const id of ["ultimate", "futures"]) {
        await page.locator('[data-tab="' + id + '"]').click();
        assert(await page.locator("#" + id).isVisible());
        assert(
          await page.evaluate(
            () => document.documentElement.scrollWidth <= innerWidth + 2,
          ),
        );
      }
    });
    await page.screenshot({
      path: path.join(qaDir, "ultimate-mobile-qa.png"),
      fullPage: true,
    });
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.locator('[data-tab="ultimate"]').click();
    await page.screenshot({
      path: path.join(qaDir, "ultimate-desktop-qa.png"),
      fullPage: true,
    });
    await check(
      "disconnect removes confidence and disables all Ultimate mutations",
      async () => {
        await page.route("**/v1/state", (route) => route.abort());
        await page.evaluate(() => refresh());
        assert.match(
          await page.locator("#ultimateHeadline").textContent(),
          /DISCONNECTED/,
        );
        assert.match(
          await page.locator("#futuresHeadline").textContent(),
          /DISCONNECTED/,
        );
        for (const id of [
          "ultimateRegister",
          "ultimateData",
          "ultimateRun",
          "ultimateExport",
          "futuresPlan",
        ])
          assert(await page.locator("#" + id).isDisabled());
      },
    );
    await check("browser executes without JS errors", async () =>
      assert.deepEqual(errors, []),
    );
    fs.writeFileSync(
      path.join(qaDir, "ultimate-browser.json"),
      JSON.stringify(
        {
          source: "SYNTHETIC_BROKER_LOCAL_HTTP_BROWSER",
          version: require("../package.json").version,
          checks,
          passed: checks.length,
          errors,
          viewports: [1440, 390],
          at: new Date().toISOString(),
        },
        null,
        2,
      ) + "\n",
    );
    console.log(JSON.stringify({ passed: checks.length, errors }));
  } finally {
    await browser.close();
    await new Promise((r) => app.close(r));
  }
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
