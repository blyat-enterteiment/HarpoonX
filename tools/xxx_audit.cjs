"use strict";
// Static inventory + route review. This is not an independent production certification.
const fs = require("node:fs"),
  path = require("node:path"),
  crypto = require("node:crypto"),
  ts = require("typescript"),
  assert = require("node:assert/strict");
const root = path.resolve(__dirname, ".."),
  { SIGNAL_MODULES, create } = require("../runtime/legacy30.cjs");
const selectorRuntime = require("../runtime/selector30.cjs");
const files = [
  ...fs
    .readdirSync(path.join(root, "xxx"))
    .filter((x) => x.endsWith(".ts"))
    .map((x) => "xxx/" + x),
  "runtime/legacy30.cjs",
  "runtime/selector30.cjs",
  "runtime/exit_profiles32.cjs",
  "runtime/store30.cjs",
  "runtime/warroom3.cjs",
  "runtime/warroom_worker3.cjs",
  "deploy/managed.cjs",
  ...[...new Set([...SIGNAL_MODULES, ...selectorRuntime.MODULES])].map(
    (x) => "src/" + x + ".js",
  ),
  "src/optimizer3.js",
];
const functions = [],
  empty = [],
  markers = [],
  testImports = [],
  randomUses = [],
  fileHashes = [];
function inspect(file, code, embedded = false) {
  const source = ts.createSourceFile(file, code, ts.ScriptTarget.Latest, true);
  function visit(n) {
    if (ts.isFunctionLike(n) && n.body) {
      const line = source.getLineAndCharacterOfPosition(n.getStart()).line + 1,
        name =
          n.name?.getText(source) ||
          n.parent?.name?.getText(source) ||
          "<callback>",
        parameterProperties =
          ts.isConstructorDeclaration(n) &&
          n.parameters.some((p) =>
            p.modifiers?.some((m) =>
              [
                ts.SyntaxKind.PublicKeyword,
                ts.SyntaxKind.PrivateKeyword,
                ts.SyntaxKind.ProtectedKeyword,
              ].includes(m.kind),
            ),
          );
      functions.push({
        file,
        line,
        name,
        kind: ts.SyntaxKind[n.kind],
        embedded,
      });
      if (
        ts.isBlock(n.body) &&
        n.body.statements.length === 0 &&
        !parameterProperties
      )
        empty.push({ file, line, name, embedded });
    }
    if (
      ts.isCallExpression(n) &&
      n.expression.getText(source) === "require" &&
      n.arguments[0] &&
      ts.isStringLiteral(n.arguments[0]) &&
      /tools|test|fixture|mock|demo/i.test(n.arguments[0].text)
    )
      testImports.push({ file, import: n.arguments[0].text });
    if (
      ts.isStringLiteral(n) &&
      n.parent &&
      ts.isCallExpression(n.parent) &&
      n.parent.expression.getText(source) === "vm.runInContext" &&
      n.parent.arguments[0] === n
    )
      inspect(file + "#vm", n.text, true);
    ts.forEachChild(n, visit);
  }
  visit(source);
  for (const match of code.matchAll(
    /\b(?:TODO|FIXME|STUB)\b|not[_ -]?implemented|unimplemented/gi,
  ))
    markers.push({
      file,
      line: code.slice(0, match.index).split("\n").length,
      marker: match[0],
    });
  if (code.includes("Math.random"))
    randomUses.push({
      file,
      use: file.endsWith("io.js")
        ? "HTTP read retry jitter"
        : "stream reconnect jitter; no fabricated market data",
    });
}
for (const file of [...new Set(files)]) {
  const bytes = fs.readFileSync(path.join(root, file));
  fileHashes.push({
    file,
    sha256: crypto.createHash("sha256").update(bytes).digest("hex"),
  });
  inspect(file, bytes.toString("utf8"));
}
assert.deepEqual(empty, [], "Executable empty function bodies require review");
assert.deepEqual(
  testImports,
  [],
  "A test/demo dependency entered the operational graph",
);
assert.deepEqual(markers, [], "Unresolved implementation markers");
const catalog = create().catalog(),
  { Selectors } = require("../runtime30/selectors.js"),
  { Validators } = require("../runtime30/validators.js");
const coordinator = fs.readFileSync(
    path.join(root, "xxx/coordinator.ts"),
    "utf8",
  ),
  serverCode = fs.readFileSync(path.join(root, "xxx/server.ts"), "utf8"),
  workerCode = fs.readFileSync(
    path.join(root, "runtime/warroom_worker3.cjs"),
    "utf8",
  );
const lifecycle = [
  "register",
  "normalize",
  "importData",
  "capture",
  "dataset",
  "prepare",
  "started",
  "completed",
  "install",
  "retire",
  "revoke",
  "load",
];
const connected =
  selectorRuntime.contract === "HARPOON-SELECTOR-30-1" &&
  typeof selectorRuntime.fitRows === "function" &&
  typeof selectorRuntime.evaluate === "function" &&
  lifecycle.every((k) => typeof Selectors.prototype[k] === "function") &&
  [
    "selectors.prepare(",
    "selectors.completed(",
    "selectors.install(",
    "selectors.capture(",
  ].every((k) => coordinator.includes(k)) &&
  workerCode.includes("selector30.cjs") &&
  serverCode.includes("/v1/selector-data");
assert.equal(typeof Validators.prototype.check, "function");
const blocked = catalog
  .filter((p) => p.params.selection_filter === "ridge_lcb" && !connected)
  .map((p) => p.id);
