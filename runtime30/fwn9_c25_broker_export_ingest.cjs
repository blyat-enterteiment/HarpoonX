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
