"use strict";
/** C27 source engineering tests: no broker, no economic account nor future bar. */
const test=require("node:test"),A=require("node:assert/strict");
const S=require("../runtime30/fwn9_c27_prebar_state.cjs");
const J=require("../runtime30/fwn9_c27_prebar_journal.cjs");
const F=require("./fwn9_c27_test_fixture.cjs");
const manifest=()=>({...F.manifest(),policyIds:[...S.POLICY_IDS]});
function validated(i){return S.validatePrebar(F.sample().frames[i],manifest());}
function mutate(index,transform){
 const x=structuredClone(F.sample().frames[index]);
 transform(x);return x;
}
test("C27 original source empty portfolio before first bar has complete zero state",()=>{
 const r=validated(0);
 A.equal(r.positionCount,0);A.equal(r.reservedPending,0);
 A.equal(r.newGeneratedOpportunityCount,0);
 A.equal(r.thisFrameDoesNotContainCurrentOHLC,true);
 A.equal(r.financialGO,false);
});
test("C27 second bar matches original OPENED reservation and one financed lot",()=>{
 const r=validated(1);
 A.equal(r.positionCount,1);A.equal(r.reservedOpened,1);
 A.equal(r.reservedRiskUsd,10);A.equal(r.markedEquityUsd,20000);
 A.equal(r.candidateOutcomes.RESERVED,1);
 A.equal(r.candidateOutcomes.REFUSED,1);
 A.equal(r.availableCashUsd,19600);
});
test("C27 source-native partial exit and persistent stop above entry is legal",()=>{
 const f=F.sample(),r=S.validatePrebar(f.frames[2],manifest());
 A.equal(r.positionCount,1);A.equal(r.markedEquityUsd,20010);
 A.equal(r.availableCashUsd,19710);
 A.equal(r.reservedOpened,1);
 A.equal(S.continuity(S.validatePrebar(f.frames[1],manifest()),r)
  .persistentStopAndTargetMonotonic,true);
});
test("C27 rejects future published bar facts instead of future-dating input",()=>{
 A.throws(()=>S.validatePrebar(mutate(0,x=>{x.currentOHLC={h:110,l:90};}),manifest()),
  /C27_CURRENT_BAR_DATA_FORBIDDEN/);
 A.throws(()=>S.validatePrebar(mutate(0,x=>{x.lastPublicKnownAt=x.barStart+1;}),manifest()),
  /C27_NO_POSTBAR_INFORMATION/);
});
test("C27 late source OPENED reservation receipt cannot appear before bar",()=>{
 A.throws(()=>S.validatePrebar(mutate(1,x=>{
  x.sourceReservationBook.reservations[0].observations[0].knownAt=x.barStart+1;
 }),manifest()),/C27_RESERVATION_FUTURE_RECEIPT/);
});
test("C27 source reservation decision itself cannot be injected after bar",()=>{
 A.throws(()=>S.validatePrebar(mutate(1,x=>{
  x.sourceReservationBook.reservations[0].decisionAt=x.barStart+1;
 }),manifest()),/C27_RESERVATION_FROM_FUTURE/);
});
test("C27 cannot silently omit a source-open position",()=>{
 A.throws(()=>S.validatePrebar(mutate(1,x=>{x.positions=[];}),manifest()),
  /C27_OPEN_RESERVATION_MISSING_POSITION/);
});
test("C27 quantity cannot exceed last source reported OPENED remaining",()=>{
 A.throws(()=>S.validatePrebar(mutate(1,x=>{x.positions[0].quantity=5;}),manifest()),
  /C27_POSITION_NOT_SOURCE_OPEN_REMAINING/);
});
test("C27 stop or TP observed after bar is prohibited",()=>{
 A.throws(()=>S.validatePrebar(mutate(1,x=>{
  x.positions[0].stop.knownAt=x.barStart+1;
 }),manifest()),/C27_STOP_NOT_KNOWN_PREBAR/);
 A.throws(()=>S.validatePrebar(mutate(1,x=>{
  x.positions[0].targets[0].knownAt=x.barStart+1;
 }),manifest()),/C27_TARGET_KNOWN_PAST_AND_INTEGER/);
});
test("C27 pending stop effective already now must have been promoted",()=>{
 A.throws(()=>S.validatePrebar(mutate(2,x=>{
  x.positions[0].pendingStop.effectiveAt=x.barStart;
 }),manifest()),/C27_PENDING_STOP_ALREADY_EFFECTIVE_OR_FUTURE_KNOWN/);
});
test("C27 pending stop cannot be future-created but valid in earlier record",()=>{
 A.throws(()=>S.validatePrebar(mutate(2,x=>{
  x.positions[0].pendingStop.knownAt=x.barStart+1;
 }),manifest()),/C27_PENDING_STOP_ALREADY_EFFECTIVE_OR_FUTURE_KNOWN/);
});
test("C27 fixed max elapsed holding <=72h is enforced",()=>{
 A.throws(()=>S.validatePrebar(mutate(1,x=>{
  x.positions[0].deadlineAt=x.positions[0].entryAt+72*3600000+1;
 }),manifest()),/C27_HOLDING_EXCEEDS_72H/);
});
test("C27 TP2 below long entry and target allocation > shares reject",()=>{
 A.throws(()=>S.validatePrebar(mutate(1,x=>{
  x.positions[0].targets[1].price=99;
 }),manifest()),/C27_LONG_TARGET_ABOVE_ENTRY/);
 A.throws(()=>S.validatePrebar(mutate(1,x=>{
  x.positions[0].targets[1].quantity=5;
 }),manifest()),/C27_TARGET_OVERALLOCATED/);
});
test("C27 missing generated refusal or unaccounted candidate fails closed",()=>{
 A.throws(()=>S.validatePrebar(mutate(1,x=>{
  x.opportunityCoverage.outcomes.pop();
 }),manifest()),/C27_CANDIDATE_SOURCE_LIST/);
 A.throws(()=>S.validatePrebar(mutate(1,x=>{
  x.opportunityCoverage.outcomes[1].reason="";
 }),manifest()),/C27_REFUSAL_REASON_MISSING/);
});
test("C27 source candidate enumeration cannot duplicate or include future decision",()=>{
 A.throws(()=>S.validatePrebar(mutate(1,x=>{
  x.opportunityCoverage.enumeratedIds[1]="R1";
 }),manifest()),/C27_DUPLICATE_ENUMERATED_ID/);
 A.throws(()=>S.validatePrebar(mutate(1,x=>{
  x.opportunityCoverage.outcomes[1].knownAt=x.barStart+1;
 }),manifest()),/C27_OPPORTUNITY_CLOCK_POLICY/);
});
test("C27 admitted signal must bind real original reservation ID, no ghost",()=>{
 A.throws(()=>S.validatePrebar(mutate(1,x=>{
  x.opportunityCoverage.enumeratedIds[0]="GHOST";
  x.opportunityCoverage.outcomes[0].id="GHOST";
 }),manifest()),/C27_RESERVED_MISSING_SOURCE_RESERVATION/);
});
test("C27 refuted NO_FILL without original IOC receipt cannot be invented",()=>{
 A.throws(()=>S.validatePrebar(mutate(1,x=>{
  x.opportunityCoverage.outcomes[1].outcome="NO_FILL";
  x.opportunityCoverage.outcomes[1].reason="IOC_NO_FILL";
 }),manifest()),/C27_NO_FILL_NOT_SOURCE_RECEIPTED/);
});
test("C27 physical cash plus marked inventory must match NAV",()=>{
 A.throws(()=>S.validatePrebar(mutate(1,x=>{
  x.physicalBook.equityUsd+=1;
 }),manifest()),/C27_PHYSICAL_EQUITY_NOT_CASH_PLUS_MARKS/);
});
test("C27 pending reservations reduce funded available cash, not opened twice",()=>{
 const x=F.sample().frames[1];
 A.equal(S.validatePrebar(x,manifest()).availableCashUsd,19600);
 A.throws(()=>S.validatePrebar(mutate(1,y=>{
  y.physicalBook.availableCashUsd=19000;
 }),manifest()),/C27_AVAILABLE_CASH_VS_PENDING_RESERVATIONS/);
});
test("C27 opening position without 72h receipt cannot be treated as closed",()=>{
 const x=mutate(1,y=>{
  y.sourceReservationBook.reservations[0].observations.push({
   id:"R1",kind:"CLOSED",at:y.barStart-500,
   knownAt:y.barStart-200,remainingQuantity:0,pendingQuantity:0});
 });
 A.throws(()=>S.validatePrebar(x,manifest()),
  /C27_POSITION_NOT_SOURCE_OPEN_REMAINING|C27_OPEN_RESERVATION_MISSING_POSITION/);
});
test("C27 continuity rejects retroactive rewrite of original reservation decisions",()=>{
 const f=F.sample(),a=S.validatePrebar(f.frames[1],manifest());
 const b=mutate(2,x=>{x.sourceReservationBook.reservations[0].notionalUsd=395;});
 const c=S.validatePrebar(b,manifest());
 A.throws(()=>S.continuity(a,c),/C27_RESERVATION_HISTORY_REWRITTEN/);
});
test("C27 continuity rejects deleting a signed previously reported OPENED receipt",()=>{
 const f=F.sample(),a=S.validatePrebar(f.frames[1],manifest());
 const b=mutate(2,x=>{
  x.sourceReservationBook.reservations[0].observations[0].at--;
 });
 const c=S.validatePrebar(b,manifest());
 A.throws(()=>S.continuity(a,c),/C27_OBSERVED_RECEIPT_RESTATED/);
});
test("C27 continuity rejects undoing target completion and lowering protective stop",()=>{
 const f=F.sample(),a=S.validatePrebar(f.frames[2],manifest());
 const next=structuredClone(f.frames[2]);next.barIndex=3;next.barStart=F.BARS[2]+300000;
 next.capturedAt=next.barStart-1000;next.lastPublicKnownAt=next.capturedAt;
 const m={...manifest(),expectedBars:[...F.BARS,next.barStart]};
 next.positions[0].pendingStop=null;
 next.positions[0].stop={price:102,knownAt:F.BARS[1]+110000};
 next.positions[0].targets[0].done=false;
 let c=S.validatePrebar(next,m);
 A.throws(()=>S.continuity(a,c),/C27_TARGET_CHANGED_OR_UNDONE/);
 next.positions[0].targets[0].done=true;
 next.positions[0].stop.price=90;
 c=S.validatePrebar(next,m);
 A.throws(()=>S.continuity(a,c),/C27_LONG_STOP_LOOSENED_OR_CLOCK_REGRESSION/);
});
test("C27 local source SHA only commits content, cannot authenticate broker",()=>{
 const a=validated(1);
 A.match(a.sourceBookHash,/^[a-f0-9]{64}$/);
 A.equal(a.sourceProviderTimestampCryptographicallyAuthenticated,false);
 A.equal(a.sourceCandidateEnumeratorIndependentlyVerified,false);
 A.equal(a.financialGO,false);
});
test("C27 strict policy ID gate disallows invented variants after viewing outcomes",()=>{
 A.throws(()=>S.validatePrebar(mutate(1,x=>{
  x.opportunityCoverage.outcomes[0].policyId="RETRO_OPTIMAL_UTC_08_16";
 }),manifest()),/C27_OPPORTUNITY_CLOCK_POLICY/);
});

