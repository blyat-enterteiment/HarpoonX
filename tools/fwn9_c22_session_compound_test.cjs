"use strict";
const test=require("node:test"),A=require("node:assert/strict");
const P=require("../runtime30/fwn9_c22_session_compound.cjs");
const utc=x=>Date.parse(x);
const winter={date:"2026-01-15",open:utc("2026-01-15T14:30:00Z"),close:utc("2026-01-15T21:00:00Z")};
const summer={date:"2026-07-15",open:utc("2026-07-15T13:30:00Z"),close:utc("2026-07-15T20:00:00Z")};
const at=utc("2026-01-15T14:35:00Z");
test("C22 DST winter verified NY exchange",()=>{
 const r=P.windowFor({book:"equity",at,calendar:[winter]});
 A.equal(r.eligible,true);
 A.equal(r.window,"RTH_OPEN_30");
 A.equal(r.executionAllowed,false);
});
test("C22 summer DST and RTH late",()=>{
 const a=P.windowFor({book:"etf",at:utc("2026-07-15T13:35:00Z"),calendar:[summer]});
 const b=P.windowFor({book:"etf",at:utc("2026-07-15T19:15:00Z"),calendar:[summer]});
 A.equal(a.window,"RTH_OPEN_30");
 A.equal(b.window,"RTH_LAST_90");
});

const c=(o={})=>({id:"S1",symbol:"SYNA",book:"equity",window:"RTH_OPEN_30",
source:"OBSERVED",costProvenance:"BROKER_RECEIPTS",executableFillEvidence:true,
researchGate:"PRESPECIFIED_OOS_FWER_PASS",preRegistered:true,frozenBenchmark:true,
grossAlphaLowerBps:25,roundTripCostUpperBps:7,impactUpperBps:4,uncertaintyBufferBps:3,
pairedCashBaselineLowerBps:2,familywiseUpperP:.012,drawdownFraction:.03,
maxDailyLossFraction:.01,independentDays:30,outOfSamplePaths:40,knownAt:at-1000,...o});
test("C22 not in verified session or half day fails",()=>{
 A.equal(P.windowFor({book:"equity",at,calendar:[]}).eligible,false);
 A.equal(P.windowFor({book:"equity",at:utc("2026-01-17T16:00:00Z"),calendar:[winter]}).eligible,false);
 const early={date:"2026-11-27",open:utc("2026-11-27T14:30:00Z"),close:utc("2026-11-27T18:00:00Z")};
 A.equal(P.windowFor({book:"equity",at:utc("2026-11-27T17:40:00Z"),calendar:[early]}).window,"RTH_LAST_90");
 A.equal(P.windowFor({book:"equity",at:utc("2026-11-27T18:10:00Z"),calendar:[early]}).eligible,false);
});
test("C22 crypto UTC buckets require venue proof",()=>{
 for(const [h,w] of [["00","UTC_00_08"],["12","UTC_08_16"],["21","UTC_16_24"]]){
  const now=utc("2026-01-17T"+h+":35:00Z");
  A.equal(P.windowFor({book:"crypto",at:now,venueOpen:true}).window,w);
  A.equal(P.windowFor({book:"crypto",at:now}).eligible,false);
 }
});
test("C22 options require contract-specific verified session",()=>{
 A.equal(P.windowFor({book:"options",at,calendar:[winter]}).eligible,false);
 A.equal(P.windowFor({book:"options",at,calendar:[winter],contractSessionVerified:true}).eligible,true);
});
test("C22 cost and independent evidence produce only research rank",()=>{
 const x=P.assess(c(),{at,calendar:[winter]});
 A.equal(x.netLowerBps,11);A.equal(x.executionAllowed,false);
});
test("C22 negative after cost, p adjusted and future data are blocked",()=>{
 const ctx={at,calendar:[winter]};
 A.equal(P.assess(c({impactUpperBps:30}),ctx).eligible,false);
 A.equal(P.assess(c({familywiseUpperP:.05}),ctx).reason,"FAMILYWISE_RISK");
 A.equal(P.assess(c({knownAt:at+1}),ctx).reason,"STALE_EVIDENCE");
 A.equal(P.assess(c({independentDays:2}),ctx).reason,"INSUFFICIENT_OOS_DAYS");
 A.equal(P.assess(c({source:"SYNTHETIC"}),ctx).reason,"UNVERIFIED_FILL_AND_COST_PROVENANCE");
});

