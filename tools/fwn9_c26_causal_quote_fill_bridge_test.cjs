"use strict";
const test=require("node:test"),A=require("node:assert/strict");
const C=require("../runtime30/fwn9_c26_causal_quote_fill_bridge.cjs");
const F="2026-11-06T14:00:00Z",T="2026-11-06T17:00:00Z";
function bundle(){
 const id="C26_SYNTHETIC_ACCOUNT_NOT_USER";
 const fill=(activity,order,qty,price,side,at)=>({
  id:activity,activity_type:"FILL",symbol:"SPY",
  order_id:order,currency:"USD",side,qty,price,
  type:"partial_fill",transaction_time:at
 });
 const fills=[
  fill("F1","B1","1","100","buy","2026-11-06T14:30:02Z"),
  fill("F2","B1","1","100","buy","2026-11-06T14:30:05Z"),
  fill("F3","S1","1","110","sell","2026-11-06T16:30:00Z")
 ];
 const order=(id,side,qty,average,submitted)=>({
  id,symbol:"SPY",side,qty,filled_qty:qty,
  filled_avg_price:average,submitted_at:submitted,status:"filled"
 });
 const account={
  schema:"HARPOON_FWN9_C25_ALPACA_OFFLINE_BUNDLE_1",
  export_type:"OFFLINE_ALPACA_TRADING_API_READ_ONLY",
  mode:"PAPER",currency:"USD",account_id:id,
  from:F,through:T,collected_at:"2026-11-06T19:00:00Z",
  instruments:[{symbol:"SPY",asset_class:"us_equity",currency:"USD",multiplier:1}],
  baseline_open_orders:[],
  baseline:{observed_at:F,
   account:{id,currency:"USD",cash:"20000",equity:"20000"},positions:[]},
  terminal:{observed_at:T,
   account:{id,currency:"USD",cash:"19909",equity:"20021"},
   positions:[{symbol:"SPY",asset_class:"us_equity",
    qty:"1",market_value:"112"}]},
  orders:{filter_status:"all",pagination_asserted_complete:true,
   rows:[order("B1","buy","2","100","2026-11-06T14:30:00Z"),
    order("S1","sell","1","110","2026-11-06T16:20:00Z")]},
  activities:{filter:"all",order:"asc",page_size:100,
   pages:[{request_page_token:null,complete:true,
    rows:[...fills,{id:"FEE1",activity_type:"FEE",
     net_amount:"-1",currency:"USD",date:"2026-11-06"}]}]},
  external_cost_coverage:{currency:"USD",from:F,through:T,
   categories:["DATA","INFRASTRUCTURE","INFERENCE","OTHER"],
   coverage_declared_complete:true,rows:[]}
 };
 const quotes=[
  {id:"Q_B",symbol:"SPY",feed:"sip",
   market_at:"2026-11-06T14:29:56Z",
   known_at:"2026-11-06T14:29:57Z",
   bp:"99.98",ap:"100.02",bs:"100",as:"100"},
  {id:"Q_S",symbol:"SPY",feed:"sip",
   market_at:"2026-11-06T16:19:56Z",
   known_at:"2026-11-06T16:19:57Z",
   bp:"109.98",ap:"110.02",bs:"100",as:"100"}
 ];
 const decisions=[
  {quote_id:"Q_B",order_id:"B1",side:"buy",
   decision_at:"2026-11-06T14:29:58Z",known_at:"2026-11-06T14:29:58Z",
   source:"LOCAL_OBSERVATION_JOURNAL_CLAIM"},
  {quote_id:"Q_S",order_id:"S1",side:"sell",
   decision_at:"2026-11-06T16:19:58Z",known_at:"2026-11-06T16:19:58Z",
   source:"LOCAL_OBSERVATION_JOURNAL_CLAIM"}
 ];
 const receipts=fills.map(f=>({
  activity_id:f.id,order_id:f.order_id,symbol:f.symbol,
  kind:"BROKER_ORDER_UPDATE_LOCAL_JOURNAL_CLAIM",
  execution_at:f.transaction_time,
  known_at:new Date(Date.parse(f.transaction_time)+1000).toISOString()
 }));
 return {schema:"HARPOON_FWN9_C26_CAUSAL_QUOTE_FILL_BUNDLE_1",
  capture_mode:"OFFLINE_PERSISTED_OBSERVATIONS",
  account_export:account,choices:{quotes,decisions,receipts}};
}
function rejects(change,tag){const x=bundle();change(x);
 A.throws(()=>C.classify(x),new RegExp("C26_"+tag));
}
test("C26 all three long native source FILLS match causal quote and receipt timestamps",()=>{
 const d=C.classify(bundle());
 A.equal(d.observedFillCount,3);
 A.equal(d.matchedFillCount,3);
 A.equal(d.matchedFeeActivityCount,1);
 A.equal(d.allPastQuoteAvailableBeforeDecision,true);
 A.equal(d.allFilledOrderReceiptsAfterExecution,true);
 A.equal(d.conservationC25,true);
 A.equal(d.originalOHLCFirstCrossEquivalenceCertified,false);
 A.equal(d.N9S,"NO_GO");
});
test("C26 signed implementation shortfall is against decision ask/bid NOT realized alpha",()=>{
 const r=C.classify(bundle());
 A(Math.abs(r.grossImplementationShortfallAgainstKnownQuoteUsd+0.06)<1e-7);
 A(r.details.every(x=>x.signedShortfallUsd<0));
 A(r.details.every(x=>x.sourceSpreadBps>0));
 A.equal(r.portfolioEconomicGrowthComparedToCashCertified,false);
 A.equal(r.receiptSourceAuthenticatedExternally,false);
});
test("C26 matching quote can never itself authorize an exchange fill",()=>{
 const r=C.classify(bundle());
 A.equal(r.SIPTopOfBookGuaranteesQueueFill,false);
 A.equal(r.quoteSizeSufficientGuaranteesFill,false);
 A(r.details.every(x=>x.executableQueueProof===false));
 A(r.details.every(x=>x.quoteIsAuthenticatedByIndependentBroker===false));
});
test("C26 source quote known AFTER decision fails lookahead gate",()=>{
 rejects(x=>{x.choices.quotes[0].known_at="2026-11-06T14:30:01Z";},
  "DECISION_KNOWLEDGE_CAUSALITY");
});
test("C26 source market event from future cannot be reported as known",()=>{
 rejects(x=>{x.choices.quotes[0].market_at="2026-11-06T14:30:10Z";},
  "QUOTE_KNOWN_BEFORE_EXCHANGE_EVENT");
});
test("C26 stale source quote >5sec before submit cannot enter evaluation",()=>{
 rejects(x=>{x.choices.quotes[0].market_at="2026-11-06T14:29:00Z";
  x.choices.quotes[0].known_at="2026-11-06T14:29:01Z";},
  "PREDECISION_QUOTE_TOO_STALE");
});
test("C26 order source decision cannot be learned after order submission",()=>{
 rejects(x=>{x.choices.decisions[0].known_at="2026-11-06T14:30:01Z";},
  "DECISION_KNOWLEDGE_CAUSALITY");
});
test("C26 broker receipt cannot be known before its exchange fill",()=>{
 rejects(x=>{x.choices.receipts[0].known_at="2026-11-06T14:30:01Z";},
  "RECEIPT_BEFORE_EXECUTION");
});
test("C26 fill raw event and receipt execution times must agree",()=>{
 rejects(x=>{x.choices.receipts[0].execution_at="2026-11-06T14:30:01Z";},
  "FILL_AND_LOCAL_RECEIPT_TIME_MISMATCH");
});
test("C26 missing receipt or missing order decision fails",()=>{
 rejects(x=>{x.choices.receipts.pop();},
  "FILL_QUOTE_AND_RECEIPT_NOT_LINKED");
 rejects(x=>{x.choices.decisions.pop();},
  "FILL_QUOTE_AND_RECEIPT_NOT_LINKED");
});
test("C26 duplicate or crossed quote, wrong side/asset get rejected",()=>{
 rejects(x=>{x.choices.quotes[1].id="Q_B";},"QUOTE_DUPLICATE_OR_AFTER_COLLECTION");
 rejects(x=>{x.choices.quotes[0].bp="101";},"QUOTE_CROSSED");
 rejects(x=>{x.choices.decisions[0].side="sell";},"DECISION_SIDE");
 rejects(x=>{x.choices.quotes[0].symbol="QQQ";},"QUOTE_ASSET_NOT_IN_ACCOUNT_CATALOG");
});
test("C26 IEX feed comparison allowed as diagnostic but cannot be NBBO",()=>{
 const x=bundle();x.choices.quotes[0].feed="iex";
 const r=C.classify(x);
 A.equal(r.details[0].quoteIsConsolidatedEquityNBBO,false);
 A.equal(r.receiptSourceAuthenticatedExternally,false);
});
test("C26 stated L1 displayed size smaller than fill is not fill-proof",()=>{
 const x=bundle();x.choices.quotes[0].as="0.1";
 const r=C.classify(x);
 A.equal(r.details[0].displayedSizeAtPreDecisionCoversFillQuantity,false);
 A.equal(r.SIPTopOfBookGuaranteesQueueFill,false);
});
test("C26 wrong quote feed for asset class fails",()=>{
 rejects(x=>{x.choices.quotes[0].feed="us";},"QUOTE_EQUITY_FEED");
});
test("C26 C25 cash tampering must fail before quote evidence certification",()=>{
 const x=bundle();x.account_export.terminal.account.cash="19910";
 x.account_export.terminal.account.equity="20022";
 A.throws(()=>C.classify(x),/C25_CASH_FROM_ACTIVITY_RECONCILIATION/);
});
test("C26 fee/commission missing triggers economic blocker not false profits",()=>{
 const x=bundle();x.account_export.external_cost_coverage=null;
 const r=C.classify(x);
 A.equal(r.portfolioEconomicGrowthComparedToCashCertified,false);
 A.equal(r.population_EA_EU_bounded,false);
});
test("C26 duplicate receipts and unlinked receipt fail closed",()=>{
 rejects(x=>{x.choices.receipts[1].activity_id="F1";},
  "RECEIPT_DUPLICATE_KIND_OR_AFTER_COLLECTION");
 const x=bundle();x.choices.receipts.push({
  activity_id:"F_NEW",order_id:"B1",symbol:"SPY",
  kind:"BROKER_ORDER_UPDATE_LOCAL_JOURNAL_CLAIM",
  execution_at:"2026-11-06T14:31:00Z",known_at:"2026-11-06T14:31:01Z"
 });
 A.throws(()=>C.classify(x),/C26_UNMATCHED_RECEIPT_NO_FILL/);
});
test("C26 non-USD/stock option filler and unsupported contract refuted via C25",()=>{
 const x=bundle();x.account_export.instruments[0].asset_class="option";
 A.throws(()=>C.classify(x),/C25_INSTRUMENT_USD_LONG_MULTIPLIER/);
});
test("C26 no original M10, no trade account execution, no quote-source signing claim",()=>{
 const r=C.classify(bundle());
 A.equal(r.originalM10FinalSealed,3200);
 A.equal(r.createdEconomicTradingAccounts,0);
 A.equal(r.submittedOrders,0);
 A.equal(r.generatedNewMarketSeeds,0);
 A.equal(r.thirdPartyBrokerFillAuthenticityCertified,false);
 A.equal(r.fundingFromKnownSettledCashBeforeEveryOrderCertified,false);
});
test("C26 missing any actual account/quote/decision/receipt reports BLOCKED",()=>{
 const d=C.absence();
 A.equal(d.status,"BLOCKED_CAUSAL_BID_ASK_AND_BROKER_ORDER_RECEIPTS_NOT_AVAILABLE");
 A.equal(d.netGrowth_vs_CASH,null);
 A.equal(d.financialGO,false);
 A.equal(d.N9S,"NO_GO");
});

