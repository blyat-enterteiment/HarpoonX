"use strict";
// Reproduce the registered historical study and expose existing funded states.
// No registry writes, strategy changes, new trials, fitting, network or orders.
const fs = require("node:fs"), path = require("node:path"), crypto = require("node:crypto"), Module = require("node:module");
const assert = require("node:assert/strict");
const app = path.resolve(process.argv[2] || "core5_work/HARPOON_XXXUltimate_30_13_0");
const out = path.resolve(__dirname);
const sha = b => crypto.createHash("sha256").update(b).digest("hex");
const read = rel => JSON.parse(fs.readFileSync(path.join(app,rel),"utf8"));
const original = read("evidence/ultimate/report.json");
const registered = read("evidence/ultimate/protocol.json");
const p = registered.protocol;
const {digest} = require(path.join(app,"runtime30/ultimate_contracts.js"));
const sourcePath = path.join(app,"runtime30/ultimate_replay.js");
const originalSource = fs.readFileSync(sourcePath,"utf8");
const retainedFiles = ["evidence/ultimate/report.json","evidence/ultimate/protocol.json","evidence/ultimate/registry.json","evidence/tp32/prepared.json","runtime30/ultimate_replay.js"];
const before = Object.fromEntries(retainedFiles.map(f=>[f,sha(fs.readFileSync(path.join(app,f)))]));
const rawBytes = fs.readFileSync(path.join(app,"evidence/tp32/prepared.json"));
const raw = JSON.parse(rawBytes);
const sourceFiles = raw.fingerprints.map(f=>({name:f.path,sha256:f.sha256}));
const sourceChecks = {verified:[],unavailable:[]};
for(const f of sourceFiles){
  const filename=path.resolve(app,f.name);
  assert(filename.startsWith(app+path.sep),"source path must remain inside integral");
  if(!fs.existsSync(filename)){sourceChecks.unavailable.push(f);continue;}
  assert.equal(sha(fs.readFileSync(filename)),f.sha256,"Historical checksum: "+f.name);
  sourceChecks.verified.push(f);
}
assert.equal(sha(rawBytes), original.source.files.find(f=>f.name==="evidence/tp32/prepared.json").sha256,"retained prepared bytes binding");
const data={
  schema:"HARPOON-ULTIMATE-DATA-1",kind:"ALPACA_PROXY",
  provenance:{source:"RETAINED_OBSERVED_ALPACA_BARS_REUSED_HISTORY",feed:"SIP",execution:"MODELED_OHLCV",files:[...sourceFiles,{name:"evidence/tp32/prepared.json",sha256:sha(rawBytes)}]},
  sessions:raw.calendar,
  splitEvents:raw.splits.filter(s=>p.universe.includes(s.symbol)).map(s=>({symbol:s.symbol,at:raw.calendar.find(d=>d.date===s.ex_date)?.open??Date.parse(s.ex_date+"T13:30:00Z"),ratio:Number(s.new_rate)/Number(s.old_rate)})),
  series:p.universe.map(symbol=>({symbol,root:symbol,pointValue:1,tick:.01,bars:raw.series[symbol].map(b=>({t:b[0],end:b[0]+300000,availableAt:b[0]+303000,o:b[1],h:b[2],l:b[3],c:b[4],v:b[5],...(b[6]?{vw:b[6]}:{})}))}))
};
assert.equal(digest(p),original.protocolHash,"protocol binding");
assert.equal(digest(data),original.datasetHash,"dataset binding");
assert.equal(registered.registeredAt,original.registeredAt,"registration binding");

