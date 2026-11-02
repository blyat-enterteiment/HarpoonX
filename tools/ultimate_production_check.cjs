"use strict";
// Isolated production dependency import. No broker credentials or HTTP calls.
const fs = require("node:fs"), path = require("node:path"), os = require("node:os"), { execFileSync } = require("node:child_process");
const root = path.resolve(__dirname, ".."), directory = fs.mkdtempSync(path.join(os.tmpdir(), "harpoon-ultimate-prod-"));
try {
  for (const name of ["package.json", "package-lock.json"]) fs.copyFileSync(path.join(root, name), path.join(directory, name));
  execFileSync("npm", ["ci", "--omit=dev", "--ignore-scripts", "--offline", "--no-audit", "--no-fund"], { cwd: directory, stdio: "pipe" });
  for (const name of ["runtime30", "runtime", "src", "deploy", "config"]) fs.cpSync(path.join(root, name), path.join(directory, name), { recursive: true });
  for (const dir of ["evidence/ultimate", "evidence/tp32"]) fs.mkdirSync(path.join(directory, dir), { recursive: true });
  for (const name of ["evidence/ultimate/report.json", "evidence/ultimate/registry.json", "evidence/tp32/report.json"]) fs.copyFileSync(path.join(root, name), path.join(directory, name));
  const code = `
    require('./runtime30/server.js');
    const fs = require('node:fs'), assert = require('node:assert/strict'), crypto = require('node:crypto');
    const { ResearchLab } = require('./runtime30/ultimate_lab.js');
    const { Validators } = require('./runtime30/validators.js');
    const { DEFAULT_REPLAY_LIMITS } = require('./runtime30/ultimate_replay.js');
    const lab = new ResearchLab(null, 'IMPORT_CHECK_NO_ACCOUNT', new Validators(), DEFAULT_REPLAY_LIMITS);
    // The retained report belongs to the old replay. Its bytes remain intact,
    // and the current implementation must reject its old code seal.
    const reportBytes=fs.readFileSync('./evidence/ultimate/report.json');
    const registryBytes=fs.readFileSync('./evidence/ultimate/registry.json');
    assert.equal(crypto.createHash('sha256').update(reportBytes).digest('hex'), '7b6fe566ac8a8ed27c5bb78be3d8e087b18a59f1b53de591324885760acaca11');
    assert.equal(crypto.createHash('sha256').update(registryBytes).digest('hex'), 'bf7e199a75451ad7b892e4bc26ddab43d6338e1f2572a4075cfcdcc5ea81fe2c');
    assert.throws(()=>lab.verifyBundled(JSON.parse(reportBytes),JSON.parse(registryBytes)), error=>String(error.message).includes('bundled report code/data/protocol binding'));
    let typescriptPresent = false;
    try { require.resolve('typescript'); typescriptPresent = true; } catch (e) { if (e.code !== 'MODULE_NOT_FOUND') throw e; }
    if (typescriptPresent) throw Error('Development dependency leaked');
    const catalogSize = require('./runtime/legacy30.cjs').create().catalog().length;
    console.log(JSON.stringify({status:'PASS', source:'ISOLATED_NPM_CI_OFFLINE_OMIT_DEV', node:process.version, typescriptPresent, inheritedCatalogSize:catalogSize, bundledReportSeal:'OLD_CODE_REJECTED_AS_REQUIRED', historicalBytesPreserved:true, externalOrders:0}));
  `;
  const result = JSON.parse(execFileSync(process.execPath, ["-e", code], { cwd: directory, encoding: "utf8" }));
  fs.writeFileSync(path.join(process.env.HARPOON_QA_OUTPUT_DIR || path.join(root, "evidence/operational-30.3.1"), "production-import.json"), JSON.stringify(result, null, 2) + "\n");
  console.log(JSON.stringify(result));
} finally { fs.rmSync(directory, { recursive: true, force: true }); }
