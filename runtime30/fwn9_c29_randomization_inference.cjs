"use strict";
/** C29 prespecified cycle-stratified RANDOMIZATION diagnostic.
 *
 * The pairwise sharp-no-treatment-effect randomization null, conditional on
 * each cycle's two arm/control positions, permits exact sign-flips of the
 * within-cycle contrast. HOLM corrects six intersection-union hypotheses:
 * each candidate must be better than CASH AND the original policy.
 *
 * This is NOT a population CI, no effect heterogeneity/carryover inference,
 * and cannot certify economic GO from user-authored economic rows or local
 * account/quote hashes. No market RNG or strategy optimization.
 */
const A=require("node:assert/strict");
const crypto=require("node:crypto");
const P=require("./fwn9_c29_frozen_assignments.cjs");
const C28=require("./fwn9_c28_one_book_prospective_comparator.cjs");
const MS_DAY=86400000;
function need(ok,c){A.ok(ok,"C29I_"+c);}
function rng(seed,i){return crypto.createHash("sha256")
 .update("C29_TEST_ONLY_SIGNFLIP_V1|"+seed+"|"+i).digest();}
function signFlipP(d,seed){
 need(Array.isArray(d)&&d.length>=4&&d.length<=128&&
  d.every(x=>typeof x==="number"&&Number.isFinite(x)),
  "DIFFERENCES");
 const observed=d.reduce((a,b)=>a+b,0);
 let exceed=0;
 if(d.length<=18){
  const n=2**d.length;
  for(let mask=0;mask<n;mask++){
   let total=0;
   for(let i=0;i<d.length;i++)total+=(mask&(2**i))?d[i]:-d[i];
   if(total>=observed-1e-12)exceed++;
  }
  return {p:exceed/n,method:"EXACT_CONDITIONAL_SIGN_FLIP",
   alternatives:n,observedSum:observed};
 }
 // Computational fallback. Under randomized sign draws, plus-one Monte Carlo
 // p is conservative under the exact sharp null. NOT an e-value nor CI.
 const draws=19999;
 for(let k=0;k<draws;k++){
  let sum=0;
  const bits=rng(seed,k);
  for(let i=0;i<d.length;i++){
   const b=(bits[Math.floor(i/8)%bits.length]>>(i%8))&1;
   sum+=b?d[i]:-d[i];
  }
  if(sum>=observed-1e-12)exceed++;
 }
 return {p:(exceed+1)/(draws+1),
  method:"DETERMINISTIC_MONTE_CARLO_SIGN_FLIP_PLUS_ONE",
  alternatives:draws,observedSum:observed};
}
function holm(pvals){
 const sorted=pvals.map((x,i)=>({p:x,i})).sort((a,b)=>a.p-b.p||a.i-b.i);
 const adj=Array(pvals.length).fill(1);
 let prev=0;
 for(let rank=0;rank<sorted.length;rank++){
  prev=Math.max(prev,Math.min(1,(sorted.length-rank)*sorted[rank].p));
  adj[sorted[rank].i]=prev;
 }
 return adj;
}
function audit({plan,observedBlocks,sourceAuthenticated=false,
  randomizationExternallyAttested=false}={}){
 P.validate(plan);
 need(Array.isArray(observedBlocks)&&observedBlocks.length===plan.blocks.length,
  "COMPLETE_INTENTION_TO_TREAT_BLOCKS");
 const data=Array.from({length:plan.cycles},()=>new Map());
 const blockRows=[];
 let account=null,wealth=null,priorKnown=0;
 for(let i=0;i<observedBlocks.length;i++){
  const row=observedBlocks[i],b=plan.blocks[i];
  need(row&&row.blockId===b.blockId&&row.arm===b.arm&&
   row.startAt===b.startAt&&row.tradeEndAt===b.tradeEndAt&&
   row.washoutEndAt===b.washoutEndAt&&
   row.assignmentKnownAt===b.assignmentKnownAt,
   "BLOCK_OUTCOME_PREASSIGNED");
  need(row.flatAtStart===true&&row.flatAtTradeEnd===true&&
   row.flatAtWashoutEnd===true,"POSITIVE_NO_CARRYOVER_STATE");
  need(Number.isSafeInteger(row.receiptKnownAt)&&
   row.receiptKnownAt>=b.washoutEndAt&&
   row.receiptKnownAt<=b.fundingReviewEndAt&&
   row.startAt>=priorKnown,"RECEIPT_FINANCING_GAP");
  const fingerprint=row.accountFingerprint;
  need(typeof fingerprint==="string"&&fingerprint.length>0&&
   (account===null||account===fingerprint),
   "SINGLE_PHYSICAL_FUNDED_ACCOUNT");
  account=fingerprint;
  for(const k of ["beginningEquityUsd","endingEquityUsd",
   "grossEconomicPnlUsd","tradingFeesUsd","externalCostsUsd","externalFlowUsd",
   "cashReferenceRate"]){
   need(typeof row[k]==="number"&&Number.isFinite(row[k]),"FINITE_"+k);
  }
  need(row.beginningEquityUsd>0&&row.endingEquityUsd>0&&
   row.tradingFeesUsd>=0&&row.externalCostsUsd>=0&&
   row.externalFlowUsd===0&&row.cashReferenceRate>-1&&
   row.costCoverageComplete===true&&row.ledgerReconciled===true,
   "ONE_BOOK_NET_COST_ACCOUNTING");
  if(i===0)need(row.beginningEquityUsd===20000,
   "FIXED_INITIAL_FUNDED_20000");
  else need(Math.abs(row.beginningEquityUsd-wealth)<=1e-7,
   "NO_RESTART_OR_HIDDEN_WASHOUT_FUNDS");
  const pnl=row.grossEconomicPnlUsd-row.tradingFeesUsd-row.externalCostsUsd;
  need(Math.abs(row.endingEquityUsd-row.beginningEquityUsd-pnl)<=1e-7,
   "ECONOMIC_LEDGER_SELF_FINANCING");
  need(Number.isSafeInteger(row.cashRateKnownAt)&&
   row.cashRateKnownAt<=b.startAt,"PRIOR_CASH_RATE_REQUIRED");
  need(Array.isArray(row.sourceFillActivityDigests)&&
   row.sourceFillActivityDigests.every(v=>/^[a-f0-9]{64}$/.test(v))&&
   (b.arm!=="CASH"||row.sourceFillActivityDigests.length===0)&&
   (b.arm==="CASH"||pnl===0||row.sourceFillActivityDigests.length>0),
   "NO_IMPUTED_STRATEGY_FILLS");
  need(row.brokerReceiptSourceIndependent===false&&
   row.marketQuoteSourceIndependent===false,
   "NO_SELF_AUTHENTICATED_BROKER");
  const returnRate=Math.log(row.endingEquityUsd/row.beginningEquityUsd)/
   ((b.washoutEndAt-b.startAt)/MS_DAY);
  need(!data[b.cycle].has(b.arm),"DUPLICATE_ARM_IN_CYCLE");
  data[b.cycle].set(b.arm,returnRate);
  blockRows.push({cycle:b.cycle,arm:b.arm,returnRate,
   cashSourceDailyRate:Math.log1p(row.cashReferenceRate)/
    ((b.washoutEndAt-b.startAt)/MS_DAY),
   sourceFillCount:row.sourceFillActivityDigests.length,
   realBrokerOriginExternallyVerified:false});
  wealth=row.endingEquityUsd;priorKnown=row.receiptKnownAt;
 }
 for(const cycle of data)need(cycle.size===8,
  "INCOMPLETE_EIGHT_ARM_RANDOMIZED_CYCLE");
 const tests=C28.ARMS.slice(0,6).map((arm,i)=>{
  const cash=[],original=[];
  for(const cycle of data){
   cash.push(cycle.get(arm)-cycle.get("CASH"));
   original.push(cycle.get(arm)-cycle.get("ORIGINAL_BASELINE"));
  }
  const pCash=signFlipP(cash,plan.planDigest+"|"+arm+"|CASH"),
   pOriginal=signFlipP(original,plan.planDigest+"|"+arm+"|ORIGINAL");
  return {arm,contrast:"GREATER_THAN_BOTH_CASH_AND_ORIGINAL",
   meanDailyLogDifferenceCash:cash.reduce((a,b)=>a+b,0)/cash.length,
   meanDailyLogDifferenceOriginal:original.reduce((a,b)=>a+b,0)/original.length,
   sharpNullOneSidedPvsCash:pCash.p,
   sharpNullOneSidedPvsOriginal:pOriginal.p,
   intersectionUnionP:Math.max(pCash.p,pOriginal.p),
   method:pCash.method,
   populationEffectLowerConfidenceBound:null};
 });
 const adjusted=holm(tests.map(x=>x.intersectionUnionP));
 for(let i=0;i<tests.length;i++){
  tests[i].holmFWERAdjustedP=adjusted[i];
  tests[i].conditionalSharpNullRejectAt025=adjusted[i]<=.025&&
   tests[i].meanDailyLogDifferenceCash>0&&
   tests[i].meanDailyLogDifferenceOriginal>0;
 }
 const possibleMinimumP=2**(-plan.cycles);
 return {schema:"HARPOON_FWN9_C29_EXACT_RANDOMIZATION_SHARP_NULL_DIAGNOSTIC_1",
  studyDigest:plan.planDigest,cycles:plan.cycles,
  observedIntentionToTreatBlocks:observedBlocks.length,
  originalSixVariantsPreserved:true,
  cashAndOriginalControlsObservedWithinDistinctRandomizedTimeBlocks:true,
  onePhysicalFundedAccount:true,
  initialCapitalUsd:20000,
  terminalAccountWealthUsd:wealth,
  familywiseErrorTarget:.025,
  minimumAttainableExactPvsSingleControl:plan.cycles<=18?possibleMinimumP:null,
  singleHypothesisBestCaseHolmAdjustedP:
   plan.cycles<=18?Math.min(1,6*possibleMinimumP):null,
  canPotentiallyRejectFirstHypothesisAt025:
   plan.cycles>=8,
  exactMethodIsUnderPairwiseSharpNullAndNoCarryoverAssumption:true,
  blockTemporalDependenceBetweenSequentialPoliciesProved:false,
  priorAssignmentIndependentOfPotentialOutcomesExternallyAuthenticated:false,
  independentBrokerAndQuoteAuthenticityVerified:false,
  familywisePopulationAlphaCertified:false,
  statisticallySignificantSharpNullAloneCannotCertifyGrowth:true,
  tests,blockRows,
  rawObservedDiagnosticOnly:true,
  finalFinancialGO:false,holdoutM10Sealed:3200,
  ordersPlaced:0,N9S:"NO_GO"};
}
module.exports={signFlipP,holm,audit};
