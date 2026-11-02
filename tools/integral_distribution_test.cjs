"use strict";
// Synthetic local distribution regression. This is NOT a Docker image build.
// Stage the final COPY layout and execute the real offline verifier in it.
const test = require("node:test"), assert = require("node:assert/strict");
const fs = require("node:fs"), os = require("node:os"), path = require("node:path");
const { spawn, spawnSync } = require("node:child_process"), crypto = require("node:crypto");
const ROOT = path.resolve(__dirname, ".."), temporary = fs.mkdtempSync(path.join(os.tmpdir(), "hx-integral-"));
const stage = path.join(temporary, "app"), outputs = path.join(temporary, "outputs");
const python = process.env.HARPOON_QUANT_PYTHON || process.env.PYTHON || "python3";
const evidence = { scope: "SYNTHETIC_OFFLINE_FINAL_COPY_LAYOUT", docker_image_built: false,
  host_dependencies_used: true, external_orders: 0, new_financial_trials: 0, checks: [] };
fs.mkdirSync(stage); fs.mkdirSync(outputs);

function stageFinalCopies() {
  const text = fs.readFileSync(path.join(ROOT, "deploy/Dockerfile.xxx"), "utf8");
  const final = text.split(/^FROM /m).at(-1);
  for (const line of final.split("\n").filter(x => x.startsWith("COPY "))) {
    const parts = line.slice(5).trim().split(/\s+/);
    const built = parts[0].startsWith("--from=");
    if (built) assert.equal(parts.shift(), "--from=build");
    const destination = parts.pop();
    for (const original of parts) {
      const relative = built ? original.replace(/^\/app\//, "") : original;
      assert(!relative.startsWith("/") && !relative.includes(".."), "Bounded COPY source");
      const source = path.join(ROOT, relative);
      const target = path.join(stage, destination, parts.length > 1 || destination.endsWith("/") ? path.basename(relative) : "");
      fs.mkdirSync(path.dirname(target), { recursive: true });
      if (relative === "node_modules") fs.symlinkSync(fs.realpathSync(source), target, "dir");
      else fs.cpSync(source, target, { recursive: true });
    }
  }
}
function run(command, args, cwd = stage) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { cwd,
      env: { ...process.env, PYTHONDONTWRITEBYTECODE: "1", PYTHONPATH: path.join(stage, "quant") } });
    let stdout = "", stderr = "", overflow = false;
    const timeout = setTimeout(() => child.kill("SIGKILL"), 45000);
    const collect = (kind, data) => {
      if (kind === "stdout") stdout += data.toString(); else stderr += data.toString();
      if (stdout.length + stderr.length > 2000000) { overflow = true; child.kill("SIGKILL"); }
    };
    child.stdout.on("data", x => collect("stdout", x)); child.stderr.on("data", x => collect("stderr", x));
    child.once("error", error => { clearTimeout(timeout); reject(error); });
    child.once("close", (status, signal) => {
      clearTimeout(timeout);
      if (signal || overflow) reject(Error("Verifier terminated: " + (signal || "output limit")));
      else resolve({ status, stdout, stderr });
    });
  });
}
async function gate(name) {
  const output = path.join(outputs, name + ".json");
  const fixture = path.join(ROOT, "quant/examples/economic_gate/coordinator_fixture");
  const r = await run(python, ["-m", "harpoon_quant.economic_gate", "--protocol", path.join(fixture, "protocol.json"),
    "--input", path.join(fixture, "input.json"), "--artifact-root", ROOT, "--output", output]);
  assert(fs.existsSync(output), r.stderr || r.stdout);
  return JSON.parse(fs.readFileSync(output, "utf8"));
}
stageFinalCopies();
test.after(() => {
  if (process.env.HARPOON_QA_OUTPUT_DIR) {
    fs.mkdirSync(process.env.HARPOON_QA_OUTPUT_DIR, { recursive: true });
    fs.writeFileSync(path.join(process.env.HARPOON_QA_OUTPUT_DIR, "distribution_layout.json"), JSON.stringify(evidence, null, 2) + "\n");
  }
  fs.rmSync(temporary, { recursive: true, force: true });
});

