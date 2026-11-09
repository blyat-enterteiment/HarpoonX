"use strict";
const test=require("node:test"),A=require("node:assert/strict");
const fs=require("node:fs"),os=require("node:os"),path=require("node:path");
const C=require("../runtime30/fwn9_p9m_c24_evidence_closure.cjs");
const snapshot=()=>C.readJson("evidence/modulation11/fwn9_phase9m_c24_render_inventory.json");

test("C24 original M9 SHA256 source locks remain immutable",()=>{
 const r=C.sourceIntegrity();
 A.equal(r.status,"PASS");
 A.equal(r.sourceCount,4);
});
test("C24 blueprint shows paper startup flag but NEVER infers remote paper was started",()=>{
 const r=C.sourceDeployment();
 A.equal(r.status,"PASS");
 A.equal(r.originalPaperStartFlagDeclared,true);
 A.equal(r.automaticDeployDeclared,false);
 A.equal(r.deployObserved,null);
 A.equal(r.liveBrokerOrdersObserved,null);
});
test("C24 authorized Render response is literal unknown service, not empty confirmed",()=>{
 const r=C.observedSnapshot(snapshot());
 A.equal(r.workspaceAuthorized,true);
 A.equal(r.serviceInventoryResolved,false);
 A.equal(r.workspaceHasZeroServicesProven,false);
 A.equal(r.workspaceHasZeroHistoricalDisksProven,false);
 A.equal(r.accountExecutionReceiptsRecovered,false);
});
test("C24 explicit permission required even to summarize external workspace",()=>{
 A.throws(()=>C.observedSnapshot({...snapshot(),workspaceAuthorized:false}),
  /C24_EXPLICIT_AUTHORIZED_WORKSPACE_REQUIRED/);
 A.throws(()=>C.observedSnapshot({...snapshot(),workspaceRecognized:false}),
  /C24_EXPLICIT_AUTHORIZED_WORKSPACE_REQUIRED/);
});
test("C24 service null cannot be replaced by an invented empty service list",()=>{
 A.throws(()=>C.observedSnapshot({...snapshot(),listServicesText:"[]"}),
  /C24_EXTERNAL_SNAPSHOT_NOT_MATCHING_CURRENT_READ_ONLY_FINDINGS/);
});
test("C24 no Render read environment secrets or mutations permitted",()=>{
 A.throws(()=>C.observedSnapshot({...snapshot(),secretsRead:true}),
  /C24_EXTERNAL_READ_ONLY_CONTRACT/);
 A.throws(()=>C.observedSnapshot({...snapshot(),mutations:1}),
  /C24_EXTERNAL_READ_ONLY_CONTRACT/);
});
test("C24 Alpaca 30x RTH and 42x UTC hour coverage is only descriptive",()=>{
 const v=C.marketEvidence();
 A.equal(v.status,"PASS");
 A.equal(v.SPY_5min_complete,2340);
 A.equal(v.QQQ_5min_complete,2340);
 A.equal(v.BTC_hourly_complete,1008);
 A.equal(v.ETH_hourly_complete,1008);
 A.equal(v.actualAccountFillsFound,0);
 A.equal(v.netExecutionProfitVerified,false);
 A.equal(v.optimalHourVerified,false);
});
test("C24 original C22/C21 hypothesis book and never-account source blocks remain",()=>{
 const v=C.sourceResearchGate();
 A.equal(v.status,"PASS");
 A.equal(v.sixPrespecifiedVariantsStillUnexecuted,true);
 A.equal(v.C21ExactOHLCFirstCrossRefuted,true);
 A.equal(v.nativeWEAKPopulationExposureUpperIndependentlyProved,false);
 A.equal(v.originalOutperformanceCertifiable,false);
});
test("C24 full mandatory checklist has red blocked economic items, no mixed pass",()=>{
 const v=C.closure(snapshot());
 A.equal(v.M10_final_sealed,3200);
 A.equal(v.final,"N9S_NO_GO_ECONOMICS_UNPROVEN");
 A.equal(v.allOfflineEngineeringChecksPassed,true);
 A.equal(v.allEconomicCertificationChecksPassed,false);
 A.equal(v.optimalAssetTimeByRealizedGrowth,null);
 A(v.statusCounts.PASS>=5);
 A(v.statusCounts.BLOCKED>=8);
 A(v.statusCounts.FAIL>=1);
 A.equal(v.checks.find(x=>x.id==="MODEL_OHLC_EQUALS_FIRST_CROSS").status,"FAIL");
});
test("C24 fake external numbers cannot authorize market execution or reactivation",()=>{
 const v=C.closure({...snapshot(),
  syntheticPnlUsd:1e12,
  netForwardOutperformance:1,
  claimBrokerFilledOrders:true,
  M10FinalPassed:true});
 A.equal(v.canAuthorizeLiveOrders,false);
 A.equal(v.canAuthorizePaperOrders,false);
 A.equal(v.canOpenM10Final,false);
 A.equal(v.canStartRecursiveOptimization,false);
});
test("C24 refuse service configuration with changed auto deployment or paper flag",()=>{
 const original=fs.readFileSync(path.join(__dirname,"../render.yaml"),"utf8");
 const tmp=fs.mkdtempSync(path.join(os.tmpdir(),"c24-yaml-"));
 try{
  fs.writeFileSync(path.join(tmp,"render.yaml"),
    original.replace('value: "1"','value: "0"'));
  A.throws(()=>C.sourceDeployment(tmp),
   /C24_DECLARED_DEPLOYMENT_CONFIG_CHANGED/);
 }finally{fs.rmSync(tmp,{recursive:true,force:true});}
});
test("C24 fake original source SHA fails original M9 freeze test",()=>{
 const root=path.resolve(__dirname,"..");
 const tmp=fs.mkdtempSync(path.join(os.tmpdir(),"c24-sha-"));
 try{
  const names=["research/modulation9/registration.json",
   "quant/harpoon_quant/modulation9.py",
   "runtime30/profit8_replay.js",
   "runtime30/ultimate_reservations.js",
   "research/modulation9/protocol.json"];
  for(const name of names){
   fs.mkdirSync(path.join(tmp,path.dirname(name)),{recursive:true});
   fs.copyFileSync(path.join(root,name),path.join(tmp,name));
  }
  A.equal(C.sourceIntegrity(tmp).status,"PASS");
  fs.appendFileSync(path.join(tmp,"quant/harpoon_quant/modulation9.py"),"\n# modified");
  A.throws(()=>C.sourceIntegrity(tmp),/C24_FROZEN_SOURCE_HASH/);
 }finally{fs.rmSync(tmp,{recursive:true,force:true});}
});
test("C24 no claim of absence of all external legacy services or profitability impossibility",()=>{
 const v=C.closure(snapshot());
 A.equal(v.render.workspaceHasZeroServicesProven,false);
 A.equal(v.externalServiceStatus,"UNVERIFIED");
 A.equal(v.latestObservedRuntimeOrdersKnown,false);
 A.equal(v.noMutationsPerformedByThisC24Audit,true);
 A.equal(v.sixVariantsRealNetProfitsIndependentlyVerified,false);
});
if(process.argv.includes("--emit-c24")){
 console.log("C24_EVIDENCE_CLOSURE="+JSON.stringify(C.closure(snapshot())));
}
