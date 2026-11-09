"use strict";
/**
 * M11 9M-C16. READ-ONLY native replay receipt -> conditional C15 A/U
 * pathwise *envelopes*. No new trading policy, generator, seed or account.
 *
 * Each native bar is generated from eight tradable Gaussian substeps but the
 * stored OHLC does NOT retain their ordered tape. Thus A exact and exact
 * execution-time U are UNIDENTIFIED; bar-high A upper and bar-range U upper
 * are valid only under the audited time/support contract below.
 */
const assert = require("node:assert/strict");
const ASSETS = ["SYNA", "SYNB"];
const DAY = 86400000;
const H = 8;
const EPS = 1e-6;
function need(ok, code) { assert.ok(ok, "C16_" + code); }
function safeInt(x) { return Number.isSafeInteger(x); }
function finite(x) { return typeof x === "number" && Number.isFinite(x); }
function near(x,y) { return finite(x)&&finite(y)&&
  Math.abs(x-y) <= EPS*Math.max(1,Math.abs(x),Math.abs(y)); }
function audit({native,data,sessions,calendarCostUsdPerDay=1}) {
  need(native?.metadata?.executionNature ===
    "HISTORICAL_MODELED_OHLCV;NOT_BROKER_RECEIPTS" &&
    native?.portfolio?.scope === "MODELED_SHARED_CAPITAL_INTEGER_LOTS_CAUSAL_RESERVATIONS" &&
    native.portfolio.limits?.capitalUsd === 20000 &&
    Array.isArray(native.funded)&&Array.isArray(native.curve)&&
    native.reservationBook?.schema === "HARPOON_FUNDED_RESERVATIONS_1" &&
    Array.isArray(native.modeledNoFills), "EXACT_NATIVE_SOURCE_ONLY");
  need(data?.schema === "HARPOON-ULTIMATE-DATA-1" &&
    data?.kind === "ALPACA_PROXY" &&
    Array.isArray(data.series)&&Array.isArray(sessions)&&sessions.length>0 &&
    data.cashDividends?.length === 0 && data.splitEvents?.length === 0,
    "NO_CORPORATE_ACTIONS_OR_UNKNOWN_DATA");
  need((calendarCostUsdPerDay===1 || calendarCostUsdPerDay===2) &&
    native.curve.length===sessions.length, "COST_AND_SESSION_WINDOW");
  need(native.accounting && near(native.accounting.dividendAccruedUsd,0),
    "CASH_ONLY_NO_DIVIDEND_PROVENANCE");
  const series=new Map();
  for(const s of data.series) {
    need(typeof s.symbol==="string"&&!series.has(s.symbol),"SERIES_UNIQUE");
    series.set(s.symbol,s);
  }
  const bookBars=new Map(), exposureRows=[];
  let preceding=-Infinity;
  for(let i=0;i<sessions.length;i++){
    const session=sessions[i];
    need(safeInt(session.open)&&safeInt(session.close)&&
      session.open<session.close&&session.open>preceding,
      "SESSIONS_STRICT_TIME");
    preceding=session.close;
    need(native.curve[i].session_id===session.date &&
      safeInt(native.curve[i].end_at) &&
      native.curve[i].end_at===session.close,"NATIVE_EVALUATION_SESSIONS");
    const bars=ASSETS.map(a=>{
      const s=series.get(a);
      need(s&&s.pointValue===1&&Array.isArray(s.bars), "LONG_CASH_SHARE_ONLY");
      const selected=s.bars.filter(b=>b.t>=session.open&&b.end<=session.close);
      need(selected.length===78, "FROZEN_78_BARS_PER_SESSION");
      for(let j=0;j<78;j++) {
        const b=selected[j];
        need(safeInt(b.t)&&safeInt(b.end)&&safeInt(b.availableAt)&&
          b.t===session.open+j*300000&&b.end===b.t+300000&&
          b.availableAt>=b.end&&[b.o,b.h,b.l,b.c].every(finite)&&
          b.l>0&&b.l<=Math.min(b.o,b.c)&&b.h>=Math.max(b.o,b.c),
          "MARKET_BAR_SOURCE_AND_CLOCK");
      }
      return selected;
    });
    for(let j=0;j<78;j++) {
      need(bars[0][j].t===bars[1][j].t &&
        bars[0][j].end===bars[1][j].end,
        "TWO_ASSET_COMMON_CLOCK");
      for(let ai=0;ai<ASSETS.length;ai++) {
        const a=ASSETS[ai],b=bars[ai][j];
        const key=a+":"+b.t;
        need(!bookBars.has(key),"BAR_ID_UNIQUE");
        bookBars.set(key,b);
      }
      exposureRows.push({
        t:bars[0][j].t,end:bars[0][j].end,
        byAsset:{SYNA:bars[0][j],SYNB:bars[1][j]}
      });
    }
  }
  need(sessions.at(-1).close - sessions[0].open < 300*DAY,
    "FINITE_EVALUATION_WINDOW");
  const buys=new Map(),sales=new Map(),events=[],seenIds=new Set();
  let eventId=0;
  for(const campaign of native.funded) {
    need(typeof campaign.id==="string"&&!seenIds.has(campaign.id) &&
      ASSETS.includes(campaign.symbol) && campaign.direction===1 &&
      safeInt(campaign.quantity)&&campaign.quantity>0 &&
      Array.isArray(campaign.inventoryEvents) &&
      campaign.inventoryEvents.length>=2, "FUNDED_CAMPAIGN_PROVENANCE");
    seenIds.add(campaign.id);
    let cumulative=0,fees=0;
    for(const e of campaign.inventoryEvents){
      need(safeInt(e.at)&&safeInt(e.knownAt)&&e.knownAt>=e.at &&
        safeInt(e.quantityDelta) && e.quantityDelta!==0 &&
        finite(e.filledPrice)&&finite(e.feeUsd)&&e.feeUsd>=0,
        "PHYSICAL_FILL_RECEIPT_AND_PRICE");
      const entry=e.kind==="ENTRY";
      need(entry === (e.quantityDelta>0) &&
        (entry||e.kind==="EXIT"),"EVENT_SIGN_AND_KIND");
      const q=Math.abs(e.quantityDelta);
      cumulative+=e.quantityDelta;
      need(cumulative>=0&&cumulative<=campaign.quantity,
        "NO_SHORT_OR_EXCESS_QUANTITY");
      fees+=e.feeUsd;
      const b=entry ?
        bookBars.get(campaign.symbol+":"+e.at) :
        bookBars.get(campaign.symbol+":"+(e.at-300000));
      need(b && (entry ? b.t===e.at : b.end===e.at),
        "EVENT_MUST_BE_AT_OPEN_OR_BAR_END");
      need(entry ? e.filledPrice>=b.o-EPS :
        (e.filledPrice>=0&&e.filledPrice<=b.h+EPS),
        "MODELED_FILL_PRICE_SUPPORT");
      // Reference at entry is the opening mark. An exit can occur at an
      // unknown ordered substep; its reference must lie in the bar range.
      const positiveCreditUpper=entry ? Math.max(0,b.o-e.filledPrice)*q :
        Math.max(0,e.filledPrice-b.l)*q;
      const ev={id:++eventId,campaignId:campaign.id,symbol:campaign.symbol,
        kind:e.kind,at:e.at,knownAt:e.knownAt,quantityDelta:e.quantityDelta,
        quantity:q,filledPrice:e.filledPrice,feeUsd:e.feeUsd,
        referenceBarOpen:b.o,referenceBarLow:b.l,
        referenceBarHigh:b.h,positiveCreditUpperUsd:positiveCreditUpper};
      events.push(ev);
      const m=entry?buys:sales;
      if(!m.has(e.at))m.set(e.at,[]);
      m.get(e.at).push(ev);
    }
    need(cumulative===0 && near(fees,campaign.feesUsd),
      "CLOSED_CAMPAIGN_AND_RECONCILED_FEES");
  }
  // Refusals or no-fills must not be misread as physical inventory.
  for(const nf of native.modeledNoFills){
    need(typeof nf.signalId==="string"&&!seenIds.has(nf.signalId)&&
      nf.positionOpened===false&&safeInt(nf.plannedEntryAt)&&
      safeInt(nf.resolutionAt)&&nf.resolutionAt>=nf.plannedEntryAt,
      "NO_FILL_IS_NOT_A_FUNDED_POSITION");
  }
  const q={SYNA:0,SYNB:0};
  let cash=20000,chargedDays=0,feesUsd=0,Alo=0,Ahi=0,Uhi=0;
  let totalEvents=0,unseenEvents=0,peakFraction=0,previousAt=-Infinity;
  const pending=[];
  const startDay=Math.floor(sessions[0].open/DAY);
  function charge(at) {
    const elapsed=Math.floor(at/DAY)-startDay+1;
    need(elapsed>=chargedDays,"MONOTONIC_CALENDAR_CHARGES");
    const extra=(elapsed-chargedDays)*calendarCostUsdPerDay;
    cash-=extra;chargedDays=elapsed;
    need(cash>=-EPS,"NO_CALENDAR_BORROWING");
  }
  function apply(at,map,expectedKind) {
    for(const e of map.get(at)||[]){
      need(e.kind===expectedKind,"EVENT_ORDER_KIND");
      const held=q[e.symbol];
      if(e.kind==="ENTRY"){
        const pendingUnconfirmed=pending.reduce((s,p)=>
          s+(p.knownAt>at ? p.amount:0),0);
        const available=cash-pendingUnconfirmed;
        const charged=e.quantity*e.filledPrice+e.feeUsd;
        need(available+EPS>=charged,
          "NO_BORROW_OR_PENDING_EXIT_RECEIPT_RECYCLING");
      }else {
        need(held>=e.quantity,"NO_SHORT_INVENTORY");
      }
      cash-=e.quantityDelta*e.filledPrice+e.feeUsd;
      q[e.symbol]+=e.quantityDelta;
      need(cash>=-EPS&&q[e.symbol]>=0,"NO_UNFUNDED_PHYSICAL_EVENT");
      if(e.kind==="EXIT"){
        const credit=e.quantity*e.filledPrice-e.feeUsd;
        if(credit>0&&e.knownAt>at)
          pending.push({knownAt:e.knownAt,amount:credit});
      }
      feesUsd+=e.feeUsd; Uhi+=e.positiveCreditUpperUsd;
      totalEvents++;
    }
  }
  for(const row of exposureRows){
    need(row.t>=previousAt,"BAR_CHRONOLOGY");previousAt=row.end;
    charge(row.t);
    apply(row.t,buys,"ENTRY");
    for(const a of ASSETS){
      const b=row.byAsset[a],notional=q[a];
      // Ahi assumes the full pre-exit lot remained across all eight steps;
      // this is conservative when OHLC exits were crossed before bar.end.
      Ahi+=H*notional*b.h;
      if(notional)
        peakFraction=Math.max(peakFraction,notional*b.h/20000);
    }
    apply(row.end,sales,"EXIT");
    // Alo uses ONLY inventory surviving the bar's possible intrabar exits.
    // A prior q*low*8 here would NOT be a valid lower for an early stop fill.
    for(const a of ASSETS)
      Alo+=H*q[a]*row.byAsset[a].l;
  }
  charge(sessions.at(-1).close);
  for(const e of events) {
    // Some last-bar exits may have delayed knowledge; this is legal and
    // must not silently increase earlier admission capacity.
    need(e.at>=sessions[0].open&&e.at<=sessions.at(-1).close,
      "ALL_EVENT_TIMES_COVERED");
  }
  unseenEvents=events.length-totalEvents;
  need(unseenEvents===0&&q.SYNA===0&&q.SYNB===0,
    "ALL_INVENTORY_EVENTS_ACCOUNTED_AND_FLAT");
  const days=Math.floor(sessions.at(-1).close/DAY)-startDay+1;
  need(chargedDays===days&&near(feesUsd,native.accounting.modeledTradingFeesUsd),
    "NATIVE_FEES_AND_FULL_CALENDAR_PARITY");
  if(native.accounting.modeledExternalCostsUsd!==null)
    need(near(native.accounting.modeledExternalCostsUsd,chargedDays*calendarCostUsdPerDay),
      "NATIVE_CALENDAR_EXTERNAL_COST_PARITY");
  const terminal=native.curve.at(-1).equity_end_usd;
  need(near(terminal,cash)&&near(terminal-20000,native.portfolio.netUsd),
    "INDEPENDENT_PHYSICAL_TERMINAL_CASH_PARITY");
  return {
    schema:"HARPOON_M11_C16_NATIVE_AU_PATHWISE_ENVELOPE_1",
    originalNativeReplay:true,sourceExecution:"MODELED_OHLCV_NOT_BROKER",
    assetNames:ASSETS,calendarDays:chargedDays,barCount:exposureRows.length,
    substepCount:exposureRows.length*H,
    nativeFundedCampaigns:native.funded.length,
    nativeNoFillCount:native.modeledNoFills.length,
    physicalFillEventCount:totalEvents,
    AObservedPathLowerDollarSubsteps:Alo,
    AObservedPathUpperDollarSubsteps:Ahi,
    UObservedPathPositiveCreditUpperUsd:Uhi,
    feesUsd,calendarCostUsd:chargedDays*calendarCostUsdPerDay,
    terminalCashUsd:cash,nativeTerminalEquityUsd:terminal,
    terminalReconciliationResidualUsd:cash-terminal,
    peakIntrabarExposureVsInitialWealthUpper:peakFraction,
    exactOrderedEightSubstepTapeAvailable:false,
    exactActualPathAIdentified:false,
    exactExecutionTimeUIdentified:false,
    cashAndPositionReconciled:true,
    pendingReceiptCannotFinanceNewEntry:true,
    pathwiseUpperOnly:true,
    populationExpectedAUpperCertified:false,
    populationExpectedUUpperCertified:false,
    C15EconomicExclusionEvaluated:false,
    N9SAdmission:"NO_GO",
    budget:{newStrategies:0,newEconomicAccounts:0,newMarketSeeds:0,
      finalM10Opened:0,prospectiveAlphaSpent:0},
    independentDecimalVerification:"REQUIRES_SEPARATE_VERIFIER",
    // Read-only bridge emits inputs for a separately implemented accountant.
    sourceForIndependentAudit:{
      sessions:sessions.map(s=>({date:s.date,open:s.open,close:s.close})),
      bars:exposureRows.map(r=>({t:r.t,end:r.end,assets:Object.fromEntries(
        ASSETS.map(a=>[a,{o:r.byAsset[a].o,h:r.byAsset[a].h,
          l:r.byAsset[a].l,c:r.byAsset[a].c}]))})),
      events:events.map(e=>({...e})),
      originalTerminalUsd:terminal
    }
  };
}
module.exports={audit};