test("the final COPY layout includes verifier and bound TypeScript sources", () => {
  for (const name of ["tools/coordinator_replay.cjs", "tools/observation_replay_input.cjs", "tools/funded_comparison.cjs", "tools/fixed_predictor_worker.cjs", "tools/measurement_registration.py", "tools/build_causal_panel.py", "tools/level4_readiness.cjs", "tools/level5_readiness.cjs", "tools/export_observation_snapshot.cjs", "tools/collect_runtime_evidence.cjs", "xxx/coordinator.ts",
    "xxx/version.ts", "runtime30/coordinator.js", "quant/harpoon_quant/economic_gate.py", "deploy/dashboard30.html"])
    assert(fs.statSync(path.join(stage, name)).isFile(), name);
  evidence.checks.push("FINAL_COPY_REQUIRED_FILES");
});
test("Docker context retains required verification tools without test fixtures", () => {
  const rules = fs.readFileSync(path.join(ROOT, ".dockerignore"), "utf8").split(/\r?\n/).map(x => x.trim());
  assert(!rules.includes("tools"), "Parent exclusion would hide the verifier");
  const exclude = rules.indexOf("tools/*"); assert(exclude >= 0);
  const required=["coordinator_replay.cjs", "observation_replay_input.cjs", "funded_comparison.cjs", "fixed_predictor_worker.cjs", "measurement_registration.py", "build_causal_panel.py", "level4_readiness.cjs", "level5_readiness.cjs", "export_observation_snapshot.cjs", "collect_runtime_evidence.cjs"];
  for (const name of required)
    assert(rules.indexOf("!tools/" + name) > exclude);
  assert.deepEqual(fs.readdirSync(path.join(stage, "tools")).sort(), required.sort());
  evidence.checks.push("CONTEXT_EXCEPTIONS_WITHOUT_TEST_FIXTURES");
});
test("the actual coordinator replay verifies from the staged final layout", async () => {
  const output = path.join(outputs, "replay-verification.json");
  const r = await run(process.execPath, ["tools/coordinator_replay.cjs", "--input",
    path.join(ROOT, "quant/examples/coordinator_replay/synthetic_request.json"), "--verify",
    path.join(ROOT, "quant/examples/coordinator_replay/synthetic_report.json"), "--output", output]);
  assert.equal(r.status, 0, r.stderr || r.stdout);
  const report = JSON.parse(fs.readFileSync(output, "utf8"));
  assert.equal(report.verified, true); assert.deepEqual(report.mismatches, []);
  evidence.replay = report; evidence.checks.push("REAL_OFFLINE_REPLAY_FROM_FINAL_LAYOUT");
});
test("Python gate can reexecute the coordinator from the final layout without granting financial acceptance", async () => {
  const report = await gate("complete-layout");
  assert.equal(report.parity?.real_coordinator_reexecuted, true, JSON.stringify(report.software_validators));
  assert.equal(report.parity.complete_paired_policy_coverage, false);
  assert.equal(report.dictamen, "VENTAJA_NO_DEMOSTRADA");
  assert.equal(report.execution_allowed, false); assert.equal(report.liveApproved, false);
  evidence.gate = { parity: report.parity, dictamen: report.dictamen, financial_blockers: report.financial_blockers };
  evidence.checks.push("GATE_REEXECUTES_AND_REMAINS_BLOCKED_FINANCIALLY");
});
test("fixed C0 Ridge and SVR comparison can be reproduced from the final layout", async () => {
  const output=path.join(outputs,"funded-verification.json");
  const fixture=path.join(ROOT,"quant/examples/funded_comparison");
  const r=await run(process.execPath,["tools/funded_comparison.cjs","--input",path.join(fixture,"synthetic_request.json"),
    "--verify",path.join(fixture,"synthetic_report.json"),"--output",output]);
  assert.equal(r.status,0,r.stderr||r.stdout);
  const report=JSON.parse(fs.readFileSync(output,"utf8"));
  assert.equal(report.verified,true);assert.equal(report.execution_allowed,false);
  assert.equal(report.financial_acceptance_allowed,false);
  evidence.funded=report;evidence.checks.push("THREE_FIXED_POLICIES_REPRODUCED_FROM_FINAL_LAYOUT");
});
test("omitting the verifier reproduces the prior distribution defect and fails closed", async () => {
  const source = path.join(stage, "tools/coordinator_replay.cjs"), hidden = source + ".hidden";
  fs.renameSync(source, hidden);
  try {
    const report = await gate("missing-verifier");
    assert.match(JSON.stringify(report.financial_blockers), /COORDINATOR_VERIFIER_MISSING/);
    assert.equal(report.parity, null);
    assert.equal(report.execution_allowed, false); assert.equal(report.financial_approval, false);
    evidence.missing_verifier = report.financial_blockers;
  } finally { fs.renameSync(hidden, source); }
  evidence.checks.push("MISSING_VERIFIER_FAILS_CLOSED");
});
test("the level5 adapter in the final layout preserves unknown evidence and never authorizes orders",async()=>{
  const input=path.join(outputs,"missing-level5-input.json"),output=path.join(outputs,"missing-level5-output.json");
  fs.writeFileSync(input,JSON.stringify({schema:"HARPOON_LEVEL5_DERIVATION_REQUEST_1",level4:{request:null},stress:[]}));
  const r=await run(process.execPath,["tools/level5_readiness.cjs","--input",input,"--output",output]);
  assert.equal(r.status,0,r.stderr||r.stdout);
  const result=JSON.parse(fs.readFileSync(output,"utf8"));
  assert.equal(result.schema,"HARPOON_LEVEL5_DERIVED_EVIDENCE_1");
  assert.equal(result.policies,null);assert.equal(result.complete_derived_comparison,false);
  assert(result.financial_blockers.length>0);assert.equal(result.execution_allowed,false);
  assert.equal(result.financial_acceptance_allowed,false);assert.equal(result.liveApproved,false);
  evidence.level5={scope:"MISSING_EVIDENCE_PATH_FROM_STAGED_LAYOUT",blockers:result.financial_blockers};
  evidence.checks.push("LEVEL5_MISSING_EVIDENCE_REMAINS_BLOCKED_FROM_FINAL_LAYOUT");
});
test("omitting the TypeScript source cannot silently bypass source integrity", () => {
  const source = path.join(stage, "xxx"), hidden = source + "_hidden";
  fs.renameSync(source, hidden);
  try {
    const verifier = require(path.join(stage, "tools/coordinator_replay.cjs"));
    assert.throws(() => verifier.sourceHashes(), error => error.code === "ENOENT" && error.path === source);
  } finally { fs.renameSync(hidden, source); }
  evidence.checks.push("MISSING_BOUND_SOURCE_REJECTED");
});
test("the delivered HTML alias and package versions agree with the active application", () => {
  const digest = file => crypto.createHash("sha256").update(fs.readFileSync(path.join(ROOT, file))).digest("hex");
  assert.equal(digest("HARPOON_XXXUltimate.html"), digest("deploy/dashboard30.html"), "Served UI and delivered HTML must be byte-identical");
  const version = require("../runtime30/version.js").ULTIMATE_VERSION;
  assert.equal(require("../package.json").version, version);
  assert.equal(require("../package-lock.json").version, version);
  evidence.application = version; evidence.checks.push("ACTIVE_UI_AND_VERSIONS_AGREE");
});

test("evidence collector loads from the final COPY layout without contacting a service", () => {
  const environment = { ...process.env };
  delete environment.NODE_TEST_CONTEXT;
  delete environment.HARPOON_PANEL_PASSWORD;
  const sourceBytes = fs.readFileSync(path.join(ROOT, "tools/collect_runtime_evidence.cjs"));
  const stagedBytes = fs.readFileSync(path.join(stage, "tools/collect_runtime_evidence.cjs"));
  assert.deepEqual(stagedBytes, sourceBytes, "Distributed collector is byte-identical to its source");
  const result = spawnSync(process.execPath, [path.join(stage, "tools/collect_runtime_evidence.cjs"), "--help"],
    {cwd: stage, env: environment, encoding: "utf8", timeout: 5000});
  assert.ifError(result.error);
  assert.equal(result.signal, null);
  assert.equal(result.status, 0, result.stderr || result.stdout);
  assert.match(result.stdout, /fixed GET routes/);
  assert.match(result.stdout, /never financial approval or a score/);
  assert.equal(result.stderr, "");
  evidence.checks.push("COLLECTOR_LOADS_FROM_FINAL_COPY_LAYOUT");
});
