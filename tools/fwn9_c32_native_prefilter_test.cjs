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
const F=require("../runtime30/fwn9_c32_forward_binding.cjs");
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

test("actual Plugins constructor with its undefined optional field can attach",()=>{
 const p=new Plugins({}, {universe:[],enabledPlugins:[],optionUnderlyings:[]});
 const rows=[],detach=W.attach(p,{sink:x=>rows.push(x),clock:clock()});
 assert.equal(typeof p.c32PrefilterTap,"function");
 assert.deepEqual(p.evaluate("crypto",EMPTY_MARKET,[],AT),[]);
 detach();
 assert.equal(p.c32PrefilterTap,undefined);
 assert.equal(rows.length,1);
 assert.equal(rows[0].site,"EVALUATE_SOURCE_BEFORE_FEATURES");
});
test("a forged local SHA cannot be promoted to native source coverage",()=>{
 const p=native(),{rows}=observe(p);
 const forged=rows.map(r=>({...r,sourceFileSha256:"f".repeat(64)}));
 assert.throws(()=>W.auditCall(context(p,"crypto",forged)),
  /C32_SOURCE_ORIGINAL_CODE_AND_NOT_FINANCIAL_EVIDENCE/);
});
test("a source record claiming pre-registered causal or broker proof is rejected",()=>{
 const p=native(),{rows}=observe(p);
 const claimed=rows.map(r=>({...r,
  sourceKnownBeforeRegisteredBarProved:true,brokerFillObserved:true}));
 assert.throws(()=>W.auditCall(context(p,"crypto",claimed)),
  /C32_SOURCE_ORIGINAL_CODE_AND_NOT_FINANCIAL_EVIDENCE/);
});

test("completed original source can be locally timestamped before next bar only",()=>{
 const p=native(),{rows}=observe(p);
 const callAudit=W.auditCall(context(p,"crypto",rows));
 const temporal=W.auditNextBar({callAudit,rows,nextBarStart:AT+5*60000});
 assert.equal(temporal.localSourceKnownBeforeNextBar,true);
 assert.equal(temporal.c28SixOriginalPolicySemanticParityCertified,false);
 assert.equal(temporal.thirdPartyTimeOrMarketAuthenticated,false);
 assert.equal(temporal.financialGO,false);
});
test("local timing gate rejects source records received after bar start",()=>{
 const p=native(),{rows}=observe(p);
 const callAudit=W.auditCall(context(p,"crypto",rows));
 assert.throws(()=>W.auditNextBar({callAudit,rows,nextBarStart:AT}),
  /C32_NATIVE_SOURCE_CAPTURE_AFTER_BAR_START/);
});
test("local timing gate requires complete source site coverage",()=>{
 const p=native(),{rows}=observe(p);
 const callAudit=W.auditCall(context(p,"crypto",rows.slice(0,1)));
 assert.throws(()=>W.auditNextBar({callAudit,rows,nextBarStart:AT+300000}),
  /C32_COMPLETE_NATIVE_SOURCE_AND_NEXT_BAR_REQUIRED/);
});

