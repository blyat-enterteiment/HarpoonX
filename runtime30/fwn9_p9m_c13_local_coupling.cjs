"use strict";
/**
 * FWN9/C13: independent, self-financing native-style event ledgers coupled
 * only through the same published mark tape and non-overlapping <=72h windows.
 * No market RNG, strategy optimizer, broker, execution-policy substitution,
 * population WEAK certificate, or terminal-price oracle at decision time.
 *
 * PHYSICAL accounting follows fill.at; INFORMATION follows fill.knownAt.
 * The former is retrospective and MUST NOT be used to admit an order.
 */
const A=require("node:assert/strict");
const HOUR=3600000, DAY=86400000, EPS=1e-6;
const near=(a,b)=>Number.isFinite(a)&&Number.isFinite(b)&&
  Math.abs(a-b)<=EPS*Math.max(1,Math.abs(a),Math.abs(b));
const guard=(ok,code)=>A.ok(ok,"C13_"+code);
const finite=x=>typeof x==="number"&&Number.isFinite(x);
const safe=x=>Number.isSafeInteger(x)&&x>=0;
const pos=x=>Math.max(0,x);
function checkBook(book,from,to,fee){
  guard(book&&["NATIVE_OHLC","FIRST_CROSS"].includes(book.mode),
    "BOOK_MODE_REQUIRED");
  guard(Array.isArray(book.admissions)&&Array.isArray(book.fills)&&
    Array.isArray(book.noFills),"INDEPENDENT_BOOK_INPUTS");
  const admissions=new Map(),balances=new Map(),seenEntry=new Set();
  for(const a of book.admissions){
    guard(typeof a.id==="string"&&a.id.length>0&&!admissions.has(a.id)&&
      ["SYNA","SYNB"].includes(a.symbol)&&
      safe(a.at)&&a.at>=from&&a.at<=to&&
      Number.isSafeInteger(a.quantity)&&a.quantity>0,
      "ADMISSION_CONTRACT");
    admissions.set(a.id,a);balances.set(a.id,0);
  }
  const events=book.fills.map(e=>({...e,mode:book.mode}));
  for(const e of events){
    const a=admissions.get(e.id);
    guard(a&&a.symbol===e.symbol&&["ENTRY","EXIT"].includes(e.kind)&&
      safe(e.at)&&safe(e.knownAt)&&e.at>=a.at&&e.knownAt>=e.at&&
      e.knownAt<=to&&finite(e.price)&&
      (e.kind==="ENTRY"?e.price>0:e.price>=0)&&
      safe(e.quantity)&&e.quantity>0&&near(e.feeUsd,e.quantity*fee),
      "RECEIPT_CAUSAL_COST_CONTRACT");
    guard(e.at-a.at<=72*HOUR,"HOLD_MAX_72H_FROM_SIGNAL");
  }
  events.sort((a,b)=>a.at-b.at||
    (a.kind==="EXIT"?-1:1)-(b.kind==="EXIT"?-1:1)||
    a.id.localeCompare(b.id));
  for(const e of events){
    const a=admissions.get(e.id),before=balances.get(e.id);
    if(e.kind==="ENTRY"){
      guard(!seenEntry.has(e.id)&&e.quantity===a.quantity&&before===0,
        "ENTRY_ORIGINAL_ADMISSION_QUANTITY");
      seenEntry.add(e.id);balances.set(e.id,e.quantity);
    }else{
      guard(seenEntry.has(e.id)&&before>=e.quantity,"NO_SHORT_OR_OVERSELL");
      balances.set(e.id,before-e.quantity);
    }
  }
  guard([...balances.values()].every(x=>x===0),"TERMINAL_INVENTORY_CLOSED");
  const nofillIds=new Set();
  for(const n of book.noFills){
    const a=admissions.get(n.id);
    guard(a&&!nofillIds.has(n.id)&&!seenEntry.has(n.id)&&
      safe(n.at)&&safe(n.knownAt)&&n.at>=a.at&&n.knownAt>=n.at&&
      n.knownAt<=to,"NOFILL_RECEIPT_OR_GHOST_FILL");
    nofillIds.add(n.id);
  }
  guard(admissions.size===seenEntry.size+nofillIds.size,
    "EVERY_RESERVATION_TERMINAL_RECEIPT");
  return {admissions,events,seenEntry,nofillIds,nofills:book.noFills};
}
function audit(input){
  const {startAt,endAt,marks,books}=input, fee=input.perSideFeeUsd??.005;
  const cost=input.calendarCostPerDayUsd??1;
  guard(safe(startAt)&&safe(endAt)&&startAt<endAt&&
    endAt-startAt<=176*DAY&&fee===.005&&cost===1&&
    (input.initialCashUsd??20000)===20000,
    "FROZEN_NOMINAL_FINITE_CONTRACT");
  guard(Array.isArray(books)&&books.length===2&&
    books[0].mode==="NATIVE_OHLC"&&books[1].mode==="FIRST_CROSS",
    "TWO_INDEPENDENT_BOOKS");
  guard(Array.isArray(marks)&&marks.length>=2,"TWO_MARK_SERIES_REQUIRED");
  const bySymbol=new Map(),price={SYNA:null,SYNB:null},events=[];
  for(const mark of marks){
    guard(["SYNA","SYNB"].includes(mark.symbol)&&
      safe(mark.at)&&mark.at>=startAt&&mark.at<=endAt&&
      finite(mark.price)&&mark.price>0&&
      (mark.first===true?
        mark.at===startAt:
        safe(mark.barEnd)&&mark.barEnd<mark.at),
      "PUBLISHED_MARK_CONTRACT");
    const prev=bySymbol.get(mark.symbol);
    if(prev)guard(mark.at>prev,"NONMONOTONE_ASSET_MARK");
    bySymbol.set(mark.symbol,mark.at);
    events.push({...mark,type:"MARK",priority:0});
  }
  guard(bySymbol.size===2&&marks.filter(x=>x.first).length===2,
    "INITIAL_MARK_FOR_BOTH_SYMBOLS");
  const parsed=books.map(b=>checkBook(b,startAt,endAt,fee));
  for(let bi=0;bi<2;bi++){
    for(const e of parsed[bi].events)events.push({
      ...e,book:bi,type:"FILL",priority:e.kind==="EXIT"?2:3
    });
  }
  const firstDay=Math.floor(startAt/DAY),lastDay=Math.floor(endAt/DAY);
  const days=lastDay-firstDay+1;
  guard(days>=1&&days<=177,"FROZEN_CALENDAR_DAYS");
  for(let d=firstDay;d<=lastDay;d++){
    const at=d===firstDay?startAt:d*DAY;
    if(at<=endAt)events.push({at,type:"FIXED",priority:1,amount:cost});
  }
  events.sort((a,b)=>a.at-b.at||a.priority-b.priority||
    (a.book??0)-(b.book??0)||String(a.symbol??"").localeCompare(String(b.symbol??"")));
  const balances=[{cash:20000,q:{SYNA:0,SYNB:0}},
                  {cash:20000,q:{SYNA:0,SYNB:0}}];
  let difference=0,unit=0;
  const windows=[];
  for(let t=startAt;t<endAt;t+=72*HOUR){
    windows.push({startAt:t,endAt:Math.min(t+72*HOUR,endAt),
      openingDifferenceUsd:null,closingDifferenceUsd:null,
      exposureTermUsd:0,executionTermUsd:0,feeTermUsd:0,fixedTermUsd:0,
      eventUpperAllowanceUsd:0,financeEventCount:0,priceEventCount:0,
      pendingReceiptCountAtEnd:0,carryPositions:null,
      exactResidualUsd:null});
  }
  const wealth=(bi)=>balances[bi].cash+
    ["SYNA","SYNB"].reduce((sum,s)=>{
      const q=balances[bi].q[s];
      if(q)guard(price[s]!==null,"MARK_BEFORE_POSITION_REQUIRED");
      return sum+q*(price[s]??0);
    },0);
  const ledger=[];
  for(const e of events){
    while(unit<windows.length&&e.at>=windows[unit].endAt&&
      windows[unit].endAt<endAt){
      const w=windows[unit];
      w.closingDifferenceUsd=wealth(0)-wealth(1);
      w.carryPositions=balances.map(b=>({...b.q}));
      unit++;
    }
    guard(unit<windows.length,"EVENT_AFTER_TERMINAL");
    const w=windows[unit];
    if(w.openingDifferenceUsd===null){
      // The first observation is before the event, including boundary inventory.
      w.openingDifferenceUsd=wealth(0)-wealth(1);
    }
    const oldDifference=wealth(0)-wealth(1);
    let exposure=0,execution=0,fees=0,fixed=0;
    if(e.type==="MARK"){
      const s=e.symbol,prev=price[s];
      if(prev!==null){
        exposure=(balances[0].q[s]-balances[1].q[s])*(e.price-prev);
      }
      price[s]=e.price;
      w.priceEventCount++;
    }else if(e.type==="FIXED"){
      for(const b of balances)b.cash-=e.amount;
      fixed=-e.amount+e.amount;
    }else{
      const b=balances[e.book],delta=e.kind==="ENTRY"?e.quantity:-e.quantity;
      guard(price[e.symbol]!==null,"MARK_FOR_FILL_REQUIRED");
      guard(b.q[e.symbol]+delta>=0,"NEGATIVE_PHYSICAL_INVENTORY");
      execution=(e.book===0?1:-1)*delta*(price[e.symbol]-e.price);
      fees=(e.book===0?-1:1)*e.feeUsd;
      b.cash-=delta*e.price+e.feeUsd;b.q[e.symbol]+=delta;
      w.financeEventCount++;
    }
    guard(balances.every(b=>b.cash>=-1e-7),
      "NO_CASH_BORROWING");
    const nextDifference=wealth(0)-wealth(1);
    guard(near(nextDifference-oldDifference,
      exposure+execution+fees+fixed),"SELF_FINANCING_DELTA_IDENTITY");
    w.exposureTermUsd+=exposure;w.executionTermUsd+=execution;
    w.feeTermUsd+=fees;w.fixedTermUsd+=fixed;
    w.eventUpperAllowanceUsd+=pos(exposure)+pos(execution)+pos(fees)+pos(fixed);
    ledger.push({at:e.at,type:e.type,mode:e.mode??null,
      symbol:e.symbol??null,book:e.book??null,
      wealthNativeUsd:wealth(0),wealthDiscreteUsd:wealth(1),
      differenceUsd:nextDifference,
      exposure,execution,fees,fixed});
  }
  const last=windows.at(-1);
  if(last.openingDifferenceUsd===null)
    last.openingDifferenceUsd=wealth(0)-wealth(1);
  last.closingDifferenceUsd=wealth(0)-wealth(1);
  last.carryPositions=balances.map(b=>({...b.q}));
  for(let i=0;i<windows.length;i++){
    const w=windows[i];
    if(w.openingDifferenceUsd===null){
      w.openingDifferenceUsd=i===0?0:windows[i-1].closingDifferenceUsd;
      w.closingDifferenceUsd=w.openingDifferenceUsd;
      w.carryPositions=balances.map(b=>({...b.q}));
    }
    guard(w.endAt-w.startAt<=72*HOUR,"WINDOW_LONGER_THAN_72H");
    if(i>0)guard(near(w.openingDifferenceUsd,
      windows[i-1].closingDifferenceUsd),"CROSS_WINDOW_DIFFERENCE_CARRY");
    const exact=w.openingDifferenceUsd+w.exposureTermUsd+
      w.executionTermUsd+w.feeTermUsd+w.fixedTermUsd;
    w.exactResidualUsd=w.closingDifferenceUsd-exact;
    guard(Math.abs(w.exactResidualUsd)<=.000001,
      "LOCAL_TELESCOPIC_RECONCILIATION");
    guard(w.closingDifferenceUsd<=
      w.openingDifferenceUsd+w.eventUpperAllowanceUsd+.000001,
      "LOCAL_UPPER_ENVELOPE");
    // Knowledge clock belongs to each BOOK, independently; this quantity
    // is the number of already effective fills still unreceived at boundary.
    w.pendingReceiptCountAtEnd=parsed.reduce((sum,b)=>
      sum+b.events.filter(e=>e.at<w.endAt&&e.knownAt>=w.endAt).length,0);
  }
  guard(balances.every(b=>b.q.SYNA===0&&b.q.SYNB===0),
    "NO_TERMINAL_INVENTORY");
  const priceA=wealth(0),priceB=wealth(1);
  const localUpper=windows.reduce((s,w)=>s+w.eventUpperAllowanceUsd,0);
  guard(priceA-priceB<=localUpper+.000001,
    "WHOLE_PATH_TELESCOPIC_UPPER");
  // Knowledge-limited conservative closed-campaign cash, never fed to an
  // admission policy: only fully received campaign exits are counted.
  const knownCashAt=(bookIndex,at)=>{
    const b=parsed[bookIndex],trades=new Map();
    for(const a of b.admissions.values())trades.set(a.id,0);
    for(const e of b.events) {
      if(e.kind==="ENTRY")trades.set(e.id,
        trades.get(e.id)-e.quantity*e.price-e.feeUsd);
      else trades.set(e.id,
        trades.get(e.id)+e.quantity*e.price-e.feeUsd);
    }
    const completedIds=new Set();
    for(const a of b.admissions.values()){
      const ev=b.events.filter(e=>e.id===a.id);
      if(ev.length&&ev.every(e=>e.knownAt<=at))completedIds.add(a.id);
    }
    const fixedPaid=at<startAt?0:
      Math.floor(at/DAY)-Math.floor(startAt/DAY)+1;
    return 20000-fixedPaid*cost+
      [...completedIds].reduce((v,id)=>v+trades.get(id),0);
  };
  const decisions=books.flatMap((b,i)=>b.admissions.map(a=>({
    mode:b.mode,id:a.id,at:a.at,
    bookIndex:i,conservativeReceivedCashUsd:knownCashAt(i,a.at),
    otherBookCashUsd:knownCashAt(1-i,a.at)
  })));
  return {schema:"HARPOON_FWN9_C13_LOCAL72_COUPLING_1",
    classification:"EXACT_FINITE_PATHWISE_INDEPENDENT_BOOKS_NOT_POPULATION",
    initialCashUsd:20000,endingNativeUsd:priceA,
    endingDiscreteUsd:priceB,
    endingDifferenceUsd:priceA-priceB,
    totalLocalDifferenceUpperUsd:localUpper,
    windows,decisions,
    receiptsValidated:parsed.reduce((s,b)=>s+b.events.length+b.nofills.length,0),
    totalFinanceEvents:ledger.filter(e=>e.type==="FILL").length,
    eventClockRecords:ledger.length,
    criteria:{nativeAndFirstCrossIndependentAdmissions:true,
      samePublishedMarkTape:true,
      nativeExecutionPriceAttainabilityCertified:false,
      fullStochasticWeakPopulationBoundCertified:false,
      nonvacuousPopulationBoundCertified:false,
      originalTwelvePercentIsAdmissionNotContinuous:true,
      noFutureReceiptUsedForDecision:true,
      N9SAccepted:false},
    budget:{newEconomicAccounts:0,marketSeeds:0,finalOpened:0,alphaSpent:0}};
}
function gaussianNoFiniteUniformRange({finiteMultiplier,windowSteps,sigmaStep}){
  guard(finite(finiteMultiplier)&&finiteMultiplier>1&&
    Number.isSafeInteger(windowSteps)&&windowSteps>0&&
    finite(sigmaStep)&&sigmaStep>0,
    "NONDEGENERATE_GAUSSIAN_SUPPORT");
  const z=Math.log(finiteMultiplier)/(sigmaStep*Math.sqrt(windowSteps));
  const phi=Math.exp(-z*z/2)/Math.sqrt(2*Math.PI);
  const conservativeTailLower=z>0&&z<25?
    (phi*z)/(z*z+1):null;
  return {finiteMultiplier,windowSteps,sigmaStep,standardDeviationWindow:
    sigmaStep*Math.sqrt(windowSteps),normalStandardDeviationThreshold:z,
    provenPositiveProbabilityForEveryFiniteMultiplier:true,
    numericalLowerProbabilityBound:conservativeTailLower,
    noDeterministicUniversalLocalPriceRatio:true,
    boundOnNativeExpectedLogWealth:false,
    why:"Unbounded support of independent WEAK idiosyncratic normal innovations; a <=72h window does not cap the price ratio with probability one"};
}
module.exports={audit,gaussianNoFiniteUniformRange};