const ledger=()=>[
 {startAt:1000,endAt:2000,knownAt:2100,beginningEquityUsd:20000,
 endingEquityUsd:21000,grossEconomicPnlUsd:1050,tradingFeesUsd:40,
 externalCostsUsd:10,externalFlowUsd:0,ledgerReconciled:true,costCoverageComplete:true},
 {startAt:2200,endAt:3000,knownAt:3100,beginningEquityUsd:21000,
 endingEquityUsd:20790,grossEconomicPnlUsd:-170,tradingFeesUsd:30,
 externalCostsUsd:10,externalFlowUsd:0,ledgerReconciled:true,costCoverageComplete:true}
];
const book=()=>({observedEquityUsd:23500,settledCashUsd:21000,
 committedCashUsd:1000,unsettledCashUsd:200,outstandingGrossUsd:0,
 outstandingRiskUsd:0,reconciled:true,receiptsComplete:true,riskHalt:false});
test("C22 rejects duplicate candidate and selects CASH if unproven",()=>{
 const x=P.rank([c({source:"SYNTHETIC"})],{at,calendar:[winter]});
 A.equal(x.bestResearchId,null);A.equal(x.fallback,"CASH");
 A.equal(x.executionAllowed,false);A.equal(x.newMarketSeeds,0);
 A.throws(()=>P.rank([c(),c()],{at,calendar:[winter]}),/C22_DUPLICATE_ID/);
});
test("C22 continuous net self-financed compounding does not reset capital",()=>{
 const x=P.compound(20000,ledger());
 A.equal(x.terminalEquityUsd,20790);A.equal(x.netEconomicPnlUsd,790);
 A(Math.abs(x.compoundReturn-.0395)<1e-12);
 A(Math.abs(Math.exp(x.logGrowth)-1.0395)<1e-12);
 A.equal(x.independentAssetAccountsCombined,false);
});
test("C22 forged cash flow, equity, unknown receipt must fail closed",()=>{
 let x=ledger();x[1].beginningEquityUsd=20000;
 A.throws(()=>P.compound(20000,x),/C22_SELF_FINANCED_EQUITY_IDENTITY/);
 x=ledger();x[1].externalFlowUsd=1000;
 A.throws(()=>P.compound(20000,x),/C22_NO_UNPRICED_EXTERNAL_CASH_FLOW/);
 x=ledger();x[0].knownAt=2300;
 A.throws(()=>P.compound(20000,x),/C22_CAUSAL_RECEIPT_CLOCK/);
});
test("C22 original 20k cap survives mark-to-market equity growth",()=>{
 const x=P.buyingPower(book());
 A.equal(x.frozenCapitalBaseUsd,20000);
 A.equal(x.settledAvailableUsd,19800);
 A.equal(x.newGrossAdmissionHeadroomUsd,2400);
 A.equal(x.newRiskHeadroomUsd,50);
 A.equal(x.executionAllowed,false);
});
test("C22 notional >12 percent at mark prevents admission not forced sale",()=>{
 const b=book();b.outstandingGrossUsd=2700;
 const x=P.buyingPower(b);
 A.equal(x.newGrossAdmissionHeadroomUsd,0);
 A.equal(x.continuousGrossCapAssumed,false);
});