const fs=require("node:fs"),os=require("node:os"),path=require("node:path");
const CLI=require("./fwn9_c26_readonly_cli.cjs");
test("C26 CLI no private bundle yields explicit financial evidence BLOCKED",()=>{
 A.equal(CLI.args([])["--bundle"],undefined);
 A.equal(C.absence().financialGO,false);
});
test("C26 CLI never reads M10 final/holdout even if it looks like an Alpaca export",()=>{
 A.throws(()=>CLI.guarded("/tmp/holdout/sensitive.json"),/C26_CLI_SEALED_M10_PATH/);
 A.throws(()=>CLI.guarded("/tmp/M10_final/sensitive.json"),/C26_CLI_SEALED_M10_PATH/);
 A.throws(()=>CLI.args(["--bundle","/tmp/a","--out","/tmp/a"]),
  /C26_CLI_REQUIRED_BUNDLE/);
});
test("C26 valid synthetic offline combined evidence writes 0600 private report",()=>{
 const tmp=fs.mkdtempSync(path.join(os.tmpdir(),"fwn9-c26-"));
 try{
  const inp=path.join(tmp,"synthetic.json"),out=path.join(tmp,"report.json");
  fs.writeFileSync(inp,JSON.stringify(bundle()),{mode:0o600});
  A.equal(CLI.run(["--bundle",inp,"--out",out]),0);
  const st=fs.statSync(out);
  A.equal(st.mode&0o777,0o600);
  const result=JSON.parse(fs.readFileSync(out,"utf8"));
  A.equal(result.matchedFillCount,3);
  A.equal(result.accountIdentityPrinted,false);
  A.equal(result.N9S,"NO_GO");
  A.equal(result.inputShaAuthenticatesBroker,false);
  A.throws(()=>CLI.run(["--bundle",inp,"--out",out]),/EEXIST/);
 }finally{fs.rmSync(tmp,{recursive:true,force:true});}
});
test("C26 missing receipt through CLI rejects without creating a report",()=>{
 const tmp=fs.mkdtempSync(path.join(os.tmpdir(),"fwn9-c26-missing-"));
 try{
  const inp=path.join(tmp,"bad.json"),out=path.join(tmp,"not-created.json");
  const x=bundle();x.choices.receipts.pop();
  fs.writeFileSync(inp,JSON.stringify(x),{mode:0o600});
  A.throws(()=>CLI.run(["--bundle",inp,"--out",out]),
   /C26_FILL_QUOTE_AND_RECEIPT_NOT_LINKED/);
  A.equal(fs.existsSync(out),false);
 }finally{fs.rmSync(tmp,{recursive:true,force:true});}
});

