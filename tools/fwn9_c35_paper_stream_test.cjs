"use strict";
const test=require("node:test");
const A=require("node:assert/strict");
const fs=require("node:fs"),os=require("node:os"),path=require("node:path");
const W=require("../runtime30/fwn9_c35_paper_trade_updates.cjs");
const J=require("../runtime30/fwn9_c35_paper_stream_journal.cjs");
const CLI=require("./fwn9_c35_capture_paper_stream.cjs");
const C25=require("../runtime30/fwn9_c25_broker_export_ingest.cjs");
const T1="2026-11-06T14:30:02Z",T2="2026-11-06T16:30:02Z";
const RX1=Date.parse("2026-11-06T14:30:03Z"),
 RX2=Date.parse("2026-11-06T16:30:03Z");
function frame(event,{orderId="ORDER_BUY",executionId="EXEC_1",timestamp=T1,
 qty="1",price="100",symbol="SPY",side="buy",orderClass="simple"}={}){
 const order={id:orderId,client_order_id:"CLIENT_TEST",
  symbol,side,order_class:orderClass,status:event==="fill"?"filled":"partially_filled",
  submitted_at:"2026-11-06T14:30:00Z"};
 return Buffer.from(JSON.stringify({stream:"trade_updates",data:{
  event,order,execution_id:executionId,timestamp,qty,price,
  position_qty:"1"
 }}),"utf8");
}
function fixture(){
 const from="2026-11-06T14:00:00Z",through="2026-11-06T17:00:00Z";
 const account={id:"C35_SYNTHETIC_NOT_ALPACA",cash:"20000",equity:"20000",currency:"USD"};
 const after={...account,cash:"20001",equity:"20001"};
 const buys={id:"ORDER_BUY",symbol:"SPY",side:"buy",qty:"1",
  filled_qty:"1",filled_avg_price:"100",submitted_at:"2026-11-06T14:30:00Z",
  status:"filled"};
 const sells={id:"ORDER_SELL",symbol:"SPY",side:"sell",qty:"1",
  filled_qty:"1",filled_avg_price:"101",submitted_at:"2026-11-06T16:30:00Z",
  status:"filled"};
 const activities=[
  {id:"ACT_BUY",order_id:buys.id,symbol:"SPY",side:"buy",
   activity_type:"FILL",type:"fill",qty:"1",price:"100",transaction_time:T1},
  {id:"ACT_SELL",order_id:sells.id,symbol:"SPY",side:"sell",
   activity_type:"FILL",type:"fill",qty:"1",price:"101",transaction_time:T2}
 ];
 return {schema:"HARPOON_FWN9_C25_ALPACA_OFFLINE_BUNDLE_1",
  export_type:"OFFLINE_ALPACA_TRADING_API_READ_ONLY",mode:"PAPER",currency:"USD",
  account_id:account.id,from,through,collected_at:"2026-11-06T17:01:00Z",
  instruments:[{symbol:"SPY",asset_class:"us_equity",currency:"USD",multiplier:1}],
  baseline_open_orders:[],
  baseline:{observed_at:from,account,positions:[]},
  terminal:{observed_at:through,account:after,positions:[]},
  orders:{filter_status:"all",pagination_asserted_complete:true,rows:[buys,sells]},
  activities:{filter:"all",order:"asc",page_size:100,
   pages:[{request_page_token:null,rows:activities,complete:true}]},
  external_cost_coverage:{currency:"USD",from,through,
   categories:["DATA","INFRASTRUCTURE","INFERENCE","OTHER"],
   coverage_declared_complete:true,rows:[]}
 };
}
function records(){
 return [
  W.observe(frame("fill"),RX1),
  W.observe(frame("fill",{orderId:"ORDER_SELL",executionId:"EXEC_2",
   timestamp:T2,price:"101",side:"sell"}),RX2)
 ];
}
function withDir(fn){
 const root=fs.mkdtempSync(path.join(os.tmpdir(),"harpoon-c35-"));
 try{return fn(path.join(root,"private"))}
 finally{fs.rmSync(root,{recursive:true,force:true});}
}
test("C35 native C25 two-fill reconciliation is strictly scoped synthetic",()=>{
 const f=fixture();
 A.equal(C25.certify(f).validated.algebraicAccountPnlUsd,1);
 const v=W.reconcile({accountExport:f,streamRecords:records()});
 A.equal(v.accountFills,2);A.equal(v.matchedSourceFillEvents,2);
 A.equal(v.matchedReceipts.length,2);
 A.equal(v.completeStreamCoverageProven,false);
 A.equal(v.providerSignedSourceAndClockAuthenticated,false);
 A.equal(v.financialGO,false);
});
test("C35 stream parses actual Alpaca PAPER binary JSON buffer",()=>{
 const v=W.observe(frame("partial_fill"),RX1);
 A.equal(v.event,"partial_fill");A.equal(v.qty,"1");
 A.equal(v.executionId,"EXEC_1");A.equal(v.brokerOrderId,"ORDER_BUY");
 A.equal(v.brokerOrderCreatedByThisObserver,false);
 A.equal(v.alpacaProviderEventCryptographicallySigned,false);
});
test("C35 authenticated authorization and listening ACK order is required",()=>{
 const s=W.session();
 const auth=Buffer.from(JSON.stringify({stream:"authorization",
  data:{status:"authorized",action:"authenticate"}}));
 const listening=Buffer.from(JSON.stringify({stream:"listening",
  data:{streams:["trade_updates"]}}));
 A.equal(s.message(auth).type,"SEND_LISTEN");
 A.equal(s.message(listening).type,"READY");
 A.equal(s.message(frame("fill"),RX1).type,"EVENT");
 A.equal(s.status().events,1);
 A.equal(s.close().state,"CLOSED_UNPROVEN_GAP");
 A.equal(s.status().continuousAuthenticatedCoverageProved,false);
});
test("C35 disallows trade event without prior stream auth and subscribe",()=>{
 const s=W.session();
 A.throws(()=>s.message(frame("fill"),RX1),/C35_PAPER_AUTH_ACK_REQUIRED/);
});
test("C35 unauthorized account and subscription gaps fail closed",()=>{
 const s=W.session();
 A.throws(()=>s.message(JSON.stringify({stream:"authorization",
  data:{status:"unauthorized"}})),/C35_PAPER_AUTH_ACK_REQUIRED/);
 const t=W.session();
 t.message(JSON.stringify({stream:"authorization",data:{status:"authorized"}}));
 A.throws(()=>t.message(JSON.stringify({stream:"listening",
  data:{streams:[]}})),/C35_TRADE_UPDATES_LISTEN_ACK_REQUIRED/);
});
test("C35 recognizes non-fill cancellation without inventing qty/fill",()=>{
 const r=W.observe(frame("canceled"),RX1);
 A.equal(r.event,"canceled");A.equal(r.executionId,null);
 A.equal(r.qty,null);A.equal(r.price,null);
});
test("C35 rejects broker timestamp not causally earlier than receipt",()=>{
 A.throws(()=>W.observe(frame("fill",{timestamp:"2026-11-06T14:30:04Z"}),RX1),
  /C35_BROKER_EVENT_AFTER_LOCAL_RECEIPT/);
});
test("C35 duplicate execution ID is rejected in stateful stream",()=>{
 const s=W.session();
 s.message(JSON.stringify({stream:"authorization",data:{status:"authorized"}}));
 s.message(JSON.stringify({stream:"listening",data:{streams:["trade_updates"]}}));
 s.message(frame("fill"),RX1);
 A.throws(()=>s.message(frame("fill"),RX1+1000),/C35_DUPLICATE_EXECUTION_ID/);
});
test("C35 rejects unsigned or malformed and oversized messages",()=>{
 A.throws(()=>W.observe(Buffer.from("{broken"),RX1),SyntaxError);
 A.throws(()=>W.observe("x".repeat(1024*1024),RX1),/C35_RAW_SIZE_LIMIT/);
 A.throws(()=>W.observe(JSON.stringify({stream:"incorrect",data:{}}),RX1),
  /C35_TRADE_UPDATES_STREAM/);
});
test("C35 rejects missing fill even when C25 cash ledger balances",()=>{
 const f=fixture();
 A.throws(()=>W.reconcile({accountExport:f,streamRecords:[records()[0]]}),
  /C35_FILL_MATCH_MISSING_OR_AMBIGUOUS/);
});
test("C35 rejects ambiguous identical executions instead of selecting one",()=>{
 const f=fixture(),rr=records();
 rr.push({...rr[0],executionId:"EXEC_DISTINCT",receivedAtMs:RX2+1000});
 A.throws(()=>W.reconcile({accountExport:f,streamRecords:rr}),
  /C35_FILL_MATCH_MISSING_OR_AMBIGUOUS/);
});
test("C35 rejects altered C25 fill quantity",()=>{
 const f=fixture();f.activities.pages[0].rows[0].qty="2";
 A.throws(()=>W.reconcile({accountExport:f,streamRecords:records()}));
});
test("C35 rejects stream event without matching C25 activity",()=>{
 const rr=records();rr.push(W.observe(frame("fill",{
  orderId:"ORDER_GHOST",executionId:"EXEC_GHOST",
  timestamp:"2026-11-06T15:00:00Z"}),RX2+1000));
 A.throws(()=>W.reconcile({accountExport:fixture(),streamRecords:rr}),
  /C35_STREAM_EXECUTION_IN_WINDOW_WITHOUT_ACCOUNT_FILL/);
});
test("C35 explicitly cannot certify multileg options contract fills",()=>{
 const multi=JSON.parse(frame("fill").toString());
 multi.data.order.order_class="mleg";
 multi.data.legs=[{execution_id:"LEG",symbol:"AAPL280121C"}];
 const row=W.observe(Buffer.from(JSON.stringify(multi)),RX1);
 A.equal(row.multilegOptionsUnsupported,true);
 A.equal(row.executionId,null);
 A.throws(()=>W.reconcile({accountExport:fixture(),
  streamRecords:[row,records()[1]]}),/C35_OPTIONS_OR_AMBIGUOUS_EXECUTION/);
});
test("C35 durable private source journal preserves ACK and fill ordering",()=>{
 withDir(dir=>{
  J.create(dir,{captureId:"C35_TEST_01"});
  const w=J.openWriter(dir);
  w.authorized(RX1-2000);w.listening(RX1-1000);
  w.event(records()[0]);const r=w.close(RX1+1000);
  A.equal(r.authRecorded,true);A.equal(r.subscriptionRecorded,true);
  A.equal(r.eventsRecorded,1);A.equal(r.closedLocally,true);
  A.equal(r.sourceOriginIndependentlyAuthenticated,false);
  A.equal(r.reconnectionGapsProvenAbsent,false);
  A.equal(J.verify(dir).head,r.head);
 });
});
test("C35 journal detects altered order receipt bytes after restart",()=>{
 withDir(dir=>{
  J.create(dir,{captureId:"C35_TEST_02"});
  const w=J.openWriter(dir);
  w.authorized(RX1-2000);w.listening(RX1-1000);
  w.event(records()[0]);w.close(RX1+1000);
  const p=path.join(dir,"events.ndjson");
  const raw=fs.readFileSync(p,"utf8");
  fs.writeFileSync(p,raw.replace('"brokerOrderId":"ORDER_BUY"',
   '"brokerOrderId":"ORDER_FAKE"'));
  A.throws(()=>J.verify(dir),/C35J_SEQUENCE_HASH_OR_CLOCK/);
 });
});
test("C35 journal refuses event before authorisation or missing listen",()=>{
 withDir(dir=>{
  J.create(dir,{captureId:"C35_TEST_03"});
  const w=J.openWriter(dir);
  A.throws(()=>w.event(records()[0]),/C35J_WRITER_EVENT/);
  w.authorized(RX1-2000);
  A.throws(()=>w.event(records()[0]),/C35J_WRITER_EVENT/);
  w.listening(RX1-1000);w.close(RX1);
 });
});
test("C35 journal refuses duplicate or overwritten authorisation",()=>{
 withDir(dir=>{
  J.create(dir,{captureId:"C35_TEST_04"});
  const w=J.openWriter(dir);w.authorized(RX1-2000);
  A.throws(()=>w.authorized(RX1-1000),/C35J_WRITER_AUTH/);
  w.listening(RX1-1000);w.close(RX1);
 });
});
test("C35 journal rejects reopened untracked partial stream",()=>{
 withDir(dir=>{
  J.create(dir,{captureId:"C35_TEST_05"});
  const w=J.openWriter(dir);
  A.throws(()=>J.openWriter(dir),/C35J_NEW_CAPTURE_WRITER_ONLY/);
  w.authorized(RX1-2000);w.listening(RX1-1000);w.close(RX1);
 });
});
test("C35 CLI cannot authorize LIVE, indefinite capture, or M10",()=>{
 A.throws(()=>CLI.argumentsOf(["--mode","LIVE","--out","/tmp/x",
  "--seconds","10"]),/C35CLI_EXPLICIT_PAPER_CAPTURE_ARGUMENTS/);
 A.throws(()=>CLI.argumentsOf(["--mode","PAPER","--out","/tmp/x",
  "--seconds","0"]),/C35CLI_EXPLICIT_PAPER_CAPTURE_ARGUMENTS/);
 A.throws(()=>CLI.argumentsOf(["--mode","PAPER","--out","/tmp/x",
  "--seconds","3601"]),/C35CLI_FINITE_PRIVATE_CAPTURE_NOT_M10/);
 A.throws(()=>CLI.argumentsOf(["--mode","PAPER","--out","/tmp/M10_final/x",
  "--seconds","10"]),/C35CLI_FINITE_PRIVATE_CAPTURE_NOT_M10/);
});