test("C22 integer equity and fractional crypto size from settled risk, no order",()=>{
 const b=P.buyingPower(book());
 const e=P.size(b,{book:"equity",unitPriceUsd:100,unitRiskUsd:1});
 A.equal(e.quantity,24);A.equal(e.grossNotionalUsd,2400);
 A.equal(e.executionAllowed,false);
 const cr=P.size(b,{book:"crypto",unitPriceUsd:50000,unitRiskUsd:1000});
 A.equal(cr.quantity,.048);A.equal(cr.executionAllowed,false);
 const op=P.size(b,{book:"options",unitPriceUsd:2,unitRiskUsd:1,multiplier:100});
 A.equal(op.eligible,false);
 A.equal(op.reason,"OPTIONS_CONTRACT_EXECUTOR_NOT_CERTIFIED");
});
test("C22 blocks unreconciled buying power and attempts to raise original risk",()=>{
 let b=book();b.reconciled=false;
 A.throws(()=>P.buyingPower(b),/C22_RECONCILED_FINANCING/);
 A.throws(()=>P.buyingPower(book(),{riskFraction:.005}),/C22_FROZEN_CAPS/);
 A.throws(()=>P.buyingPower(book(),{hardCapitalUsd:0}),/C22_FROZEN_CAPS/);
});
test("C22 canonical audit hash includes nested entries not just top-level",()=>{
 const a={x:1,b:{z:1,a:2},steps:[1,2]};
 const b={steps:[1,2],b:{a:2,z:1},x:1};
 A.equal(P.fingerprint(a),P.fingerprint(b));
 A.notEqual(P.fingerprint(a),P.fingerprint({...a,b:{a:3,z:1}}));
 A.throws(()=>P.fingerprint({invalid:Infinity}),/C22_NONFINITE_HASH_INPUT/);
});

test("C22 near fractional boundary never rounds to an unauthorized crypto lot",()=>{
 const cap=P.buyingPower(book());
 cap.newGrossAdmissionHeadroomUsd=.0000999;
 const result=P.size(cap,{book:"crypto",unitPriceUsd:10000,unitRiskUsd:100});
 A.equal(result.quantity,0);
 A(result.grossNotionalUsd<=cap.newGrossAdmissionHeadroomUsd);
 A.throws(()=>P.size({}, {book:"equity",unitPriceUsd:100,unitRiskUsd:1}),
  /C22_SIZE_REQUIRES_VERIFIED_CAPACITY_OBJECT/);
});

const conservativeKelly=(o={})=>({
 observedResearchGate:"PRESPECIFIED_OOS_FWER_PASS",
 pWinLower:.60,gainLowerFraction:.03,lossUpperFraction:.02,
 roundTripCostUpperFraction:.001,independentlyVerifiedLossTail:true,
 brokerFillReachability:true,capital:P.buyingPower(book()),...o
});
test("C22 fractional geometric research objective is bounded by original risk and cash",()=>{
 const r=P.geometricFraction(conservativeKelly());
 A(r.conservativeResearchFraction>0);
 A(r.conservativeResearchFraction<=.12);
 A(r.downsideRiskFractionOfEquity<=.0025+1e-12);
 A(r.conservativeExpectedLogPerTrade>0);
 A.equal(r.executionAllowed,false);
});
test("C22 negative pessimistic Kelly edge yields CASH fraction zero",()=>{
 const r=P.geometricFraction(conservativeKelly({pWinLower:.30,
  gainLowerFraction:.02,lossUpperFraction:.05}));
 A.equal(r.conservativeResearchFraction,0);
 A.equal(r.conservativeExpectedLogPerTrade,0);
});
test("C22 nonreachable OHLC stop and unverified tail must block geometric allocator",()=>{
 A.throws(()=>P.geometricFraction(conservativeKelly({
  brokerFillReachability:false})),/C22_GEOMETRIC_ATTAINABLE_LOSS_BOUND_NOT_PROVED/);
 A.throws(()=>P.geometricFraction(conservativeKelly({
  independentlyVerifiedLossTail:false})),/C22_GEOMETRIC_ATTAINABLE_LOSS_BOUND_NOT_PROVED/);
 A.throws(()=>P.geometricFraction(conservativeKelly({
  pWinLower:1.3})),/C22_GEOMETRIC_DOMAIN/);
});
