"use strict";
/**
 * M11/P9A — actual-native-campaign receipt adapter for independent funded books.
 * A diagnostic factory, not an executable broker, trading policy or model.
 * Future native replay is consumed only in a deferred evidence factory after
 * each funding decision; the mirror has no access to pending factory events
 * before their individual knownAt. No stochastic parity theorem is claimed.
 */
const assert=require("node:assert/strict");
const Native=require("./profit8_replay.js");
const Campaign=require("./modulation11_stateful_campaign.cjs");
const Mirror=require("./modulation11_admission_mirror_v2.cjs");
const EPS=1e-7;
const near=(a,b)=>Math.abs(a-b)<=EPS*Math.max(1,Math.abs(a),Math.abs(b));
function roundUp(price,tick){return Math.ceil(price/tick-1e-10)*tick;}
function requireIntegerTime(x){assert(Number.isSafeInteger(x)&&x>=0,"P9A_BAD_EVENT_TIME");}
function receiptFactory(context,receiptsAudit){
  const {data,protocol,substeps}=context;
  return ({mode,signal,quantity,iocPlan})=>{
    assert(["NATIVE_OHLC","FIRST_CROSS"].includes(mode),"P9A_MODE");
    assert(Number.isSafeInteger(quantity)&&quantity>0&&iocPlan.status==="PLANNED","P9A_VALID_ADMISSION");
    const series=data.series.find(s=>s.symbol===signal.symbol);
    assert(series&&series.pointValue===1&&series.tick>0,"P9A_SERIES");
    const entryBar=series.bars.find(b=>b.t===signal.plannedEntryAt);
    assert(entryBar,"P9A_UNOBSERVED_IOC_OPEN");
    const f=(protocol.costs.spreadBps/2+protocol.costs.slippageBps)/10000;
    const price=roundUp(entryBar.o*(1+f),series.tick);
    requireIntegerTime(entryBar.t);
    assert(price>0&&Number.isFinite(price),"P9A_ENTRY_PRICE");
    const ioc={id:signal.id,kind:"IOC",at:entryBar.t,
      knownAt:entryBar.t,price};
    if(price>iocPlan.priceCeiling+1e-8){
      receiptsAudit.push({mode,id:signal.id,quantity,kind:"NO_FILL",
        price,priceCeiling:iocPlan.priceCeiling});
      return [ioc];
    }
    const trace=Campaign.compareNative({signal,series,data,protocol,quantity,
      substeps:substeps[signal.symbol]});
    const trade=trace.native;
    assert(trade.id===signal.id&&trade.quantity===quantity&&
      near(trade.entry,price)&&trade.opened===entryBar.t,
      "P9A_NATIVE_IOC_PARITY");
    const nativeExits=trade.inventoryEvents.filter(e=>e.kind==="EXIT");
    const events=mode==="NATIVE_OHLC"?
      nativeExits.map(e=>({at:e.at,knownAt:e.knownAt,
        price:e.filledPrice,quantity:-e.quantityDelta,reason:e.reason})):
      trace.discrete.fills.map(e=>({at:e.at,knownAt:e.knownAt,
        price:e.price,quantity:e.quantity,reason:e.reason}));
    assert(events.length>0&&events.reduce((s,e)=>s+e.quantity,0)===quantity,
      "P9A_EXITS_RECONCILE_FULL_ORIGINAL_QUANTITY");
    const finalKnownAt=mode==="NATIVE_OHLC"?
      Native.profit8KnownAt(trade):trace.discrete.terminalKnownAt;
    let priorAt=entryBar.t,priorReceipt=entryBar.t;
    const out=[ioc];
    for(let i=0;i<events.length;i++){
      const e=events[i];
      const knownAt=i===events.length-1?Math.max(e.knownAt,finalKnownAt):e.knownAt;
      requireIntegerTime(e.at);requireIntegerTime(knownAt);
      assert(e.at>=priorAt&&knownAt>=e.at&&knownAt>=priorReceipt&&
        e.at-entryBar.t<=72*3600000,"P9A_EXIT_CLOCK_OR_72H");
      assert(e.quantity>0&&Number.isSafeInteger(e.quantity)&&Number.isFinite(e.price)&&
        e.price>0,"P9A_BAD_EXIT");
      out.push({id:signal.id,kind:"EXIT",at:e.at,knownAt,
        price:e.price,quantity:e.quantity});
      priorAt=e.at;priorReceipt=knownAt;
    }
    // The native controller may delay final booking until all marks are known;
    // this deliberately preserves its final close receipt clock.
    const expectedNet=mode==="NATIVE_OHLC"?trade.netUsd:trace.discrete.netUsd;
    const reconstructed=out.slice(1).reduce((s,e)=>s+
      (e.price-price)*e.quantity-protocol.costs.perSideUsd*e.quantity,0)-
      quantity*protocol.costs.perSideUsd;
    assert(near(reconstructed,expectedNet),"P9A_CAMPAIGN_SELF_FINANCING");
    receiptsAudit.push({mode,id:signal.id,quantity,kind:"FILLED",
      nativeNetUsd:trade.netUsd,modeledNetUsd:expectedNet,
      exitEvents:events.length,finalReceiptAt:priorReceipt});
    return out;
  };
}
/**
 * Replay the same two synthetic engineering symbols with actual native exits.
 * This function calls no generator, model trainer, broker or network service.
 * It explicitly refuses to certify global clocks or observational stochastic
 * parity: the mirror is decision-clock-only and lacks the daily loss gate.
 */
