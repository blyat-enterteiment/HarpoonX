"use strict";
// Executes the real Ultimate pipeline on retained observed Alpaca bars. Fills remain modeled.
const fs = require("node:fs"),
  path = require("node:path"),
  crypto = require("node:crypto");
const { ResearchLab } = require("../../runtime30/ultimate_lab.js");
const {
  defaultProtocol,
  digest,
} = require("../../runtime30/ultimate_contracts.js");
const { Validators } = require("../../runtime30/validators.js");
const { DEFAULT_REPLAY_LIMITS } = require("../../runtime30/ultimate_replay.js");
const { DurableStore } = require("../../runtime/store30.cjs");
const root = path.resolve(__dirname, "../.."),
  output = path.join(root, "evidence/ultimate");
async function main() {
  fs.mkdirSync(output, { recursive: true });
  const rawPath = path.join(root, "evidence/tp32/prepared.json"),
    bytes = fs.readFileSync(rawPath),
    raw = JSON.parse(bytes);
  const protocol = defaultProtocol("ALPACA_PROXY");
  const sourceFiles = raw.fingerprints.map((f) => ({
    name: f.path,
    sha256: f.sha256,
  }));
  for (const f of sourceFiles) {
    const file = path.resolve(root, f.name);
    if (
      !file.startsWith(root + path.sep) ||
      crypto
        .createHash("sha256")
        .update(fs.readFileSync(file))
        .digest("hex") !== f.sha256
    )
      throw Error("Historical source checksum changed: " + f.name);
  }
  const data = {
    schema: "HARPOON-ULTIMATE-DATA-1",
    kind: "ALPACA_PROXY",
    provenance: {
      source: "RETAINED_OBSERVED_ALPACA_BARS_REUSED_HISTORY",
      feed: "SIP",
      execution: "MODELED_OHLCV",
      files: [
        ...sourceFiles,
        {
          name: "evidence/tp32/prepared.json",
          sha256: crypto.createHash("sha256").update(bytes).digest("hex"),
        },
      ],
    },
    sessions: raw.calendar,
    splitEvents: raw.splits
      .filter((s) => protocol.universe.includes(s.symbol))
      .map((s) => ({
        symbol: s.symbol,
        at:
          raw.calendar.find((d) => d.date === s.ex_date)?.open ??
          Date.parse(s.ex_date + "T13:30:00Z"),
        ratio: Number(s.new_rate) / Number(s.old_rate),
      })),
    series: protocol.universe.map((symbol) => ({
      symbol,
      root: symbol,
      pointValue: 1,
      tick: 0.01,
      bars: raw.series[symbol].map((b) => ({
        t: b[0],
        end: b[0] + 300000,
        availableAt: b[0] + 303000,
        o: b[1],
        h: b[2],
        l: b[3],
        c: b[4],
        v: b[5],
        ...(b[6] ? { vw: b[6] } : {}),
      })),
    })),
  };
  const runId = "proxy-" + Date.now(),
    account = "RETAINED-PROXY-RESEARCH",
    store = await new DurableStore(path.join(output, "research.sqlite")).open();
  // Preserve the first reviewed run when moving from its original isolated journal.
  if (
    !(await store.get("ultimate-lab-" + account)) &&
    fs.existsSync(path.join(output, "registry.json"))
  ) {
    const prior = JSON.parse(
      fs.readFileSync(path.join(output, "registry.json"), "utf8"),
    );
    if (prior.trial?.datasetHash !== digest(data))
      throw Error("Cannot migrate a different frozen dataset");
    await store.put("ultimate-lab-" + account, {
      schema: "HARPOON-ULTIMATE-LEDGER-1",
      trials: [prior.trial],
      budget: 72,
      spent: prior.trial.slots,
      chain: prior.chain,
    });
    await store.put(
      "ultimate-lab-" + account + ":dataset:" + prior.trial.id,
      data,
    );
  }
  const lab = new ResearchLab(
    store,
    account,
    new Validators(),
    DEFAULT_REPLAY_LIMITS,
  );
  const start = performance.now();
  try {
    await lab.load();
    const trial = await lab.register(protocol);
    fs.writeFileSync(
      path.join(output, "protocol.json"),
      JSON.stringify(
        {
          ...trial,
          purpose: "RETROSPECTIVE_PROXY_EXPLORATION_NOT_UNSEEN_HOLDOUT",
        },
        null,
        2,
      ) + "\n",
    );
    await lab.importData(trial.id, data);
    await lab.queue(trial.id);
    await lab.tick();
    const evidence = lab.export(trial.id),
      report = evidence.trial.result;
    if (!report) throw Error(evidence.trial.error || "No computed report");
    fs.writeFileSync(
      path.join(output, "report.json"),
      JSON.stringify(report, null, 2) + "\n",
    );
    fs.writeFileSync(
      path.join(output, "registry.json"),
      JSON.stringify(evidence, null, 2) + "\n",
    );
    const validation = {
      source: "OBSERVED_ALPACA_PROXY_MODELED_FILLS",
      runId,
      elapsedMs: performance.now() - start,
      datasetHash: digest(data),
      sourceFileCount: sourceFiles.length,
      promotions: 0,
      node: process.version,
    };
    fs.writeFileSync(
      path.join(output, "execution.json"),
      JSON.stringify(validation, null, 2) + "\n",
    );
    console.log(
      JSON.stringify({
        ...validation,
        campaigns: report.rows.map((r) => ({
          id: r.id,
          oos: r.oos.campaigns,
          expectancyR: r.oos.expectancyR,
          holdoutR: r.holdout.expectancyR,
        })),
        portfolio: report.fundedPortfolio,
        windows: report.windows,
        promotion: report.promotion,
      }),
    );
  } finally {
    await lab.stop();
    await store.close();
  }
}
if (require.main === module)
  main().catch((e) => {
    console.error(e.message);
    process.exitCode = 1;
  });
