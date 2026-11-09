"use strict";
/* FWN9 P9K: deterministic engineering matrix, no M9 market accounts. */
const test=require("node:test");
const A=require("node:assert/strict");
const {performance}=require("node:perf_hooks");
const {FaultMatrix,LIMITS}=require("../runtime30/fwn9_p9k_fault_matrix.cjs");
const T=Date.UTC(2025,0,3,14,30),H=3600000,DAY=86400000;
const f=()=>new FaultMatrix();
const event=(id,type,t,rest={})=>({id,type,effectiveAt:t,knownAt:t,...rest});
function base(d=f()){
 d.apply(event("q1","QUOTE",T,{symbol:"SYNA",price:100}));
 d.apply(event("q2","QUOTE",T+10,{symbol:"SYNB",price:100}));
 return d;
}
const admit=(id,cell,symbol,time,quantity=10,price=100.1,stopDistance=.25)=>
 event("ad"+id,"ADMIT",time,{orderId:id,cell,symbol,quantity,
 limitPrice:price,stopDistance});
const fill=(id,time,quantity,price=100.05,at=time)=>
 event("fill"+id+time,"ENTRY_FILL",time,{orderId:id,quantity,price,effectiveAt:at});
const exit=(id,time,quantity,price=101,at=time)=>
 event("exit"+id+time,"EXIT_FILL",time,{orderId:id,quantity,price,effectiveAt:at});
