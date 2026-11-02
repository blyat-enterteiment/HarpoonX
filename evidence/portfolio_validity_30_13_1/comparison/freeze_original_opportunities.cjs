"use strict";
// Reproduce only the original experiment. Diagnostic capture; no new variant.
const fs=require("node:fs"),path=require("node:path"),assert=require("node:assert/strict"),Module=require("node:module");
const {loadBaseline,sha,fileHash}=require("./frozen_inputs.cjs");
const {app,report,registered,protocol,data}=loadBaseline(process.argv[2]);
const destination=path.join(__dirname,"frozen_study.json");
assert(!fs.existsSync(destination),"Frozen inputs already exist; do not overwrite registered evidence");
const sourcePath=path.join(app,"runtime30/ultimate_replay.js"),source=fs.readFileSync(sourcePath,"utf8");
const anchor='    return {\n        schema: "HARPOON-ULTIMATE-REPORT-1",';
assert.equal(source.split(anchor).length-1,1,"Nonunique observer anchor");
const injection='    exports.__frozenComparisonInputs = {common, oos, folds: folds.map(f=>({train:f.train,test:f.test,selected:f.selected})), limits};\n';
const patched=source.replace(anchor,injection+anchor),loaded=new Module(sourcePath,module);
loaded.filename=sourcePath;loaded.paths=Module._nodeModulePaths(path.dirname(sourcePath));loaded._compile(patched,sourcePath);
const reproduced=loaded.exports.runStudy(protocol,data,registered.registeredAt,report.fundedPortfolio.limits);
function stable(value){const copy=structuredClone(value);delete copy.generatedAt;return copy;}
assert.deepEqual(stable(reproduced),stable(report),"Original complete report failed exact reproduction");
const input=loaded.exports.__frozenComparisonInputs;
const frozen={schema:"HARPOON_FIXED_SELECTION_FUNDED_COMPARISON_INPUTS_1",scope:"FROZEN_REUSED_HISTORY_EXPLORATORY_ONLY",financialAcceptanceAllowed:false,
  protocol,datasetHash:report.datasetHash,protocolHash:report.protocolHash,registeredAt:report.registeredAt,
  baselineReportSha256:fileHash(path.join(app,"evidence/ultimate/report.json")),baselineReplaySha256:sha(source),
  preparedSha256:fileHash(path.join(app,"evidence/tp32/prepared.json")),
  sourceCapture:{method:"OBSERVATIONAL_IN_MEMORY_EXPORT_AFTER_IDENTICAL_REPRODUCTION",ignoredFields:["generatedAt"],anchor,injection},
  ...input};
fs.writeFileSync(destination,JSON.stringify(frozen,null,2)+"\n",{flag:"wx"});
const receipt={schema:"HARPOON_FROZEN_COMPARISON_CAPTURE_VERIFICATION_1",identicalReportExceptGeneratedAt:true,newFinancialTrials:0,fits:0,registryWrites:0,
  file:"frozen_study.json",sha256:fileHash(destination),opportunities:input.common.length,folds:input.folds.length,sessions:input.oos.length,
  baseline:report.fundedPortfolio,sourceSha256:sha(source),instrumentedSourceSha256:sha(patched)};
fs.writeFileSync(path.join(__dirname,"freeze_verification.json"),JSON.stringify(receipt,null,2)+"\n",{flag:"wx"});
console.log(JSON.stringify({file:destination,sha256:receipt.sha256,opportunities:input.common.length,folds:input.folds.length,sessions:input.oos.length,identicalReportExceptGeneratedAt:true}));
