"use strict";
const test=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const os=require("node:os");
const path=require("node:path");
const {Plugins}=require("../runtime30/plugins.js");
const W=require("../runtime30/fwn9_c31_native_postfilter_witness.cjs");
const J=require("../runtime30/fwn9_c31_native_call_journal.cjs");
function native(){
 const p=Object.create(Plugins.prototype);
 p.cfg={universe:[]};
 p.catalog=[];p.diagnostics=[];p.legacy={};
 return p;
}
function clock(start=1000){let n=start;return()=>++n;}
function scratch(fn){
 const parent=fs.mkdtempSync(path.join(os.tmpdir(),"harpoon-c31-"));
 try{return fn(path.join(parent,"private-journal"));}
 finally{fs.rmSync(parent,{recursive:true,force:true});}
}
function observed(p,clockFn=clock()){
 const records=[];
 const detach=W.attach(p,{clock:clockFn,sink:r=>records.push(r)});
 assert.deepEqual(p.evaluate("crypto",{},[],500),[]);
 detach();
 assert.equal(records.length,1);
 return records[0];
}
test("C31 read-only observer attaches but never evaluates by itself",()=>{
 const p=native(),records=[];
 const original=p.evaluate;
 const detach=W.attach(p,{sink:r=>records.push(r),clock:clock()});
 assert.equal(records.length,0);
 assert.notEqual(p.evaluate,original);
 detach();
 assert.equal(p.evaluate,original);
 assert.equal(records.length,0);
});
test("actual native Plugins.prototype.evaluate returns untouched result",()=>{
 const p=native(),original=p.evaluate;
 const r=observed(p);
 assert.equal(p.evaluate,original);
 assert.equal(r.resultStatus,"RETURNED");
 assert.equal(r.outputCount,0);
 assert.equal(r.nativeMethodCalledExactlyOnceByWrapper,true);
 assert.equal(r.sourcePhase,"NATIVE_POSTFILTER_METHOD_RETURN");
 assert.equal(r.c22SixFrozenPrefilterEvaluationsProved,false);
 assert.equal(r.financialOrdersAuthorized,false);
 assert.deepEqual(r.emittedNativeIds,[]);
});
test("native selected plugin registration cannot masquerade as C22 source",()=>{
 const p=native();
 p.catalog=[{id:"options-call-breakout",book:"options"},{id:"crypto-shock-recovery",book:"crypto"}];
 const report=W.inspectLineage(p);
 assert.equal(report.frozenC22Policies.length,6);
 assert.equal(report.variantIdsAreNativePluginIds,false);
 assert.equal(report.sixVariantNativePrefilterProved,false);
 assert.ok(report.frozenC22Policies.filter(x=>x.book.includes("options")).every(x=>
  x.matchingNativeCatalogIds.includes("options-call-breakout")&&
  x.exactOneToOneNativePolicyBindingCertified===false));
 const records=[];const detach=W.attach(p,{sink:x=>records.push(x),clock:clock()});
 assert.deepEqual(p.evaluate("crypto",{},["crypto-shock-recovery"],500),[]);
 detach();
 assert.deepEqual(records[0].selectedNativePluginIds,["crypto-shock-recovery"]);
 assert.equal(records[0].c22SixFrozenPrefilterEvaluationsProved,false);
});
test("cannot install on spoofed instance or install twice",()=>{
 assert.throws(()=>W.attach({evaluate(){}},{sink(){} }),/C31W_ORIGINAL_PROTOTYPE/);
 const p=native(),detach=W.attach(p,{clock:clock(),sink(){}});
 assert.throws(()=>W.attach(p,{clock:clock(),sink(){} }),/C31W_ORIGINAL_PROTOTYPE_UNWRAPPED/);
 detach();
});
test("original exception remains thrown after recording failure",()=>{
 const p=native();p.diagnostics=null;
 const rows=[];const detach=W.attach(p,{clock:clock(),sink:r=>rows.push(r)});
 assert.throws(()=>p.evaluate("crypto",{},[],500),TypeError);
 detach();
 assert.equal(rows.length,1);assert.equal(rows[0].resultStatus,"THREW");
 assert.equal(rows[0].errorType,"TypeError");
 assert.equal(rows[0].outputCount,0);
});
test("sink failure stops downstream result (fail-closed)",()=>{
 const p=native(),detach=W.attach(p,{clock:clock(),sink(){throw Error("DISK_UNAVAILABLE");}});
 assert.throws(()=>p.evaluate("crypto",{},[],500),/DISK_UNAVAILABLE/);
 detach();
});
test("future timestamps and invalid books are rejected",()=>{
 const p=native(),detach=W.attach(p,{clock:clock(),sink(){}});
 assert.throws(()=>p.evaluate("crypto",{},[],999999),/C31W_FUTURE_ASOF/);
 assert.throws(()=>p.evaluate("fictional",{},[],500),/C31W_ORIGINAL_CALL_ARGUMENTS/);
 detach();
});
test("local SHA fingerprint identifies actual source but never attests it",()=>{
 const p=native(),r=W.inspectLineage(p);
 assert.match(r.sourceFingerprint.runtimeFileSha256,/^[a-f0-9]{64}$/);
 assert.equal(r.sourceFingerprint.sourceAuthenticityExternallyAttested,false);
});
test("append-only journal retains native invocation over restart",()=>{
 scratch(dir=>{
  const fp=W.sourceFingerprint().runtimeFileSha256;
  J.create(dir,{runId:"C31-UNIT",sourceFileSha256:fp});
  const p=native();
  let number=1000;
  const detach=W.attach(p,{clock:()=>++number,sink:r=>J.append(dir,r)});
  assert.deepEqual(p.evaluate("crypto",{},[],500),[]);
  assert.deepEqual(p.evaluate("crypto",{},[],500),[]);
  detach();
  const restored=J.verify(dir);
  assert.equal(restored.entries,2);
  assert.match(restored.head,/^[a-f0-9]{64}$/);
  assert.equal(restored.sixC22NativePrefilterCallsProven,false);
  assert.equal(restored.independentlyTimeAndBrokerAuthenticated,false);
 });
});
test("changed native record bytes are detected even if well-formed JSON",()=>{
 scratch(dir=>{
  J.create(dir,{runId:"C31-UNIT",sourceFileSha256:W.sourceFingerprint().runtimeFileSha256});
  J.append(dir,observed(native()));
  const file=fs.readdirSync(dir).find(x=>x!=="manifest.json");
  const pathName=path.join(dir,file);
  const item=JSON.parse(fs.readFileSync(pathName,"utf8"));
  item.record.outputCount=99;
  fs.writeFileSync(pathName,JSON.stringify(item)+"\n");
  assert.throws(()=>J.verify(dir),/C31J_CHAIN_SOURCE_OR_HASH/);
 });
});
test("missing first record is rejected; no silent sequence healing",()=>{
 scratch(dir=>{
  J.create(dir,{runId:"C31-UNIT",sourceFileSha256:W.sourceFingerprint().runtimeFileSha256});
  J.append(dir,observed(native(),clock(1000)));
  J.append(dir,observed(native(),clock(2000)));
  const first=fs.readdirSync(dir).filter(x=>x!=="manifest.json").sort()[0];
  fs.unlinkSync(path.join(dir,first));
  assert.throws(()=>J.verify(dir),/C31J_CHAIN_GAP_OR_FOREIGN_FILE/);
 });
});
test("foreign record and insecure file permissions fail closed",()=>{
 scratch(dir=>{
  J.create(dir,{runId:"C31-UNIT",sourceFileSha256:W.sourceFingerprint().runtimeFileSha256});
  fs.writeFileSync(path.join(dir,"other.txt"),"unauthorized",{mode:0o600});
  assert.throws(()=>J.verify(dir),/C31J_CHAIN_GAP_OR_FOREIGN_FILE/);
  fs.unlinkSync(path.join(dir,"other.txt"));
  fs.chmodSync(path.join(dir,"manifest.json"),0o644);
  assert.throws(()=>J.verify(dir),/C31J_PRIVATE_FILE_0600/);
 });
});
test("cannot use source hash from another engine",()=>{
 scratch(dir=>{
  J.create(dir,{runId:"C31-UNIT",sourceFileSha256:"f".repeat(64)});
  assert.throws(()=>J.append(dir,observed(native())),/C31J_APPEND_SOURCE_CONTRACT/);
 });
});

