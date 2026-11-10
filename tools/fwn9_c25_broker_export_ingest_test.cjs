"use strict";
/** C25: deterministic synthetic engineering receipts. NO actual broker/export,
 * no trading signals, no market seeds, no financial alpha evaluation.
 */
const test=require("node:test"),A=require("node:assert/strict");
const C=require("../runtime30/fwn9_c25_broker_export_ingest.cjs");
const FROM="2026-11-06T14:00:00Z",TO="2026-11-06T17:00:00Z";
function fixture(){
 const acc="C25_SYNTHETIC_NOT_REAL_ACCOUNT",o1="C25_BUY",o2="C25_SELL";
 const f=(id,order,qty,price,side,time,type="partial_fill")=>({
  id,activity_type:"FILL",asset_class:"us_equity",
  order_id:order,currency:"USD",symbol:"SPY",type,side,
  qty,price,transaction_time:time
 });
 const a=[
  f("FILL_1",o1,"1","100","buy","2026-11-06T14:30:02Z"),
  f("FILL_2",o1,"1","100","buy","2026-11-06T14:30:05Z","fill"),
  f("FILL_3",o2,"1","110","sell","2026-11-06T16:30:00Z","fill"),
  {id:"FEE_1",activity_type:"FEE",date:"2026-11-06",net_amount:"-1",currency:"USD"}
 ];
 return {
  schema:"HARPOON_FWN9_C25_ALPACA_OFFLINE_BUNDLE_1",
  export_type:"OFFLINE_ALPACA_TRADING_API_READ_ONLY",
  mode:"PAPER",currency:"USD",account_id:acc,
  from:FROM,through:TO,collected_at:"2026-11-06T19:00:00Z",
  instruments:[{symbol:"SPY",asset_class:"us_equity",currency:"USD",multiplier:1}],
  baseline_open_orders:[],
  baseline:{observed_at:FROM,account:{id:acc,currency:"USD",equity:"20000",cash:"20000"},positions:[]},
  terminal:{observed_at:TO,
   account:{id:acc,currency:"USD",equity:"20021",cash:"19909"},
   positions:[{symbol:"SPY",qty:"1",market_value:"112",asset_class:"us_equity"}]},
  orders:{filter_status:"all",pagination_asserted_complete:true,rows:[
   {id:o1,side:"buy",symbol:"SPY",qty:"2",filled_qty:"2",
    filled_avg_price:"100",submitted_at:"2026-11-06T14:30:00Z",status:"filled"},
   {id:o2,side:"sell",symbol:"SPY",qty:"1",filled_qty:"1",
    filled_avg_price:"110",submitted_at:"2026-11-06T16:20:00Z",status:"filled"}
  ]},
  activities:{filter:"all",order:"asc",page_size:100,
   pages:[{request_page_token:null,rows:a,complete:true}]},
  external_cost_coverage:{currency:"USD",from:FROM,through:TO,
   categories:["DATA","INFRASTRUCTURE","INFERENCE","OTHER"],
   coverage_declared_complete:true,rows:[]}
 };
}
function expectThrow(change,code){
 const x=fixture();change(x);
 A.throws(()=>C.certify(x),new RegExp("(?:C25_)?"+code));
}
test("C25 real native parse and independent exact synthetic cash, shares and order activity",()=>{
 const o=C.certify(fixture());
 A.equal(o.validated.orders,2);
 A.equal(o.validated.fills,3);
 A.equal(o.validated.activities,4);
 A.equal(o.validated.reportedFeeCashUsd,-1);
 A.equal(o.validated.algebraicAccountPnlUsd,21);
 A.equal(o.validated.conditionalAfterDeclaredCostsPnlUsd,21);
 A.equal(o.validated.independentCashAndInventoryReconciled,true);
 A.equal(o.sourceInputExternallyAuthenticated,false);
 A.equal(o.admission.familywiseOutsideSampleNetAlphaCertified,false);
 A.equal(o.admission.N9S,"NO_GO");
});
test("C25 absence of broker export always BLOCKED not empty profit",()=>{
 const r=C.missingEvidence();
 A.equal(r.status,"BLOCKED_NO_AUTHENTICATED_PRIVATE_BROKER_EXPORT");
 A.equal(r.financialPerformanceDemonstrated,false);
 A.equal(r.holdoutM10Sealed,3200);
});
test("C25 independent instrument qty arithmetic rejects forged broker cash and NAV",()=>{
 expectThrow(x=>{x.terminal.account.cash="19910";x.terminal.account.equity="20022";},"CASH_FROM_ACTIVITY_RECONCILIATION");
 expectThrow(x=>{x.terminal.account.equity="20022";},"NAV_MISMATCH");
});
test("C25 tampered order average fill or total quantity fails closed",()=>{
 expectThrow(x=>{x.orders.rows[0].filled_avg_price="105";},"ORDER_WEIGHTED_FILL_AVERAGE_MISMATCH");
 expectThrow(x=>{x.orders.rows[0].filled_qty="1.5";},"ORDER_ACTIVITY_FILL_QUANTITY_MISMATCH");
});
test("C25 forged known order side and missing exported order rejected",()=>{
 expectThrow(x=>{x.orders.rows[0].side="sell";},"ORDER_FILL_SYMBOL_SIDE_TIME");
 expectThrow(x=>{x.orders.rows.pop();},"FILL_WITHOUT_EXPORTED_ORDER");
});
test("C25 duplicate trade activity and two-page cursor loops rejected",()=>{
 expectThrow(x=>{x.activities.pages[0].rows[1].id="FILL_1";},"DUPLICATE_ACTIVITY_ID");
 expectThrow(x=>{x.activities.page_size=2;
   const r=x.activities.pages[0].rows;
   x.activities.pages=[
    {request_page_token:null,rows:r.slice(0,2),complete:false},
    {request_page_token:"BAD",rows:r.slice(2),complete:false},
    {request_page_token:"FEE_1",rows:[],complete:true}
   ];
  },"ACTIVITY_CURSOR_OR_SIZE");
});
test("C25 exhaustive last page must be smaller than page_size",()=>{
 expectThrow(x=>{x.activities.page_size=4;},"LAST_PAGE_NOT_EXHAUSTED");
});
test("C25 complete three-page activity pagination with exact last cursor is supported",()=>{
 const x=fixture(),a=x.activities.pages[0].rows;
 x.activities.page_size=2;
 x.activities.pages=[
  {request_page_token:null,rows:a.slice(0,2),complete:false},
  {request_page_token:"FILL_2",rows:a.slice(2,4),complete:false},
  {request_page_token:"FEE_1",rows:[],complete:true}
 ];
 A.equal(C.certify(x).validated.fills,3);
});
test("C25 incomplete activity page / source query must not appear exhaustive",()=>{
 expectThrow(x=>{x.activities.pages[0].complete=false;},"ACTIVITY_PAGE_TERMINATOR");
 expectThrow(x=>{x.activities.filter="FILL";},"ACTIVITY_QUERY_CONTRACT");
});
test("C25 action without source-long inventory cannot short/sell extra",()=>{
 expectThrow(x=>{x.activities.pages[0].rows[2].qty="3";
   x.orders.rows[1].qty="3";x.orders.rows[1].filled_qty="3";
   x.orders.rows[1].filled_avg_price="110";
   x.terminal.account.cash="20129";
   x.terminal.account.equity="20129";
   x.terminal.positions=[];
  },"NO_UNDISCLOSED_SHORT_OR_SELL_BEFORE_INVENTORY");
});
test("C25 late/future activity or out of window cannot finance original book",()=>{
 expectThrow(x=>{x.activities.pages[0].rows[0].transaction_time="2026-11-06T18:00:00Z";},"FILL_OUTSIDE_EXPORTED_ACCOUNT_PERIOD");
});
test("C25 no prebaseline open order silently adopted as complete",()=>{
 expectThrow(x=>{x.baseline_open_orders=[{id:"OLDER"}];},"PREBASELINE_PENDING_ORDERS_REQUIRE_SEPARATE_RECONCILIATION");
});
test("C25 no options, borrowed short or unknown cash currency",()=>{
 expectThrow(x=>{x.instruments[0].asset_class="option";},"INSTRUMENT_USD_LONG_MULTIPLIER");
 expectThrow(x=>{x.baseline.account.currency="EUR";},"ACCOUNT_ID_AND_CURRENCY");
});
test("C25 fee sign, missing coverage and no double account NAV commission",()=>{
 expectThrow(x=>{x.activities.pages[0].rows[3].net_amount="1";},"FEE_SIGN");
 const x=fixture();delete x.external_cost_coverage;
 const r=C.certify(x);
 A.equal(r.validated.conditionalAfterDeclaredCostsPnlUsd,null);
 A(r.blockers.includes("EXTERNAL_COST_COVERAGE_INCOMPLETE"));
});
test("C25 external costs not in NAV subtracted once while broker FEE already in NAV",()=>{
 const x=fixture();
 x.external_cost_coverage.rows=[
  {id:"EXTRA1",at:"2026-11-06T16:50:00Z",known_at:"2026-11-06T18:00:00Z",
   reference:"C25_SYNTHETIC_INVOICE",category:"DATA",amount_usd:"2",
   already_in_account:false}
 ];
 const r=C.certify(x);
 A.equal(r.validated.algebraicAccountPnlUsd,21);
 A.equal(r.validated.externalCostsNotInNavUsd,2);
 A.equal(r.validated.conditionalAfterDeclaredCostsPnlUsd,19);
 A.equal(r.admission.realCompoundedOutperformanceVsCashCertified,false);
});
test("C25 claimed included fee without explicit linkage cannot be charged twice",()=>{
 expectThrow(x=>{x.external_cost_coverage.rows=[
  {id:"FAKE",at:"2026-11-06T16:50:00Z",known_at:"2026-11-06T17:00:00Z",
   reference:"NONE",category:"DATA",amount_usd:"1",already_in_account:true}
  ];},"C25_FEES_ALREADY_IN_NAV_NOT_DOUBLE_CHARGED");
});
test("C25 private export SHA cannot authenticate origin or infer optimal hour",()=>{
 const x=fixture(),r=C.certify(x);
 const digest=r.sourceDigestSha256;
 A.match(digest,/^[0-9a-f]{64}$/);
 x.orders.rows[0].status="canceled";
 A.notEqual(C.certify(x).sourceDigestSha256,digest);
 A.equal(C.certify(x).admission.independentFinancialProfitabilityLevel9,false);
});
test("C25 absent broker-knownAt prevents any time causal admission proof",()=>{
 const r=C.certify(fixture());
 A.equal(r.admission.receiptLevelPredecisionFiltrationCertified,false);
 A(r.blockers.includes("NO_TRUSTWORTHY_PREDECISION_KNOWN_AT_OR_EXCHANGE_QUEUE_FILLS"));
});
test("C25 unknown vendor activity cannot be papered over as fee",()=>{
 expectThrow(x=>{x.activities.pages[0].rows[3].activity_type="CORR";},"UNSUPPORTED_ACTIVITY_TYPE");
});
test("C25 risk of external cash flows blocks simple compound without TWR",()=>{
 const x=fixture();x.activities.pages[0].rows.push({
  id:"CSD_1",activity_type:"CSD",currency:"USD",date:"2026-11-06",net_amount:"1000"
 });
 x.terminal.account.cash="20909";x.terminal.account.equity="21021";
 const r=C.certify(x);
 A(r.blockers.includes("EXTERNAL_CAPITAL_FLOW_REQUIRES_TWR"));
 A.equal(r.validated.recordedCashFlowUsd,1000);
 A.equal(r.validated.algebraicAccountPnlUsd,21);
});
test("C25 fully synthetic smoke uses zero new broker orders or M10 final",()=>{
 const x=C.certify(fixture());
 A.equal(x.placedBrokerOrders,0);
 A.equal(x.createdEconomicTrialAccounts,0);
 A.equal(x.holdoutM10Sealed,3200);
});
module.exports={fixture};

test("C25 official Alpaca TradeActivity FILL without asset_class uses bound asset catalog",()=>{
 const x=fixture();
 for(const r of x.activities.pages[0].rows)if(r.activity_type==="FILL")delete r.asset_class;
 const y=C.certify(x);
 A.equal(y.validated.fills,3);
 A.equal(y.validated.independentCashAndInventoryReconciled,true);
});
test("C25 if explicit FILL asset class disagrees with catalog reject",()=>{
 const x=fixture();x.activities.pages[0].rows[0].asset_class="crypto";
 A.throws(()=>C.certify(x),/C25_FILL_ASSET_CLASS_MISMATCH/);
});

test("C25 source order status must agree with filled, partial and rejected quantities",()=>{
 expectThrow(x=>{x.orders.rows[0].status="new";},"ORDER_NONFILLED_STATUS_QUANTITY");
 expectThrow(x=>{x.orders.rows[0].qty="3";},"ORDER_FILLED_STATUS_QUANTITY");
 expectThrow(x=>{x.orders.rows[0].status="partially_filled";},
  "ORDER_PARTIAL_STATUS_QUANTITY");
 const canceled=fixture();
 canceled.orders.rows[0].status="canceled";
 A.equal(C.certify(canceled).validated.orders,2);
});
