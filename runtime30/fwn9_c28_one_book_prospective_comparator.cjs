"use strict";
/** C28: SINGLE funded account net-log evaluation, with preassigned arms.
 *
 * Produces descriptive bookkeeping, NEVER a financial GO from locally supplied
 * JSON or an OHLC simulation. Real randomized prospective acceptance requires
 * authenticated broker source, signed pre-outcome registration, full opportunity
 * coverage and independently verified original+cash comparability.
 */
const A=require("node:assert/strict");
const C22=require("./fwn9_c22_session_compound.cjs");
const C26=require("./fwn9_c26_causal_quote_fill_bridge.cjs");
const SOURCES=require("./fwn9_c28_source_obligations.cjs");
const ARMS=Object.freeze([...SOURCES.EXPECTED.map(x=>x.policy),
 "ORIGINAL_BASELINE","CASH"]);
function need(v,tag){A.ok(v,"C28P_"+tag);}
function str(v,k){need(typeof v==="string"&&v.length>0&&v.length<=256,k);return v;}
function t(v,k){need(Number.isSafeInteger(v)&&v>=0,k);return v;}
function num(v,k){need(typeof v==="number"&&Number.isFinite(v),k);return v;}
function assess({sourcePanel,brokerBundle=null,periods=[],
  prespecified=null}={}){
 need(sourcePanel?.schema==="HARPOON_FWN9_C28_COMPLETE_C27_SLOT_OBSERVABILITY_1"&&
  sourcePanel.completeSchedule===true&&
  sourcePanel.FWN9FinancialGo===false&&sourcePanel.M10Sealed===3200,
  "SOURCE_C27_C28_PANEL_REQUIRED");
 need(Array.isArray(periods)&&periods.length<=100000,"PERIODS");
 const prereg=prespecified;
 if(prereg!==null){
  need(prereg?.schema==="HARPOON_FWN9_C28_FROZEN_ARM_ASSIGNMENTS_1"&&
   Array.isArray(prereg.assignments)&&
   prereg.assignments.length===periods.length&&
   prereg.researchVariants.length===6&&
   prereg.researchVariants.every((x,i)=>x===ARMS[i]),
   "ORIGINAL_SIX_VARIANTS_ONLY");
 }
 let broker=null;
 if(brokerBundle!==null){
  broker=C26.classify(brokerBundle);
  need(broker.N9S==="NO_GO"&&broker.conservationC25===true,
   "C26_REAL_ACCOUNT_RECONCILIATION_REQUIRED");
 }
 const names=new Set(),all=[],forCompound=[];
 if(periods.length>0)need(periods[0].beginningEquityUsd===20000,
  "ORIGINAL_FROZEN_20000_INITIAL_ACCOUNT_CAPITAL");
 let id=null,prior=-1,cashLog=0;
 const counts=Object.fromEntries(ARMS.map(x=>[x,{
  completedBlocks:0,netLogSum:0,netEconomicPnlUsd:0,
  sourceOriginAuthenticated:false
 }]));
 for(let i=0;i<periods.length;i++){
  const r=periods[i];
  need(r&&typeof r==="object","PERIOD");
  const label=str(r.arm,"ARM");
  need(ARMS.includes(label),"FROZEN_ARM_RESEARCH_ONLY");
  const key=str(r.blockId,"BLOCK_ID");
  need(!names.has(key),"DUPLICATE_BLOCK");names.add(key);
  const a=t(r.startAt,"START_AT"),b=t(r.endAt,"END_AT"),
   k=t(r.knownAt,"RECEIPT_KNOWN_AT");
  need(b>a&&a>=prior&&k>=b,"PERIOD_CAUSAL_TIMELINE");
  const freeze=t(r.assignmentKnownAt,"FROZEN_ASSIGNMENT_KNOWN_AT");
  need(freeze<=a,"ASSIGNMENT_CHOSEN_AFTER_OUTCOME");
  if(prereg!==null){
   const pre=prereg.assignments[i];
   need(pre.blockId===key&&pre.arm===label&&
    pre.assignmentKnownAt===freeze&&pre.startAt===a,
    "ASSIGNMENT_NOT_REGISTERED_EX_ANTE");
  }
  const account=str(r.accountFingerprint,"ONE_ACCOUNT_FINGERPRINT");
  if(id===null)id=account;
  need(id===account,"INDEPENDENT_ACCOUNTS_NOT_ONE_FINANCED_BOOK");
  need(r.flatAtStart===true&&r.flatAtEnd===true,
   "CROSS_ARM_CARRY_EXPOSURE_NOT_ATTRIBUTABLE");
  need(Array.isArray(r.sourceReceiptDigests)&&
   r.sourceReceiptDigests.every(x=>typeof x==="string"&&/^[a-f0-9]{64}$/.test(x)),
   "BASIC_RECEIPT_ID_DIGEST_COVERAGE");
  const cashRate=num(r.cashReturnFraction,"CASH_BENCHMARK_RETURN");
  need(cashRate>-1&&t(r.cashRateKnownAt,"CASH_SOURCE_KNOWN_AT")<=a,
   "FUTURE_CASH_BENCHMARK");
  const gross=num(r.grossEconomicPnlUsd,"GROSS_PNL"),
   fees=num(r.tradingFeesUsd,"TRADING_FEES"),
   external=num(r.externalCostsUsd,"EXTERNAL_COSTS");
  need(fees>=0&&external>=0&&num(r.externalFlowUsd,"EXTERNAL_FLOW")===0,
   "SINGLE_BOOK_FLOW_AND_FEES");
  need(r.ledgerReconciled===true&&r.costCoverageComplete===true,
   "UNVERIFIED_COST_COVERAGE");
  if(label!=="CASH"&&gross!==0)
   need(r.sourceReceiptDigests.length>0,
    "TRADED_GROSS_GAIN_WITHOUT_ANY_SOURCE_FILL_RECEIPT");
  if(label==="CASH")need(r.sourceReceiptDigests.length===0,
   "CASH_CONTROL_MUST_NOT_USE_TRADING_FILLED_ORDERS");
  if(i>0){
   need(periods[i-1].knownAt<=a,"NO_REUSE_OF_UNKNOWN_PROCEEDS");
  }
  forCompound.push({
   startAt:a,endAt:b,knownAt:k,beginningEquityUsd:r.beginningEquityUsd,
   endingEquityUsd:r.endingEquityUsd,grossEconomicPnlUsd:gross,
   tradingFeesUsd:fees,externalCostsUsd:external,
   externalFlowUsd:0,ledgerReconciled:true,costCoverageComplete:true
  });
  const base=num(r.beginningEquityUsd,"BEGINNING_EQUITY"),
   ending=num(r.endingEquityUsd,"ENDING_EQUITY");
  need(base>0&&ending>0,"POSITIVE_WEALTH");
  const netLog=Math.log(ending/base);
  const group=counts[label];
  group.completedBlocks++;
  group.netLogSum+=netLog;
  group.netEconomicPnlUsd+=gross-fees-external;
  cashLog+=Math.log1p(cashRate);
  all.push({blockId:key,arm:label,
   sourceReceiptCount:r.sourceReceiptDigests.length,
   netLogGrowth:netLog,knownAt:k,
   cashReferenceLogGrowth:Math.log1p(cashRate)});
  prior=b;
 }
 const w=periods.length?C22.compound(periods[0].beginningEquityUsd,
  forCompound):null;
 const issues=[];
 if(periods.length===0)issues.push("NO_OBSERVED_PROSPECTIVE_FINANCED_BLOCKS");
 if(prereg===null)issues.push("NO_EX_ANTE_ARM_ASSIGNMENT_REGISTRY");
 if(!broker)issues.push("NO_INDEPENDENTLY_VERIFIED_BROKER_FILLS_OR_NAV");
 else{
  issues.push("C26_OFFLINE_RECEIPT_SOURCE_STILL_UNAUTHENTICATED");
  issues.push("C26_DOES_NOT_PROVE_EXCHANGE_QUEUE_OR_COUNTERFACTUAL_FILLS");
 }
 if(counts.ORIGINAL_BASELINE.completedBlocks===0)
  issues.push("NO_ORIGINAL_POLICY_EXECUTED_BASELINE");
 if(counts.CASH.completedBlocks===0)issues.push("NO_CASH_EXECUTED_CONTROL");
 for(const policy of ARMS.slice(0,6))
  if(counts[policy].completedBlocks<30)
   issues.push("INSUFFICIENT_PROSPECTIVE_INDEPENDENT_BLOCKS:"+policy);
 issues.push("RANDOMIZATION_PROVENANCE_AND_EXCHANGE_EVENT_AUTHENTICATION_UNVERIFIED");
 issues.push("NO_VALID_MULTIPLE_TESTING_INFERENCE_WITHOUT_DEPENDENCE_PROOF");
 issues.push("ORIGINAL_M9_C21_OHLC_FIRST_CROSS_NON_EQUIVALENCE");
 return {schema:"HARPOON_FWN9_C28_ONE_FINANCED_ACCOUNT_RESEARCH_COMPARATOR_1",
  description:"DESCRIPTIVE_ONLY_NO_C28_FINANCIAL_PASS",
  accountsCombined:1,periodCount:periods.length,
  perArm:counts,blocks:all,
  fundedEconomicNetReturn:w?w.compoundReturn:null,
  fundedNetLogGrowth:w?w.logGrowth:null,
  cashReferenceLogGrowth:periods.length?cashLog:null,
  accountLogGrowthMinusDeclaredCashReference:
   w?w.logGrowth-cashLog:null,
  originalPolicyPairedExecutableAlphaCertified:false,
  sixVariantsOutperformedCashAndOriginalCertified:false,
  alphaFamilywiseAdjustedCertified:false,
  sourceTapC27CompletenessWithinRegisteredGrid:true,
  brokerSourceAuthenticatedExternally:false,
  completenessAndRealExecutionBlockers:issues,
  canOpenM10Final:false,canDeployOrTrade:false,
  N9S:"NO_GO",finalM10Sealed:3200};
}
module.exports={ARMS,assess};