function compare({signals,data,protocol,limits,substeps,fixedCosts,terminalAt}){
  assert(signals.length>=2&&data.sessions.length>0,"P9A_FULL_NATIVE_INPUT");
  const opts={continuous:true,cashDividends:true,
    entryExecution:"IOC_LIMIT_COMMON_CAUSAL_30BPS",
    externalCostPerSessionUsd:0,calendarCostPerDayUsd:1,
    profit8:{mode:"NATIVE_MAX"},researchModulation:true};
  const nativeReplay=Native.replayFundedPortfolio(signals,data,protocol,
    [{test:data.sessions,selected:"ALL:BASELINE"}],data.sessions,limits,opts);
  const audits=[];
  const mirror=Mirror.mirror({signals,data,protocol,limits,fixedCosts,terminalAt,
    receiptFactory:receiptFactory({data,protocol,substeps},audits)});
  const byId=new Map(nativeReplay.funded.map(t=>[t.id,t]));
  const nativeAdmits=mirror.native.admits;
  const nativeAdmittedFull=signals.filter(s=>byId.has(s.id));
  const fullIdentityQuantity=nativeAdmits.length===nativeAdmittedFull.length&&
    nativeAdmits.every(a=>byId.get(a.id)?.quantity===a.quantity);
  const fullNet=nativeReplay.funded.reduce((s,t)=>s+t.netUsd,0);
  const nativeMirrorNet=mirror.native.bookedTradingUsd;
  const nativeNetParity=near(fullNet,nativeMirrorNet);
  const nativeStates=nativeReplay.states;
  const mirrorRows=new Map(mirror.native.decisions.map(x=>[x.id,x]));
  const decisionRows=nativeStates.filter(s=>s.reservationStatus==="RESERVED");
  const anchorRows=decisionRows.map(s=>{
    const m=mirrorRows.get(s.opportunity.id);
    return {id:s.opportunity.id,matched:!!m&&m.status==="RESERVED"&&
      m.quantity===s.quantity&&near(m.equityUsd,s.equity)&&
      near(m.cashPoolUsd,s.cashPoolUsd)&&
      near(m.priorRiskUsd,s.reservationBefore.riskUsd)&&
      near(m.priorNotionalUsd,s.reservationBefore.notionalUsd),
      quantityNative:s.quantity,quantityMirror:m?.quantity??null,
      equityNativeUsd:s.equity,equityMirrorUsd:m?.equityUsd??null,
      cashNativeUsd:s.cashPoolUsd,cashMirrorUsd:m?.cashPoolUsd??null};
  });
  const allAnchors=anchorRows.length>0&&anchorRows.every(r=>r.matched);
  const fixedFees=fixedCosts.reduce((s,c)=>s+c.usd,0);
  return {schema:"HARPOON_M11_PHASE9A_NATIVE_RECEIPT_PARITY_1",
    accounts:0,marketSeedsOpened:[],alphaSpent:0,holdoutOpened:false,
    nativeFundedCount:nativeReplay.funded.length,
    nativeAdmitted:nativeAdmits,causalAdmitted:mirror.causal.admits,
    nativeTerminalNetUsd:fullNet-fixedFees,
    nativeMirrorNetUsd:mirror.native.netUsd,
    causalMirrorNetUsd:mirror.causal.netUsd,
    nativeReplayTradingNetUsd:fullNet, nativeMirrorTradingNetUsd:nativeMirrorNet,
    receiptAudit:audits,anchorRows,
    parity:{nativeAdmittedFullQuantity:fullIdentityQuantity,
      nativeTradeNet:nativeNetParity,nativeDecisionAnchor:allAnchors,
      sourceNativeCampaigns:true,discreteEightSubstepExits:true,
      nativeFullMarkAndDailyGate:false,stochasticPopulationBridge:false},
    outstanding:{nativeFullMarkEquityClock:true,
      dailyLossClock:true,marketDepthPartialRejectImpact:true,
      virtualCellCoordinator:true},
    accountantInput:{native:mirror.native,causal:mirror.causal,
      funds:nativeReplay.funded.map(t=>({id:t.id,netUsd:t.netUsd,quantity:t.quantity})),
      fixedFees, expectedNativeNetUsd:fullNet-fixedFees}};
}
module.exports={receiptFactory,compare};
