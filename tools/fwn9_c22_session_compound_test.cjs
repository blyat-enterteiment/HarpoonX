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