function frozenCompositeNativeSource(){
 const p=native();
 p.cfg.universe=[
  {symbol:"SPY",book:"equity",venueOpen:true,contractSessionVerified:false},
  {symbol:"QQQ",book:"etf",venueOpen:true,contractSessionVerified:false},
  {symbol:"BTC/USD",book:"crypto",venueOpen:true,contractSessionVerified:false},
  {symbol:"SPY261218C00600000",book:"options",venueOpen:true,
   contractSessionVerified:true}
 ];
 p.catalog=[
  {id:"equity-native",book:"equity",family:"native_equity",version:"30"},
  {id:"etf-native",book:"etf",family:"native_etf",version:"30"},
  {id:"crypto-native-original",book:"crypto",family:"native_crypto",version:"30"},
  {id:"options-native",book:"options",family:"native_options",version:"30"}
 ];
 const enabled=p.catalog.map(x=>x.id);
 const definition=F.freeze({plugins:p,enabledPluginIds:enabled,
  registeredUniverse:p.cfg.universe,calendarSha256:"a".repeat(64),proposedAt:AT});
 return {p,definition};
}
test("new six-window native composite defines deterministic forward source only",()=>{
 const {definition}=frozenCompositeNativeSource();
 assert.equal(F.validate(definition),true);
 assert.equal(definition.sixProspectiveWindowBindings.length,6);
 assert.deepEqual(definition.controls,["ORIGINAL_BASELINE","CASH"]);
 assert.equal(definition.originalC22StrategyEquivalent,false);
 assert.equal(definition.independentPreOutcomeRegistration,false);
 assert.equal(definition.nativeOptionContractExecutionCertified,false);
 assert.equal(definition.financialGO,false);
 assert.notEqual(definition.sixProspectiveWindowBindings[2].window,
  definition.sixProspectiveWindowBindings[3].window);
 assert.deepEqual(definition.sixProspectiveWindowBindings[2].nativePluginsByBook,
  definition.sixProspectiveWindowBindings[3].nativePluginsByBook);
});
function observeFrozenCrypto(p){
 const selected=p.catalog.filter(x=>x.book==="crypto"),rows=[];
 const stop=W.attach(p,{clock:clock(),sink:r=>rows.push(r)});
 p.evaluate("crypto",EMPTY_MARKET,selected.map(x=>x.id),AT);stop();
 return W.auditCall({rows,book:"crypto",asOf:AT,
  selectedPlugins:selected,universe:p.cfg.universe,
  optionUnderlyings:p.cfg.optionUnderlyings,calendar:[]});
}
test("forward native binding matches exact registered source in the same universe",()=>{
 const {definition,p}=frozenCompositeNativeSource();
 const audit=observeFrozenCrypto(p);
 assert.equal(audit.sourceUniverseDigest,definition.universeDigest);
 const result=F.link({definition,callAudit:audit});
 assert.equal(result.newCompositeSourceDefinitionLocallyDeterministic,true);
 assert.equal(result.existingC22SixStrategiesSemanticallyEquivalent,false);
 assert.equal(result.records[0].matchedWindow,
  "H22_CRYPTO_UTC_LIQUIDITY@UTC_00_08");
 assert.equal(result.records[0].status,"FORWARD_ONLY_WINDOWED_NATIVE_SOURCE_BOUND");
 assert.equal(result.brokerFillsOrPaperOrdersAllowed,false);
});
test("unregistered native plugin cannot borrow another frozen C22 identity",()=>{
 const {definition,p}=frozenCompositeNativeSource();
 p.catalog.find(x=>x.book==="crypto").id="unregistered-crypto";
 const audit=observeFrozenCrypto(p);
 assert.throws(()=>F.link({definition,callAudit:audit}),
  /C32B_NATIVE_ENABLED_SET_MISMATCH/);
});
test("partial source universe cannot borrow a registered forward binding",()=>{
 const {definition}=frozenCompositeNativeSource(),p=native();
 const {rows}=observe(p),audit=W.auditCall(context(p,"crypto",rows));
 assert.throws(()=>F.link({definition,callAudit:audit}),
  /C32B_VERIFIED_NATIVE_SCOPE_REQUIRED/);
});
test("missing enabled native class blocks definition of all six variants",()=>{
 const {p}=frozenCompositeNativeSource();
 const enabled=p.catalog.map(x=>x.id).filter(x=>x!=="options-native");
 assert.throws(()=>F.freeze({plugins:p,enabledPluginIds:enabled,
  registeredUniverse:p.cfg.universe,calendarSha256:"a".repeat(64),proposedAt:AT}),
  /C32B_MISSING_ENABLED_NATIVE_PLUGIN_FOR_options/);
});
test("a tampered binding or bogus external certificate never passes validation",()=>{
 const {definition}=frozenCompositeNativeSource();
 definition.independentPreOutcomeRegistration=true;
 assert.throws(()=>F.validate(definition),/C32B_SOURCE_BINARY_DIGEST_CHANGED/);
});