const substitutions=[
  {before:"const funded = [], portfolioSkips = {};",after:"const funded = [], portfolioSkips = {}, __diagnosticFundedSizing = [];"},
  {before:"        if (quantity < 1) {",after:"        __diagnosticFundedSizing.push({ opportunity: {...opportunity}, equity, px, riskUnit, openRisk, notional, quantity, selected: fold.selected, activeCampaignIds: active.map(t=>t.id), day: {...day} });\n        if (quantity < 1) {"},
  {before:'    return {\n        schema: "HARPOON-ULTIMATE-REPORT-1",',after:'    exports.__diagnosticCapture = {funded, sizing: __diagnosticFundedSizing, oos, fundedPnl, fundedReturns, limits, portfolioSkips, folds: folds.map(f=>({train:f.train,test:f.test,selected:f.selected}))};\n    return {\n        schema: "HARPOON-ULTIMATE-REPORT-1",'},
];
let instrumented=originalSource;
for(const s of substitutions){
  assert.equal(instrumented.split(s.before).length-1,1,"observer anchor must be unique");
  instrumented=instrumented.replace(s.before,s.after);
}
const observedModule = new Module(sourcePath,module);
observedModule.filename=sourcePath;
observedModule.paths=Module._nodeModulePaths(path.dirname(sourcePath));
observedModule._compile(instrumented,sourcePath);
const start=performance.now();
const reproduction=observedModule.exports.runStudy(p,data,registered.registeredAt,original.fundedPortfolio.limits);
const elapsedMs=performance.now()-start;
const withoutGeneratedAt=x=>{const y=structuredClone(x);delete y.generatedAt;return y;};
const mismatches=[];
function compare(a,b,pointer=""){
  if(JSON.stringify(a)===JSON.stringify(b))return;
  if(a && b && typeof a==="object" && typeof b==="object"){
    for(const key of new Set([...Object.keys(a),...Object.keys(b)]))compare(a[key],b[key],pointer+"/"+key);
  }else mismatches.push({pointer,retained:a??null,reproduced:b??null});
}
compare(withoutGeneratedAt(original),withoutGeneratedAt(reproduction));
const after=Object.fromEntries(retainedFiles.map(f=>[f,sha(fs.readFileSync(path.join(app,f)))]));
assert.deepEqual(before,after,"integral input files changed");
const verification={schema:"HARPOON_FROZEN_FUNDED_REPRODUCTION_1",scope:"EXACT_REPRODUCTION_OBSERVATIONAL_CAPTURE_ONLY",newFinancialTrials:0,trainingExecuted:false,registryWrites:0,externalOrders:0,financialAcceptanceAllowed:false,
  protocolHash:digest(p),datasetHash:digest(data),sourceFileCount:sourceFiles.length,
  sourceChecks,preparedBytesMatchRetainedReport:true,originalRawProvenanceFullyReverified:sourceChecks.unavailable.length===0,
  inputHashes:before,inputsUnchanged:true,sourceInstrumentedOnlyInMemory:true,
  sourceSha256:sha(originalSource),instrumentedSourceSha256:sha(instrumented),substitutions,
  comparedReportIgnoringOnly:["generatedAt"],identical:mismatches.length===0,mismatches,
  elapsedMs,node:process.version,portfolio:reproduction.fundedPortfolio};
fs.mkdirSync(out,{recursive:true});
fs.writeFileSync(path.join(out,"reproduction_verification.json"),JSON.stringify(verification,null,2)+"\n");
fs.writeFileSync(path.join(out,"reproduced_report.json"),JSON.stringify(reproduction,null,2)+"\n");
if(mismatches.length)throw Error("Frozen report not reproduced exactly; see reproduction_verification.json");
const capture=observedModule.exports.__diagnosticCapture;
assert.equal(capture.funded.length,original.fundedPortfolio.oos.campaigns);
assert(Math.abs(capture.funded.reduce((n,t)=>n+t.netUsd,0)-original.fundedPortfolio.netUsd)<1e-9);
fs.writeFileSync(path.join(out,"reproduction_capture.json"),JSON.stringify({scope:verification.scope,protocolHash:digest(p),datasetHash:digest(data),verifiedAgainstFrozenReport:true,...capture},null,2)+"\n");
console.log(JSON.stringify({identical:true,campaigns:capture.funded.length,sizingStates:capture.sizing.length,netUsd:reproduction.fundedPortfolio.netUsd,elapsedMs}));
