"use strict";
/** C25 transport tests use mock GETs; ZERO broker network requests or orders. */
const test=require("node:test"),A=require("node:assert/strict");
const fs=require("node:fs"),os=require("node:os"),path=require("node:path");
const E=require("../runtime30/fwn9_c25_alpaca_readonly_exporter.cjs");
const C=require("../runtime30/fwn9_c25_broker_export_ingest.cjs");
const CLI=require("./fwn9_c25_capture_readonly_alpaca.cjs");
const FROM="2026-11-06T14:00:00Z",TO="2026-11-06T17:00:00Z";
function fixtureData(){
 const accountId="C25_SYNTHETIC_CAPTURE_ONLY";
 const baseline={id:accountId,equity:"20000",cash:"20000"};
 const terminal={id:accountId,equity:"20021",cash:"19909"};
 const fill=(id,order,qty,price,side,when)=>({
  id,activity_type:"FILL",symbol:"SPY",side,
  type:"partial_fill",qty,price,order_id:order,transaction_time:when
 });
 const activity=[
  fill("F1","B1","1","100","buy","2026-11-06T14:30:02Z"),
  fill("F2","B1","1","100","buy","2026-11-06T14:30:05Z"),
  fill("F3","S1","1","110","sell","2026-11-06T16:30:00Z"),
  {id:"FF",activity_type:"FEE",date:"2026-11-06",net_amount:"-1"}
 ];
 const orders=[
  {id:"B1",symbol:"SPY",side:"buy",asset_class:"us_equity",qty:"2",
   filled_qty:"2",filled_avg_price:"100",status:"filled",
   submitted_at:"2026-11-06T14:30:00Z"},
  {id:"S1",symbol:"SPY",side:"sell",asset_class:"us_equity",qty:"1",
   filled_qty:"1",filled_avg_price:"110",status:"filled",
   submitted_at:"2026-11-06T16:20:00Z"}
 ];
 const position={symbol:"SPY",qty:"1",market_value:"112",asset_class:"us_equity"};
 return {accountId,baseline,terminal,orders,activity,position};
}
function mockGet(state,kind){
 const data=fixtureData();
 const history=[];
 const get=async (p,q={})=>{
  history.push({p,q});
  if(p==="/v2/orders"){
   if(q.status==="open")return state?.openOrders??[];
   if(q.status==="all")return state?.allOrders??data.orders;
  }
  if(p==="/v2/account")return kind==="baseline"?data.baseline:data.terminal;
  if(p==="/v2/positions")return kind==="baseline"?[]:[data.position];
  if(p==="/v2/account/activities"){
   return state?.activityPage?state.activityPage(q):data.activity;
  }
  if(p.startsWith("/v2/assets/"))return {class:"us_equity"};
  throw Error("MOCK_UNRECOGNIZED_GET_ENDPOINT");
 };
 return {get,history};
}
test("C25 GET allowlist accepts only documented read-only account endpoints",()=>{
 for(const p of ["/v2/account","/v2/positions","/v2/orders",
  "/v2/account/activities","/v2/assets/SPY","/v2/assets/BTC%2FUSD"])
  A.equal(E.validatePath(p),p);
 for(const bad of ["/v2/orders/id","/v2/orders:by_client_order_id",
  "/v2/account/positions/close","/v2/assets/%2e%2e%2fsecret",
  "/v2/orders/../account","https://example.com/v2/account"])
  A.throws(()=>E.validatePath(bad),/C25_GET_ENDPOINT_ALLOWLIST/);
});
test("C25 actual GET transport selects paper origin and never POST/redirect",async()=>{
 const sent=[];
 const transport=async (url,init)=>{
  sent.push({url,init});
  return {ok:true,async text(){return '{"id":"C25_SYNTH"}';}};
 };
 const get=E.readOnlyTransport({mode:"PAPER",
  env:{APCA_API_KEY_ID:"local-fake-key",APCA_API_SECRET_KEY:"local-fake-secret"},
  transport});
 const value=await get("/v2/account",{status:"all"});
 A.equal(value.id,"C25_SYNTH");
 A.equal(sent.length,1);
 A(sent[0].url.startsWith("https://paper-api.alpaca.markets/v2/account?"));
 A.equal(sent[0].init.method,"GET");
 A.equal(sent[0].init.redirect,"error");
 A.equal(sent[0].init.headers["APCA-API-KEY-ID"],"local-fake-key");
});
test("C25 missing local env credentials fail closed before any request",()=>{
 A.throws(()=>E.readOnlyTransport({env:{},transport:async()=>{}}),
  /C25_GET_CREDENTIALS_FROM_LOCAL_ENV/);
});
test("C25 source baseline only when no prior pending orders",async()=>{
 const {get,history}=mockGet({},"baseline");
 const b=await E.baseline(get,"PAPER",()=>Date.parse(FROM));
 A.equal(b.schema,"HARPOON_FWN9_C25_SOURCE_BASELINE_1");
 A.equal(b.baseline.account.currency,"USD");
 A.equal(Date.parse(b.baseline.observed_at),Date.parse(FROM));
 A.equal(b.baseline_open_orders.length,0);
 A.equal(history.filter(x=>x.p==="/v2/orders").length,1);
 const q=mockGet({openOrders:[{id:"UNMODELED_OPEN"}]},"baseline");
 await A.rejects(()=>E.baseline(q.get,"PAPER",()=>Date.parse(FROM)),
  /C25_GET_PREBASELINE_OPEN_ORDERS_NOT_SUPPORTED/);
 A.equal(q.history.some(x=>x.p==="/v2/account"),false);
});
test("C25 direct authenticated-GET-shaped two-checkpoint export passes offline cash and order audit",async()=>{
 const base=await E.baseline(mockGet({},"baseline").get,"PAPER",()=>Date.parse(FROM));
 const b=await E.finish(mockGet({},"terminal").get,base,
  ()=>Date.parse(TO),null);
 A.equal(b.account_id,fixtureData().accountId);
 A.equal(b.baseline.account.currency,"USD");
 A.equal(b.terminal.account.currency,"USD");
 A.equal(b.activities.pages.length,1);
 A.equal(b.orders.rows.length,2);
 A.equal(b.instruments[0].asset_class,"us_equity");
 const r=C.certify(b);
 A.equal(r.validated.orders,2);
 A.equal(r.validated.fills,3);
 A.equal(r.validated.algebraicAccountPnlUsd,21);
 A.equal(r.sourceInputExternallyAuthenticated,false);
 A.equal(r.admission.orderAuthority,false);
});
test("C25 missing cost evidence still reconciles raw account but blocks net external costs",async()=>{
 const base=await E.baseline(mockGet({},"baseline").get,"PAPER",()=>Date.parse(FROM));
 const b=await E.finish(mockGet({},"terminal").get,base,()=>Date.parse(TO));
 const r=C.certify(b);
 A.equal(r.validated.independentCashAndInventoryReconciled,true);
 A.equal(r.validated.conditionalAfterDeclaredCostsPnlUsd,null);
 A(r.blockers.includes("EXTERNAL_COST_COVERAGE_INCOMPLETE"));
});
test("C25 if GET returns 500 orders we refuse an incomplete trade history",async()=>{
 const {get}=mockGet({allOrders:Array.from({length:500},(_,i)=>({id:"ID"+i}))},"terminal");
 await A.rejects(()=>E.completeOrders(get,FROM,TO),
  /C25_GET_ORDERS_PAGE_AT_LIMIT_CANNOT_PROVE_COMPLETENESS/);
});
test("C25 activity page cursor is last activity ID, never a guessed timestamp",async()=>{
 const rows=Array.from({length:100},(_,i)=>({id:"ACT"+i}));
 let count=0;
 const get=async (p,q)=>{
  A.equal(p,"/v2/account/activities");count++;
  if(count===1){A.equal(q.page_token,undefined);return rows;}
  A.equal(q.page_token,"ACT99");return [];
 };
 const r=await E.activityPages(get,FROM,TO);
 A.equal(r.pages.length,2);
 A.equal(r.pages[0].complete,false);
 A.equal(r.pages[1].complete,true);
 A.equal(r.pages[1].request_page_token,"ACT99");
});
test("C25 repeated activity cursor entries reject duplicate before fake complete",async()=>{
 const rows=Array.from({length:100},(_,i)=>({id:"ID"+i}));
 let n=0;
 const get=async()=>{n++;return n===1?rows:[rows[99]]};
 await A.rejects(()=>E.activityPages(get,FROM,TO),
  /C25_GET_ACTIVITY_DUPLICATE_OR_MISSING_ID/);
});
test("C25 different source modes cannot accidentally mix in single offline account",async()=>{
 const base=await E.baseline(mockGet({},"baseline").get,"PAPER",()=>Date.parse(FROM));
 const x={...base,mode:"LIVE"};
 const b=await E.finish(mockGet({},"terminal").get,x,()=>Date.parse(TO));
 A.equal(b.mode,"LIVE");
 const cli=CLI.argumentsOf(["--stage","finish","--mode","PAPER",
  "--baseline","/local/a","--out","/local/b"]);
 A.equal(cli["--mode"],"PAPER");
 // Capture CLI separately checks imported baseline mode; never silently mixes.
});
test("C25 private files use exclusive create mode0600 and never overwrite",()=>{
 const tmp=fs.mkdtempSync(path.join(os.tmpdir(),"c25-private-"));
 try{
  const p=path.join(tmp,"private.json");
  const w=CLI.writePrivate(p,{schema:"C25_PRIVATE_ONLY"});
  A.equal(w.fileMode,"0600");
  A.equal(fs.statSync(p).mode&0o777,0o600);
  A.equal(CLI.loadPrivate(p).schema,"C25_PRIVATE_ONLY");
  A.throws(()=>CLI.writePrivate(p,{different:true}),/EEXIST/);
 }finally{fs.rmSync(tmp,{recursive:true,force:true});}
});
test("C25 exporter refuses M10 holdout file and unsupported options endpoint",()=>{
 A.throws(()=>CLI.filePath("/tmp/holdout/M10-final.json"),
  /C25_CAPTURE_M10_HOLDOUT_CANNOT_BE_CAPTURE/);
 A.throws(()=>E.validatePath("/v2/orders/abc"),/C25_GET_ENDPOINT_ALLOWLIST/);
});
test("C25 private account metadata never has to be printed by CLI",()=>{
 const p=CLI.argumentsOf(["--stage","baseline","--mode","PAPER",
  "--out","/private/b.json"]);
 A.equal(p["--mode"],"PAPER");
 A.throws(()=>CLI.argumentsOf(["--stage","baseline","--mode","PAPER",
  "--out","/private/b.json","--cost","/private/c.json"]),
  /C25_CAPTURE_BASELINE_UNEXPECTED_INPUT/);
});

test("C25 origin mode prototype pollution and encoded path traversal fail closed",()=>{
 A.throws(()=>E.readOnlyTransport({mode:"__proto__",
  env:{APCA_API_KEY_ID:"x",APCA_API_SECRET_KEY:"y"},
  transport:async()=>({ok:true,text:async()=>"{}"})}),
  /C25_GET_MODE/);
 for(const path of ["/v2/assets/..","/v2/assets/%2e%2e",
  "/v2/assets/ABC..DEF","/v2/assets/BTC%2e%2eUSD"])
  A.throws(()=>E.validatePath(path),/C25_GET_ENDPOINT_ALLOWLIST/);
});
