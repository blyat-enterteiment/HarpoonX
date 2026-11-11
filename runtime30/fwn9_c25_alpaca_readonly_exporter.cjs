"use strict";
/** FWN9 C25: DIRECT READ-ONLY Alpaca Trading API capture.
 * Explicit two-stage account snapshots; GET only; no retry trading methods,
 * no browser cookies or token storage, no live/paper orders.
 * This is a local user-invoked exporter, never run by CI against a broker.
 */
const A=require("node:assert/strict");
const ALLOWED_ORIGINS=Object.freeze({
 PAPER:"https://paper-api.alpaca.markets",
 LIVE:"https://api.alpaca.markets"
});
function need(v,code){A.ok(v,"C25_GET_"+code);}
function iso(t){return new Date(t).toISOString();}
function time(s){const t=Date.parse(s);need(Number.isSafeInteger(t)&&t>0,"TIME");return t;}
function validatePath(path){
 need(typeof path==="string"&&!path.includes("..")&&
  !/%2e/i.test(path)&&(
  path==="/v2/account"||path==="/v2/positions"||
  path==="/v2/orders"||path==="/v2/account/activities"||
  /^\/v2\/assets\/(?:[A-Za-z0-9._-]|%2F)+$/i.test(path)
 ),"ENDPOINT_ALLOWLIST");
 return path;
}
function readOnlyTransport({mode="PAPER",env=process.env,transport=fetch}={}){
 need(Object.hasOwn(ALLOWED_ORIGINS,mode),"MODE");
 const key=env.APCA_API_KEY_ID,secret=env.APCA_API_SECRET_KEY;
 need(typeof key==="string"&&key.length>0&&
  typeof secret==="string"&&secret.length>0,"CREDENTIALS_FROM_LOCAL_ENV");
 need(typeof transport==="function","FETCH_TRANSPORT");
 const origin=ALLOWED_ORIGINS[mode];
 return async function get(path,query={}){
  const url=new URL(origin+validatePath(path));
  need(query&&typeof query==="object"&&!Array.isArray(query),"QUERY");
  for(const [name,value] of Object.entries(query)){
   need(/^[a-z_]+$/.test(name)&&typeof value==="string"&&value.length<3000,
    "QUERY_PARAMETER");
   url.searchParams.set(name,value);
  }
  need(url.origin===origin&&url.protocol==="https:"&&
   url.pathname===path,"HTTPS_SAME_ORIGIN");
  const response=await transport(url.toString(),{
   method:"GET",redirect:"error",
   headers:{"APCA-API-KEY-ID":key,"APCA-API-SECRET-KEY":secret,
    "Accept":"application/json"},
   signal:AbortSignal.timeout(15000)
  });
  need(response&&typeof response.ok==="boolean","HTTP_RESPONSE");
  if(!response.ok)throw Error("C25_GET_HTTP_NON200_NO_ACCOUNT_DATA_PRINTED");
  const text=await response.text();
  need(text.length<10*1024*1024,"RESPONSE_SIZE");
  const decoded=JSON.parse(text);
  need(typeof decoded==="object"&&decoded!==null,"JSON_RESPONSE");
  return decoded;
 };
}
function normalizeAccount(account){
 need(account&&typeof account==="object"&&
  typeof account.id==="string"&&account.id.length>0,
  "ACCOUNT_ID");
 // Alpaca Trading Account model uses USD; baseline stores this explicit
 // adapter assumption rather than asserting the raw broker supplied a currency.
 if(account.currency!==undefined)need(account.currency==="USD","CURRENCY");
 return {...account,currency:"USD"};
}
async function snapshot(get,now=()=>Date.now()){
 const received=now(),account=normalizeAccount(await get("/v2/account"));
 const positions=await get("/v2/positions");
 need(Array.isArray(positions),"POSITIONS_ARRAY");
 const completed=now();
 need(completed>=received&&completed-received<15000,
  "SNAPSHOT_ATOMICITY_UNVERIFIED_TIME_SPAN");
 return {observed_at:iso(completed),account,positions,
  local_receipt_span_ms:completed-received,
  source_clock:"LOCAL_HTTP_RESPONSE_TIME_NOT_EXCHANGE_NAV_TIMESTAMP"};
}
async function baseline(get,mode,now=()=>Date.now()){
 need(["PAPER","LIVE"].includes(mode),"MODE");
 // Fail closed for any pending order before baseline, because a future fill
 // might be economically sourced from an unmodelled pre-baseline reservation.
 const open=await get("/v2/orders",{status:"open",limit:"500"});
 need(Array.isArray(open)&&open.length===0,"PREBASELINE_OPEN_ORDERS_NOT_SUPPORTED");
 const snap=await snapshot(get,now);
 return {schema:"HARPOON_FWN9_C25_SOURCE_BASELINE_1",mode,
  created_at:iso(now()),account_id:snap.account.id,
  baseline:snap,baseline_open_orders:[],
  source_claim:"READONLY_ALPACA_HTTP_CAPTURE_TLS_ORIGIN_NOT_INDEPENDENT_FINANCIAL_CERTIFICATION"};
}
async function activityPages(get,from,through){
 const pages=[],seen=new Set();let token=null,limit=100;
 for(let i=0;i<100;i++){
  const query={after:from,until:through,direction:"asc",page_size:String(limit)};
  if(token!==null)query.page_token=token;
  const rows=await get("/v2/account/activities",query);
  need(Array.isArray(rows)&&rows.length<=limit,"ACTIVITY_PAGE_FORMAT");
  const ids=[];
  for(const row of rows){
   need(row&&typeof row==="object"&&typeof row.id==="string"&&
    row.id.length>0&&!seen.has(row.id),"ACTIVITY_DUPLICATE_OR_MISSING_ID");
   seen.add(row.id);ids.push(row.id);
  }
  const done=rows.length<limit;
  pages.push({request_page_token:token,rows,complete:done});
  if(done)return {filter:"all",order:"asc",page_size:limit,pages};
  const next=ids.at(-1);
  need(next&&next!==token,"ACTIVITY_CURSOR_LOOP");
  token=next;
 }
 throw Error("C25_GET_ACTIVITY_PAGINATION_LIMIT_NOT_COMPLETE");
}
async function completeOrders(get,from,through){
 // Alpaca Trading API /v2/orders does not advertise page_token in the
 // documented GET parameters. Refuse exactly-500 rows instead of guessing a
 // timestamp cursor and silently skipping simultaneous submissions.
 const rows=await get("/v2/orders",{status:"all",limit:"500",
  after:iso(time(from)-1),until:iso(time(through)+1),direction:"asc",nested:"false"});
 need(Array.isArray(rows)&&rows.length<500,
  "ORDERS_PAGE_AT_LIMIT_CANNOT_PROVE_COMPLETENESS");
 return {filter_status:"all",pagination_asserted_complete:true,rows,
  no_account_order_history_completeness_proven:false};
}
async function instrumentCatalog(get,base,terminal,orders){
 const symbols=new Map();
 for(const r of [...base.positions,...terminal.positions,...orders.rows]){
  if(!r.symbol)continue;
  const symbol=r.symbol,kind=r.asset_class;
  if(symbols.has(symbol))continue;
  if(kind==="us_equity"||kind==="crypto")symbols.set(symbol,kind);
  else{
   // This GET resolves the instrument class. No option contracts allowed
   // without verified multiplier and exercise/settlement accounting.
   const asset=await get("/v2/assets/"+encodeURIComponent(symbol));
   need(["us_equity","crypto"].includes(asset.class),"ASSET_CLASS");
   symbols.set(symbol,asset.class);
  }
 }
 // A legitimately flat CASH block has no position/order instruments.
 need(symbols.size<=10000,"INSTRUMENT_CATALOG_BOUND");
 return [...symbols].map(([symbol,asset_class])=>({
  symbol,asset_class,currency:"USD",multiplier:1
 }));
}
async function finish(get,source,now=()=>Date.now(),externalCostCoverage=null){
 need(source&&source.schema==="HARPOON_FWN9_C25_SOURCE_BASELINE_1"&&
  ["PAPER","LIVE"].includes(source.mode)&&
  source.baseline?.account?.id===source.account_id&&
  Array.isArray(source.baseline_open_orders)&&
  source.baseline_open_orders.length===0,"BASELINE_SCOPE");
 const terminal=await snapshot(get,now);
 need(terminal.account.id===source.account_id,"SAME_ACCOUNT");
 const from=source.baseline.observed_at,through=terminal.observed_at;
 need(time(through)>time(from),"POSITIVE_OBSERVATION_WINDOW");
 const [activities,orders]=await Promise.all([
  activityPages(get,from,through),completeOrders(get,from,through)
 ]);
 const instruments=await instrumentCatalog(get,source.baseline,terminal,orders);
 return {schema:"HARPOON_FWN9_C25_ALPACA_OFFLINE_BUNDLE_1",
  export_type:"OFFLINE_ALPACA_TRADING_API_READ_ONLY",
  mode:source.mode,currency:"USD",account_id:source.account_id,
  from,through,collected_at:iso(now()),instruments,
  baseline_open_orders:[],baseline:source.baseline,terminal,
  orders,activities,external_cost_coverage:externalCostCoverage,
  declared_api_queries_from_live_TLS_capture:true,
  independent_broker_source_authentication:false,
  external_quote_and_opportunity_trace_not_provided:true};
}
module.exports={readOnlyTransport,baseline,finish,activityPages,completeOrders,
 instrumentCatalog,snapshot,validatePath};