test("P9K L0: immutable initial capital and original admission risk contract",()=>{
 const d=f();A.equal(d.snapshot().equityUsd,20000);
 A.equal(LIMITS.gross,.12);A.equal(LIMITS.openRisk,.0025);
 A.equal(LIMITS.loss,.02);A.equal(LIMITS.drawdown,.08);
 A.equal(LIMITS.holdMs,72*H);
});
test("P9K L1: physical cash principal, fees and independent equity identity",()=>{
 const d=base();d.apply(admit("a","EQUITY","SYNA",T+1000));
 d.apply(fill("a",T+2000,10));
 const s=d.snapshot();
 A(Math.abs(s.physicalCashUsd-(19999-10*100.05-.05))<1e-7);
 A(Math.abs(s.equityUsd-(s.physicalCashUsd+s.inventoryUsd-s.exitFeeUsd))<1e-7);
 A.equal(s.positions,1);
 A(d.audit().feeReconciliation);
});
test("P9K L2: cross-cell shared exposure cap at reservation, not a continuous cap",()=>{
 const d=base();
 A.equal(d.apply(admit("a","EQUITY","SYNA",T+1000,12)).status,"RESERVED");
 const refusal=d.apply(admit("b","CRYPTO","SYNB",T+1100,12));
 A.equal(refusal.status,"REFUSED");
 A.equal(refusal.reason,"PORTFOLIO_NOTIONAL_CAPACITY");
 A.equal(d.snapshot().reservationCount,1);
 A.equal(d.apply(admit("c","CRYPTO","SYNB",T+1200,11)).status,"RESERVED");
 A.equal(d.snapshot().reservationCount,2);
});
test("P9K L2: same symbol reserved by another order cannot double commit",()=>{
 const d=base();d.apply(admit("a","EQUITY","SYNA",T+1000));
 const x=d.apply(admit("dup","EQUITY","SYNA",T+1100));
 A.equal(x.status,"REFUSED");A.equal(x.reason,"SYMBOL_RESERVED");
});
test("P9K L3: partial IOC entry debits cash and retains original pending commitment",()=>{
 const d=base();d.apply(admit("a","EQUITY","SYNA",T+1000));
 d.apply(fill("a",T+2000,4));
 const s=d.snapshot(),book=d.state.book.reservations[0];
 A.equal(book.quantity,10);A.equal(s.positions,1);
 A.equal(d.state.orders.a.pending,6);A.equal(s.reservationCount,1);
 A.equal(book.observations[0].kind,"OPENED");
 A.equal(book.observations[0].remainingQuantity,4);
 A.equal(book.observations[0].pendingQuantity,6);
});
test("P9K L3: cancel intent never frees original commitment until receipt",()=>{
 const d=base();d.apply(admit("a","EQUITY","SYNA",T+1000));
 const old=d.snapshot().reservationCount;
 const req=d.apply(event("cx","CANCEL_REQUEST",T+1500,{orderId:"a"}));
 A.equal(req.reservationReleased,false);
 A.equal(d.snapshot().reservationCount,old);
 const receipt=d.apply(event("expire","ENTRY_EXPIRE",T+1700,{orderId:"a"}));
 A.equal(receipt.status,"REJECTED");A.equal(d.snapshot().reservationCount,0);
 A.equal(d.snapshot().positions,0);
});
test("P9K L3: reject residual after partial fill retains opened reservation",()=>{
 const d=base();d.apply(admit("a","EQUITY","SYNA",T+1000));
 d.apply(fill("a",T+2000,4));
 const result=d.apply(event("rej","ENTRY_REJECT",T+3000,{orderId:"a"}));
 A.equal(result.status,"PARTIAL_LOCKED");A.equal(result.reservationReleased,false);
 A.equal(d.snapshot().reservationCount,1);
 A.equal(d.state.book.reservations[0].observations.at(-1).pendingQuantity,0);
});
test("P9K L3: full IOC no-fill produces no shares and releases only at knownAt",()=>{
 const d=base();d.apply(admit("a","EQUITY","SYNA",T+1000));
 const e=event("nf","ENTRY_NO_FILL",T+2500,{orderId:"a"});
 e.effectiveAt=T+2000; const out=d.apply(e);
 A.equal(out.status,"NO_FILL");A.equal(out.inventory,0);
 A.equal(out.reservationCount,0);A.equal(d.audit().feeReconciliation,true);
 const original=d.state.book.reservations[0];
 A.equal(original.observations[0].knownAt,T+2500);
});
test("P9K L4: outage halts new admission and prevents fictitious fill, recovery retains state",()=>{
 const d=base();d.apply(admit("a","EQUITY","SYNA",T+1000));
 A.equal(d.apply(event("off","OUTAGE",T+1100)).status,"HALTED");
 const before=JSON.stringify(d.state);
 A.throws(()=>d.apply(admit("b","CRYPTO","SYNB",T+1200)),/P9K_OUTAGE_HALTS_ADMISSION/);
 A.throws(()=>d.apply(fill("a",T+1300,10)),/P9K_OUTAGE_RECEIPT_NOT_YET_OBSERVED/);
 A.equal(JSON.stringify(d.state),before);
 A.equal(d.apply(event("on","RECOVER",T+1400)).status,"RECOVERED");
 A.equal(d.snapshot().reservationCount,1);
});
test("P9K L4: any delayed receipt from the future fails closed",()=>{
 const d=base();d.apply(admit("a","EQUITY","SYNA",T+1000));
 const past=JSON.stringify(d.state);
 const bad=fill("a",T+2000,10,100.05,T+3000);
 A.throws(()=>d.apply(bad),/P9K_INVALID_KNOWNAT/);
 A.equal(JSON.stringify(d.state),past);
});
test("P9K L4: event replay idempotent; conflicting replay leaves no mutation",()=>{
 const d=base(),e=admit("a","EQUITY","SYNA",T+1000);
 d.apply(e);const n=d.state.log.length;
 A.equal(d.apply(e).status,"IDEMPOTENT");
 A.equal(d.state.log.length,n);
 const bad={...e,quantity:11};
 A.throws(()=>d.apply(bad),/P9K_CONFLICTING_EVENT_ID/);
 A.equal(d.state.log.length,n);
});
test("P9K L5: entry IOC price ceiling enforces impact; no fake fill",()=>{
 const d=base();d.apply(admit("a","EQUITY","SYNA",T+1000));
 const old=JSON.stringify(d.state);
 A.throws(()=>d.apply(fill("a",T+2000,10,101)),/P9K_ENTRY_PRICE_EXCEEDS_IOC_CEILING/);
 A.equal(JSON.stringify(d.state),old);
});
test("P9K L5: impact is a measured shortfall, not a fabricated market fill",()=>{
 const d=base();d.apply(admit("a","EQUITY","SYNA",T+1000));
 d.apply(fill("a",T+2000,10,100.05));
 A(Math.abs(d.snapshot().impactShortfallUsd-.5)<1e-7);
});
test("P9K L6: partial exit maintains original reservation until terminal close",()=>{
 const d=base();d.apply(admit("a","EQUITY","SYNA",T+1000));
 d.apply(fill("a",T+2000,10));
 const r=exit("a",T+4000,4);
 d.apply(r);
 A.equal(d.state.book.reservations[0].quantity,10);
 A.equal(d.snapshot().reservationCount,1);
 A.equal(d.state.positions.a.remaining,6);
 const result=d.apply(exit("a",T+5000,6));
 A.equal(result.status,"CLOSED");
 A.equal(d.snapshot().reservationCount,0);
 A.equal(d.snapshot().positions,0);
 A(d.audit().feeReconciliation);
});
test("P9K L6: overdraw sell rejected transactionally",()=>{
 const d=base();d.apply(admit("a","EQUITY","SYNA",T+1000));
 d.apply(fill("a",T+2000,10));
 const old=JSON.stringify(d.state);
 A.throws(()=>d.apply(exit("a",T+4000,11)),/P9K_EXIT_OVERDRAW/);
 A.equal(JSON.stringify(d.state),old);
});
test("P9K L6: original risk cash and fee accounting reconcile after closed campaign",()=>{
 const d=base();d.apply(admit("a","EQUITY","SYNA",T+1000));
 d.apply(fill("a",T+2000,10,100.05));
 d.apply(exit("a",T+4000,10,101));
 const s=d.snapshot();
 const fees=10*.005*2;
 const expected=20000-1+10*(101-100.05)-fees;
 A(Math.abs(s.equityUsd-expected)<1e-6);
 A(Math.abs(s.physicalCashUsd-expected)<1e-6);
 A(Math.abs(s.feesPaidUsd-fees)<1e-7);
});
test("P9K L7: maximum hold 72h, late exit cannot silently be fabricated",()=>{
 const d=base();d.apply(admit("a","EQUITY","SYNA",T+1000));
 d.apply(fill("a",T+2000,10));
 const old=JSON.stringify(d.state);
 A.throws(()=>d.apply(exit("a",T+2000+73*H,10,101)),/P9K_HOLD_72H_BREACH/);
 A.equal(JSON.stringify(d.state),old);
 d.apply(event("late_quote","QUOTE",T+2000+73*H,{symbol:"SYNA",price:100}));
 A.throws(()=>d.audit(),/P9K_INVENTORY_OR_HOLD_UNRESOLVED/);
});
test("P9K L7: daily loss gate prohibits another asset without asserting continuous gross cap",()=>{
 const d=base();d.apply(admit("a","EQUITY","SYNA",T+1000,20));
 d.apply(fill("a",T+2000,20));
 d.apply(event("down","QUOTE",T+3000,{symbol:"SYNA",price:70}));
 A.throws(()=>d.apply(admit("b","CRYPTO","SYNB",T+4000)),
   /P9K_DAILY_LOSS_ADMISSION/);
});
test("P9K L7: market appreciation may pass continuous 12% inventory exposure",()=>{
 const d=base();d.apply(admit("a","EQUITY","SYNA",T+1000,12));
 d.apply(fill("a",T+2000,12));
 d.apply(event("gap","QUOTE",T+3000,{symbol:"SYNA",price:1000}));
 A(d.snapshot().currentExposureFraction>.12);
 A.equal(d.audit().n9sEligible,false);
});
test("P9K L8: new calendar days and weekends debit fees without hidden resets",()=>{
 const d=base();
 d.apply(event("day2","QUOTE",T+3*DAY,{symbol:"SYNA",price:100}));
 A.equal(d.snapshot().externalCostsUsd,4);
 A.equal(d.snapshot().equityUsd,19996);
});
test("P9K L8: common portfolio risk across cells and no fabricated promotion",()=>{
 const d=base();
 d.apply(admit("a","EQUITY","SYNA",T+1000,10));
 d.apply(admit("b","CRYPTO","SYNB",T+1100,10));
 const x=d.audit();A.equal(x.sharedPortfolio,true);
 A.equal(x.allNativeM9PathsProven,false);
 A.equal(x.fullPartialRejectOutageImpactProvedUnderM9,false);
 A.equal(x.multicellEngineParityProvedUnderM9,false);
 A.equal(x.n9sEligible,false);
});
test("P9K L8: fail-closed corrupted physical cash detected at audit",()=>{
 const d=base();d.apply(admit("a","EQUITY","SYNA",T+1000));
 d.state.cash=-100;
 A.throws(()=>d.audit(),/P9K_NONPOSITIVE_EQUITY|P9K_UNFUNDED_CASH_AUDIT|P9K_NONPOSITIVE_EQUITY/);
});
test("P9K L3: overfilled entry and zero shares fail before cash mutation",()=>{
 const d=base();d.apply(admit("a","EQUITY","SYNA",T+1000));
 const prev=JSON.stringify(d.state);
 A.throws(()=>d.apply(fill("a",T+2000,11)),/P9K_ENTRY_OVERFILL_OR_NONPOSITIVE/);
 A.equal(JSON.stringify(d.state),prev);
});
test("P9K L4: cannot consume an out-of-order known receipt",()=>{
 const d=base();d.apply(admit("a","EQUITY","SYNA",T+1000));
 d.apply(event("new_quote","QUOTE",T+3000,{symbol:"SYNA",price:100}));
 const previous=JSON.stringify(d.state);
 A.throws(()=>d.apply(fill("a",T+2000,2)),/P9K_RECEIPT_CLOCK_REGRESSION/);
 A.equal(JSON.stringify(d.state),previous);
});
test("P9K L5: unsupported short sell and negative entry prices rejected",()=>{
 const d=base();d.apply(admit("a","EQUITY","SYNA",T+1000));
 A.throws(()=>d.apply(exit("a",T+3000,1,-10)),/P9K_INVALID_EXIT_FILL/);
 A.throws(()=>d.apply(fill("a",T+4000,1,-10)),/P9K_ENTRY_PRICE_EXCEEDS_IOC_CEILING/);
});
test("P9K L7: stress calendar fee world remains 2 USD per day",()=>{
 const d=base(new FaultMatrix({calendarCostPerDayUsd:2}));
 A.equal(d.snapshot().externalCostsUsd,2);
 d.apply(event("stressday","QUOTE",T+DAY,{symbol:"SYNA",price:100}));
 A.equal(d.snapshot().externalCostsUsd,4);
});
function auditFixture(){
 const d=base();
 d.apply(admit("a","EQUITY","SYNA",T+1000,10));
 d.apply(admit("b","CRYPTO","SYNB",T+1100,10));
 d.apply(fill("a",T+2000,4,100.05));
 d.apply(event("stop_pending","ENTRY_REJECT",T+2100,{orderId:"a"}));
 d.apply(event("no_fill_b","ENTRY_NO_FILL",T+2300,{orderId:"b"}));
 d.apply(exit("a",T+4000,4,101));
 return d;
}
if(process.argv.includes("--emit-audit")){
 const d=auditFixture(),s=d.audit();
 console.log("P9K_AUDIT="+JSON.stringify({snapshot:s,orders:d.state.orders,
   book:d.state.book,log:d.state.log,calendarCostPerDayUsd:1,capitalUsd:20000,
   perSideFeeUsd:.005,sourceFrozenLimits:LIMITS,
   classification:"DETERMINISTIC_ENGINEERING_ONLY"}));
}
if(process.argv.includes("--bench")){
 const t=performance.now();
 for(let k=0;k<80;k++)auditFixture().audit();
 console.log("P9K_80_FULL_FAULT_CYCLES_MS="+(performance.now()-t));
}
