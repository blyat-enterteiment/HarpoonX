"use strict";
/**
 * C35: Alpaca PAPER trade_updates source-time witness. This module is a
 * passive parser and C25 FILL cross-check; it does not connect to a broker,
 * emit orders, or confer broker/authentication authority.
 */
const A=require("node:assert/strict");
const C25=require("./fwn9_c25_broker_export_ingest.cjs");
const C26=require("./fwn9_c26_causal_quote_fill_bridge.cjs");
const {netLedgerDigest}=require("./net_accounting.js");
const SCHEMA="HARPOON_FWN9_C35_PAPER_TRADE_UPDATE_WITNESS_1";
const EVENTS=new Set(["new","fill","partial_fill","canceled","expired",
 "done_for_day","replaced","accepted","rejected","pending_new",
 "stopped","pending_cancel","pending_replace","calculated",
 "suspended","order_replace_rejected","order_cancel_rejected"]);
const FILLS=new Set(["fill","partial_fill"]);
function need(x,k){A.ok(x,"C35_"+k);}
function text(x,k){need(typeof x==="string"&&x.length>0&&x.length<=500,k);return x;}
function clock(x,k){need(Number.isSafeInteger(x)&&x>0,k);return x;}
function decimal(x,k){
 need(typeof x==="string"&&/^(?:0|[1-9]\d*)(?:\.\d{1,8})?$/.test(x),k);
 return C26.dec(x,k,{positive:false});
}
function decode(raw){
 need(Buffer.isBuffer(raw)||typeof raw==="string","RAW_MESSAGE_TYPE");
 const s=Buffer.isBuffer(raw)?raw.toString("utf8"):raw;
 need(Buffer.byteLength(s)<1024*1024,"RAW_SIZE_LIMIT");
 const parsed=JSON.parse(s);
 need(parsed&&typeof parsed==="object"&&!Array.isArray(parsed),
  "ORIGINAL_ALPACA_STREAM_OBJECT_REQUIRED");
 return parsed;
}
function observe(raw,receivedAtMs,{priorExecutionIds=new Set()}={}){
 const event=decode(raw);
 need(event.stream==="trade_updates"&&
  event.data&&typeof event.data==="object"&&
  !Array.isArray(event.data),"TRADE_UPDATES_STREAM");
 const data=event.data,kind=text(data.event,"EVENT");
 need(EVENTS.has(kind),"UNSUPPORTED_ORDER_EVENT");
 const order=data.order;
 need(order&&typeof order==="object"&&!Array.isArray(order),
  "ORIGINAL_ORDER_BODY");
 const orderId=text(order.id,"BROKER_ORDER_ID");
 const at=clock(receivedAtMs,"LOCAL_RECEIVED_AT");
 const multi=order.order_class==="mleg"||Array.isArray(data.legs)&&data.legs.length>0;
 const f=FILLS.has(kind);
 let executedAt=null,executionId=null,qty=null,price=null;
 if(f){
  executedAt=text(data.timestamp,"FILL_EXECUTED_AT");
  need(C26.stampNs(executedAt,"BROKER_EXECUTION_TIME")<=
   BigInt(at)*1000000n,"BROKER_EVENT_AFTER_LOCAL_RECEIPT");
  if(!multi){
   executionId=text(data.execution_id,"EXECUTION_ID");
   need(!priorExecutionIds.has(executionId),"DUPLICATE_EXECUTION_ID");
   qty=text(data.qty,"FILL_QTY");
   price=text(data.price,"FILL_PRICE");
   need(decimal(qty,"QTY")>0n&&decimal(price,"PRICE")>0n,
    "POSITIVE_QTY_PRICE");
  }
 }
 return {
  schema:SCHEMA,source:"ALPACA_PAPER_TRADE_UPDATES_WS_CLAIM",
  event:kind,brokerOrderId:orderId,
  clientOrderId:typeof order.client_order_id==="string"?
   order.client_order_id:null,
  symbol:typeof order.symbol==="string"?order.symbol:null,
  side:typeof order.side==="string"?order.side:null,
  executionId,brokerExecutionAt:executedAt,receivedAtMs:at,
  qty,price,multilegOptionsUnsupported:multi,
  rawMessageDigest:netLedgerDigest(event),
  // Serialized personally sensitive order IDs live only in a private local
  // journal. Never publish this record to GitHub.
  sourceOrderSubmittedAt:order.submitted_at??null,
  sourceOrderStatus:order.status??null,
  localReceiveClockExternallyAuthenticated:false,
  alpacaProviderEventCryptographicallySigned:false,
  brokerOrderCreatedByThisObserver:false,
  tradingAuthority:false,N9S:"NO_GO"
 };
}
/** A stream is not complete unless it has explicit auth and subscribe ACKs.
 * The caller must treat every disconnect, timeout and parser error as a gap.
 */