test("original native WAIT diagnostic is accounted without treating it as C22",()=>{
 const p=native();
 p.cfg={universe:[{book:"crypto",symbol:"BTC/USD"}],quoteAgeMs:15000,maxSpreadBps:50};
 p.catalog=[{id:"crypto-native",book:"crypto",family:"shock_recovery",params:{}}];
 const rows=[],detach=W.attach(p,{sink:r=>rows.push(r),clock:clock()});
 assert.deepEqual(p.evaluate("crypto",{quotes:{},daily:{}},["crypto-native"],500),[]);
 detach();
 assert.equal(rows.length,1);
 assert.equal(rows[0].nativeDiagnostics.declaredNativePluginSymbolPairs,1);
 assert.equal(rows[0].nativeDiagnostics.diagnosedNativePluginSymbolPairs,1);
 assert.equal(rows[0].nativeDiagnostics.diagnosticsCompleteForDeclaredNativePairs,true);
 assert.equal(rows[0].nativeDiagnostics.actualNativePrefilterEvaluationAndZeroSignalCompletenessProved,false);
 assert.equal(rows[0].c22SixFrozenPrefilterEvaluationsProved,false);
});
test("silent original-native outcomes cannot count as observed evaluation",()=>{
 const p=native();
 p.cfg.universe=[{book:"crypto",symbol:"BTC/USD"}];
 p.catalog=[{id:"crypto-native",book:"crypto",family:"shock_recovery"}];
 p.diagnostics=[];
 const audit=W.auditNativeDiagnostics(p,"crypto",["crypto-native"]);
 assert.equal(audit.declaredNativePluginSymbolPairs,1);
 assert.deepEqual(audit.undiagnosedNativePairIds,["crypto-native|BTC/USD"]);
 assert.equal(audit.diagnosticsCompleteForDeclaredNativePairs,false);
 assert.equal(audit.sixC22PolicyLineageProved,false);
});
