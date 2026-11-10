"use strict";
/** C27 direct adapter tests of original QUANT OBSERVATION source contract.
 * Not candidate selection and no new prospective economic account.
 */
const test=require("node:test"),A=require("node:assert/strict");
const Q=require("../runtime30/fwn9_c27_quant_observation_adapter.cjs");
const S=require("../runtime30/fwn9_c27_prebar_state.cjs");
const F=require("./fwn9_c27_test_fixture.cjs");
const PLUG1="H22_OPENING_CONFIRMATION@RTH_OPEN_30",
 PLUG2="H22_CRYPTO_UTC_LIQUIDITY@UTC_00_08";
function sample(){
 const now=F.BARS[0]-1000;
 const input={now,signals:[
  {plugin:PLUG1,symbol:"SYNA"},
  {plugin:PLUG2,symbol:"SYNB"}
 ]};
 const t=new Date(now).toISOString();
 const observation={schema:"HARPOON_RUNTIME_OBSERVATION_1",
  asof:t,status:"OBSERVATION_CAPTURED",
  execution_allowed:false,liveApproved:false,selected:[],
  observations:[{id:PLUG1+"|SYNA",features:[1,2,3,4,5,6,7,8],
   known_at:t,asof:t}],
  rejected:{[PLUG2+"|SYNB"]:"BAR_SOURCE_NOT_READY"}
 };
 return {input,observation,barStart:F.BARS[0],
  universe:["SYNA","SYNB"],generatorHash:F.SOURCE_HASH};
}
test("C27 original observation adapter requires accepted+rejected EXACT requested coverage",()=>{
 const x=sample(),out=Q.fromOriginalObservation(x.input,x.observation,x);
 A.equal(out.requested,2);
 A.equal(out.withFeatures,1);A.equal(out.refused,1);
 A.deepEqual(out.opportunityCoverage.enumeratedIds,
  [PLUG1+"|SYNA",PLUG2+"|SYNB"]);
 A.equal(out.opportunityCoverage.outcomes[0].outcome,"OBSERVED_ONLY");
 A.equal(out.opportunityCoverage.outcomes[1].outcome,"REFUSED");
 A.equal(out.originalQuanObservationScopeVerified,true);
 A.equal(out.sourceEnumeratorExhaustiveOfAllPossibleMarketOpportunities,false);
});
test("C27 observation adapter integrates with full source prebar state and no physical trades",()=>{
 const x=sample(),o=Q.fromOriginalObservation(x.input,x.observation,x);
 const snap=F.sample().frames[0];
 snap.opportunityCoverage=o.opportunityCoverage;
 const r=S.validatePrebar(snap,{...F.manifest(),policyIds:S.POLICY_IDS});
 A.equal(r.candidateOutcomes.OBSERVED_ONLY,1);
 A.equal(r.candidateOutcomes.REFUSED,1);
 A.equal(r.positionCount,0);
 A.equal(r.sourceCandidateEnumeratorIndependentlyVerified,false);
});
test("C27 requested but neither observed nor rejected is a critical missing opportunity",()=>{
 const x=sample();delete x.observation.rejected[PLUG2+"|SYNB"];
 A.throws(()=>Q.fromOriginalObservation(x.input,x.observation,x),
  /C27O_ORIGINAL_OBSERVATION_CANDIDATE_OMISSION/);
});
test("C27 duplicated accepted and rejected source ID cannot claim two outcomes",()=>{
 const x=sample();x.observation.rejected[PLUG1+"|SYNA"]="INSUFFICIENT";
 A.throws(()=>Q.fromOriginalObservation(x.input,x.observation,x),
  /C27O_REJECTED_SOURCE_ID_REASON/);
});
test("C27 future knownAt from original runtime observation is prohibited",()=>{
 const x=sample();x.observation.observations[0].known_at=
  new Date(x.input.now+1000).toISOString();
 A.throws(()=>Q.fromOriginalObservation(x.input,x.observation,x),
  /C27O_FEATURE_PREBAR_KNOWN_AND_COMPLETE/);
});
test("C27 original observation never enables orders, model selection or forged policy",()=>{
 const x=sample();x.observation.execution_allowed=true;
 A.throws(()=>Q.fromOriginalObservation(x.input,x.observation,x),
  /C27O_READONLY_ORIGINAL_QUANT_OBSERVATION/);
 const y=sample();y.input.signals[0].plugin="RETRO_FAVORITE_SESSION";
 A.throws(()=>Q.fromOriginalObservation(y.input,y.observation,y),
  /C27O_ORIGINAL_SIGNAL_ENVELOPE/);
});
test("C27 original observation needs exact eight finite features, not placeholder",()=>{
 const x=sample();x.observation.observations[0].features=[1,2,3];
 A.throws(()=>Q.fromOriginalObservation(x.input,x.observation,x),
  /C27O_FEATURE_PREBAR_KNOWN_AND_COMPLETE/);
});
test("C27 rejection must specify reason, no silent no-fill count",()=>{
 const x=sample();x.observation.rejected[PLUG2+"|SYNB"]="";
 A.throws(()=>Q.fromOriginalObservation(x.input,x.observation,x),
  /C27O_REJECTED_SOURCE_ID_REASON/);
});
