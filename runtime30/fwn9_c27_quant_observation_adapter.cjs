"use strict";
/** C27 source adapter for existing runtime30/quant_observations.js contract.
 *
 * Reuses the *native* observation input signal-id coverage:
 * requested plugin|symbol == accepted feature rows U rejected reasons.
 * Captures no signals, orders, broker calls or market data itself.
 * OBSERVED_ONLY never means a planned or filled trade.
 */
const A=require("node:assert/strict");
const S=require("./fwn9_c27_prebar_state.cjs");
function need(x,code){A.ok(x,"C27O_"+code);}
function key(s){return s.plugin+"|"+s.symbol;}
function fromOriginalObservation(input,observation,{barStart,universe,
 generatorHash}){
 need(input&&typeof input==="object"&&
  observation?.schema==="HARPOON_RUNTIME_OBSERVATION_1"&&
  observation.execution_allowed===false&&
  observation.liveApproved===false&&
  Array.isArray(observation.selected)&&observation.selected.length===0&&
  ["OBSERVATION_CAPTURED","WAIT_FEATURE_DATA"].includes(observation.status),
  "READONLY_ORIGINAL_QUANT_OBSERVATION");
 need(Number.isSafeInteger(input.now)&&input.now>0&&
  Number.isSafeInteger(barStart)&&barStart>=input.now&&
  Number.isFinite(Date.parse(observation.asof))&&
  Date.parse(observation.asof)===input.now,
  "SOURCE_OBSERVATION_KNOWN_PREBAR");
 need(Array.isArray(input.signals)&&input.signals.length<=10000&&
  Array.isArray(universe)&&universe.length>0&&
  generatorHash==="9d4afa402d2b70791f175e79219495f9bbbe25eb3cd0b7e9212cef6bccbd68ab",
  "SOURCE_REGISTERED_GENERATOR");
 const u=new Set(universe),requested=new Map();
 for(const row of input.signals){
  const id=key(row);
  need(typeof row.plugin==="string"&&
   S.POLICY_IDS.includes(row.plugin)&&
   typeof row.symbol==="string"&&u.has(row.symbol)&&
   !requested.has(id),"ORIGINAL_SIGNAL_ENVELOPE");
  requested.set(id,{id,policyId:row.plugin,symbol:row.symbol,
   decisionAt:input.now,knownAt:input.now});
 }
 need(Array.isArray(observation.observations)&&
  observation.rejected&&typeof observation.rejected==="object"&&
  !Array.isArray(observation.rejected),"ORIGINAL_FEATURES_AND_REJECTED");
 const covered=new Map();
 for(const row of observation.observations){
  need(requested.has(row.id)&&!covered.has(row.id)&&
   Array.isArray(row.features)&&row.features.length===8&&
   row.features.every(n=>typeof n==="number"&&Number.isFinite(n))&&
   Date.parse(row.asof)===input.now&&
   Number.isFinite(Date.parse(row.known_at))&&
   Date.parse(row.known_at)<=input.now,
   "FEATURE_PREBAR_KNOWN_AND_COMPLETE");
  covered.set(row.id,{...requested.get(row.id),
   knownAt:Date.parse(row.known_at),
   outcome:"OBSERVED_ONLY",reason:"NOT_ROUTED_N9S_NO_GO"});
 }
 for(const [id,reason] of Object.entries(observation.rejected)){
  need(requested.has(id)&&!covered.has(id)&&
   typeof reason==="string"&&reason.trim().length>0,
   "REJECTED_SOURCE_ID_REASON");
  covered.set(id,{...requested.get(id),
   outcome:"REFUSED",reason});
 }
 need(covered.size===requested.size,
  "ORIGINAL_OBSERVATION_CANDIDATE_OMISSION");
 const output={generatorSourceHash:generatorHash,
  candidateCollectionCompleteDeclared:true,
  enumeratedIds:[...requested.keys()],
  outcomes:[...requested.keys()].map(id=>covered.get(id))};
 // This verifier only proves the source already accounts for its requested
 // list, not that all possible market signals were ever requested.
 return {schema:"HARPOON_FWN9_C27_ORIGINAL_OBSERVATION_COVERAGE_1",
  opportunityCoverage:output,
  requested:requested.size,withFeatures:observation.observations.length,
  refused:Object.keys(observation.rejected).length,
  sourceRecordsCryptographicallyAuthentic:false,
  sourceEnumeratorExhaustiveOfAllPossibleMarketOpportunities:false,
  originalQuanObservationScopeVerified:true,
  noTradingAuthority:true,N9S:"NO_GO"};
}
module.exports={fromOriginalObservation};