test("C26 quote received 100ns AFTER decision in same millisecond must be rejected",()=>{
 const x=bundle();
 x.choices.quotes[0].known_at="2026-11-06T14:29:58.000000100Z";
 x.choices.quotes[0].market_at="2026-11-06T14:29:56.000000001Z";
 x.choices.decisions[0].decision_at="2026-11-06T14:29:58.000000000Z";
 x.choices.decisions[0].known_at="2026-11-06T14:29:58.000000000Z";
 A.equal(Date.parse(x.choices.quotes[0].known_at),
  Date.parse(x.choices.decisions[0].decision_at));
 A.throws(()=>C.classify(x),/C26_DECISION_KNOWLEDGE_CAUSALITY/);
});
test("C26 receipt at +1ns within the same millisecond cannot match original FILL",()=>{
 const x=bundle();
 x.choices.receipts[0].execution_at="2026-11-06T14:30:02.000000001Z";
 A.equal(Date.parse(x.choices.receipts[0].execution_at),
  Date.parse(x.account_export.activities.pages[0].rows[0].transaction_time));
 A.throws(()=>C.classify(x),/C26_FILL_AND_LOCAL_RECEIPT_TIME_MISMATCH/);
});
test("C26 nanosecond timestamp order independent of textual milliseconds format",()=>{
 const a=C.stampNs("2026-11-06T14:29:58.123456789Z","TEST"),
  b=C.stampNs("2026-11-06T14:29:58.123456790Z","TEST");
 A.equal(b-a,1n);
 A.throws(()=>C.stampNs("2026-11-06T14:29:58.1234567891Z","TEST"),
  /C26_TEST/);
});