test("C27 PROSPECTIVE source receipt after capture but before bar is future information",()=>{
 const x=mutate(1,y=>{
  y.mode="PROSPECTIVE_LOCAL_CAPTURE";y.capturedAt=y.barStart-10000;
  y.lastPublicKnownAt=y.capturedAt;y.physicalBook.knownAt=y.capturedAt;
  y.sourceReservationBook.reservations[0].observations[0].knownAt=y.barStart-5000;
 });
 const m={...manifest(),mode:"PROSPECTIVE_LOCAL_CAPTURE"};
 A.throws(()=>S.validatePrebar(x,m),/C27_RESERVATION_FUTURE_RECEIPT/);
});
test("C27 PROSPECTIVE stop revision after capture is unusable even before next open",()=>{
 const x=mutate(1,y=>{
  y.mode="PROSPECTIVE_LOCAL_CAPTURE";y.capturedAt=y.barStart-10000;
  y.lastPublicKnownAt=y.capturedAt;y.physicalBook.knownAt=y.capturedAt;
  y.positions[0].stop.knownAt=y.barStart-5000;
 });
 A.throws(()=>S.validatePrebar(x,{...manifest(),mode:"PROSPECTIVE_LOCAL_CAPTURE"}),
  /C27_STOP_NOT_KNOWN_PREBAR/);
});
test("C27 PROSPECTIVE rejected candidate event after local seal cannot leak",()=>{
 const x=mutate(1,y=>{
  y.mode="PROSPECTIVE_LOCAL_CAPTURE";y.capturedAt=y.barStart-10000;
  y.lastPublicKnownAt=y.capturedAt;y.physicalBook.knownAt=y.capturedAt;
  y.opportunityCoverage.outcomes[1].knownAt=y.barStart-5000;
 });
 A.throws(()=>S.validatePrebar(x,{...manifest(),mode:"PROSPECTIVE_LOCAL_CAPTURE"}),
  /C27_OPPORTUNITY_CLOCK_POLICY/);
});