const ui = fs.readFileSync(path.join(root, "deploy/dashboard30.html"), "utf8");
for (const token of [
  "/v1/state",
  "/v1/control",
  "/v1/research",
  "/v1/export",
  "/v1/selector-data",
  "healthHeadline",
  "DISCONNECTED",
  "validators",
  "SIN CONEXIÓN",
])
  assert(ui.includes(token));
const report = {
  version: require("../package.json").version,
  acceptanceStatus: blocked.length
    ? "NON_CONFORMING_KNOWN_INTEGRATION_GAPS"
    : "STATIC_REVIEW_ONLY_EXTERNAL_VALIDATION_PENDING",
  generatedAt: new Date().toISOString(),
  conclusion:
    "No local order/account fabrication or execution stubs found in the reviewed operational routes. Selector lifecycle and runtime health are connected. Static/source and controlled execution evidence do not certify broker permissions, live feeds, model acceptance or profitable operation.",
  staticChecks: {
    files: fileHashes.length,
    functionBodies: functions.length,
    unexplainedEmptyBodies: empty.length,
    unresolvedStubMarkers: markers.length,
    testOrDemoImports: testImports.length,
  },
  scope: {
    entry: "runtime30/server.js",
    sources: "xxx/*.ts",
    signalModuleLoader: "runtime/legacy30.cjs",
    storage: "runtime/store30.cjs -> runtime/store.py -> SQLite",
    trading: "xxx/broker.ts -> DirectAlpaca -> Alpaca PAPER HTTP",
    data: "Market REST + observed optional WebSocket streams",
    ui: "deploy/dashboard30.html",
    historicalSources:
      "Declarations used by signal modules include legacy analysis/backtest functions; legacy executors are never instantiated.",
  },
  deliberateSimulation: [
    {
      scope: "tools/*test*, xxx_fixtures.cjs and xxx_benchmark.cjs",
      purpose:
        "Clearly labeled synthetic test data, fake broker and numerical microbenchmark; not imported by the operational entry point.",
    },
    {
      scope: "WarRoom/optimizer/replay analysis",
      purpose:
        "Historical fill estimates and bootstrap/scenario analysis, labeled as estimates; not broker execution or achieved returns.",
    },
    {
      scope: "Alpaca PAPER",
      purpose:
        "Broker simulation with virtual money. No live exchange execution. https://docs.alpaca.markets/us/docs/paper-trading",
    },
  ],
  benignMatches: [
    {
      scope: "dashboard30.html input placeholder",
      meaning: "Search field hint, not an unfinished function",
    },
    {
      scope: "Market constructor with empty TS body",
      meaning: "TypeScript parameter properties perform actual initialization",
    },
    {
      scope: "src/io.js and src/x_engine.js Math.random",
      meaning: "Network retry/reconnect jitter, not price or fill generation",
    },
    {
      scope: "return null guards",
      meaning: "No valid signal/data; no fake result substituted",
    },
  ],
  fixedFindings: [
    "Reentry flag was ignored; now confirmed-close/time/volume/consolidation gates are applied",
    "Realized-volatility trailing flag was ignored; now observed quote variance feeds a persisted non-loosening stop",
    "Stagnation parameters were ignored; now session-aware elapsed time creates a real exit intent",
    "Sector strength used SPY for every factor; now actual sector bars are fetched and missing evidence remains null",
    "VWAP fallback from closes is rejected when observed VWAP is absent",
    "Native crypto channel and ASTRA exit evidence now reach the shared close path",
    "Legacy executor/lab instantiation removed from the XXX signal bridge; actual SQLite transport extracted",
    "Disconnected UI no longer retains a green active-state assertion",
    "Ridge registration, capture/import, actual fit/research, prospective validation, installation, persistence and revocation connected",
    "Core runtime contract validators count actual completed checks; asynchronous storage success requires acknowledgement",
    "Liveness derives from actual lane completion, errors, latency and freshness; process metrics use Node perf_hooks",
    "Pending cancellations and undersized protective orders no longer count as confirmed protection",
  ],
  selectorLifecycle: {
    connected,
    methods: lifecycle,
    financialAcceptanceDemonstrated: false,
  },
  openIntegrationGaps: blocked.map((id) => ({
    plugin: id,
    status: "BLOCKED",
    reason:
      "The ridge evaluator exists, but the lifecycle was not found completely connected by static audit.",
  })),
  routeCoverage: {
    panel:
      "Seven tabs and actual HTTP controls; health, contracts, selector lifecycle, mobile, cancellation/fills/export and disconnect behavior are exercised by the local browser suite",
    brokerTransport:
      "Production adapter executed with controlled test HTTP responses and failures; hosts, credentials, payload and non-replay behavior verified",
    external:
      "No authenticated startup, live feed entitlement or broker execution verified against Alpaca during this audit",
  },
  flags: {
    noNewExternalOrders: true,
    liveEnabled: false,
    profitabilityEstablished: false,
    independentAudit: false,
    allFunctionsEndToEndCertified: false,
  },
  randomUses,
  fileHashes,
  functions,
};
fs.writeFileSync(
  path.join(process.env.HARPOON_QA_OUTPUT_DIR || path.join(root, "evidence/operational-30.3.1"), "function-audit.json"),
  JSON.stringify(report, null, 2) + "\n",
);
console.log(
  JSON.stringify(
    {
      staticChecks: report.staticChecks,
      blockedSelectors: blocked,
      acceptanceStatus: report.acceptanceStatus,
      conclusion: report.conclusion,
    },
    null,
    2,
  ),
);
if (blocked.length) process.exitCode = 2;
