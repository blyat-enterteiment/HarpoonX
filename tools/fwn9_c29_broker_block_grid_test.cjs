"use strict";
/** C29 full grid and per-block broker source tests: synthetic engineering only. */
const test=require("node:test"),A=require("node:assert/strict");
const R=require("../runtime30/fwn9_c29_frozen_assignments.cjs");
const G=require("../runtime30/fwn9_c29_segmented_source_coverage.cjs");
const B=require("../runtime30/fwn9_c29_broker_block_reconciliation.cjs");
const HOUR=3600000,START=Date.parse("2026-11-13T00:00:00Z");
const PLAN=()=>R.freeze({studyId:"C29_SAFE_SOURCE_TEST_ONLY",
 registeredAt:START-72*HOUR,startAt:START,cycles:4,
 assignmentNonce:"C29_PRESPECIFIED_DESIGN_CRYPTO_NONCE_NOT_MARKET_SEED"});
const step=300000;
function grid(p){const start=p.startAt,end=p.blocks.at(-1).fundingReviewEndAt;
 return Array.from({length:(end-start)/step},(_,i)=>start+i*step);}
function segments(p){
 const a=grid(p);
 return [a.slice(0,50000),a.slice(50000)].map(expectedBars=>({
  expectedBars,completeC27:true,completeC28:true}));
}
function account(b,mode="PAPER"){
 const at=x=>new Date(x).toISOString(),cash="20000";
 return {
  schema:"HARPOON_FWN9_C25_ALPACA_OFFLINE_BUNDLE_1",
  export_type:"OFFLINE_ALPACA_TRADING_API_READ_ONLY",
  mode,currency:"USD",account_id:"C29_ONE_SYNTHETIC_TEST_ACCOUNT",
  from:at(b.startAt),through:at(b.washoutEndAt),
  collected_at:at(b.washoutEndAt+1000),
  instruments:[{symbol:"SPY",asset_class:"us_equity",currency:"USD",multiplier:1}],
  baseline_open_orders:[],
  baseline:{observed_at:at(b.startAt),
   account:{id:"C29_ONE_SYNTHETIC_TEST_ACCOUNT",currency:"USD",cash,equity:cash},
   positions:[]},
  terminal:{observed_at:at(b.washoutEndAt),
   account:{id:"C29_ONE_SYNTHETIC_TEST_ACCOUNT",currency:"USD",cash,equity:cash},
   positions:[]},
  orders:{filter_status:"all",pagination_asserted_complete:true,rows:[]},
  activities:{filter:"all",order:"asc",page_size:100,
   pages:[{request_page_token:null,complete:true,rows:[]}]},
  external_cost_coverage:{
   currency:"USD",from:at(b.startAt),through:at(b.washoutEndAt),
   categories:["DATA","INFRASTRUCTURE","INFERENCE","OTHER"],
   rows:[],coverage_declared_complete:true}
 };
}
function data(p){return p.blocks.map(b=>({blockId:b.blockId,arm:b.arm,
 cashReferenceRate:0,cashRateKnownAt:b.startAt-1000,
 accountExport:account(b)}));}
