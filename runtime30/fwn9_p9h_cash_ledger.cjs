"use strict";
/* FWN9 P9H: offline source-causal ledger for known native receipts only.
 * Ex-post auditing must not be used to submit orders or to infer fills.
 * Intentionally fails closed on unsettled effective exits, missing quotes,
 * dividends/splits, and incomplete event identities. No population certificate. */
const A=require("node:assert/strict");
const N=require("./profit8_replay.js");
const M9=require("./modulation9_exit.cjs");
const R=require("./ultimate_reservations.js");
const EPS=1e-6;
function near(a,b){return Math.abs(a-b)<=EPS*Math.max(1,Math.abs(a),Math.abs(b));}
function need(ok,code){A.ok(ok,"P9H_"+code);}
function quote(data,symbol,at){
  const series=data.series.find(x=>x.symbol===symbol);
  need(series&&series.pointValue===1&&series.tick>0,"CASH_SHARE_SERIES");
  const ref=M9.causalPriceLookup(data.series,N.causalReferencePrice)({at},series);
  need(ref?.status==="AVAILABLE"&&Number.isFinite(ref.price)&&ref.price>0,"CAUSAL_QUOTE_MISSING");
  return ref.price;
}
function ledgerAt({nativeReplay,data,protocol,limits,at,costPerCalendarDayUsd=1}){
  need([1,2].includes(costPerCalendarDayUsd)&&limits.capitalUsd===20000,"FIXED_CAPITAL_COST_SCOPE");
  need(data.sessions.length>0&&data.splitEvents?.length===0&&
    data.cashDividends?.length===0,"NO_DIVIDEND_SPLIT_SCOPE");
  need(protocol.costs.perSideUsd>0&&
    nativeReplay?.funded&&nativeReplay?.states&&nativeReplay?.reservationBook,
    "REPLAY_CONTRACT");
  const beginning=data.sessions[0].open;
  const calendarDays=at<beginning?0:Math.floor(at/86400000)-
    Math.floor(beginning/86400000)+1;
  need(calendarDays>=0&&calendarDays<=176,"CALENDAR_RANGE");
  const calendarCosts=calendarDays*costPerCalendarDayUsd;
  let physicalCash=limits.capitalUsd-calendarCosts;
  let closedCampaignPool=physicalCash;
  let inventoryMark=0,remainingExitFee=0;
  const open=[];
  const closeKnown=new Map(nativeReplay.states.filter(s=>
    s.modeledCloseKnownAt!==undefined).map(s=>[s.opportunity.id,s.modeledCloseKnownAt]));
  for(const t of nativeReplay.funded){
    if(t.opened>at)continue;
    need(t.direction===1&&t.quantity>0&&t.entry>0&&
      t.inventoryEvents?.length>0,"FUNDED_LONG_RECEIPT_TRACE");
    const ins=t.inventoryEvents.filter(e=>e.kind==="ENTRY");
    need(ins.length===1&&ins[0].at===t.opened&&
      ins[0].knownAt===t.opened&&ins[0].quantityDelta===t.quantity&&
      near(ins[0].feeUsd,t.quantity*protocol.costs.perSideUsd),
      "ENTRY_RECEIPT");
    physicalCash-=t.quantity*t.entry+ins[0].feeUsd;
    let q=t.quantity;
    const exits=t.inventoryEvents.filter(e=>e.kind==="EXIT")
      .sort((a,b)=>a.knownAt-b.knownAt||a.at-b.at);
    need(exits.length>0&&exits.length+1===t.inventoryEvents.length,
      "COMPLETE_ENTRY_EXIT_TRACE");
    for(const e of exits){
      need(Number.isSafeInteger(e.knownAt)&&e.knownAt>=e.at&&
        Number.isFinite(e.filledPrice)&&e.filledPrice>0&&
        e.quantityDelta<0&&near(e.feeUsd,-e.quantityDelta*protocol.costs.perSideUsd),
        "VALID_EXIT_RECEIPT");
      // An effective execution known later is not free cash or safely held stock.
      if(e.at<=at&&e.knownAt>at)throw Error("P9H_UNSETTLED_EFFECTIVE_EXIT");
      if(e.knownAt>at)continue;
      q+=e.quantityDelta;
      need(q>=0,"OVER_SOLD_INVENTORY");
      physicalCash+=-e.quantityDelta*e.filledPrice-e.feeUsd;
    }
    if(q>0){
      const px=quote(data,t.symbol,at);
      inventoryMark+=q*px;
      remainingExitFee+=q*protocol.costs.perSideUsd;
      open.push({id:t.id,symbol:t.symbol,remaining:q,original:t.quantity,price:px});
    }
    const known=closeKnown.get(t.id);
    need(Number.isSafeInteger(known)&&known>=t.closed,"TERMINAL_RECEIPT");
    if(known<=at){
      need(q===0,"CLOSED_WITH_OPEN_INVENTORY");
      closedCampaignPool+=t.netUsd;
    }
  }
  return {at,calendarDays,calendarCosts,physicalCashUsd:physicalCash,
    nativeClosedCampaignPoolUsd:closedCampaignPool,
    inventoryMarkUsd:inventoryMark,open,remainingExitFeeUsd:remainingExitFee,
    impliedNativeEquityUsd:physicalCash+inventoryMark-remainingExitFee};
}
function auditDecision(args){
  const {nativeReplay,data,protocol,limits,state}=args;
  need(state?.reservationStatus==="RESERVED"&&
    state.reservationBefore&&state.reservationAfter&&
    state.opportunity&&Number.isSafeInteger(state.opportunity.at),
    "ACCEPTED_DECISION_AND_RESERVATIONS");
  const at=state.opportunity.at;
  const book=ledgerAt({...args,at});
  const before=state.reservationBefore,after=state.reservationAfter;
  need(before.at===at&&after.at===at&&
    Number.isFinite(state.equity)&&Number.isFinite(state.cashPoolUsd)&&
    Number.isFinite(state.causalPeakEquityUsd),"DECISION_KNOWN_CLOCK");
  const afterIds=new Map(after.reservations.map(x=>[x.id,x]));
  need(afterIds.size===after.reservations.length,"RESERVATION_DUPLICATE");
  for(const pos of book.open){
    const row=afterIds.get(pos.id);
    need(row?.state==="OPENED"&&
      row.quantity===pos.original,"OPEN_STOCK_RESERVATION_CORRESPONDENCE");
  }
  for(const row of after.reservations){
    if(row.state==="OPENED")need(book.open.some(p=>p.id===row.id),
      "RESERVATION_OPEN_WITHOUT_STOCK");
  }
  const pending=after.reservations.filter(x=>x.state==="PENDING");
  const pendingNotional=pending.reduce((n,x)=>n+x.notionalUsd,0);
  const futureFees=book.remainingExitFeeUsd+
    pending.reduce((n,x)=>n+2*x.quantity*protocol.costs.perSideUsd,0);
  const stockPlusPending=book.inventoryMarkUsd+pendingNotional;
  const conservativeNotional=after.reservations.reduce((n,x)=>{
    if(x.state==="PENDING")return n+x.notionalUsd;
    const pos=book.open.find(p=>p.id===x.id);
    return n+Math.max(x.notionalUsd,x.quantity*pos.price);
  },0);
  need(near(state.equity,book.impliedNativeEquityUsd),
    "PHYSICAL_CASH_MARK_NATIVE_EQUITY_MISMATCH");
  need(near(state.cashPoolUsd,book.nativeClosedCampaignPoolUsd),
    "SOURCE_CASH_POOL_RECONCILIATION");
  need(state.equity>0.92*state.causalPeakEquityUsd&&
    state.causalPeakEquityUsd>=limits.capitalUsd,
    "LAST_ADMISSION_GATE_NOT_PROVED");
  need(stockPlusPending<=limits.grossFraction*state.equity+EPS,
    "CURRENT_RESIDUAL_STOCK_PENDING_EXCEEDS_GROSS");
  need(conservativeNotional<=limits.grossFraction*state.equity+EPS,
    "ORIGINAL_FULL_MARK_PLUS_PENDING_EXCEEDS_GROSS");
  need(futureFees<=after.riskUsd+EPS&&
    after.riskUsd<=limits.openRiskFraction*state.equity+EPS,
    "UNCOVERED_FUTURE_RECEIPT_FEES");
  need(book.physicalCashUsd+book.inventoryMarkUsd+EPS>=state.equity,
    "MISSING_NONNEGATIVE_EQUITY_SLACK");
  need(book.physicalCashUsd>=0,"NEGATIVE_PHYSICAL_CASH");
  const remainingCosts=(176-book.calendarDays)*args.costPerCalendarDayUsd||
    (176-book.calendarDays);
  const ledgerFloor=book.physicalCashUsd-pendingNotional-futureFees-remainingCosts;
  const constantFloor=(1-.12-.0025)*.92*20000-
    176*(args.costPerCalendarDayUsd||1);
  need(ledgerFloor>constantFloor-EPS,"CONDITIONAL_FLOOR_NOT_RECOVERED");
  return {...book,decisionId:state.opportunity.id,
    observedNativeEquityUsd:state.equity,observedCashPoolUsd:state.cashPoolUsd,
    reservationAfterRiskUsd:after.riskUsd,reservationAfterNotionalUsd:after.notionalUsd,
    pendingNotionalUsd:pendingNotional,currentStockPlusPendingUsd:stockPlusPending,
    conservativeNotionalUsd:conservativeNotional,futureFeeUpperUsd:futureFees,
    physicalVsClosedPoolUsd:book.physicalCashUsd-book.nativeClosedCampaignPoolUsd,
    residualGrossGate:true,sourceCashMarkIdentity:true,
    localLedgerFloorUsd:ledgerFloor,conditionalGlobalFloorUsd:constantFloor,
    sampleOnly:true,fullM9Certificate:false,nativeOhlcCreditBound:false};
}
function auditNoFill({nativeReplay,at}){
  const items=nativeReplay.modeledNoFills||[];
  need(items.length>0,"REQUIRES_NO_FILL");
  const first=items[0];
  need(at>=first.plannedEntryAt,"NO_FILL_RECEIPT_NOT_YET_KNOWN");
  const snapshot=R.snapshotFundedReservations(nativeReplay.reservationBook,at);
  need(!snapshot.reservations.some(x=>x.id===first.signalId),"NO_FILL_NOT_RELEASED");
  need(!nativeReplay.funded.some(x=>x.id===first.signalId),
    "NO_FILL_CREATED_PHANTOM_STOCK");
  return {id:first.signalId,at,noFillReleased:true,
    noPhantomInventory:true,valuationClockP9BProven:false};
}
module.exports={ledgerAt,auditDecision,auditNoFill};
