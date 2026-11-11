"use strict";
const test=require("node:test");
const A=require("node:assert/strict");
const fs=require("node:fs"),os=require("node:os"),path=require("node:path");
const E=require("../runtime30/fwn9_c25_alpaca_readonly_exporter.cjs");
const C25=require("../runtime30/fwn9_c25_broker_export_ingest.cjs");
const W=require("../runtime30/fwn9_c33_broker_get_witness.cjs");
const J=require("../runtime30/fwn9_c33_broker_get_journal.cjs");
const CLI=require("./fwn9_c33_paper_capture.cjs");
const FROM="2026-11-06T14:00:00Z",TO="2026-11-06T17:00:00Z";
function cashBundle(){
 const account={id:"SYNTHETIC_CASH_ACCOUNT_NOT_ALPACA",cash:"20000",equity:"20000",currency:"USD"};
 return {schema:"HARPOON_FWN9_C25_ALPACA_OFFLINE_BUNDLE_1",
  export_type:"OFFLINE_ALPACA_TRADING_API_READ_ONLY",mode:"PAPER",currency:"USD",
  account_id:account.id,from:FROM,through:TO,collected_at:"2026-11-06T17:01:00Z",
  instruments:[],baseline_open_orders:[],
  baseline:{observed_at:FROM,account,positions:[]},
  terminal:{observed_at:TO,account:{...account},positions:[]},
  orders:{filter_status:"all",pagination_asserted_complete:true,rows:[]},
  activities:{filter:"all",order:"asc",page_size:100,pages:[
   {request_page_token:null,rows:[],complete:true}
  ]},
  external_cost_coverage:{currency:"USD",from:FROM,through:TO,
   categories:["DATA","INFRASTRUCTURE","INFERENCE","OTHER"],
   coverage_declared_complete:true,rows:[]}
 };
}
function scratch(fn){
 const p=fs.mkdtempSync(path.join(os.tmpdir(),"harpoon-c33-"));
 const clean=()=>fs.rmSync(p,{force:true,recursive:true});
 try{
  const result=fn(path.join(p,"private"));
  if(result&&typeof result.then==="function")return result.finally(clean);
  clean();return result;
 }catch(e){clean();throw e;}
}
function getFixtureTransport(data='{"cash":"20000"}'){
 return async(url,init)=>({status:200,ok:true,
  headers:{get:()=>new Date(1762444800000).toUTCString()},
  async text(){return data;}});
}
function witnessEvents(sink,transport=getFixtureTransport()){
 let t=1762444800000;
 return W.wrapTransport({mode:"PAPER",sink,transport,now:()=>++t});
}
function c25Get(transport){
 return E.readOnlyTransport({mode:"PAPER",
  env:{APCA_API_KEY_ID:"TEST_KEY_NOT_REAL",
   APCA_API_SECRET_KEY:"TEST_SECRET_NOT_REAL"},transport});
}
test("C33 CASH control with no instruments, orders or activity reconciles",()=>{
 const r=C25.certify(cashBundle());
 A.equal(r.validated.instruments,0);
 A.equal(r.validated.orders,0);
 A.equal(r.validated.fills,0);
 A.equal(r.validated.independentCashAndInventoryReconciled,true);
 A.equal(r.validated.algebraicAccountPnlUsd,0);
 A.equal(r.validated.conditionalAfterDeclaredCostsPnlUsd,0);
 A.equal(r.admission.N9S,"NO_GO");
 A.equal(r.sourceInputExternallyAuthenticated,false);
});
test("C25 forbids zero instruments with a hidden order",()=>{
 const b=cashBundle();
 b.orders.rows=[{id:"O",symbol:"SPY",qty:"1",filled_qty:"0",
  submitted_at:"2026-11-06T15:00:00Z",side:"buy",status:"canceled"}];
 A.throws(()=>C25.certify(b),
  /C25_EMPTY_INSTRUMENT_CATALOG_REQUIRES_CASH_ONLY_NO_ORDERS_OR_FILLS/);
});
test("C25 forbids empty catalog when a position or FILL exists",()=>{
 for(const mutate of [
  b=>b.terminal.positions.push({symbol:"SPY",qty:"1",market_value:"100"}),
  b=>b.activities.pages[0].rows.push({id:"F",activity_type:"FILL"})
 ]){
  const b=cashBundle();mutate(b);
  A.throws(()=>C25.certify(b),/C25_EMPTY_INSTRUMENT_CATALOG_REQUIRES_CASH_ONLY/);
 }
});
test("native C25 exporter returns an empty catalog for a truly flat account",async()=>{
 let calls=0;
 const get=async()=>{calls++;throw Error("NO_SYMBOL_GET_ALLOWED");};
 const result=await E.instrumentCatalog(get,{positions:[]},{positions:[]},{rows:[]});
 A.deepEqual(result,[]);
 A.equal(calls,0);
});
test("native C25 exporter still looks up unknown instrument and rejects options",async()=>{
 await A.rejects(E.instrumentCatalog(async()=>({class:"option"}),
  {positions:[{symbol:"CONTRACT",asset_class:"option"}]},
  {positions:[]},{rows:[]}),/C25_GET_ASSET_CLASS/);
});
test("C33 records actual C25 GET response body bytes without credentials",async()=>{
 const rows=[],transport=witnessEvents(r=>rows.push(r));
 const get=c25Get(transport);
 A.deepEqual(await get("/v2/account"),{cash:"20000"});
 A.equal(rows.length,1);
 A.equal(rows[0].origin,"https://paper-api.alpaca.markets");
 A.match(rows[0].responseBodySha256,/^[a-f0-9]{64}$/);
 A.equal(rows[0].method,"GET");
 A.equal(rows[0].paperOrLiveOrdersPermitted,false);
 A.equal(rows[0].transportReceiptsIndependentlyBrokerSigned,false);
 A.equal(JSON.stringify(rows).includes("TEST_SECRET_NOT_REAL"),false);
 A.equal(JSON.stringify(rows).includes('{"cash":"20000"}'),false);
});
test("C33 fails closed when the GET receipt sink fails",async()=>{
 const transport=witnessEvents(()=>{throw Error("DISK_FULL");});
 await A.rejects(c25Get(transport)("/v2/account"),/DISK_FULL/);
});
test("C33 refuses non-GET, wrong URL, redirect or LIVE mode",async()=>{
 const w=witnessEvents(()=>{});
 const init={method:"GET",redirect:"error",
  headers:{"APCA-API-KEY-ID":"x","APCA-API-SECRET-KEY":"y"}};
 await A.rejects(w("https://api.alpaca.markets/v2/account",init),
  /C33GET_STRICT_PAPER/);
 await A.rejects(w("https://paper-api.alpaca.markets/v2/account/positions/close",init),
  /C25_GET_ENDPOINT_ALLOWLIST/);
 await A.rejects(w("https://paper-api.alpaca.markets/v2/account",{...init,method:"POST"}),
  /C33GET_STRICT_PAPER/);
 A.throws(()=>W.wrapTransport({mode:"LIVE",sink(){} }),/C33GET_PAPER_GET_ONLY/);
});
test("C33 private journal persists and detects corruption across restart",async()=>{
 await scratch(async dir=>{
  J.create(dir,{captureId:"TEST_C33_GET"});
  const writer=J.openWriter(dir);
  const transport=witnessEvents(r=>writer.append(r));
  const get=c25Get(transport);
  await get("/v2/account");
  const result=writer.close();
  A.equal(result.count,1);
  A.equal(J.verify(dir).head,result.head);
  A.equal(result.sourceExternallyAuthenticated,false);
  const file=path.join(dir,"receipts.ndjson");
  const original=fs.readFileSync(file,"utf8");
  fs.writeFileSync(file,original.replace('"method":"GET"','"method":"POST"'));
  A.throws(()=>J.verify(dir),/C33GET_WITNESS_SCHEMA/);
 });
});
test("C33 journal rejects abandoned lock and insecure permissions",()=>{
 scratch(dir=>{
  J.create(dir,{captureId:"TEST_C33_GET"});
  const writer=J.openWriter(dir);
  A.throws(()=>J.openWriter(dir),/C33J_STALE_LOCK/);
  writer.close();
  fs.chmodSync(path.join(dir,"manifest.json"),0o644);
  A.throws(()=>J.verify(dir),/C33J_PRIVATE_0600/);
 });
});
test("C33 coverage is descriptive not authenticated even with all GET families",async()=>{
 const rows=[],get=c25Get(witnessEvents(r=>rows.push(r)));
 for(const ep of ["/v2/account","/v2/positions","/v2/orders",
  "/v2/account/activities"]){await get(ep);}
 const result=W.verifyCoverage({witnesses:rows});
 A.equal(result.allRequiredEndpointKindsWitnessed,true);
 A.equal(result.brokerSourceIndependentlyAuthenticated,false);
 A.equal(result.completeAccountAndOrderHistoryCertified,false);
 A.equal(result.financedReturnVsCashCertified,false);
});
test("C33 coverage cannot claim all GET endpoints if account activities absent",async()=>{
 const rows=[],get=c25Get(witnessEvents(r=>rows.push(r)));
 await get("/v2/account");
 const result=W.verifyCoverage({witnesses:rows});
 A.equal(result.allRequiredEndpointKindsWitnessed,false);
 A.deepEqual(result.missingRequiredEndpoints,
  ["/v2/positions","/v2/orders","/v2/account/activities"]);
});
test("C33 wrapper is PAPER only and never silently invokes main()",()=>{
 A.throws(()=>CLI.argsOf(["--stage","baseline","--mode","LIVE",
  "--out","/tmp/receipt.json","--get-journal","/tmp/receipt-log"]),
  /C33_CLI_PAPER_ONLY/);
 A.equal(typeof CLI.main,"function");
});
test("C33 witness refuses fabricated broker or independent time attestations",()=>{
 const w={schema:W.SCHEMA,sequence:1,method:"GET",
  origin:"https://paper-api.alpaca.markets",endpointPath:"/v2/account",
  requestQuerySha256:"a".repeat(64),responseBodySha256:"b".repeat(64),
  httpStatus:200,responseBodyBytes:5,startedAt:1,completedAt:2,
  transportReceiptsIndependentlyBrokerSigned:true,
  localWallClockIndependentlyNotarized:true,
  paperOrLiveOrdersPermitted:false,N9S:"NO_GO"};
 A.throws(()=>W.acceptWitness(w),/C33GET_WITNESS_SCHEMA/);
});
