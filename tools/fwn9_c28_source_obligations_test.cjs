"use strict";
/** No real signal, no market generator seed. Fixed source C27 engineering frames. */
const test=require("node:test"),A=require("node:assert/strict");
const fs=require("node:fs"),os=require("node:os"),path=require("node:path");
const F=require("./fwn9_c27_test_fixture.cjs");
const C27=require("../runtime30/fwn9_c27_prebar_state.cjs");
const J=require("../runtime30/fwn9_c27_prebar_journal.cjs");
const C=require("../runtime30/fwn9_c28_source_obligations.cjs");
const registry=[{symbol:"SYNA",book:"equity"},
 {symbol:"SYNB",book:"equity"}];
const day=F.BARS[0],exchange=[{
 date:new Date(day).toISOString().slice(0,10),open:day,close:day+78*300000
}];
const now=t=>()=>t;
function frame(i){return C27.validatePrebar(F.sample().frames[i],
 {...F.manifest(),policyIds:C27.POLICY_IDS});}
function taps(i,{reg=registry,calendar=exchange,edit=null}={}){
 const f=F.sample().frames[i],obs=f.opportunityCoverage.outcomes;
 const result=C.obligations({barStart:f.barStart,registry:reg,calendar});
 const data=result.map(o=>{
  const emitted=obs.filter(x=>x.symbol===o.symbol&&x.policyId===o.policyId)
   .map(x=>({id:x.id,policyId:x.policyId,symbol:x.symbol}));
  const source=o.requiredEvaluation?()=>emitted:null;
  return C.makeTap({obligation:o,sourceCall:source,now:now(f.barStart-500)});
 });
 if(edit)edit(data);
 return data;
}
function journal(fn){
 const tmp=fs.mkdtempSync(path.join(os.tmpdir(),"c28-grid-"));
 const dir=path.join(tmp,"prebar");
 try{
  const f=F.sample();
  J.newJournal(dir,{...F.manifest()});
  for(const row of f.frames)J.append(dir,row);
  return fn(dir);
 }finally{fs.rmSync(tmp,{recursive:true,force:true});}
}
test("C28 exact C22 original equity windows obligation grid is independent of generated signals",()=>{
 const r=C.obligations({barStart:day,registry,calendar:exchange});
 A.equal(r.length,6); // 2 per symbol + original baseline
 A.equal(r.filter(x=>x.requiredEvaluation).length,4);
 A.equal(r.filter(x=>!x.requiredEvaluation).length,2);
 A.equal(r.find(x=>x.symbol==="SYNA"&&x.policyId.includes("MORNING")).skipReason,
  "FROZEN_VARIANT_WINDOW_NOT_ACTIVE");
});
test("C28 declared generator call is invoked exactly once for eligible slot",()=>{
 const o=C.obligations({barStart:day,registry,calendar:exchange})
  .find(x=>x.requiredEvaluation);
 let called=0;
 const tap=C.makeTap({obligation:o,sourceCall:()=>{
  called++;return [];
 },now:now(day-1000)});
 A.equal(called,1);
 A.equal(tap.status,"EVALUATED");
 A.equal(tap.reason,"EMPTY_SOURCE_OUTPUT");
 A.equal(tap.sourceOriginAuthenticated,false);
});
test("C28 inactive window must be explicitly SKIPPED without source invocation",()=>{
 const o=C.obligations({barStart:day,registry,calendar:exchange})
  .find(x=>!x.requiredEvaluation);
 const tap=C.makeTap({obligation:o,sourceCall:null,now:now(day-1000)});
 A.equal(tap.status,"SKIPPED");
 A.equal(tap.reason,"FROZEN_VARIANT_WINDOW_NOT_ACTIVE");
 A.throws(()=>C.makeTap({obligation:o,sourceCall:()=>[],now:now(day-1000)}),
  /C28_INELIGIBLE_SOURCE_MUST_NOT_RUN/);
});
test("C28 original source frame1 binds all prefilter emissions incl refused candidate",()=>{
 const f=frame(1),r=C.verifyFrame({frame:f,registry,calendar:exchange,taps:taps(1)});
 A.equal(r.evaluationsCompleted,4);
 A.equal(r.explicitIneligible,2);
 A.equal(r.rawCandidatesMatched,2);
 A.equal(r.C27candidateCount,2);
 A.equal(r.allRegisteredAssetVariantSlotsAccountedFor,true);
 A.equal(r.N9S,"NO_GO");
});
test("C28 independent source tap cannot omit emitted original rejected opportunity",()=>{
 const x=taps(1,{edit:a=>{
  const row=a.find(y=>y.symbol==="SYNB"&&y.requiredEvaluation&&
   y.policyId.includes("OPEN_30"));
  row.emittedIds=[];row.reason="EMPTY_SOURCE_OUTPUT";
 }});
 A.throws(()=>C.verifyFrame({frame:frame(1),registry,calendar:exchange,taps:x}),
  /C28_C27_CANDIDATE_NOT_IN_PREFILTER_SOURCE/);
});
test("C28 cannot hide source generated raw signal missing downstream C27",()=>{
 const x=taps(1,{edit:a=>{
  const row=a.find(y=>y.symbol==="SYNA"&&y.policyId.includes("OPEN_30"));
  row.emittedIds.push("GHOST_RAW_GENERATED");
 }});
 A.throws(()=>C.verifyFrame({frame:frame(1),registry,calendar:exchange,taps:x}),
  /C28_PRE_FILTER_GENERATED_SIGNAL_OMITTED_FROM_C27/);
});
test("C28 cannot claim source EVALUATED if callback never completed",()=>{
 const x=taps(1,{edit:a=>{const row=a.find(y=>y.requiredEvaluation);
  row.status="SKIPPED";
 }});
 A.throws(()=>C.verifyFrame({frame:frame(1),registry,calendar:exchange,taps:x}),
  /C28_EVALUATOR_NOT_OBSERVED_OR_FALSE_EMPTY/);
});
test("C28 quote/calendar skip reason cannot be used to hide eligible window",()=>{
 const x=taps(0,{edit:a=>{const row=a.find(y=>y.requiredEvaluation);
  row.requiredEvaluation=false;row.status="SKIPPED";row.reason="OUTSIDE_RTH";
 }});
 A.throws(()=>C.verifyFrame({frame:frame(0),registry,calendar:exchange,taps:x}),
  /C28_INDEPENDENT_SLOT_ORIGINAL_REGISTRY_MISMATCH/);
});
test("C28 no registry instrument may be deleted after seeing signals",()=>{
 A.throws(()=>C.verifyFrame({frame:frame(1),
  registry:registry.slice(0,1),calendar:exchange,
  taps:taps(1)}),/C28_SOURCE_UNIVERSE_NOT_MATCHING_C27/);
});
test("C28 missing one inactive slot is still incomplete audit",()=>{
 const x=taps(0);x.pop();
 A.throws(()=>C.verifyFrame({frame:frame(0),registry,calendar:exchange,taps:x}),
  /C28_SLOT_COUNT_MISMATCH/);
});
test("C28 duplicate source tap slot or duplicate signal fails",()=>{
 const x=taps(1);
 x[1]=structuredClone(x[0]);
 A.throws(()=>C.verifyFrame({frame:frame(1),registry,calendar:exchange,taps:x}),
  /C28_INDEPENDENT_SLOT_ORIGINAL_REGISTRY_MISMATCH/);
 const y=C.obligations({barStart:day,registry,calendar:exchange})
  .find(z=>z.requiredEvaluation);
 A.throws(()=>C.makeTap({obligation:y,sourceCall:()=>[
  {id:"SAME",policyId:y.policyId,symbol:y.symbol},
  {id:"SAME",policyId:y.policyId,symbol:y.symbol}
 ],now:now(day-1000)}),/C28_SOURCE_DUPLICATE_ID/);
});
test("C28 any source output with wrong instrument or variant is rejected upstream",()=>{
 const y=C.obligations({barStart:day,registry,calendar:exchange})
  .find(z=>z.requiredEvaluation);
 A.throws(()=>C.makeTap({obligation:y,sourceCall:()=>[
  {id:"A",policyId:"RETROSPECTIVE_WINNER",symbol:y.symbol}
 ],now:now(day-1000)}),/C28_SOURCE_OUTPUT_ORIGIN_PAIR/);
});
test("C28 source evaluation after capture cutoff is forbidden",()=>{
 const x=taps(1,{edit:a=>{a[0].knownAt=F.BARS[1]+1000;}});
 A.throws(()=>C.verifyFrame({frame:frame(1),registry,calendar:exchange,taps:x}),
  /C28_SOURCE_EVALUATION_AFTER_PREBAR_SEAL/);
});
test("C28 registered crypto slots are evaluated only in their original UTC windows",()=>{
 const btc=[{symbol:"BTC/USD",book:"crypto",venueOpen:true}];
 const zero=Date.parse("2026-11-07T00:05:00Z");
 const daySlots=C.obligations({barStart:zero,registry:btc,calendar:[]});
 A.equal(daySlots.length,3);
 A.equal(daySlots.filter(x=>x.requiredEvaluation).length,2);
 A(daySlots.some(x=>x.policyId.includes("UTC_00_08")&&x.requiredEvaluation));
 A(daySlots.some(x=>x.policyId.includes("UTC_16_24")&&!x.requiredEvaluation));
 const evening=C.obligations({barStart:Date.parse("2026-11-07T18:10:00Z"),
  registry:btc,calendar:[]});
 A(evening.some(x=>x.policyId.includes("UTC_16_24")&&x.requiredEvaluation));
});
test("C28 when crypto venue status unavailable all crypto slots are explicitly blocked",()=>{
 const btc=[{symbol:"BTC/USD",book:"crypto"}];
 const data=C.obligations({barStart:Date.parse("2026-11-07T01:00:00Z"),
  registry:btc,calendar:[]});
 A.equal(data.every(x=>!x.requiredEvaluation),true);
 A.equal(data.every(x=>x.skipReason==="VENUE_STATUS_UNKNOWN"),true);
});
test("C28 options require contract-specific session verification; never option order",()=>{
 const opt=[{symbol:"CBOE_TEST",book:"options",contractSessionVerified:false}];
 const blocked=C.obligations({barStart:day,registry:opt,calendar:exchange});
 A.equal(blocked.filter(x=>x.requiredEvaluation).length,0);
 A(blocked.some(x=>x.skipReason==="OPTION_CLASS_SESSION_UNVERIFIED"));
 const admitted=C.obligations({barStart:day+80*60000,
  registry:[{symbol:"CBOE_TEST",book:"options",contractSessionVerified:true}],
  calendar:exchange});
 A.equal(admitted.filter(x=>x.requiredEvaluation).length,2);
});
test("C28 full C27 3-bar journal passes per slot, but NOT global market opportunity proof",()=>journal(dir=>{
 const t=[taps(0),taps(1),taps(2)];
 const out=C.inspectJournal({dir,registry,calendar:exchange,tapsByBar:t});
 A.equal(out.barCount,3);
 A.equal(out.totalSlots,18);
 A.equal(out.generatedSignalsMatched,2);
 A.equal(out.completeRegisteredPolicyUniverseVerified,true);
 A.equal(out.sourceGeneratorGlobalMarketOpportunitiesProved,false);
 A.equal(out.FWN9FinancialGo,false);
 A.equal(out.M10Sealed,3200);
}));
test("C28 journal requires complete C27 scheduled bars; partial journal cannot be promoted",()=>{
 const parent=fs.mkdtempSync(path.join(os.tmpdir(),"c28-incomplete-"));
 const dir=path.join(parent,"journal");
 try{
  J.newJournal(dir,F.manifest());J.append(dir,F.sample().frames[0]);
  A.throws(()=>C.inspectJournal({dir,registry,calendar:exchange,tapsByBar:[taps(0)]}),
   /C28_INCOMPLETE_C27_BAR_SCHEDULE/);
 }finally{fs.rmSync(parent,{recursive:true,force:true});}
});
test("C28 any omitted entire bar source-tap group invalidates complete market panel",()=>journal(dir=>{
 A.throws(()=>C.inspectJournal({dir,registry,calendar:exchange,
  tapsByBar:[taps(0),taps(1)]}),/C28_INCOMPLETE_C27_BAR_SCHEDULE/);
}));
test("C28 source tap locally controlled hash cannot independently authenticate broker",()=>{
 const result=C.verifyFrame({frame:frame(0),registry,calendar:exchange,taps:taps(0)});
 A.equal(result.originalNativeBrokerReceiptSourceAuthenticated,false);
 A.equal(result.underlyingGeneratorCoverageBeyondRegisteredSlotsCertified,false);
 A.equal(result.executableOrdersAllowed,false);
});
