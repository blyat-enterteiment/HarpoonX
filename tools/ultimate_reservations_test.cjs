"use strict";
// Synthetic software checks only. No optimizer, broker, fit or financial trial.
const test=require("node:test"),assert=require("node:assert/strict"),path=require("node:path");
const runtime=process.env.HARPOON_RESERVATIONS_TEST_MODULE||path.join(__dirname,"../runtime30/ultimate_reservations.js");
const {emptyFundedReservationBook,snapshotFundedReservations,reserveFundedEntry,recordFundedReservationObservation,FundedReservationError}=require(runtime);
const C={equity:20000,cashAvailableUsd:20000,riskFraction:.0025,openRiskFraction:.015,grossFraction:.5,assetFraction:.12};
function entry(i=0,changes={}){return {id:"S"+i,symbol:"ASSET"+i,decisionAt:1000,quantity:24,riskUsd:49.44,notionalUsd:2400,cashUsd:2400,...changes};}
function reserve(book,r=entry(),c=C){const result=reserveFundedEntry(book,r,c);assert.equal(result.status,"RESERVED");return result.book;}
function opened(changes={}){return {id:"S0",kind:"OPENED",at:2000,knownAt:2010,remainingQuantity:24,pendingQuantity:0,...changes};}
function closed(changes={}){return {id:"S0",kind:"CLOSED",at:5000,knownAt:5010,remainingQuantity:0,pendingQuantity:0,...changes};}

test("seven simultaneous pending entries cannot spend the same notional capacity",()=>{
  let book=emptyFundedReservationBook();const receipts=[];
  for(let i=0;i<7;i++){const r=reserveFundedEntry(book,entry(i),C);receipts.push(r);book=r.book;}
  assert.equal(receipts.filter(r=>r.status==="RESERVED").length,4);
  assert(receipts.slice(4).every(r=>r.reason==="PORTFOLIO_NOTIONAL_CAPACITY"));
  const s=snapshotFundedReservations(book,1000);
  assert.equal(s.pending,4);assert.equal(s.notionalUsd,9600);assert.equal(s.cashUsd,9600);
  assert(s.riskUsd<=C.equity*C.openRiskFraction);
});

test("the joint risk ceiling binds independently of available cash and notional",()=>{
  let book=emptyFundedReservationBook();let last;
  for(let i=0;i<7;i++){last=reserveFundedEntry(book,entry(i,{quantity:1,notionalUsd:100,cashUsd:100,riskUsd:50}),C);book=last.book;}
  assert.equal(last.status,"REFUSED");assert.equal(last.reason,"PORTFOLIO_RISK_CAPACITY");
  const s=snapshotFundedReservations(book,1000);assert.equal(s.riskUsd,300);assert.equal(s.cashUsd,600);
});

test("a pending symbol is busy before the first modeled fill",()=>{
  const book=reserve(emptyFundedReservationBook());
  const r=reserveFundedEntry(book,entry(1,{symbol:"ASSET0",decisionAt:1001}),C);
  assert.equal(r.status,"REFUSED");assert.equal(r.reason,"SYMBOL_RESERVED");
  assert.deepEqual(book,r.book);
});

test("release waits for the close to be known, not just its effective timestamp",()=>{
  let book=reserve(emptyFundedReservationBook());
  book=recordFundedReservationObservation(book,opened());
  book=recordFundedReservationObservation(book,closed());
  assert.equal(snapshotFundedReservations(book,2000).pending,1);
  assert.equal(snapshotFundedReservations(book,2010).opened,1);
  assert.equal(snapshotFundedReservations(book,5009).cashUsd,2400);
  assert.equal(snapshotFundedReservations(book,5010).cashUsd,0);
  const again=reserveFundedEntry(book,entry(1,{symbol:"ASSET0",decisionAt:5010}),C);
  assert.equal(again.status,"RESERVED");
});

test("partial observations retain the full approved budgets and residual order",()=>{
  let book=reserve(emptyFundedReservationBook());
  book=recordFundedReservationObservation(book,opened({remainingQuantity:6,pendingQuantity:18}));
  book=recordFundedReservationObservation(book,opened({at:3000,knownAt:3010,remainingQuantity:4,pendingQuantity:0}));
  const s=snapshotFundedReservations(book,3010);
  assert.equal(s.cashUsd,2400);assert.equal(s.notionalUsd,2400);assert.equal(s.riskUsd,49.44);
  assert.equal(s.reservations[0].observedRemainingQuantity,4);
  assert.throws(()=>recordFundedReservationObservation(book,closed({remainingQuantity:4})),/CLOSE_WITH_RESIDUAL_EXPOSURE/);
  assert.throws(()=>recordFundedReservationObservation(book,closed({pendingQuantity:1})),/CLOSE_WITH_RESIDUAL_EXPOSURE/);
});

