"use strict";
// FWN9 C13: bounded deterministic research fixtures, plus actual native replay.
const test=require("node:test");
const A=require("node:assert/strict");
const N=require("../runtime30/profit8_replay.js");
const K=require("../runtime30/ultimate_contracts.js");
const C=require("../runtime30/modulation11_stateful_campaign.cjs");
const W=require("../runtime30/fwn9_p9m_c13_local_coupling.cjs");
const H=3600000,DAY=86400000,BAR=300000;
const near=(a,b)=>A(Math.abs(a-b)<1e-6*Math.max(1,Math.abs(a),Math.abs(b)),
  String(a)+" != "+String(b));
function independentFixture(){
 const t=Date.UTC(2025,0,3,14,30),at=h=>t+h*H;
 const marks=[{symbol:"SYNA",at:t,price:100,first:true},
   {symbol:"SYNB",at:t,price:50,first:true},
   ...[["SYNA",10,103],["SYNB",50,45],["SYNA",73,101],
     ["SYNA",96,110],["SYNB",125,40]].map(([symbol,h,price])=>({
     symbol,at:at(h),barEnd:at(h)-1000,price}))];
 const fee=q=>q*.005;
 const admission=(id,symbol,quantity,h)=>({id,symbol,quantity,at:at(h)});
 const fill=(id,symbol,kind,quantity,h,px,knownDelay=0)=>({
   id,symbol,kind,quantity,at:at(h),knownAt:at(h+knownDelay),
   price:px,feeUsd:fee(quantity)});
 const native={
   mode:"NATIVE_OHLC",
   admissions:[admission("A1","SYNA",8,9),admission("A2","SYNB",4,85)],
   fills:[
    fill("A1","SYNA","ENTRY",8,11,103.03),
    fill("A1","SYNA","EXIT",2,15,105,1),
    fill("A1","SYNA","EXIT",6,77,98,6),
    fill("A2","SYNB","ENTRY",4,86,45.02),
    fill("A2","SYNB","EXIT",4,125,40,15)
   ],noFills:[]
 };
 const discrete={
   mode:"FIRST_CROSS",
   admissions:[admission("B1","SYNB",5,2),
     admission("B2","SYNA",9,80),admission("B3","SYNA",3,130)],
   fills:[
    fill("B1","SYNB","ENTRY",5,3,50.02),
    fill("B1","SYNB","EXIT",5,52,45,23),
    fill("B2","SYNA","ENTRY",9,81,101.03),
    fill("B2","SYNA","EXIT",9,116,110,1)
   ],
   noFills:[{id:"B3",at:at(131),knownAt:at(132)}]
 };
 return {startAt:t,endAt:at(150),marks,books:[native,discrete],
   initialCashUsd:20000,perSideFeeUsd:.005,calendarCostPerDayUsd:1};
}
const evaluate=()=>W.audit(independentFixture());
test("C13: two independent books different ids, assets, quantities and exits telescope through <=72h windows",()=>{
 const x=evaluate();
 A.equal(x.criteria.nativeAndFirstCrossIndependentAdmissions,true);
 A.equal(x.windows.length,3);
 A(x.windows.every(w=>w.endAt-w.startAt<=72*H));
 A(x.windows.every(w=>Math.abs(w.exactResidualUsd)<1e-6));
 A(x.windows.every(w=>w.closingDifferenceUsd<=w.openingDifferenceUsd+
   w.eventUpperAllowanceUsd+1e-6));
 A(x.totalFinanceEvents===9);
 A(x.endingDifferenceUsd<=x.totalLocalDifferenceUpperUsd+1e-6);
 A.equal(x.criteria.fullStochasticWeakPopulationBoundCertified,false);
});
test("C13: boundary positions carry to next window and cannot be reset",()=>{
 const x=evaluate();
 A.equal(x.windows[0].carryPositions[0].SYNA,6);
 A.equal(x.windows[0].carryPositions[1].SYNA,0);
 A(x.windows[1].exposureTermUsd!==0);
 near(x.windows[0].closingDifferenceUsd,x.windows[1].openingDifferenceUsd);
 near(x.windows[1].closingDifferenceUsd,x.windows[2].openingDifferenceUsd);
});
test("C13: effective fill cash and received-only conservative cash are distinct",()=>{
 const x=evaluate();
 A(x.windows[0].pendingReceiptCountAtEnd>=1);
 const B2=x.decisions.find(d=>d.id==="B2");
 const A2=x.decisions.find(d=>d.id==="A2");
 A(B2.conservativeReceivedCashUsd<20000);
 A(A2.conservativeReceivedCashUsd<20000);
 A(x.receiptsValidated===10);
});
test("C13: pending IOC no-fill never creates physical inventory",()=>{
 const f=independentFixture();
 const withNoFill=W.audit(f);
 A(withNoFill.decisions.some(d=>d.id==="B3"));
 A.equal(withNoFill.totalFinanceEvents,9);
 f.books[1].noFills[0].knownAt=f.books[1].noFills[0].at-1;
 A.throws(()=>W.audit(f),/C13_NOFILL_RECEIPT_OR_GHOST_FILL/);
});
test("C13: adversarial oversell and fee tamper rejected",()=>{
 const f=independentFixture();
 f.books[0].fills.find(e=>e.id==="A1"&&e.kind==="EXIT").quantity=9;
 A.throws(()=>W.audit(f),/C13_(RECEIPT_CAUSAL_COST_CONTRACT|NO_SHORT_OR_OVERSELL)/);
 const g=independentFixture();
 g.books[0].fills[0].feeUsd=0;
 A.throws(()=>W.audit(g),/C13_RECEIPT_CAUSAL_COST_CONTRACT/);
});
test("C13: late receipt outside terminal, long holding and negative economic cash fail closed",()=>{
 const f=independentFixture();
 f.books[0].fills.at(-1).knownAt=f.endAt+1;
 A.throws(()=>W.audit(f),/C13_RECEIPT_CAUSAL_COST_CONTRACT/);
 const g=independentFixture();
 g.books[0].fills[2].at=g.books[0].admissions[0].at+73*H;
 A.throws(()=>W.audit(g),/C13_HOLD_MAX_72H_FROM_SIGNAL/);
 const h=independentFixture();
 h.books[0].fills[0].price=100000;
 A.throws(()=>W.audit(h),/C13_NO_CASH_BORROWING/);
});
test("C13: time-published market prices are never claimed known before publication",()=>{
 const f=independentFixture();
 f.marks[2].barEnd=f.marks[2].at+1;
 A.throws(()=>W.audit(f),/C13_PUBLISHED_MARK_CONTRACT/);
 const g=independentFixture();
 g.books[0].admissions[0].quantity=10;
 A.throws(()=>W.audit(g),/C13_ENTRY_ORIGINAL_ADMISSION_QUANTITY/);
});
test("C13: WEAK nondegenerate Gaussian tails refute a universal deterministic local price ratio",()=>{
 const sigma=.00075*1.25*.9*Math.exp(-.7)*
   Math.sqrt(1-.45**2)/Math.sqrt(8);
 const p=W.gaussianNoFiniteUniformRange({
   finiteMultiplier:1.02,windowSteps:3*78*8,sigmaStep:sigma});
 A.equal(p.provenPositiveProbabilityForEveryFiniteMultiplier,true);
 A(p.numericalLowerProbabilityBound>0);
 A.equal(p.noDeterministicUniversalLocalPriceRatio,true);
 A.equal(p.boundOnNativeExpectedLogWealth,false);
 for(const ratio of [1.05,1.1]){
  const x=W.gaussianNoFiniteUniformRange({
   finiteMultiplier:ratio,windowSteps:3*78*8,sigmaStep:sigma});
  A(x.numericalLowerProbabilityBound>0);
 }
 A.throws(()=>W.gaussianNoFiniteUniformRange({
   finiteMultiplier:1,windowSteps:3,sigmaStep:sigma}),
   /C13_NONDEGENERATE_GAUSSIAN_SUPPORT/);
});
function actualNativeFixture(){
 const sessions=[0,3,4,5,6,7].map(k=>{
  const open=Date.UTC(2025,0,3,14,30)+k*DAY;
  return {date:new Date(open).toISOString().slice(0,10),open,close:open+78*BAR};
 });
 const series=["SYNA","SYNB"].map(symbol=>({symbol,root:symbol,tick:.01,
  pointValue:1,bars:sessions.flatMap(session=>Array.from({length:78},(_,i)=>({
    t:session.open+i*BAR,end:session.open+(i+1)*BAR,
    availableAt:session.open+(i+1)*BAR+1000,
    o:100,h:100.1,l:99.9,c:100,v:1000})))
 }));
 const data={schema:"HARPOON-ULTIMATE-DATA-1",kind:"ALPACA_PROXY",
   sessions,series,splitEvents:[],cashDividends:[],
   provenance:{execution:"MODELED_OHLCV",source:"SYNTHETIC_ENGINEERING_ONLY",
     feed:"FWN9_C13_NATIVE_TWO_ASSET_FIXTURE",
     files:[{name:"C13",sha256:"0".repeat(64)}]}};
 const protocol={...K.defaultProtocol("ALPACA_PROXY"),universe:["SYNA","SYNB"],
   costs:{spreadBps:2,slippageBps:2,perSideUsd:.005}};
 const signals=[["SYNA",60,2],["SYNB",90,5]].map(([symbol,m,distance])=>{
  const at=sessions[0].open+m*60000+1000;
  return {id:symbol+":"+m,symbol,hypothesis:"CLOSED_CHANNEL",
    direction:1,at,index:0,plannedEntryAt:N.planSignalEntryAt(at,sessions),
    stopDistance:distance,regime:.4,
    metadata:{roadmapHorizonHours:72,modulation9:{profile:"NATIVE72"}}};
 });
 const limits={...N.PROFIT8_REPLAY_LIMITS};
 const native=N.replayFundedPortfolio(signals,data,protocol,
  [{test:sessions,selected:"ALL:BASELINE"}],sessions,limits,{
   continuous:true,cashDividends:true,
   entryExecution:"IOC_LIMIT_COMMON_CAUSAL_30BPS",
   externalCostPerSessionUsd:0,calendarCostPerDayUsd:1,
   profit8:{mode:"NATIVE_MAX"},researchModulation:true});
 const solo=N.replayFundedPortfolio([signals[1]],data,protocol,
  [{test:sessions,selected:"ALL:BASELINE"}],sessions,limits,{
   continuous:true,cashDividends:true,
   entryExecution:"IOC_LIMIT_COMMON_CAUSAL_30BPS",
   externalCostPerSessionUsd:0,calendarCostPerDayUsd:1,
   profit8:{mode:"NATIVE_MAX"},researchModulation:true});
 const firstCross=solo.funded.map(t=>{
  const ser=series.find(s=>s.symbol===t.symbol);
  const steps=Object.fromEntries(ser.bars.map(b=>[b.t,
    [100.1,99.9,100,100,100,100,100,100]]));
  const sig=signals.find(s=>s.id===t.id);
  const result=C.compareNative({signal:sig,series:ser,data,protocol,
    quantity:t.quantity,substeps:steps});
  return {trade:t,discrete:result.discrete};
 });
 const convert=(mode,replay,discreteById=new Map())=>{
  const ad=replay.states.filter(s=>s.reservationStatus==="RESERVED")
    .map(s=>({id:s.opportunity.id,symbol:s.opportunity.symbol,
      at:s.opportunity.at,quantity:s.quantity}));
  const fills=[];
  for(const t of replay.funded){
    const eventEntry=t.inventoryEvents.find(e=>e.kind==="ENTRY");
    fills.push({id:t.id,symbol:t.symbol,kind:"ENTRY",quantity:t.quantity,
      at:eventEntry.at,knownAt:eventEntry.knownAt,
      price:eventEntry.filledPrice,feeUsd:eventEntry.feeUsd});
    const alt=discreteById.get(t.id);
    if(alt){
      for(const exit of alt.fills)fills.push({id:t.id,symbol:t.symbol,
        kind:"EXIT",quantity:exit.quantity,
        price:exit.price,at:exit.at,knownAt:exit.knownAt,
        feeUsd:exit.quantity*.005});
    }else for(const e of t.inventoryEvents.filter(e=>e.kind==="EXIT"))
      fills.push({id:t.id,symbol:t.symbol,kind:"EXIT",
        quantity:-e.quantityDelta,at:e.at,knownAt:e.knownAt,
        price:e.filledPrice,feeUsd:e.feeUsd});
  }
  return {mode,admissions:ad,fills,noFills:replay.modeledNoFills.map(n=>({
    id:n.signalId,at:n.plannedEntryAt,knownAt:n.resolutionAt}))};
 };
 const startAt=sessions[0].open,endAt=sessions.at(-1).close;
 const marks=[
  ...series.map(s=>({symbol:s.symbol,at:startAt,price:s.bars[0].o,first:true})),
  ...series.flatMap(s=>s.bars.filter(b=>b.availableAt<=endAt).map(b=>({
    symbol:s.symbol,at:b.availableAt,barEnd:b.end,price:b.c})))
 ];
 const audit=W.audit({startAt,endAt,marks,books:[
   convert("NATIVE_OHLC",native),
   convert("FIRST_CROSS",solo,new Map(firstCross.map(x=>[x.trade.id,x.discrete])))
 ]});
 return {audit,native,solo,firstCross,sessions};
}
test("C13: actual native funded replay book vs independently sized first-cross counterbook",()=>{
 const {audit,native,solo,firstCross,sessions}=actualNativeFixture();
 A(native.funded.length>=1&&solo.funded.length>=1);
 A(audit.windows.length>=2);
 A(audit.windows.every(w=>Math.abs(w.exactResidualUsd)<1e-6));
 near(audit.endingNativeUsd,native.curve.at(-1).equity_end_usd);
 const days=Math.floor(sessions.at(-1).close/DAY)-
   Math.floor(sessions[0].open/DAY)+1;
 near(audit.endingDiscreteUsd,20000-days+
   firstCross.reduce((n,x)=>n+x.discrete.netUsd,0));
 A.equal(audit.criteria.fullStochasticWeakPopulationBoundCertified,false);
});
if(process.argv.includes("--emit-evidence")){
 const f=independentFixture(),a=W.audit(f),n=actualNativeFixture();
 console.log("FWN9_C13_AUDIT="+JSON.stringify({
  engineering:{startAt:f.startAt,endAt:f.endAt,books:f.books,marks:f.marks},
  result:{endingNativeUsd:a.endingNativeUsd,
    endingDiscreteUsd:a.endingDiscreteUsd,endingDifferenceUsd:a.endingDifferenceUsd,
    upper:a.totalLocalDifferenceUpperUsd,windows:a.windows,
    pending:a.windows.map(x=>x.pendingReceiptCountAtEnd),
    bookDecisions:a.decisions},
  nativeIntegration:{fundedNative:n.native.funded.length,
    fundedCounterbook:n.solo.funded.length,
    equityNativeUsd:n.audit.endingNativeUsd,
    equityDiscreteUsd:n.audit.endingDiscreteUsd,
    checkedWindows:n.audit.windows.length},
  gaussian:W.gaussianNoFiniteUniformRange({
    finiteMultiplier:1.02,windowSteps:3*78*8,
    sigmaStep:.00075*1.25*.9*Math.exp(-.7)*
      Math.sqrt(1-.45**2)/Math.sqrt(8)})}));
}
if(process.argv.includes("--bench")){
 const start=process.hrtime.bigint();
 for(let i=0;i<1000;i++)evaluate();
 console.log("C13_1000_LOCAL_BOOKS_MS="+
   (Number(process.hrtime.bigint()-start)/1e6).toFixed(3));
}
