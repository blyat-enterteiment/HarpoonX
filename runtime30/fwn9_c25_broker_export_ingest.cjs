"use strict";
/** C25 READ-ONLY, OFFLINE Alpaca Trading API export validator.
 * A SHA-256 digest of local bytes is NOT broker-origin authentication.
 * No HTTP, SDK, credentials, broker orders, or mutation of the native ledger.
 */
const A=require("node:assert/strict");
const crypto=require("node:crypto");
const {NetAccountLedger,netLedgerDigest}=require("./net_accounting.js");
const SCHEMA="HARPOON_FWN9_C25_ALPACA_OFFLINE_BUNDLE_1";
const SCALE=100000000n,MAX=10n**28n;
function need(cond,code){A.ok(cond,"C25_"+code);}
function plain(x,code){need(x&&typeof x==="object"&&!Array.isArray(x),code);return x;}
function str(x,code){need(typeof x==="string"&&x.length>0&&x.length<=500,code);return x;}
function time(x,code){
 need(typeof x==="string"&&/T.*(?:Z|[+-]\d{2}:\d{2})$/.test(x),code);
 const t=Date.parse(x);need(Number.isSafeInteger(t)&&t>0,code);return t;
}
function dec(x,code,{positive=false,negativeAllowed=false}={}){
 need(typeof x==="string"&&/^-?(?:0|[1-9]\d*)(?:\.\d{1,8})?$/.test(x),code);
 const sign=x.startsWith("-")?-1n:1n,s=x.startsWith("-")?x.slice(1):x;
 const [whole,frac=""]=s.split(".");
 const n=sign*(BigInt(whole)*SCALE+BigInt(frac.padEnd(8,"0")));
 need((negativeAllowed||n>=0n)&&(!positive||n>0n)&&
  n<MAX&&n>-MAX,code);
 return n;
}
function money(x){return Number(x)/Number(SCALE);}
function mult(a,b){
 const n=a*b;
 const abs=n<0n?-n:n;
 const rounded=(abs+SCALE/2n)/SCALE;
 return n<0n?-rounded:rounded;
}
function sha(x){return crypto.createHash("sha256").update(x).digest("hex");}
function snapshot(row,ledger,instruments,accountId,observedAt){
 plain(row,"SNAPSHOT");
 need(time(row.observed_at,"SNAPSHOT_TIME")<=observedAt,
  "SNAPSHOT_OBSERVED_AFTER_EXPORT");
 const account=plain(row.account,"ACCOUNT"),positions=row.positions;
 need(account.id===accountId&&account.currency==="USD"&&Array.isArray(positions),
  "ACCOUNT_ID_AND_CURRENCY");
 const obs=time(row.observed_at,"OBSERVED_AT");
 const native=ledger.snapshot(account,positions,obs,0,new Map(instruments));
 const cash=dec(account.cash,"CASH", {negativeAllowed:true});
 const equity=dec(account.equity,"EQUITY", {negativeAllowed:true});
 const pos=new Map();
 let marks=0n;
 for(const r of positions){
  const s=str(r.symbol,"POSITION_SYMBOL");
  need(instruments.has(s)&&!pos.has(s),"POSITION_ASSET_UNREGISTERED_OR_DUPLICATE");
  const q=dec(r.qty,"POSITION_QTY");
  const mv=dec(r.market_value,"POSITION_MARK", {negativeAllowed:true});
  need(mv>=0n&&q>=0n,"LONG_ONLY_NO_SHORT");
  pos.set(s,q);marks+=mv;
 }
 need((equity-cash-marks<=5000000n)&&
  (cash+marks-equity<=5000000n),"INDEPENDENT_NAV_MISMATCH");
 return {at:obs,cash,equity,positions:pos,sourceHash:native.sourceHash};
}
function flattenPages(pages,pageSize){
 need(Array.isArray(pages)&&pages.length>0&&pages.length<=1000&&
  Number.isSafeInteger(pageSize)&&pageSize>0&&pageSize<=100,
  "PAGINATION");
 const rows=[],seen=new Set();let cursor=null;
 for(let i=0;i<pages.length;i++){
  const p=plain(pages[i],"ACTIVITY_PAGE");
  need(p.request_page_token===cursor&&Array.isArray(p.rows)&&
   p.rows.length<=pageSize,"ACTIVITY_CURSOR_OR_SIZE");
  need(p.complete=== (i===pages.length-1),"ACTIVITY_PAGE_TERMINATOR");
  if(i<pages.length-1)need(p.rows.length===pageSize,"TRUNCATED_MIDDLE_PAGE");
  for(const x of p.rows){
   plain(x,"ACTIVITY_ROW");
   const id=str(x.id,"ACTIVITY_ID");
   need(!seen.has(id),"DUPLICATE_ACTIVITY_ID");
   seen.add(id);rows.push(x);
  }
  if(i<pages.length-1)need(p.rows.length>0,"EMPTY_NONFINAL_PAGE");
  cursor=p.rows.length?p.rows.at(-1).id:cursor;
 }
 need(pages.at(-1).rows.length<pageSize,"LAST_PAGE_NOT_EXHAUSTED");
 return rows;
}
function instrumentsFor(rows){
 need(Array.isArray(rows)&&rows.length>0&&rows.length<=10000,
  "INSTRUMENT_CATALOG");
 const m=new Map();
 for(const x of rows){
  plain(x,"INSTRUMENT");
  const s=str(x.symbol,"SYMBOL");
  need(!m.has(s)&&x.currency==="USD"&&
   ["us_equity","crypto"].includes(x.asset_class)&&
   x.multiplier===1,"INSTRUMENT_USD_LONG_MULTIPLIER");
  m.set(s,{symbol:s,asset_class:x.asset_class,currency:"USD",
   multiplier:1,book:x.asset_class==="crypto"?"crypto":"equity"});
 }
 return m;
}
function activityRows(rows,ledger,instruments,from,to,at){
 const activity=[],ids=new Set(),balances=new Map();
 let flow=0n,fee=0n,accountCash=0n,fillCash=0n;
 for(const raw of rows){
  need(!ids.has(raw.id),"DUPLICATE_ACTIVITY_ID");
  ids.add(raw.id);
  const normalized=ledger.activity(raw,at,false,instruments);
  need(["FILL","FEE","ACCOUNT_CASH","EXTERNAL_FLOW"].includes(normalized.classification),
   "UNSUPPORTED_OR_BASELINE_ACTIVITY");
  let cash=0n;
  if(normalized.classification==="FILL"){
   const t=time(raw.transaction_time,"FILL_TIMESTAMP");
   need(t>from&&t<=to,"FILL_OUTSIDE_EXPORTED_ACCOUNT_PERIOD");
   const qty=dec(raw.qty,"FILL_QTY",{positive:true}),
    price=dec(raw.price,"FILL_PRICE",{positive:true});
   const orderId=str(raw.order_id,"FILL_ORDER_ID");
   const symbol=str(raw.symbol,"FILL_SYMBOL");
   need(instruments.has(symbol)&&["buy","sell"].includes(raw.side),
    "FILL_ASSET_SIDE");
   need(instruments.get(symbol).asset_class===raw.asset_class,
    "FILL_ASSET_CLASS_MISMATCH");
   const signed=raw.side==="buy"?qty:-qty;
   cash=-mult(signed,price);
   fillCash+=cash;
   balances.set(orderId,[
     ...(balances.get(orderId)||[]),
     {symbol,side:raw.side,qty,price,at:t}
   ]);
  }else{
   need(typeof raw.date==="string"&&raw.date.length>0,
    "NONTRADE_DATE_REQUIRED");
   cash=dec(raw.net_amount,"NONTRADE_NET_AMOUNT",{negativeAllowed:true});
   // An FEE or dividend may be date-only. It is a valid settlement total,
   // NOT an intraday knownAt proof.
   const date=raw.date.slice(0,10);
   need(/^\d{4}-\d\d-\d\d$/.test(date)&&
    Date.parse(date)>=Date.parse(new Date(from).toISOString().slice(0,10))&&
    Date.parse(date)<=Date.parse(new Date(to).toISOString().slice(0,10)),
    "NONTRADE_DATE_OUTSIDE_PERIOD");
   if(normalized.classification==="FEE"){
     need(cash<=0n,"FEE_SIGN");
     fee+=cash;
   }else if(normalized.classification==="ACCOUNT_CASH")accountCash+=cash;
   else flow+=cash;
  }
  need(Math.abs(Number(cash)-normalized.cashDeltaUsd*1e8)<=1000000,
   "NATIVE_ACTIVITY_CASH_DISAGREEMENT");
  activity.push({id:raw.id,classification:normalized.classification,
   sourceHash:normalized.rawHash});
 }
 return {activity,flow,fee,accountCash,fillCash,balances};
}
function ordersCrossCheck(orders,filledByOrder,from,to){
 need(orders&&typeof orders==="object"&&orders.filter_status==="all"&&
  orders.pagination_asserted_complete===true&&Array.isArray(orders.rows)&&
  orders.rows.length<=100000,"COMPLETE_ALL_ORDERS_EXPORT_REQUIRED");
 const seen=new Set(),out=[];
 for(const o of orders.rows){
  plain(o,"ORDER");
  const id=str(o.id,"ORDER_ID");
  need(!seen.has(id),"DUPLICATE_ORDER");
  seen.add(id);
  need(["buy","sell"].includes(o.side)&&
   typeof o.symbol==="string"&&
   ["new","accepted","partially_filled","filled","canceled","expired",
    "rejected","done_for_day","replaced","pending_cancel",
    "pending_replace","stopped","suspended","calculated"].includes(o.status),
   "ORDER_STATUS_SIDE");
  const qty=dec(o.qty,"ORDER_QTY",{positive:true});
  const filled=dec(o.filled_qty,"ORDER_FILLED_QTY");
  need(filled<=qty,"ORDER_OVERFILL");
  const submitted=time(o.submitted_at,"ORDER_SUBMITTED_AT");
  need(submitted>=from&&submitted<=to,"ORDER_PREBASELINE_OR_POSTTERMINAL");
  const rows=filledByOrder.get(id)||[];
  let quantity=0n,notional=0n;
  for(const x of rows){
   need(x.symbol===o.symbol&&x.side===o.side&&
    x.at>=submitted,"ORDER_FILL_SYMBOL_SIDE_TIME");
   quantity+=x.qty;notional+=mult(x.qty,x.price);
  }
  need(quantity===filled,"ORDER_ACTIVITY_FILL_QUANTITY_MISMATCH");
  if(filled>0n){
   need(o.filled_avg_price!==null&&o.filled_avg_price!==undefined,
    "ORDER_MISSING_AVERAGE_FILL_PRICE");
   const average=dec(o.filled_avg_price,"ORDER_AVG_PRICE",{positive:true});
   const difference=notional-mult(filled,average);
   need(difference<=1000000n&&difference>=-1000000n,
    "ORDER_WEIGHTED_FILL_AVERAGE_MISMATCH");
  }else need(!o.filled_avg_price||dec(o.filled_avg_price,"UNFILLED_AVG")===0n,
   "ORDER_WITHOUT_ACTIVITIES_HAS_AVG_PRICE");
  out.push({id,quantity,filled,notional,originalStatus:o.status});
 }
 for(const id of filledByOrder.keys())need(seen.has(id),
  "FILL_WITHOUT_EXPORTED_ORDER");
 return {orders:out,orderCount:out.length,
  ordersWithFills:out.filter(x=>x.filled>0n).length};
}
function certify(bundle){
 plain(bundle,"OFFLINE_BUNDLE");
 need(bundle.schema===SCHEMA&&bundle.mode==="PAPER"||bundle.schema===SCHEMA&&bundle.mode==="LIVE",
  "BUNDLE_SCHEMA_AND_MODE");
 need(bundle.export_type==="OFFLINE_ALPACA_TRADING_API_READ_ONLY"&&
  bundle.currency==="USD","OFFLINE_EXPORT_CONTRACT");
 const id=str(bundle.account_id,"ACCOUNT_IDENTIFIER");
 const from=time(bundle.from,"FROM"),to=time(bundle.through,"THROUGH"),
  collected=time(bundle.collected_at,"COLLECTED_AT");
 need(from<to&&to<=collected,"COLLECTION_TIME_WINDOW");
 const catalog=instrumentsFor(bundle.instruments);
 // Stub store / transport cannot initiate network IO: only native read-only
 // snapshot() and activity() methods are invoked directly.
 const ledger=new NetAccountLedger({},{},"c25-offline-unpersisted",id,
  {currency:"USD",fillCashBasis:"GROSS_PLUS_SEPARATE_ACTIVITY_FEES"});
 const original=new Map(catalog);
 const b=snapshot(bundle.baseline,ledger,original,id,collected);
 const e=snapshot(bundle.terminal,ledger,original,id,collected);
 need(b.at===from&&e.at===to,"OBSERVATIONS_NOT_BOUND_TO_EXPORTED_WINDOW");
 const page=plain(bundle.activities,"ACTIVITIES");
 need(page.filter==="all"&&page.order==="asc"&&
  Number.isSafeInteger(page.page_size),"ACTIVITY_QUERY_CONTRACT");
 const activities=flattenPages(page.pages,page.page_size);
 const audited=activityRows(activities,ledger,catalog,from,to,collected);
 const chk=ordersCrossCheck(bundle.orders,audited.balances,from,to);
 let cash=b.cash+audited.fillCash+audited.fee+audited.accountCash+audited.flow;
 need(cash-e.cash<=1000000n&&e.cash-cash<=1000000n,
  "CASH_FROM_ACTIVITY_RECONCILIATION");
 const positions=new Map(b.positions);
 const fills=activities.filter(x=>x.activity_type==="FILL")
  .sort((x,y)=>Date.parse(x.transaction_time)-Date.parse(y.transaction_time)||
   x.id.localeCompare(y.id));
 for(const f of fills){
  const q=dec(f.qty,"RECONCILE_FILL_QTY",{positive:true});
  const old=positions.get(f.symbol)??0n;
  const next=old+(f.side==="buy"?q:-q);
  need(next>=0n,"NO_UNDISCLOSED_SHORT_OR_SELL_BEFORE_INVENTORY");
  positions.set(f.symbol,next);
 }
 for(const sym of new Set([...positions.keys(),...e.positions.keys()])){
  const delta=(positions.get(sym)??0n)-(e.positions.get(sym)??0n);
  need(delta<=1n&&delta>=-1n,"FINAL_INVENTORY_FROM_FILLED_QUANTITIES");
 }
 let costDeclaredComplete=false,totalExternal=0n;
 const coverage=bundle.external_cost_coverage;
 if(coverage!==undefined&&coverage!==null){
  plain(coverage,"COST_COVERAGE");
  need(coverage.currency==="USD"&&coverage.from===bundle.from&&
   coverage.through===bundle.through&&
   Array.isArray(coverage.categories)&&
   ["DATA","INFRASTRUCTURE","INFERENCE","OTHER"].every(x=>coverage.categories.includes(x))&&
   coverage.categories.length===4&&Array.isArray(coverage.rows),
   "FULL_COST_CATEGORY_SCOPE");
  const costIds=new Set();
  for(const x of coverage.rows){
   plain(x,"COST_ROW");
   need(!costIds.has(x.id)&&typeof x.id==="string"&&
    typeof x.reference==="string"&&x.reference.length>0&&
    coverage.categories.includes(x.category),"COST_DOCUMENT_BOUND");
   costIds.add(x.id);
   const amount=dec(x.amount_usd,"COST_AMOUNT");
   need(x.already_in_account===false,"C25_FEES_ALREADY_IN_NAV_NOT_DOUBLE_CHARGED");
   const at=time(x.at,"COST_AT"),known=time(x.known_at,"COST_KNOWN_AT");
   need(at>=from&&at<=to&&known>=at&&known<=collected,"COST_CLOCK");
   totalExternal+=amount;
  }
  costDeclaredComplete=coverage.coverage_declared_complete===true;
 }
 const blockers=[
  "OFFLINE_JSON_HASH_DOES_NOT_AUTHENTICATE_ALPACA_ORIGIN",
  "NO_INDEPENDENT_BROKER_ENDPOINT_ATTESTATION",
  "NO_TRUSTWORTHY_PREDECISION_KNOWN_AT_OR_EXCHANGE_QUEUE_FILLS",
  "ORIGINAL_NATIVE_OHLC_FIRST_CROSS_NON_EQUIVALENCE_C21",
  "NO_COMPLETE_UNFILLED_OPPORTUNITY_TRACE_FOR_C22",
  "SIX_C22_VARIANTS_NOT_EXECUTED_PROSPECTIVELY",
  "NO_INDEPENDENT_ORIGINAL_POLICY_NET_BASELINE"
 ];
 if(audited.flow!==0n)blockers.push("EXTERNAL_CAPITAL_FLOW_REQUIRES_TWR");
 if(!costDeclaredComplete)blockers.push("EXTERNAL_COST_COVERAGE_INCOMPLETE");
 if(activities.some(x=>x.activity_type!=="FILL"&&!x.date.includes("T")))
  blockers.push("DAY_ONLY_NONTRADE_EVENTS_CANNOT_CERTIFY_INTRADAY_FINANCING");
 const hash=netLedgerDigest({schema:SCHEMA,account_id:id,from:bundle.from,
  through:bundle.through,baseline_hash:b.sourceHash,terminal_hash:e.sourceHash,
  activities:audit_for_hash(audited.activity),orders:chk.orders.map(x=>x.id)});
 const accountDelta=e.equity-b.equity-audited.flow;
 const economicDelta=accountDelta-totalExternal;
 return {
  schema:"HARPOON_FWN9_C25_OFFLINE_ACCOUNT_SOURCE_RECONCILIATION_1",
  sourceDigestSha256:hash,
  sourceInputExternallyAuthenticated:false,
  mode:bundle.mode,
  sourceAccountIdRedacted:true,
  window:{from:bundle.from,through:bundle.through,collectedAt:bundle.collected_at},
  validated:{orders:chk.orderCount,withFills:chk.ordersWithFills,
   activities:audited.activity.length,
   fills:fills.length,
   activityFees:audited.activity.filter(x=>x.classification==="FEE").length,
   instruments:catalog.size,sourceNativeActivityParity:true,
   sourceNativeNavParity:true,
   independentCashAndInventoryReconciled:true,
   reportedFeeCashUsd:money(audited.fee),
   recordedCashFlowUsd:money(audited.flow),
   externalCostsDeclaredComplete:costDeclaredComplete,
   externalCostsNotInNavUsd:money(totalExternal),
   algebraicAccountPnlUsd:money(accountDelta),
   conditionalAfterDeclaredCostsPnlUsd:costDeclaredComplete?
    money(economicDelta):null,
   brokerAuthenticatedEconomicPnlUsd:null
  },
  admission:{
   reconstructedPastBrokerFillsAreNotProspectiveC22Trades:true,
   receiptLevelPredecisionFiltrationCertified:false,
   originalOHLCModelExecutionEquivalent:false,
   familywiseOutsideSampleNetAlphaCertified:false,
   realCompoundedOutperformanceVsCashCertified:false,
   independentFinancialProfitabilityLevel9:false,
   orderAuthority:false,N9S:"NO_GO"
  },
  blockers, holdoutM10Sealed:3200,createdMarketSeeds:0,
  createdEconomicTrialAccounts:0,placedBrokerOrders:0
 };
}
function audit_for_hash(items){return items.map(x=>[x.id,x.sourceHash]);}
function missingEvidence(){
 return {schema:"HARPOON_FWN9_C25_OFFLINE_ACCOUNT_SOURCE_RECONCILIATION_1",
  status:"BLOCKED_NO_AUTHENTICATED_PRIVATE_BROKER_EXPORT",
  sourceAccountIdRedacted:true,sourceInputExternallyAuthenticated:false,
  financialPerformanceDemonstrated:false,
  missing:["OFFLINE_ALPACA_ACCOUNT_SNAPSHOTS","COMPLETE_ORDER_AND_ACTIVITY_PAGINATION",
   "INDEPENDENT_ORIGIN_AUTHENTICATION_AND_OBSERVED_RECEIPT_CLOCKS",
   "CASH_FEES_POSITION_COST_COVERAGE","SIX_UNEXECUTED_C22_VARIANTS"],
  orderAuthority:false,N9S:"NO_GO",holdoutM10Sealed:3200};
}
module.exports={certify,missingEvidence,flattenPages,dec,sourceDigest:sha};
