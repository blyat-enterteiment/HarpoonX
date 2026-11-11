"use strict";
/** FWN9 C28 source completeness for SIX FROZEN C22 variants plus original.
 * Deterministically enumerate ALL registered asset/window obligations BEFORE
 * interpreting a generator's output. Empty output requires an explicit source
 * invocation record, not absence of an opportunity row.
 *
 * No broker, orders, market generator, account trials, holdout or deployment.
 * Caller-supplied local hashes/knownAt do NOT authenticate market source.
 */
const A=require("node:assert/strict");
const C22=require("./fwn9_c22_session_compound.cjs");
const C27=require("./fwn9_c27_prebar_state.cjs");
const J=require("./fwn9_c27_prebar_journal.cjs");
const fs=require("node:fs"),path=require("node:path");
const EXPECTED=Object.freeze([
 {policy:"H22_OPENING_CONFIRMATION@RTH_OPEN_30",book:["equity","etf"],window:"RTH_OPEN_30"},
 {policy:"H22_OPENING_CONFIRMATION@RTH_MORNING_30_120",book:["equity","etf"],window:"RTH_MORNING_30_120"},
 {policy:"H22_CRYPTO_UTC_LIQUIDITY@UTC_00_08",book:["crypto"],window:"UTC_00_08"},
 {policy:"H22_CRYPTO_UTC_LIQUIDITY@UTC_16_24",book:["crypto"],window:"UTC_16_24"},
 {policy:"H22_OPTION_ASYMMETRY_RESEARCH_ONLY@RTH_MORNING_30_120",book:["options"],window:"RTH_MORNING_30_120"},
 {policy:"H22_OPTION_ASYMMETRY_RESEARCH_ONLY@RTH_LAST_90",book:["options"],window:"RTH_LAST_90"}
]);
const TAP="HARPOON_FWN9_C28_PRE_FILTER_SOURCE_TAP_1";
function need(x,c){A.ok(x,"C28_"+c);}
function text(x,c){need(typeof x==="string"&&x.length>0&&x.length<=256,c);return x;}
function safe(t,c){need(Number.isSafeInteger(t)&&t>=0,c);return t;}
function reg(rows){
 need(Array.isArray(rows)&&rows.length>0&&rows.length<=48,"REGISTRY_LENGTH");
 const seen=new Set(),out=[];
 for(const r of rows){
  need(r&&typeof r==="object","REGISTRY_ITEM");
  const symbol=text(r.symbol,"REGISTRY_SYMBOL"),book=text(r.book,"REGISTRY_BOOK");
  need(["equity","etf","crypto","options"].includes(book)&&!seen.has(symbol),
   "REGISTRY_DUPLICATE_OR_CLASS");
  need(r.venueOpen===undefined||typeof r.venueOpen==="boolean",
   "REGISTRY_VENUE");
  need(r.contractSessionVerified===undefined||
   typeof r.contractSessionVerified==="boolean","REGISTRY_OPTIONS");
  seen.add(symbol);out.push({symbol,book,
   venueOpen:r.venueOpen===true,
   contractSessionVerified:r.contractSessionVerified===true});
 }
 return out.sort((a,b)=>a.symbol.localeCompare(b.symbol));
}
function slot({barStart,asset,variant,calendar}){
 const w=C22.windowFor({book:asset.book,at:barStart,
  calendar,venueOpen:asset.venueOpen,
  contractSessionVerified:asset.contractSessionVerified});
 const active=w.eligible===true&&w.window===variant.window;
 const reason=active?null:
  !w.eligible?w.reason:"FROZEN_VARIANT_WINDOW_NOT_ACTIVE";
 return {barStart,symbol:asset.symbol,policyId:variant.policy,
  book:asset.book,requiredEvaluation:active,skipReason:reason};
}
function obligations({barStart,registry,calendar}){
 safe(barStart,"BAR_CLOCK");
 need(Array.isArray(calendar),"VERIFIED_CALENDAR_ARRAY_REQUIRED");
 const assets=reg(registry);
 const out=[];
 for(const asset of assets){
  for(const variant of EXPECTED){
   if(!variant.book.includes(asset.book))continue;
   out.push(slot({barStart,asset,variant,calendar}));
  }
  const own=C22.windowFor({book:asset.book,at:barStart,calendar,
   venueOpen:asset.venueOpen,
   contractSessionVerified:asset.contractSessionVerified});
  out.push({barStart,symbol:asset.symbol,policyId:"ORIGINAL_BASELINE",
   book:asset.book,requiredEvaluation:own.eligible,
   skipReason:own.eligible?null:own.reason});
 }
 return out.sort((a,b)=>a.symbol.localeCompare(b.symbol)||
  a.policyId.localeCompare(b.policyId));
}
function makeTap({obligation,sourceCall,now=Date.now}){
 need(obligation&&typeof obligation==="object","OBLIGATION");
 need(typeof now==="function","CLOCK");
 const start=safe(now(),"TAP_STARTED");
 if(!obligation.requiredEvaluation){
  need(sourceCall===null||sourceCall===undefined,"INELIGIBLE_SOURCE_MUST_NOT_RUN");
  return {...obligation,schema:TAP,startedAt:start,knownAt:safe(now(),"TAP_FINISHED"),
   status:"SKIPPED",reason:obligation.skipReason,emittedIds:[],
   sourceMethod:"NO_PLUGIN_INVOCATION",sourceOriginAuthenticated:false};
 }
 need(typeof sourceCall==="function","SOURCE_FUNCTION_REQUIRED");
 const result=sourceCall();
 need(Array.isArray(result)&&result.length<=10000,"SOURCE_OUTPUT_ARRAY");
 const names=[];
 for(const r of result){
  need(r&&typeof r==="object"&&r.policyId===obligation.policyId&&
   r.symbol===obligation.symbol,"SOURCE_OUTPUT_ORIGIN_PAIR");
  names.push(text(r.id,"SOURCE_OUTPUT_ID"));
 }
 need(new Set(names).size===names.length,"SOURCE_DUPLICATE_ID");
 const end=safe(now(),"TAP_FINISHED");
 need(end>=start,"TAP_CLOCK_REGRESSION");
 return {...obligation,schema:TAP,startedAt:start,knownAt:end,
  status:"EVALUATED",reason:names.length?null:"EMPTY_SOURCE_OUTPUT",
  emittedIds:names,sourceMethod:"PRE_FILTER_EXACT_CALL_RETURN",
  sourceOriginAuthenticated:false};
}
function verifyFrame({frame,registry,calendar,taps}){
 need(frame?.schema==="HARPOON_FWN9_C27_PREBAR_VALIDATED_FRAME_1",
  "C27_FRAME_REQUIRED");
 const input=frame.originalInput,expected=obligations({
  barStart:frame.barStart,registry,calendar});
 const universe=reg(registry).map(x=>x.symbol);
 need(universe.length===input.universe.length&&
  universe.every((x,i)=>x===[...input.universe].sort()[i]),
  "SOURCE_UNIVERSE_NOT_MATCHING_C27");
 need(Array.isArray(taps)&&taps.length===expected.length,
  "SLOT_COUNT_MISMATCH");
 const target=new Map(expected.map(x=>[x.symbol+"|"+x.policyId,x]));
 const observed=new Map();
 const emitted=new Set();
 const outcomes=input.opportunityCoverage.outcomes;
 const c27=new Map(outcomes.map(x=>[x.id,x]));
 need(c27.size===outcomes.length,"DUPLICATE_C27_OUTCOME");
 const cutoff=frame.captureKnowledgeCutoff;
 let active=0,skipped=0,zero=0,withCandidates=0;
 for(const tap of taps){
  need(tap?.schema===TAP,"SOURCE_TAP_SCHEMA");
  const key=tap.symbol+"|"+tap.policyId,e=target.get(key);
  need(e&&!observed.has(key)&&e.barStart===tap.barStart&&
   e.requiredEvaluation===tap.requiredEvaluation&&
   e.book===tap.book&&e.skipReason===tap.skipReason,
   "INDEPENDENT_SLOT_ORIGINAL_REGISTRY_MISMATCH");
  observed.set(key,tap);
  need(safe(tap.startedAt,"TAP_START")<=
   safe(tap.knownAt,"TAP_KNOWN")&&tap.knownAt<=cutoff,
   "SOURCE_EVALUATION_AFTER_PREBAR_SEAL");
  need(Array.isArray(tap.emittedIds)&&
   new Set(tap.emittedIds).size===tap.emittedIds.length,
   "TAP_EMITTED_IDS");
  need(tap.sourceOriginAuthenticated===false,"TAP_SELF_AUTHENTICATED");
  if(e.requiredEvaluation){
   need(tap.status==="EVALUATED"&&
    tap.sourceMethod==="PRE_FILTER_EXACT_CALL_RETURN"&&
    tap.reason===(tap.emittedIds.length?null:"EMPTY_SOURCE_OUTPUT"),
    "EVALUATOR_NOT_OBSERVED_OR_FALSE_EMPTY");
   active++;
   if(tap.emittedIds.length===0)zero++;
   for(const id of tap.emittedIds){
    need(!emitted.has(id)&&c27.has(id)&&
     c27.get(id).policyId===tap.policyId&&
     c27.get(id).symbol===tap.symbol,
     "PRE_FILTER_GENERATED_SIGNAL_OMITTED_FROM_C27");
    emitted.add(id);withCandidates++;
   }
  }else{
   need(tap.status==="SKIPPED"&&
    tap.reason===e.skipReason&&tap.emittedIds.length===0&&
    tap.sourceMethod==="NO_PLUGIN_INVOCATION",
    "INELIGIBLE_SLOT_EVALUATED_OR_NOT_EXPLAINED");
   skipped++;
  }
 }
 for(const row of outcomes){
  if(row.policyId==="CASH")need(false,"CASH_MUST_NOT_CREATE_TRADING_CANDIDATES");
  need(emitted.has(row.id),"C27_CANDIDATE_NOT_IN_PREFILTER_SOURCE");
 }
 return {schema:"HARPOON_FWN9_C28_ALL_REGISTERED_SLOT_GATE_1",
  barStart:frame.barStart,obligationCount:expected.length,
  evaluationsCompleted:active,explicitIneligible:skipped,
  evaluatedWithoutSignal:zero,rawCandidatesMatched:withCandidates,
  C27candidateCount:outcomes.length,
  allRegisteredAssetVariantSlotsAccountedFor:true,
  allSourceEmissionsBoundToC27:true,
  underlyingGeneratorCoverageBeyondRegisteredSlotsCertified:false,
  originalNativeBrokerReceiptSourceAuthenticated:false,
  downstreamOriginalEconomicPolicyChanged:false,
  executableOrdersAllowed:false,N9S:"NO_GO"};
}
function inspectJournal({dir,registry,calendar,tapsByBar}){
 need(typeof dir==="string"&&dir.length>0,"JOURNAL_PATH");
 need(Array.isArray(tapsByBar),"TAPS_FOR_ALL_BARS");
 const checked=J.verifyJournal(dir);
 need(checked.coverageComplete&&
  checked.verifiedFrames===tapsByBar.length,
  "INCOMPLETE_C27_BAR_SCHEDULE");
 const rows=[];
 for(let i=0;i<checked.verifiedFrames;i++){
  const prior=checked.entries[i],
   file=String(i+1).padStart(8,"0")+"-"+prior.frameHash+".json";
  const saved=JSON.parse(fs.readFileSync(path.join(dir,file),"utf8"));
  need(saved.frameHash===prior.frameHash&&
   saved.input.barStart===prior.barStart,"FRAME_NOT_CHAIN_BOUND");
  const frame=C27.validatePrebar(saved.input,checked.manifest);
  rows.push(verifyFrame({frame,registry,calendar,
   taps:tapsByBar[i]}));
 }
 return {schema:"HARPOON_FWN9_C28_COMPLETE_C27_SLOT_OBSERVABILITY_1",
  completeSchedule:true,barCount:rows.length,
  totalSlots:rows.reduce((n,x)=>n+x.obligationCount,0),
  evaluatedSlots:rows.reduce((n,x)=>n+x.evaluationsCompleted,0),
  explicitSkippedSlots:rows.reduce((n,x)=>n+x.explicitIneligible,0),
  generatedSignalsMatched:rows.reduce((n,x)=>n+x.rawCandidatesMatched,0),
  c27ChainDigest:checked.finalizedEvidenceHead,rows,
  completeRegisteredPolicyUniverseVerified:true,
  sourceGeneratorGlobalMarketOpportunitiesProved:false,
  independentExchangeAuthenticityProved:false,
  FWN9FinancialGo:false,N9S:"NO_GO",M10Sealed:3200};
}
module.exports={EXPECTED,TAP,reg,obligations,makeTap,verifyFrame,inspectJournal};
