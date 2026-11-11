"use strict";
const test=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const os=require("node:os");
const path=require("node:path");
const {Plugins}=require("../runtime30/plugins.js");
const W=require("../runtime30/fwn9_c32_native_prefilter_gate.cjs");
const J=require("../runtime30/fwn9_c32_prefilter_journal.cjs");
const C27=require("../runtime30/fwn9_c27_prebar_state.cjs");
const C28=require("../runtime30/fwn9_c28_source_obligations.cjs");
const EMPTY_MARKET={quotes:{},bars:{},daily:{},calendar:[],assets:{},snapshots:{},metadata:{}};
const AT=Date.parse("2026-11-10T01:00:00.000Z");
function native(book="crypto"){
 const p=Object.create(Plugins.prototype);
 p.cfg={universe:[{symbol:book==="crypto"?"BTC/USD":book==="options"?
  "SPY261218C00600000":"SPY",book,venueOpen:true,
  contractSessionVerified:true}],optionUnderlyings:book==="options"?["SPY"]:[],
  quoteAgeMs:15000,maxSpreadBps:50,maxOptionSpreadBps:100,
  slippageBps:2,cryptoFeeBps:25};
 p.catalog=[{id:book+"-native-original",book,family:"shock_recovery",params:{}}];
 p.diagnostics=[];p.legacy={settings:{},HX:{},HXX:{}};
 return p;
}
function clock(t=AT+1000){return()=>++t;}
function scratch(callback){
 const base=fs.mkdtempSync(path.join(os.tmpdir(),"harpoon-c32-"));
 try{return callback(path.join(base,"journal"))}
 finally{fs.rmSync(base,{recursive:true,force:true});}
}
function observe(p,book="crypto",asOf=AT){
 const rows=[],stop=W.attach(p,{sink:r=>rows.push(r),clock:clock()});
 let result;
 try{result=p.evaluate(book,EMPTY_MARKET,[p.catalog[0].id],asOf);}
 finally{stop();}
 return {rows,result};
}
function context(p,book,rows){
 return {rows,book,asOf:AT,selectedPlugins:p.catalog,universe:p.cfg.universe,
  optionUnderlyings:p.cfg.optionUnderlyings,calendar:[]};
}
test("original source file and all three evaluator sites are instrumented",()=>{
 const p=native();
 const sha=W.originalMethodIdentity(p);
 assert.match(sha,/^[a-f0-9]{64}$/);
 assert.equal(W.sourceHash(),sha);
});
test("attachment does not evaluate plugins or generate any signal",()=>{
 const p=native();const records=[],nativeMethod=p.evaluate;
 const stop=W.attach(p,{sink:x=>records.push(x),clock:clock()});
 assert.equal(p.evaluate,nativeMethod);assert.equal(records.length,0);
 stop();assert.equal(Object.hasOwn(p,"c32PrefilterTap"),false);
});
test("crypto original call records source pair BEFORE quote failure",()=>{
 const p=native(),{rows,result}=observe(p);
 assert.deepEqual(result,[]);
 assert.deepEqual(rows.map(r=>r.site),
  ["EVALUATE_SOURCE_BEFORE_FEATURES","NATIVE_PAIR_PRE_QUOTE"]);
 assert.equal(p.diagnostics[0].status,"WAIT");
 assert.match(p.diagnostics[0].reason,/STALE_QUOTE/);
 const a=W.auditCall(context(p,"crypto",rows));
 assert.equal(a.nativePairScopeComplete,true);
 assert.equal(a.expectedNativePrefilterPairs,1);
 assert.equal(a.observedNativePrefilterPairs,1);
 assert.equal(a.c28FrozenSixPolicyIdentityAndExecutionEquivalent,false);
 assert.deepEqual(a.conditionalWindowProjections[0].candidateFrozenWindowPolicies,
  ["H22_CRYPTO_UTC_LIQUIDITY@UTC_00_08"]);
 assert.equal(a.conditionalWindowProjections[0].semanticallyEquivalentToFrozenC22Strategy,false);
});
test("equity source marks happen BEFORE feature quote filtering",()=>{
 const p=native("equity"),{rows,result}=observe(p,"equity");
 assert.deepEqual(result,[]);
 assert.deepEqual(rows.map(r=>r.site),
 ["EVALUATE_SOURCE_BEFORE_FEATURES","FEATURE_PRE_QUOTE","NATIVE_PAIR_PRE_QUOTE"]);
 assert.equal(p.diagnostics.filter(x=>x.status==="WAIT_DATA").length,1);
 assert.equal(p.diagnostics.filter(x=>x.status==="WAIT").length,1);
 const a=W.auditCall(context(p,"equity",rows));
 assert.equal(a.nativePairScopeComplete,true);
 assert.equal(a.c28FrozenSixPolicyIdentityAndExecutionEquivalent,false);
});
test("options underlying source is distinct from an evaluated contract",()=>{
 const p=native("options");
 const {rows,result}=observe(p,"options");
 assert.deepEqual(result,[]);
 assert.deepEqual(rows.map(r=>r.site),
 ["EVALUATE_SOURCE_BEFORE_FEATURES","NATIVE_PAIR_PRE_QUOTE",
  "OPTIONS_UNDERLYING_PRE_FILTERS"]);
 const a=W.auditCall(context(p,"options",rows));
 assert.equal(a.nativePairScopeComplete,true);
 assert.equal(a.nativeOptionUnderlyingScopeComplete,true);
 assert.equal(a.optionsEvaluatedPerContract,false);
 assert.equal(a.c28FrozenSixPolicyIdentityAndExecutionEquivalent,false);
});
test("missing prefilter source pair cannot pass audit",()=>{
 const p=native(),{rows}=observe(p);
 const a=W.auditCall(context(p,"crypto",rows.slice(0,1)));
 assert.equal(a.nativePairScopeComplete,false);
 assert.deepEqual(a.missingNativePairs,["crypto-native-original|BTC/USD"]);
});
test("duplicate source event cannot masquerade as exhaustive evaluation",()=>{
 const p=native(),{rows}=observe(p);
 const copy={...rows[1],sequence:3,localRecordedAt:rows[1].localRecordedAt+1};
 const a=W.auditCall(context(p,"crypto",[...rows,copy]));
 assert.equal(a.nativePairScopeComplete,false);
});
test("source quote filter exceptions do not fabricate candidate IDs",()=>{
 const p=native(),{rows}=observe(p);
 assert.equal(rows.some(x=>Object.hasOwn(x,"entry")||
  Object.hasOwn(x,"profit")||Object.hasOwn(x,"fill")),false);
 assert.equal(rows.every(x=>x.brokerFillObserved===false),true);
 assert.equal(rows.every(x=>x.paperOrLiveOrderAuthorized===false),true);
});
test("source time in future is rejected before sink",()=>{
 const p=native(),rows=[],stop=W.attach(p,{clock:()=>AT-10000,sink:r=>rows.push(r)});
 assert.throws(()=>p.evaluate("crypto",EMPTY_MARKET,[p.catalog[0].id],AT),
  /C32_RECEIPT_CLOCK_NOT_CAUSAL/);
 stop();
 assert.equal(rows.length,0);
});
test("observer write failure is not swallowed by original native filters",()=>{
 const p=native(),stop=W.attach(p,{clock:clock(),
  sink(){throw Error("STORAGE_IO_FAULT")}});
 assert.throws(()=>p.evaluate("crypto",EMPTY_MARKET,[p.catalog[0].id],AT),
  /STORAGE_IO_FAULT/);
 stop();
 assert.equal(p.diagnostics.length,0);
});
test("double attachment and replaced native evaluator are rejected",()=>{
 const p=native(),stop=W.attach(p,{clock:clock(),sink(){}});
 assert.throws(()=>W.attach(p,{clock:clock(),sink(){}}),
  /C32_NO_HOOK_OVERWRITE_AND_SINK_REQUIRED/);
 stop();p.evaluate=()=>[];
 assert.throws(()=>W.attach(p,{clock:clock(),sink(){}}),
  /C32_ORIGINAL_NATIVE_METHODS/);
});
test("C22 two windows per asset book are not one native strategy identity",()=>{
 const p=native();
 assert.equal(C28.EXPECTED.filter(x=>x.book.includes("crypto")).length,2);
 assert.equal(p.catalog.length,1);
 const {rows}=observe(p),a=W.auditCall(context(p,"crypto",rows));
 assert.equal(a.conditionalWindowProjections[0].candidateFrozenWindowPolicies.length,1);
 assert.equal(a.c28FrozenSixPolicyIdentityAndExecutionEquivalent,false);
});
test("C32 immutable journal survives process restart and preserves raw events",()=>{
 scratch(dir=>{
  const p=native(),hash=W.sourceHash(),registry=C27.digest(p.cfg.universe);
  J.create(dir,{runId:"TEST_C32",sourceFileSha256:hash,policyRegistryHash:registry});
  const writer=J.openWriter(dir);
  const stop=W.attach(p,{sink:row=>writer.append(row),clock:clock()});
  p.evaluate("crypto",EMPTY_MARKET,[p.catalog[0].id],AT);
  stop();
  const close=writer.close(),reopened=J.verify(dir);
  assert.equal(close.count,2);assert.equal(reopened.head,close.head);
  assert.equal(reopened.sixFrozenStrategyIdentitiesProven,false);
  assert.equal(reopened.externallyTimestamped,false);
 });
});
test("C32 journal detects bit-tampered event and refuses restart",()=>{
 scratch(dir=>{
  const p=native();J.create(dir,{runId:"TEST_C32",
   sourceFileSha256:W.sourceHash(),policyRegistryHash:C27.digest(p.cfg.universe)});
  const w=J.openWriter(dir),stop=W.attach(p,{sink:r=>w.append(r),clock:clock()});
  p.evaluate("crypto",EMPTY_MARKET,[p.catalog[0].id],AT);stop();w.close();
  const f=path.join(dir,"events.ndjson"),data=fs.readFileSync(f,"utf8");
  fs.writeFileSync(f,data.replace("NATIVE_PAIR_PRE_QUOTE","NATIVE_PAIR_FAKE"));
  assert.throws(()=>J.verify(dir),/C32J_CHAIN_HASH_OR_SOURCE/);
 });
});
test("truncated journal line invalidates the history",()=>{
 scratch(dir=>{
  const p=native();J.create(dir,{runId:"TEST_C32",
   sourceFileSha256:W.sourceHash(),policyRegistryHash:C27.digest(p.cfg.universe)});
  fs.writeFileSync(path.join(dir,"events.ndjson"),'{"partial":true');
  assert.throws(()=>J.verify(dir),/C32J_TRUNCATED_EVENT/);
 });
});
test("journal lock is not automatically cleared after interruption",()=>{
 scratch(dir=>{
  const p=native();J.create(dir,{runId:"TEST_C32",
   sourceFileSha256:W.sourceHash(),policyRegistryHash:C27.digest(p.cfg.universe)});
  const w=J.openWriter(dir);
  assert.throws(()=>J.openWriter(dir),/C32J_STALE_LOCK_REQUIRES_REVIEW/);
  w.close();
 });
});
test("C32 journal private file permissions are enforced",()=>{
 scratch(dir=>{
  const p=native();J.create(dir,{runId:"TEST_C32",
   sourceFileSha256:W.sourceHash(),policyRegistryHash:C27.digest(p.cfg.universe)});
  fs.chmodSync(path.join(dir,"events.ndjson"),0o644);
  assert.throws(()=>J.verify(dir),/C32J_PRIVATE_FILE_0600_AND_LIMIT/);
 });
});
