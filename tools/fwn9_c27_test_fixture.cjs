"use strict";
/** C27 fixture: THREE existing-style bar boundaries, no trading engine,
 * no market RNG, no new signal or economic account; only source R operations.
 */
const R=require("../runtime30/ultimate_reservations.js");
const S=require("../runtime30/fwn9_c27_prebar_state.cjs");
const DAY=Date.UTC(2026,10,6,14,30);
const BARS=[DAY,DAY+300000,DAY+600000];
const SOURCE_HASH="9d4afa402d2b70791f175e79219495f9bbbe25eb3cd0b7e9212cef6bccbd68ab";
function manifest({mode="ENGINEERING_REPLAY"}={}){
 return {runId:"C27_SYNTHETIC_ENGINEERING_ONLY",mode,
  expectedBars:[...BARS],generatorHash:SOURCE_HASH};
}
function snap(barIndex,book,positions=[],candidateRows=[],cash=20000,
 equity=20000){
 const t=BARS[barIndex];
 return {schema:S.SCHEMA,runId:"C27_SYNTHETIC_ENGINEERING_ONLY",
  mode:"ENGINEERING_REPLAY",barStart:t,barIndex,
  capturedAt:t-1000,lastPublicKnownAt:t-1000,
  scope:{originalSource:"ORIGINAL_M9_NATIVE_SOURCE_READONLY",
   sourceInputsAuthenticatedExternally:false,
   allCandidatesIndependentlyAuthenticated:false},
  universe:["SYNA","SYNB"],
  sourceReservationBook:structuredClone(book),
  admissionDecisions:book.reservations.map(r=>({id:r.id,
   decisionAt:r.decisionAt,knownAt:r.decisionAt,
   equityAtDecisionUsd:20000,cashAvailableAtDecisionUsd:20000})),
  positions:structuredClone(positions),
  physicalBook:{knownAt:t-1000,physicalPnlOrigin:"SYNTHETIC_ENGINEERING_ONLY",
   cashUsd:cash,settledCashUsd:cash,unsettledCashUsd:0,
   extraCommittedCashUsd:0,equityUsd:equity,
   availableCashUsd:cash-book.reservations.filter(r=>
    r.observations.length===0).reduce((a,r)=>a+r.cashUsd,0)},
  opportunityCoverage:{generatorSourceHash:SOURCE_HASH,
   candidateCollectionCompleteDeclared:true,
   enumeratedIds:candidateRows.map(x=>x.id),
   outcomes:structuredClone(candidateRows)}
 };
}
function sample(){
 const b0=R.emptyFundedReservationBook();
 const before=snap(0,b0,[],[],20000,20000);
 const t=BARS[0],admissionAt=t+60000,entryAt=t+61000;
 const capacity={equity:20000,cashAvailableUsd:20000,
  riskFraction:.0025,openRiskFraction:.0025,grossFraction:.12,
  assetFraction:.12};
 const r={id:"R1",symbol:"SYNA",decisionAt:admissionAt,
  quantity:4,riskUsd:10,notionalUsd:400,cashUsd:400};
 const accepted=R.reserveFundedEntry(b0,r,capacity);
 if(accepted.status!=="RESERVED")throw Error("TEST_SOURCE_RESERVATION");
 const b1=R.recordFundedReservationObservation(accepted.book,{
  id:"R1",kind:"OPENED",at:entryAt,knownAt:entryAt+1000,
  remainingQuantity:4,pendingQuantity:0});
 const position=(qty,stop,done=false)=>({
  reservationId:"R1",symbol:"SYNA",quantity:qty,entryAt,entryPrice:100,
  positionKnownAt:entryAt+1000,deadlineAt:entryAt+72*3600000,
  stop:{price:stop,knownAt:done?BARS[1]+100000:entryAt+1000},
  pendingStop:done?{price:102,knownAt:BARS[1]+110000,
   effectiveAt:BARS[2]+300000}:null,
  lastMarkKnownAt:done?BARS[1]+150000:entryAt+2000,
  lastKnownMarkPrice:100,
  targets:[{id:"TP1",price:110,quantity:1,knownAt:entryAt+1000,done},
   {id:"TP2",price:120,quantity:1,knownAt:entryAt+1000,done:false}]
 });
 const admitted=[
  {id:"R1",policyId:"H22_OPENING_CONFIRMATION@RTH_OPEN_30",
   symbol:"SYNA",decisionAt:admissionAt,knownAt:admissionAt,
   outcome:"RESERVED",reason:null},
  {id:"REF1",policyId:"H22_OPENING_CONFIRMATION@RTH_OPEN_30",
   symbol:"SYNB",decisionAt:admissionAt+2000,
   knownAt:admissionAt+2000,outcome:"REFUSED",reason:"GROSS_RISK_CAP"}
 ];
 const second=snap(1,b1,[position(4,95)],admitted,19600,20000);
 const b2=R.recordFundedReservationObservation(b1,{
  id:"R1",kind:"OPENED",at:BARS[1]+100000,
  knownAt:BARS[1]+110000,remainingQuantity:3,pendingQuantity:0});
 const third=snap(2,b2,[position(3,101,true)],[],19710,20010);
 return {manifest:manifest(),frames:[before,second,third],
  sourceBooks:[b0,b1,b2]};
}
module.exports={BARS,SOURCE_HASH,manifest,sample,snap};