test("C29 complete 4-cycle UTC grid requires 55,680 prebar five-minute observations",()=>{
 const p=PLAN(),g=G.auditGrids(p,segments(p));
 A.equal(g.sourceVerifiedBars,55680);
 A.equal(g.expectedBars,55680);
 A.equal(g.segmentCount,2);
 A.equal(g.fullCalendarVerifiedAgainstPreregisteredUTCGrid,true);
 A.equal(g.sourceFromRealProductionAuthenticated,false);
 A.equal(g.offlineEconomicGO,false);
});
test("C29 one removed five-minute bar in second segment fails continuous source proof",()=>{
 const p=PLAN(),s=segments(p);s[1].expectedBars.splice(5,1);
 A.throws(()=>G.auditGrids(p,s),/C29G_MISSING_OR_DUPLICATED_FIVE_MINUTE_BAR/);
});
test("C29 fabricated segment complete flags cannot be accepted as complete",()=>{
 const p=PLAN(),s=segments(p);s[0].completeC27=false;
 A.throws(()=>G.auditGrids(p,s),/C29G_SOURCE_C27_C28_BOTH_COMPLETE/);
});
test("C29 duplicated segment clock is rejected, no silent second capital campaign",()=>{
 const p=PLAN(),s=segments(p);s[1].expectedBars.unshift(s[0].expectedBars.at(-1));
 A.throws(()=>G.auditGrids(p,s),
  /C29G_MISSING_OR_DUPLICATED_FIVE_MINUTE_BAR/);
});
test("C29 account bridge reconciles exact no-order CASH block in one funded source",()=>{
 const p=PLAN(),r=B.auditBlock(p.blocks.find(b=>b.arm==="CASH"),
  data(p).find(x=>x.arm==="CASH"));
 A.equal(r.ledgerReconciled,true);
 A.equal(r.flatAtStart,true);
 A.equal(r.flatAtWashoutEnd,true);
 A.equal(r.tradingFeesUsd,0);
 A.equal(r.sourceFillActivityDigests.length,0);
 A.equal(r.C25C26RealAccountAuthenticationIndependentlyVerified,false);
});
test("C29 empty real broker source is BLOCKED not zero net alpha",()=>{
 const r=B.absent();
 A.equal(r.status,"BLOCKED_NO_AUTHENTICATED_NATIVE_PRODUCER_AND_BROKER_RECEIPTS");
 A.equal(r.netGrowthVsCash,null);
 A.equal(r.financialGO,false);
 A.equal(r.M10FinalSealed,3200);
});
test("C29 wrong C25 from-to interval fails assigned sample clock",()=>{
 const p=PLAN(),b=p.blocks[0],row=data(p)[0];
 row.accountExport.from=new Date(b.startAt+120000).toISOString();
 row.accountExport.baseline.observed_at=row.accountExport.from;
 A.throws(()=>B.auditBlock(b,row),/C29B_SOURCE_INTERVAL_NOT_MATCHING_PREASSIGNED_BLOCK/);
});
test("C29 a CASH block cannot conceal active orders even if no fills",()=>{
 const p=PLAN(),b=p.blocks.find(x=>x.arm==="CASH");
 const row=data(p).find(x=>x.arm==="CASH");
 row.accountExport.orders.rows.push({
  id:"UNFILLED_CASH_ORDER",symbol:"SPY",side:"buy",qty:"1",
  filled_qty:"0",filled_avg_price:null,status:"canceled",
  submitted_at:new Date(b.startAt+1000).toISOString()
 });
 A.throws(()=>B.auditBlock(b,row),/C29B_CASH_ARM_CONTAINS_BROKER_ORDERS/);
});
test("C29 source C25 cashflow external deposit blocks self financed compounding",()=>{
 const p=PLAN(),r=data(p)[0];
 r.accountExport.activities.pages[0].rows.push({
  id:"CSD",activity_type:"CSD",date:new Date(p.startAt).toISOString().slice(0,10),
  currency:"USD",net_amount:"500"
 });
 // Source C25 detects the mismatched account cash even earlier.
 A.throws(()=>B.auditBlock(p.blocks[0],r),
  /C25_CASH_FROM_ACTIVITY_RECONCILIATION/);
});
test("C29 study can reconcile 32 deterministic no-trade periods but cannot prove edge",()=>{
 const p=PLAN(),s=G.auditGrids(p,segments(p));
 const r=B.auditStudy({plan:p,blocks:data(p),sourceProof:s});
 A.equal(r.observedIntentionToTreatBlocks,32);
 A.equal(r.originalBrokerAccountIdNotReturned,true);
 A.equal(r.realProspectiveOutperformanceCertified,false);
 A.equal(r.terminalAccountWealthUsd,20000);
 A.equal(r.finalFinancialGO,false);
 A.equal(r.N9S,"NO_GO");
 A.equal(r.holdoutM10Sealed,3200);
});
test("C29 all eight arms must have real rows, not imputable counterfactual fills",()=>{
 const p=PLAN(),s=G.auditGrids(p,segments(p));
 A.throws(()=>B.auditStudy({plan:p,blocks:data(p).slice(0,31),
  sourceProof:s}),/C29B_ALL_PRESPECIFIED_BLOCK_SOURCE_EXPORTS_REQUIRED/);
});
test("C29 single account identity cannot change despite redacted user-facing ID",()=>{
 const p=PLAN(),s=G.auditGrids(p,segments(p)),d=data(p);
 d[10].accountExport.account_id="DIFFERENT_ACCOUNT";
 d[10].accountExport.baseline.account.id="DIFFERENT_ACCOUNT";
 d[10].accountExport.terminal.account.id="DIFFERENT_ACCOUNT";
 A.throws(()=>B.auditStudy({plan:p,blocks:d,sourceProof:s}),
  /C29B_MULTIPLE_BROKER_ACCOUNTS/);
});
test("C29 original strategy unexecuted source block cannot receive invented PnL",()=>{
 const p=PLAN(),r=data(p).find(x=>x.arm==="ORIGINAL_BASELINE");
 r.accountExport.terminal.account.equity="20100";
 A.throws(()=>B.auditBlock(p.blocks.find(x=>x.arm==="ORIGINAL_BASELINE"),r),
  /C25_NAV_MISMATCH|C29B_SOURCE_NATIVE_ECONOMIC_NAV_PARITY/);
});