test("future observations and future prices cannot alter a decision-time reservation",()=>{
  const b=reserve(emptyFundedReservationBook());
  const atDecision=snapshotFundedReservations(b,1000);
  let future=recordFundedReservationObservation(b,{...opened(),futureFillPrice:100000});
  future=recordFundedReservationObservation(future,{...closed(),futurePnlUsd:999999});
  assert.deepEqual(snapshotFundedReservations(future,1000),atDecision);
  const changed=reserveFundedEntry(emptyFundedReservationBook(),{...entry(),futurePrice:1},C);
  assert.deepEqual(changed.book,b);
  assert.equal(snapshotFundedReservations(future,999).cashUsd,0);
});

test("identical retries do not duplicate capacity and conflicting ids raise an incident",()=>{
  const empty=emptyFundedReservationBook(),book=reserve(empty);
  assert.equal(empty.reservations.length,0,"pure function must not mutate the prior state");
  const again=reserveFundedEntry(book,entry(),C);
  assert.equal(again.status,"UNCHANGED");assert.deepEqual(again.book,book);
  assert.throws(()=>reserveFundedEntry(book,entry(0,{riskUsd:48}),C),e=>e instanceof FundedReservationError&&e.code==="CONFLICTING_RESERVATION_ID"&&e.economicPnlUsd===null);
  assert.equal(book.reservations.length,1);assert.equal(book.reservations[0].riskUsd,49.44);
});

test("duplicate exposure observations are idempotent, conflicts preserve the original record",()=>{
  const reserved=reserve(emptyFundedReservationBook()),book=recordFundedReservationObservation(reserved,opened());
  assert.equal(reserved.reservations[0].observations.length,0);
  assert.deepEqual(recordFundedReservationObservation(book,opened()),book);
  assert.throws(()=>recordFundedReservationObservation(book,opened({remainingQuantity:23})),/CONFLICTING_RESERVATION_OBSERVATION/);
  assert.equal(book.reservations[0].observations[0].remainingQuantity,24);
});

test("unknown, regressing and post-close exposure cannot become a silent release",()=>{
  assert.throws(()=>recordFundedReservationObservation(emptyFundedReservationBook(),opened()),/OBSERVATION_WITHOUT_RESERVATION/);
  let book=reserve(emptyFundedReservationBook());
  assert.throws(()=>recordFundedReservationObservation(book,closed()),/CLOSE_WITHOUT_OBSERVED_OPEN/);
  book=recordFundedReservationObservation(book,opened());
  assert.throws(()=>recordFundedReservationObservation(book,opened({at:1999,knownAt:2020})),/RESERVATION_OBSERVATION_REGRESSION/);
  assert.throws(()=>recordFundedReservationObservation(book,closed({at:5000,knownAt:4999})),/INVALID_RESERVATION_OBSERVATION/);
  book=recordFundedReservationObservation(book,closed());
  assert.throws(()=>recordFundedReservationObservation(book,opened({at:6000,knownAt:6010,remainingQuantity:1})),e=>e.code==="EXPOSURE_REPORTED_AFTER_COMPLETE_CLOSE"&&e.details.observation.remainingQuantity===1&&e.economicPnlUsd===null);
});

test("cash fees, reduced equity and per-entry limits are enforced without loosening limits",()=>{
  const book=reserve(emptyFundedReservationBook(),entry(0,{cashUsd:2410}));
  let result=reserveFundedEntry(book,entry(1,{cashUsd:2410}),{...C,cashAvailableUsd:4819});
  assert.equal(result.reason,"PORTFOLIO_CASH_CAPACITY");
  result=reserveFundedEntry(book,entry(1),{...C,equity:10000});
  assert.equal(result.reason,"PER_ENTRY_RISK_CAPACITY");
  result=reserveFundedEntry(emptyFundedReservationBook(),entry(0,{riskUsd:50.01}),C);
  assert.equal(result.reason,"PER_ENTRY_RISK_CAPACITY");
  result=reserveFundedEntry(emptyFundedReservationBook(),entry(0,{notionalUsd:2401,cashUsd:2401}),C);
  assert.equal(result.reason,"PER_ENTRY_NOTIONAL_CAPACITY");
  assert.throws(()=>reserveFundedEntry(emptyFundedReservationBook(),entry(0,{cashUsd:NaN}),C),/INVALID_EX_ANTE_RESERVATION/);
});