function session(){
 let state="AWAIT_AUTH",closed=false,count=0,last=0;
 const executions=new Set();
 return {
  status(){return {state,events:count,closed,
    continuousAuthenticatedCoverageProved:false,
    financialGO:false,N9S:"NO_GO"};},
  message(raw,receivedAtMs){
   need(!closed,"CLOSED_STREAM");
   const input=decode(raw);
   if(state==="AWAIT_AUTH"){
    need(input.stream==="authorization"&&
     input.data?.status==="authorized","PAPER_AUTH_ACK_REQUIRED");
    state="AWAIT_SUBSCRIBE";return {type:"SEND_LISTEN"};
   }
   if(state==="AWAIT_SUBSCRIBE"){
    need(input.stream==="listening"&&
     Array.isArray(input.data?.streams)&&
     input.data.streams.length===1&&
     input.data.streams[0]==="trade_updates",
     "TRADE_UPDATES_LISTEN_ACK_REQUIRED");
    state="LISTENING";return {type:"READY"};
   }
   need(state==="LISTENING","LISTENER_STATE");
   need(receivedAtMs>=last,"LOCAL_CLOCK_REGRESSION");
   const record=observe(raw,receivedAtMs,{
    priorExecutionIds:executions
   });
   if(record.executionId)executions.add(record.executionId);
   last=receivedAtMs;count++;
   return {type:"EVENT",record};
  },
  close(){closed=true;state="CLOSED_UNPROVEN_GAP";
   return this.status();}
 };
}
function reconcile({accountExport,streamRecords,sessionEndedWithGap=false}={}){
 need(Array.isArray(streamRecords)&&streamRecords.length>0,
  "PROSPECTIVE_STREAM_EVENTS_REQUIRED");
 const account=C25.certify(accountExport);
 need(account.mode==="PAPER","PAPER_C25_ONLY");
 let last=0;const ids=new Set(),tokens=[];
 for(const r of streamRecords){
  need(r?.schema===SCHEMA&&
   r.localReceiveClockExternallyAuthenticated===false&&
   r.alpacaProviderEventCryptographicallySigned===false&&
   r.brokerOrderCreatedByThisObserver===false&&r.tradingAuthority===false&&
   r.N9S==="NO_GO"&&
   r.receivedAtMs>=last&&
   typeof r.brokerOrderId==="string"&&
   typeof r.rawMessageDigest==="string",
   "UNTRUSTED_OR_OUT_OF_ORDER_STREAM");
  last=r.receivedAtMs;
  if(!FILLS.has(r.event))continue;
  need(!r.multilegOptionsUnsupported&&
   r.executionId&&r.symbol&&r.side&&r.qty&&r.price&&
   r.brokerExecutionAt,"OPTIONS_OR_AMBIGUOUS_EXECUTION");
  need(!ids.has(r.executionId),"DUPLICATE_EXECUTION_ID");
  ids.add(r.executionId);
  const ns=C26.stampNs(r.brokerExecutionAt,"STREAM_EXECUTION_NS");
  tokens.push({id:r.executionId,order:r.brokerOrderId,
   symbol:r.symbol,side:r.side,timeNs:ns,
   qty:decimal(r.qty,"STREAM_QTY"),
   price:decimal(r.price,"STREAM_PRICE"),
   knownAt:r.receivedAtMs});
 }
 const activities=C25.flattenPages(accountExport.activities.pages,
  accountExport.activities.page_size);
 const fills=activities.filter(r=>r.activity_type==="FILL");
 const matched=new Set(),matches=[];
 const until=Date.parse(accountExport.through),
  from=Date.parse(accountExport.from);
 for(const a of fills){
  const ts=C26.stampNs(a.transaction_time,"ACCOUNT_EXECUTION_NS");
  const possible=tokens.filter(t=>
   t.order===a.order_id&&t.symbol===a.symbol&&t.side===a.side&&
   t.timeNs===ts&&t.qty===decimal(a.qty,"ACCOUNT_QTY")&&
   t.price===decimal(a.price,"ACCOUNT_PRICE"));
  need(possible.length===1,"FILL_MATCH_MISSING_OR_AMBIGUOUS");
  const t=possible[0];
  need(!matched.has(t.id)&&t.knownAt<=Date.parse(accountExport.collected_at),
   "DUPLICATE_MATCH_OR_RECEIPT_AFTER_ACCOUNT_CAPTURE");
  matched.add(t.id);
  matches.push({activityDigest:netLedgerDigest(a),
   executionIdDigest:netLedgerDigest({id:t.id}),
   matchedBy:"ORDER_SYMBOL_SIDE_EXECUTION_NS_QTY_PRICE",
   localReceiptKnownAt:t.knownAt,
   timestampProvenance:"LOCAL_WALL_CLOCK_ONLY_NOT_INDEPENDENT",
   nativeBrokerEventSignatureVerified:false});
 }
 const unmatchedInWindow=tokens.filter(t=>!matched.has(t.id)&&
  Number(t.timeNs/1000000n)>from&&Number(t.timeNs/1000000n)<=until);
 need(unmatchedInWindow.length===0,
  "STREAM_EXECUTION_IN_WINDOW_WITHOUT_ACCOUNT_FILL");
 return {
  schema:"HARPOON_FWN9_C35_PAPER_STREAM_C25_EXACT_FILL_JOIN_1",
  accountSourceHash:account.sourceDigestSha256,
  seenStreamFillEvents:tokens.length,
  matchedSourceFillEvents:matched.size,
  accountFills:fills.length,
  matchedReceipts:matches,
  originalC25IndependentCashAndInventoryVerified:
   account.validated.independentCashAndInventoryReconciled,
  completeStreamCoverageProven:!sessionEndedWithGap&&false,
  networkStreamActuallyConnectedByThisFunction:false,
  providerSignedSourceAndClockAuthenticated:false,
  c26KnownQuoteBeforeDecisionCertified:false,
  lateBrokerFeeRestatementClosed:false,
  optionsContractExecutionSupported:false,
  genuineProspectiveFinancialReturnsObserved:false,
  financialGO:false,N9S:"NO_GO",M10FinalSealed:3200
 };
}
module.exports={SCHEMA,decode,observe,session,reconcile};
