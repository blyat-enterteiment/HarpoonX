"use strict";
/**
 * C14: OHLC bar-high attainable-price ENVELOPE for two independent funded books.
 * This proves a cash-share inequality under observable bar HIGH support, NOT
 * that OHLC threshold prices are present in the eight-step executable tape.
 * Acquisition at the bar open only; no cash borrowing or intrabar recycling.
 * Economic event.at and knowledge event.knownAt are kept separate.
 */
const A=require("node:assert/strict");
const EPS=1e-7;
const SYMBOLS=["SYNA","SYNB"];
const need=(x,name)=>A.ok(x,"C14_"+name);
const finite=x=>typeof x==="number"&&Number.isFinite(x);
const near=(x,y)=>finite(x)&&finite(y)&&
  Math.abs(x-y)<=EPS*Math.max(1,Math.abs(x),Math.abs(y));

function validateBars(bars){
  need(bars&&SYMBOLS.every(x=>bars[x]),"TWO_REGISTERED_ASSETS");
  const times=SYMBOLS.map(x=>[bars[x].t,bars[x].end,bars[x].availableAt]);
  need(JSON.stringify(times[0])===JSON.stringify(times[1]),"COMMON_BAR_CLOCK");
  for(const symbol of SYMBOLS){
    const b=bars[symbol];
    need([b.t,b.end,b.availableAt].every(Number.isSafeInteger)&&
      b.t<b.end&&b.availableAt>b.end&&[b.o,b.h,b.l,b.c].every(finite)&&
      b.l>0&&b.l<=Math.min(b.o,b.c)&&b.h>=Math.max(b.o,b.c),
      "ORIGINAL_OHLC_BAR_CONTRACT");
  }
}
function auditOneBar({mode,bars,cash,inventory,fills=[],noFills=[],perSideFee=.005,
  calendarFee=0}){
  validateBars(bars);
  need(["NATIVE_OHLC","FIRST_CROSS"].includes(mode)&&finite(cash)&&cash>=0&&
    (perSideFee===.005||perSideFee===.01)&&
    finite(calendarFee)&&calendarFee>=0,"SCENARIO_CASH_AND_MODE");
  const q=Object.fromEntries(SYMBOLS.map(s=>[s,inventory[s]]));
  need(SYMBOLS.every(s=>Number.isSafeInteger(q[s])&&q[s]>=0),
    "INVENTORY_IS_LONG_INTEGER");
  const t=bars.SYNA.t,end=bars.SYNA.end;
  const wealth=()=>cash+SYMBOLS.reduce((total,s)=>total+q[s]*bars[s].o,0);
  const w0=wealth();
  need(w0>0,"POSITIVE_STARTING_WEALTH");
  const fillRows=fills.map((e,i)=>({...e,sourceIndex:i}))
    .sort((a,b)=>a.at-b.at||a.sourceIndex-b.sourceIndex);
  let openedCount=0,closedCount=0,paidFees=0;
  for(const r of noFills){
    need(Number.isSafeInteger(r.at)&&Number.isSafeInteger(r.knownAt)&&
      r.at>=t&&r.at<=end&&r.knownAt>=r.at &&
      SYMBOLS.includes(r.symbol),"NOFILL_IS_ONLY_RECEIPT");
  }
  for(const e of fillRows){
    need(SYMBOLS.includes(e.symbol)&&["ENTRY","EXIT"].includes(e.kind)&&
      Number.isSafeInteger(e.at)&&Number.isSafeInteger(e.knownAt)&&
      e.at>=t&&e.at<=end&&e.knownAt>=e.at&&
      Number.isSafeInteger(e.quantity)&&e.quantity>0&&
      finite(e.price)&&finite(e.feeUsd)&&
      near(e.feeUsd,e.quantity*perSideFee),"RECEIPT_COST_AND_TIME");
    if(e.kind==="ENTRY"){
      need(e.at===t&&e.price>=bars[e.symbol].o-EPS,
        "BUY_ONLY_AT_OBSERVED_OPEN_NOT_BELOW_OPEN");
    }else{
      need(e.price>=0&&e.price<=bars[e.symbol].h+EPS,
        "SELL_NONNEGATIVE_BELOW_OBSERVED_HIGH");
    }
  }
  // All acquisitions are pre-price-innovation and budgeted before sale proceeds.
  const opens=fillRows.filter(e=>e.kind==="ENTRY");
  const exits=fillRows.filter(e=>e.kind==="EXIT");
  for(const e of opens){
    const charge=e.quantity*e.price+e.feeUsd;
    need(cash+EPS>=charge,"NO_CASH_BORROWING_ON_ENTRY");
    cash-=charge;q[e.symbol]+=e.quantity;
    paidFees+=e.feeUsd;openedCount++;
  }
  const postOpenCash=cash;
  const qAfterOpen={...q};
  const postOpenWealth=cash+SYMBOLS.reduce((z,s)=>z+q[s]*bars[s].o,0);
  need(postOpenWealth>0&&postOpenWealth<=w0+EPS,
    "BUY_NOT_FINANCING_NEW_WEALTH");
  const sharpGrossUpper=cash+SYMBOLS.reduce((z,s)=>z+q[s]*bars[s].h,0);
  for(const e of exits){
    need(e.quantity<=q[e.symbol],"NO_UNCOVERED_SALES");
    q[e.symbol]-=e.quantity;
    cash+=e.quantity*e.price-e.feeUsd;
    paidFees+=e.feeUsd;closedCount++;
    need(cash>=-EPS,"NO_NEGATIVE_CASH_AFTER_SALE");
  }
  cash-=calendarFee;
  need(cash>=-EPS,"NONNEGATIVE_CASH_AFTER_FIXED_COST");
  const endWealth=cash+SYMBOLS.reduce((z,s)=>z+q[s]*bars[s].c,0);
  const maxR=Math.max(1,...SYMBOLS.map(s=>bars[s].h/bars[s].o));
  need(endWealth<=sharpGrossUpper+EPS*Math.max(1,sharpGrossUpper),
    "NATIVE_BAR_HIGH_SUPPORT_ENVELOPE");
  need(endWealth<=w0*maxR+EPS*Math.max(1,w0*maxR),
    "NATIVE_LONG_BAR_RATIO_ENVELOPE");
  return {mode,startCashUsd:w0-SYMBOLS.reduce((z,s)=>z+inventory[s]*bars[s].o,0),
    startWealthUsd:w0,postOpenWealthUsd:postOpenWealth,
    postOpenCashUsd:postOpenCash,postOpenInventory:qAfterOpen,
    grossAtHighUpperUsd:sharpGrossUpper,
    endCashUsd:cash,endInventory:q,endWealthUsd:endWealth,
    maxHighRatio:maxR,admittedCashForOpeningBuysUsd:w0-
      SYMBOLS.reduce((z,s)=>z+inventory[s]*bars[s].o,0),
    openedCount,closedCount,paidFeesUsd:paidFees,
    pendingNoFillReceiptCount:noFills.length,
    requiresSeparateDecisionClock:true,
    intrabarExecutorEquivalentToEightSteps:false,
    fullNativePopulationCertified:false};
}
function auditTwoBooks({bars,books,perSideFee=.005,calendarFee=0}){
  need(Array.isArray(books)&&books.length===2&&
    books[0].mode==="NATIVE_OHLC"&&books[1].mode==="FIRST_CROSS",
    "BOOKS_ARE_INDEPENDENT");
  const native=auditOneBar({...books[0],bars,perSideFee,calendarFee});
  const causal=auditOneBar({...books[1],bars,perSideFee,calendarFee});
  return {schema:"HARPOON_FWN9_C14_NATIVE_BAR_HIGH_FINANCED_ENVELOPE_1",
    native,causal,
    terminalWealthDifferenceUsd:native.endWealthUsd-causal.endWealthUsd,
    fillsNotForcedToMatch:true,
    nativePopulationMomentCertification:false,source:"ENGINEERING_ONLY"};
}
function auditNativeFillPriceSupport({data,native,perSideFee=.005}){
  need(native&&Array.isArray(native.funded)&&Array.isArray(data?.series)&&
    data.series.length>=2,"NATIVE_REPLAY_CAMPAIGNS_REQUIRED");
  const checked=[];
  for(const campaign of native.funded){
    const series=data.series.find(s=>s.symbol===campaign.symbol);
    need(series&&Array.isArray(series.bars)&&campaign.quantity>0,
      "NATIVE_SERIES_AND_LOT");
    for(const e of campaign.inventoryEvents){
      need(e.knownAt>=e.at&&Number.isSafeInteger(e.quantityDelta)&&
        finite(e.filledPrice)&&finite(e.feeUsd)&&
        near(e.feeUsd,Math.abs(e.quantityDelta)*perSideFee),
        "NATIVE_FILL_RECEIPT_CAUSAL_AND_COST");
      const candidates=series.bars.filter(b=>
        e.kind==="ENTRY" ? b.t===e.at : b.end===e.at||b.t===e.at);
      const compatible=candidates.find(b=>e.kind==="ENTRY"?
        e.filledPrice>=b.o-EPS && e.filledPrice>0 :
        e.filledPrice>=0&&e.filledPrice<=b.h+EPS);
      need(!!compatible,"NATIVE_FILL_OUTSIDE_BAR_HIGH_OR_OPEN");
      checked.push({symbol:campaign.symbol,id:campaign.id,kind:e.kind,
        at:e.at,knownAt:e.knownAt,price:e.filledPrice,
        barOpen:compatible.o,barHigh:compatible.h,
        observedEightStepExecutionCertified:false});
    }
  }
  return {schema:"HARPOON_FWN9_C14_NATIVE_FILL_SUPPORT_AUDIT_1",
    checkedFills:checked.length,events:checked,
    allNativePricesInBarHighEnvelope:true,
    eightSubstepTradeableFillPricesProven:false,
    fullNativePopulationAudited:false};
}
module.exports={auditOneBar,auditTwoBooks,auditNativeFillPriceSupport};
