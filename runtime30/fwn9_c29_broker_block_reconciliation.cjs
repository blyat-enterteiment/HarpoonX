"use strict";
/** C29 actual C25+C26 exported execution receipts to ONE financed account.
 * Does NOT call Alpaca, generate variants, open live accounts, place orders,
 * or treat historical OHLC fills as broker fills. Caller-provided JSON remains
 * unauthenticated unless independently signed and source-vetted elsewhere.
 */
const A=require("node:assert/strict");
const C25=require("./fwn9_c25_broker_export_ingest.cjs");
const C26=require("./fwn9_c26_causal_quote_fill_bridge.cjs");
const P=require("./fwn9_c29_frozen_assignments.cjs");
const I=require("./fwn9_c29_randomization_inference.cjs");
function need(x,c){A.ok(x,"C29B_"+c);}
function ms(s){const d=Date.parse(s);need(Number.isSafeInteger(d),"ISO_CLOCK");return d;}
const SKEW=60000;
function auditBlock(b,row){
 need(row&&row.blockId===b.blockId&&row.arm===b.arm,
  "FROZEN_BLOCK_BINDING");
 const account=row.accountExport;
 need(account&&account.schema==="HARPOON_FWN9_C25_ALPACA_OFFLINE_BUNDLE_1",
  "C25_RAW_BROKER_EXPORT_REQUIRED");
 const source=C25.certify(account);
 need(source.N9S===undefined&&source.admission.N9S==="NO_GO"&&
  source.validated.independentCashAndInventoryReconciled,
  "C25_ACCOUNT_REQUIRED");
 need(source.mode==="PAPER"||source.mode==="LIVE",
  "BROKER_CAPTURE_MODE");
 const start=ms(account.from),end=ms(account.through),
  collected=ms(account.collected_at);
 need(Math.abs(start-b.startAt)<=SKEW&&
  Math.abs(end-b.washoutEndAt)<=SKEW&&
  collected>=end&&collected<=b.fundingReviewEndAt,
  "SOURCE_INTERVAL_NOT_MATCHING_PREASSIGNED_BLOCK");
 need(Array.isArray(account.baseline.positions)&&
  account.baseline.positions.length===0&&
  Array.isArray(account.terminal.positions)&&
  account.terminal.positions.length===0,
  "OPEN_CARRY_POSITIONS_UNATTRIBUTABLE");
 need(source.validated.recordedCashFlowUsd===0&&
  source.validated.externalCostsDeclaredComplete===true&&
  source.validated.externalCostsNotInNavUsd===0,
  "MISSING_REAL_FUNDED_EXTERNAL_COST_OR_CASH_FLOW");
 const digest=new Set();
 let c26=null;
 const activities=account.activities.pages.flatMap(x=>x.rows);
 const fills=activities.filter(x=>x.activity_type==="FILL");
 const orders=account.orders.rows;
 for(const o of orders)
  need(ms(o.submitted_at)>=b.startAt-SKEW&&
   ms(o.submitted_at)<b.tradeEndAt,
   "ORDER_SUBMITTED_DURING_EMBARGO_OR_AFTER_TRADE");
 for(const x of fills)
  need(ms(x.transaction_time)<b.tradeEndAt,
   "FILL_AFTER_MAXIMUM_TRADE_WINDOW");
 if(fills.length>0){
  need(row.quoteReceiptBundle&&
   row.quoteReceiptBundle.schema==="HARPOON_FWN9_C26_CAUSAL_QUOTE_FILL_BUNDLE_1",
   "C26_PREDECISION_QUOTE_AND_RECEIPT_REQUIRED");
  const reference=C25.certify(row.quoteReceiptBundle.account_export);
  need(reference.sourceDigestSha256===source.sourceDigestSha256,
   "C25_C26_MUST_SHARE_EXACT_RAW_SOURCE_EXPORT");
  c26=C26.classify(row.quoteReceiptBundle);
  need(c26.observedFillCount===fills.length&&
   c26.matchedFillCount===fills.length,
   "COMPLETE_SOURCE_FILL_MATCH");
  for(const detail of c26.details){
   need(detail.receiptKnownAt<=b.tradeEndAt&&
    detail.decisionAt>=b.startAt-SKEW&&
    detail.quoteKnownAt<=detail.decisionAt,
    "RECEIPT_NOT_KNOWN_BY_TRADE_WINDOW_END");
   need(!digest.has(detail.activityDigest),"DUPLICATE_BROKER_FILL_DIGEST");
   digest.add(detail.activityDigest);
  }
 }else need(row.quoteReceiptBundle===null||row.quoteReceiptBundle===undefined,
  "NO_FILLS_BUT_UNWARRANTED_C26_EXECUTION_DATA");
 if(b.arm==="CASH")need(orders.length===0&&fills.length===0,
  "CASH_ARM_CONTAINS_BROKER_ORDERS");
 // Source-native broker NAV has already charged brokerage FEE activities.
 // Other external subscription/infra costs are not provably inside broker
 // equity; the strict one-financed-book contract rejects them until booked
 // in the same physical ledger or externally audited liability waterfall.
 const net=source.validated.algebraicAccountPnlUsd;
 const fees=Math.max(0,-source.validated.reportedFeeCashUsd);
 need(fees>=0,"FEES_SIGN");
 const originalGross=net+fees;
 const begin=Number(account.baseline.account.equity),
  ending=Number(account.terminal.account.equity);
 need(Number.isFinite(begin)&&Number.isFinite(ending)&&begin>0&&ending>0,
  "BROKER_NAV_DOMAIN");
 need(Math.abs(ending-begin-net)<=1e-6,
  "SOURCE_NATIVE_ECONOMIC_NAV_PARITY");
 need(typeof row.cashReferenceRate==="number"&&
  Number.isFinite(row.cashReferenceRate)&&row.cashReferenceRate>-1&&
  Number.isSafeInteger(row.cashRateKnownAt)&&
  row.cashRateKnownAt<=b.startAt,
  "CASH_BENCHMARK_PRIOR_TO_ASSIGNMENT");
 return {blockId:b.blockId,arm:b.arm,startAt:b.startAt,
  tradeEndAt:b.tradeEndAt,washoutEndAt:b.washoutEndAt,
  assignmentKnownAt:b.assignmentKnownAt,
  flatAtStart:true,flatAtTradeEnd:true,flatAtWashoutEnd:true,
  receiptKnownAt:collected,
  accountFingerprint:"SHA256_OF_BROKER_ACCOUNT_ID_NOT_RETURNED_TO_USER",
  accountIdentityInternal:account.account_id,
  beginningEquityUsd:begin,endingEquityUsd:ending,
  grossEconomicPnlUsd:originalGross,
  tradingFeesUsd:fees,externalCostsUsd:0,externalFlowUsd:0,
  costCoverageComplete:true,ledgerReconciled:true,
  cashReferenceRate:row.cashReferenceRate,
  cashRateKnownAt:row.cashRateKnownAt,
  sourceFillActivityDigests:[...digest],
  brokerReceiptSourceIndependent:false,
  marketQuoteSourceIndependent:false,
  accountSourceHash:source.sourceDigestSha256,
  brokerObservationTimestampErrorMs:{
   atStart:start-b.startAt,atEnd:end-b.washoutEndAt},
  C25C26RealAccountAuthenticationIndependentlyVerified:false,
  portfolioNAVReconstructedFromOriginalAccount:true,
  exchangeQueueFillPriceAttainableCounterfactually:false};
}
function auditStudy({plan,blocks,sourceProof}={}){
 P.validate(plan);
 need(Array.isArray(blocks)&&blocks.length===plan.blocks.length,
  "ALL_PRESPECIFIED_BLOCK_SOURCE_EXPORTS_REQUIRED");
 need(sourceProof?.schema==="HARPOON_FWN9_C29_C27_C28_ALL_FIVE_MINUTES_VERIFIED_1"&&
  sourceProof.sourceVerifiedBars===sourceProof.expectedBars&&
  sourceProof.noMarketOHLCUsedInProof===true,
  "COMPLETE_PREBAR_SOURCE_GRID_REQUIRED");
 const verified=[],receiptIds=new Set();
 let id=null;
 for(let i=0;i<blocks.length;i++){
  const d=auditBlock(plan.blocks[i],blocks[i]);
  if(id===null)id=d.accountIdentityInternal;
  need(d.accountIdentityInternal===id,"MULTIPLE_BROKER_ACCOUNTS");
  for(const x of d.sourceFillActivityDigests){
   need(!receiptIds.has(x),"BROKER_FILL_DUPLICATED_ACROSS_BLOCKS");
   receiptIds.add(x);
  }
  const safe={...d};delete safe.accountIdentityInternal;
  verified.push(safe);
 }
 const measured=I.audit({plan,observedBlocks:verified});
 return {...measured,
  schema:"HARPOON_FWN9_C29_C25_C26_C27_C28_JOINED_OFFLINE_AUDIT_1",
  originalBrokerAccountIdNotReturned:true,
  quoteTimeAndNAVProofScope:"OFFLINE_CONTRACT_COHERENCE_NOT_BROKER_ATTESTATION",
  externallyVerifiedExchangeAndBrokerSource:false,
  allC27C28ClockSlotsCompleteWithinDeclaredGrid:true,
  actualC27C28SourceFilesReplayed:sourceProof.originalC27C28FilesActuallyReplayed===true,
  networkAccountActuallyQueriedByThisAudit:false,
  privateSourceOriginVerifiedByPinnedIndependentVerifier:false,
  realProspectiveOutperformanceCertified:false,
  finalFinancialGO:false,N9S:"NO_GO"};
}
function absent(){
 return {schema:"HARPOON_FWN9_C29_C25_C26_C27_C28_JOINED_OFFLINE_AUDIT_1",
  status:"BLOCKED_NO_AUTHENTICATED_NATIVE_PRODUCER_AND_BROKER_RECEIPTS",
  sixArmsActuallyExecutedProspectively:false,
  brokerEvidenceRetrievedByThisAudit:false,
  SharpeOrAlphaCorrectedPopulationBound:null,
  netGrowthVsCash:null,netGrowthVsOriginal:null,
  financialGO:false,N9S:"NO_GO",M10FinalSealed:3200};
}
module.exports={auditBlock,auditStudy,absent};
