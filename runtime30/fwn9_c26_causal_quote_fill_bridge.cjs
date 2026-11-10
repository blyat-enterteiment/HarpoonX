"use strict";
/** C26: Source-time causal BBO + broker FILL receipt bridge (OFFLINE).
 *
 * Uses C25's original native account activity & fixed-decimal verification.
 * A quote known before decision is a comparison reference, NEVER a guaranteed
 * IOC fill. Historical downloads cannot assert past local receipt timestamps.
 * This module sends NO orders, fetches NOTHING, and cannot certify alpha.
 */
const A=require("node:assert/strict");
const {netLedgerDigest}=require("./net_accounting.js");
const C25=require("./fwn9_c25_broker_export_ingest.cjs");
const SCHEMA="HARPOON_FWN9_C26_CAUSAL_QUOTE_FILL_BUNDLE_1";
const SCALE=100000000n,MAX_ROWS=100000;
function need(ok,code){A.ok(ok,"C26_"+code);}
function record(x,code){need(x&&typeof x==="object"&&!Array.isArray(x),code);return x;}
function id(x,code){need(typeof x==="string"&&x.length>0&&x.length<=500,code);return x;}
function stamp(x,code){
 need(typeof x==="string"&&/T.*(?:Z|[+-]\d{2}:\d{2})$/.test(x),code);
 const n=Date.parse(x);need(Number.isSafeInteger(n)&&n>0,code);return n;
}
function dec(x,code,{positive=false}={}){
 need(typeof x==="string"&&/^(?:0|[1-9]\d*)(?:\.\d{1,8})?$/.test(x),code);
 const [w,f=""]=x.split("."),v=BigInt(w)*SCALE+BigInt(f.padEnd(8,"0"));
 need(!positive||v>0n,code);return v;
}
function rnd(a,b){
 need(b>0n,"DENOMINATOR");
 return Number((a*100000000n)/b)/1e8;
}
function num(v){return Number(v)/1e8;}
function normalizeQuote(q,allowedSymbols){
 record(q,"QUOTE");
 const symbol=id(q.symbol,"QUOTE_SYMBOL");
 need(allowedSymbols.has(symbol),"QUOTE_ASSET_NOT_IN_ACCOUNT_CATALOG");
 const cls=allowedSymbols.get(symbol);
 const feed=id(q.feed,"QUOTE_FEED");
 if(cls==="us_equity")need(["sip","iex"].includes(feed),"QUOTE_EQUITY_FEED");
 else need(cls==="crypto"&&feed==="us","QUOTE_CRYPTO_FEED");
 const bid=dec(q.bp,"QUOTE_BID",{positive:true}),ask=dec(q.ap,"QUOTE_ASK",{positive:true});
 const bs=dec(q.bs,"QUOTE_BID_SIZE"),as=dec(q.as,"QUOTE_ASK_SIZE");
 need(ask>=bid,"QUOTE_CROSSED");
 const market=stamp(q.market_at,"QUOTE_EXCHANGE_TIME"),
  known=stamp(q.known_at,"QUOTE_LOCAL_RECEIPT_TIME");
 need(market<=known,"QUOTE_KNOWN_BEFORE_EXCHANGE_EVENT");
 return {id:id(q.id,"QUOTE_ID"),symbol,feed,bid,ask,bs,as,
  market,known,rawHash:netLedgerDigest(q)};
}
function normalizeReceipt(r){
 record(r,"RECEIPT");
 const at=stamp(r.execution_at,"EXECUTION_AT"),known=stamp(r.known_at,"FILL_KNOWN_AT");
 need(known>=at,"RECEIPT_BEFORE_EXECUTION");
 return {activityId:id(r.activity_id,"RECEIPT_ACTIVITY_ID"),
  orderId:id(r.order_id,"RECEIPT_ORDER_ID"),symbol:id(r.symbol,"RECEIPT_SYMBOL"),
  at,known,kind:id(r.kind,"RECEIPT_KIND")};
}
function classify(bundle){
 record(bundle,"BUNDLE");
 need(bundle.schema===SCHEMA&&bundle.capture_mode==="OFFLINE_PERSISTED_OBSERVATIONS",
  "FROZEN_C26_CONTRACT");
 const account=record(bundle.account_export,"ACCOUNT_EXPORT");
 const src=C25.certify(account); // invokes native read-only NetAccountLedger.
 need(src.validated.independentCashAndInventoryReconciled===true,
  "C25_ACCOUNT_RECONCILIATION");
 const collected=stamp(account.collected_at,"ACCOUNT_COLLECTED_TIME");
 const inputs=record(bundle.choices,"CHOICE_REGISTER");
 const catalog=new Map(account.instruments.map(x=>[x.symbol,x.asset_class]));
 need(catalog.size===account.instruments.length&&Array.isArray(inputs.quotes)&&
  Array.isArray(inputs.decisions)&&Array.isArray(inputs.receipts)&&
  inputs.quotes.length<=MAX_ROWS&&inputs.decisions.length<=MAX_ROWS&&
  inputs.receipts.length<=MAX_ROWS,"BOUNDED_CHOICE_TRACES");
 const quotes=new Map();
 for(const raw of inputs.quotes){
  const q=normalizeQuote(raw,catalog);
  need(!quotes.has(q.id)&&q.known<=collected,"QUOTE_DUPLICATE_OR_AFTER_COLLECTION");
  quotes.set(q.id,q);
 }
 const orders=new Map(account.orders.rows.map(o=>[o.id,o]));
 need(orders.size===account.orders.rows.length,"ORDER_IDS");
 const decisions=new Map();
 for(const raw of inputs.decisions){
  record(raw,"DECISION");
  const order=id(raw.order_id,"DECISION_ORDER_ID");
  need(orders.has(order)&&!decisions.has(order),"DECISION_ORDER_BINDING");
  const o=orders.get(order),quote=quotes.get(id(raw.quote_id,"DECISION_QUOTE_ID"));
  need(quote&&quote.symbol===o.symbol,"DECISION_QUOTE_MISMATCH");
  const at=stamp(raw.decision_at,"DECISION_AT"),
    known=stamp(raw.known_at,"DECISION_KNOWN_AT"),
    submitted=stamp(o.submitted_at,"ORDER_SUBMITTED_AT");
  need(quote.known<=at&&known>=at&&known<=submitted&&
   at<=submitted,"DECISION_KNOWLEDGE_CAUSALITY");
  need(submitted-quote.known<=5000&&quote.market<=quote.known,
   "PREDECISION_QUOTE_TOO_STALE");
  need(raw.source==="LOCAL_OBSERVATION_JOURNAL_CLAIM",
   "DECISION_SOURCE_UNVERIFIED_FORMAT");
  need(["buy","sell"].includes(raw.side)&&raw.side===o.side,
   "DECISION_SIDE");
  decisions.set(order,{at,known,submitted,quote,order:o,
    digest:netLedgerDigest(raw)});
 }
 const receipts=new Map();
 for(const raw of inputs.receipts){
  const r=normalizeReceipt(raw);
  need(r.kind==="BROKER_ORDER_UPDATE_LOCAL_JOURNAL_CLAIM"&&
   !receipts.has(r.activityId)&&r.known<=collected,
   "RECEIPT_DUPLICATE_KIND_OR_AFTER_COLLECTION");
  receipts.set(r.activityId,r);
 }
 const page=account.activities.pages.flatMap(p=>p.rows);
 const fills=page.filter(x=>x.activity_type==="FILL");
 const seenFills=new Set(),details=[];
 let shortfallCents=0n,feeMatched=src.validated.activityFees;
 for(const fill of fills){
  need(!seenFills.has(fill.id),"DUPLICATE_FILL");
  seenFills.add(fill.id);
  const r=receipts.get(fill.id),d=decisions.get(fill.order_id);
  need(r&&d&&r.orderId===fill.order_id&&r.symbol===fill.symbol,
   "FILL_QUOTE_AND_RECEIPT_NOT_LINKED");
  const t=stamp(fill.transaction_time,"FILL_TIME");
  need(t===r.at&&r.known>=t&&r.known>=d.submitted,
   "FILL_AND_LOCAL_RECEIPT_TIME_MISMATCH");
  need(t>=d.submitted&&t<=stamp(account.through,"ACCOUNT_THROUGH"),
   "FILL_BEFORE_ORDER_OR_AFTER_ACCOUNT");
  const qty=dec(fill.qty,"FILL_QUANTITY",{positive:true}),
    price=dec(fill.price,"FILL_PRICE",{positive:true});
  const ref=fill.side==="buy"?d.quote.ask:d.quote.bid;
  const signed=fill.side==="buy"?price-ref:ref-price;
  const dollars=(signed*qty)/SCALE;
  shortfallCents+=dollars;
  const spread=d.quote.ask-d.quote.bid,mid=d.quote.ask+d.quote.bid;
  const bps=Number((signed*20000n*SCALE)/mid)/1e8;
  details.push({
   activityDigest:netLedgerDigest(fill),
   orderDigest:netLedgerDigest(d.order),
   quoteDigest:d.quote.rawHash,
   side:fill.side,symbol:fill.symbol,quantity:num(qty),
   quoteFeed:d.quote.feed,
   quoteAt:d.quote.market,quoteKnownAt:d.quote.known,
   decisionAt:d.at,orderSubmittedAt:d.submitted,
   fillAt:t,receiptKnownAt:r.known,
   signedShortfallUsd:num(dollars),
   signedShortfallBpsVsPriorMid:bps,
   sourceSpreadBps:Number((spread*20000n*SCALE)/mid)/1e8,
   quoteSizeAtReference:num(fill.side==="buy"?d.quote.as:d.quote.bs),
   displayedSizeAtPreDecisionCoversFillQuantity:
    (fill.side==="buy"?d.quote.as:d.quote.bs)>=qty,
   quoteIsConsolidatedEquityNBBO:d.quote.feed==="sip",
   quoteIsAuthenticatedByIndependentBroker:false,
   executableQueueProof:false,
  });
 }
 need(receipts.size===seenFills.size,"UNMATCHED_RECEIPT_NO_FILL");
 const withFills=account.orders.rows.filter(x=>Number(x.filled_qty)>0);
 const missingDecisions=withFills.filter(o=>!decisions.has(o.id));
 const unmatchedOpenOrders=account.orders.rows.filter(o=>!decisions.has(o.id));
 need(missingDecisions.length===0,"FILLED_ORDER_MISSING_PREDECISION_JOURNAL");
 // Even if every fill is causally associated with a reported quote, raw JSON
 // and its source SHA cannot independently authenticate broker origin, source
 // quote arrival, depth consumed or all unfilled counterfactual opportunities.
 return {
  schema:"HARPOON_FWN9_M11_C26_CAUSAL_FILL_RESEARCH_DIAGNOSTIC_1",
  accountDigest:src.sourceDigestSha256,
  evidenceDigest:netLedgerDigest(bundle),
  accountIdentityPrinted:false,
  proofScope:"OFFLINE_DECLARED_JOURNAL_COHERENCE_NOT_VERIFIED_MARKET_EXECUTABILITY",
  observedFillCount:fills.length,matchedFillCount:details.length,
  unmatchedNonfilledOrders:unmatchedOpenOrders.length,
  matchedDecisionCount:decisions.size,matchedFeeActivityCount:feeMatched,
  grossImplementationShortfallAgainstKnownQuoteUsd:num(shortfallCents),
  details,
  conservationC25:src.validated.independentCashAndInventoryReconciled,
  allPastQuoteAvailableBeforeDecision:true,
  allFilledOrderReceiptsAfterExecution:true,
  quoteSizeSufficientGuaranteesFill:false,
  SIPTopOfBookGuaranteesQueueFill:false,
  receiptSourceAuthenticatedExternally:false,
  thirdPartyBrokerFillAuthenticityCertified:false,
  fundingFromKnownSettledCashBeforeEveryOrderCertified:false,
  matchedOptionsQuoteAndContractNotSupported:true,
  originalOHLCFirstCrossEquivalenceCertified:false,
  portfolioEconomicGrowthComparedToCashCertified:false,
  population_EA_EU_bounded:false,
  N9S:"NO_GO",originalM10FinalSealed:3200,
  generatedNewSignals:0,generatedNewMarketSeeds:0,
  createdEconomicTradingAccounts:0,submittedOrders:0
 };
}
function absence(){
 return {schema:"HARPOON_FWN9_M11_C26_CAUSAL_FILL_RESEARCH_DIAGNOSTIC_1",
  status:"BLOCKED_CAUSAL_BID_ASK_AND_BROKER_ORDER_RECEIPTS_NOT_AVAILABLE",
  matchedFills:0,netGrowth_vs_CASH:null,
  optimalWindow:null,financialGO:false,
  sourceEvidenceAuthenticated:false,N9S:"NO_GO",
  sealedM10Final:3200};
}
module.exports={classify,absence,normalizeQuote,normalizeReceipt,dec,stamp};