test("C27 unknown top/nested fields cannot smuggle future OHLC into prebar frame",()=>{
 A.throws(()=>S.validatePrebar(mutate(1,x=>{
  x.futureBarHigh=200;
 }),manifest()),/C27_UNDECLARED_PREBAR_FIELD/);
 A.throws(()=>S.validatePrebar(mutate(1,x=>{
  x.positions[0].barHigh=200;
 }),manifest()),/C27_UNDECLARED_POSITION_FIELD/);
 A.throws(()=>S.validatePrebar(mutate(1,x=>{
  x.positions[0].stop.next_bar_close=101;
 }),manifest()),/C27_UNDECLARED_STOP_FIELD/);
});

test("C27 each original funded IOC reservation needs an ex-ante capacity receipt",()=>{
 A.throws(()=>S.validatePrebar(mutate(1,x=>{
  x.admissionDecisions=[];
 }),manifest()),/C27_COMPLETE_SOURCE_ADMISSION_CAPACITY_PROOF/);
});
test("C27 original decision 12pct gross/0.25pct risk and physical cash are admission-only caps",()=>{
 A.throws(()=>S.validatePrebar(mutate(1,x=>{
  x.admissionDecisions[0].equityAtDecisionUsd=1000;
  x.admissionDecisions[0].cashAvailableAtDecisionUsd=1000;
 }),manifest()),/C27_ORIGINAL_DECISION_RISK_GROSS_CASH_CAP/);
 A.throws(()=>S.validatePrebar(mutate(1,x=>{
  x.admissionDecisions[0].cashAvailableAtDecisionUsd=100;
 }),manifest()),/C27_ORIGINAL_DECISION_RISK_GROSS_CASH_CAP/);
});
test("C27 cannot justify capital with equity known after reservation decision",()=>{
 A.throws(()=>S.validatePrebar(mutate(1,x=>{
  x.admissionDecisions[0].knownAt=x.admissionDecisions[0].decisionAt+1;
 }),manifest()),/C27_ADMISSION_CAPACITY_NOT_KNOWN_AT_DECISION/);
});
test("C27 cannot silently revise the previously certified decision equity on next bar",()=>{
 const f=F.sample(),before=S.validatePrebar(f.frames[1],manifest());
 const x=mutate(2,y=>{y.admissionDecisions[0].equityAtDecisionUsd=19500;
  y.admissionDecisions[0].cashAvailableAtDecisionUsd=19500;});
 const after=S.validatePrebar(x,manifest());
 A.throws(()=>S.continuity(before,after),
  /C27_ADMISSION_EXANTE_CAPACITY_RESTATED/);
});
