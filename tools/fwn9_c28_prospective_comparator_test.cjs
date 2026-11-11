"use strict";
/** C28 financing & prospective comparator tests: synthetic BOOKKEEPING only.
 * Not newly executed trading accounts, signals, market data or alpha.
 */
const test=require("node:test"),A=require("node:assert/strict");
const P=require("../runtime30/fwn9_c28_one_book_prospective_comparator.cjs");
const C=require("../runtime30/fwn9_c28_source_obligations.cjs");
const base=()=>({schema:"HARPOON_FWN9_C28_COMPLETE_C27_SLOT_OBSERVABILITY_1",
 completeSchedule:true,FWN9FinancialGo:false,M10Sealed:3200});
const SHA="b".repeat(64);
const period=(override={})=>({
 blockId:"BLOCK_1",arm:"H22_OPENING_CONFIRMATION@RTH_OPEN_30",
 accountFingerprint:"SYNTHETIC_SINGLE_FUNDED_ACCOUNT",
 assignmentKnownAt:500,startAt:1000,endAt:2000,knownAt:2100,
 beginningEquityUsd:20000,endingEquityUsd:20100,
 grossEconomicPnlUsd:110,tradingFeesUsd:5,externalCostsUsd:5,
 externalFlowUsd:0,ledgerReconciled:true,costCoverageComplete:true,
 flatAtStart:true,flatAtEnd:true,sourceReceiptDigests:[SHA],
 cashReturnFraction:.001,cashRateKnownAt:400,...override
});
const prereg=(p)=>({schema:"HARPOON_FWN9_C28_FROZEN_ARM_ASSIGNMENTS_1",
 researchVariants:P.ARMS.slice(0,6),
 assignments:p.map(x=>({blockId:x.blockId,arm:x.arm,
  assignmentKnownAt:x.assignmentKnownAt,startAt:x.startAt}))});
function rejects(change,pattern){
 const p=[period()];change(p);
 A.throws(()=>P.assess({sourcePanel:base(),periods:p,prespecified:prereg(p)}),
  new RegExp("(?:C28P_|C22_)"+pattern));
}
test("C28 frozen exact six variants plus CASH and original are all retained",()=>{
 A.equal(P.ARMS.length,8);
 A.deepEqual(P.ARMS.slice(0,6),C.EXPECTED.map(x=>x.policy));
 A.equal(P.ARMS.at(-2),"ORIGINAL_BASELINE");
 A.equal(P.ARMS.at(-1),"CASH");
});
test("C28 zero sourced prospective blocks produces no false historic alpha",()=>{
 const r=P.assess({sourcePanel:base()});
 A.equal(r.periodCount,0);
 A.equal(r.fundedEconomicNetReturn,null);
 A.equal(r.sixVariantsOutperformedCashAndOriginalCertified,false);
 A.equal(r.N9S,"NO_GO");
 A(r.completenessAndRealExecutionBlockers.includes("NO_OBSERVED_PROSPECTIVE_FINANCED_BLOCKS"));
});
test("C28 deterministic one-book net financial example is DESCRIPTIVE only",()=>{
 const p=[period()],r=P.assess({sourcePanel:base(),periods:p,prespecified:prereg(p)});
 A.equal(r.periodCount,1);
 A(Math.abs(r.fundedEconomicNetReturn-.005)<1e-12);
 A(Math.abs(r.accountLogGrowthMinusDeclaredCashReference-
  (Math.log(20100/20000)-Math.log1p(.001)))<1e-12);
 A.equal(r.originalPolicyPairedExecutableAlphaCertified,false);
 A.equal(r.alphaFamilywiseAdjustedCertified,false);
 A.equal(r.brokerSourceAuthenticatedExternally,false);
});
test("C28 two actual periods compound one book and never reset initial capital",()=>{
 const p=[period(),period({blockId:"BLOCK_2",arm:"ORIGINAL_BASELINE",
  assignmentKnownAt:2100,startAt:2500,endAt:3500,knownAt:3600,
  beginningEquityUsd:20100,endingEquityUsd:20090,
  grossEconomicPnlUsd:-5,tradingFeesUsd:3,externalCostsUsd:2,
  cashReturnFraction:0,cashRateKnownAt:2400})];
 const r=P.assess({sourcePanel:base(),periods:p,prespecified:prereg(p)});
 A.equal(r.periodCount,2);
 A(Math.abs(r.fundedEconomicNetReturn-.0045)<1e-12);
 A.equal(r.perArm.ORIGINAL_BASELINE.completedBlocks,1);
 A.equal(r.perArm["H22_OPENING_CONFIRMATION@RTH_OPEN_30"].completedBlocks,1);
 A.equal(r.originalPolicyPairedExecutableAlphaCertified,false);
});
test("C28 independently funded second asset account cannot be silently merged",()=>{
 rejects(p=>p.push(period({blockId:"BLOCK_2",startAt:2500,endAt:3500,knownAt:3600,
  accountFingerprint:"NEW_20K_ACCOUNT",assignmentKnownAt:2000})),
  "INDEPENDENT_ACCOUNTS_NOT_ONE_FINANCED_BOOK");
});
test("C28 external deposits and fee-free PnL laundering rejected",()=>{
 rejects(p=>{p[0].externalFlowUsd=1000;},"SINGLE_BOOK_FLOW_AND_FEES");
 rejects(p=>{p[0].costCoverageComplete=false;},"UNVERIFIED_COST_COVERAGE");
 rejects(p=>{p[0].tradingFeesUsd=-5;},"SINGLE_BOOK_FLOW_AND_FEES");
});
test("C28 fabricated gains without NAV conservation rejected by C22 core",()=>{
 rejects(p=>{p[0].endingEquityUsd=30000;}, "SELF_FINANCED_EQUITY_IDENTITY");
});
test("C28 future arm assignment after block start is lookahead",()=>{
 rejects(p=>{p[0].assignmentKnownAt=1001;},
  "ASSIGNMENT_CHOSEN_AFTER_OUTCOME");
});
test("C28 invalid cash reference learned after execution period starts",()=>{
 rejects(p=>{p[0].cashRateKnownAt=1001;},"FUTURE_CASH_BENCHMARK");
});
test("C28 arbitrary new variant chosen after seeing return fails registered-arm gate",()=>{
 rejects(p=>{p[0].arm="H22_CRYPTO_UTC_LIQUIDITY@RETRO_BEST_HOUR";},
  "FROZEN_ARM_RESEARCH_ONLY");
});
test("C28 absent prespecified assignments cannot become causal comparison",()=>{
 const r=P.assess({sourcePanel:base(),periods:[period()]});
 A(r.completenessAndRealExecutionBlockers.includes(
  "NO_EX_ANTE_ARM_ASSIGNMENT_REGISTRY"));
 A.equal(r.sixVariantsOutperformedCashAndOriginalCertified,false);
});
test("C28 even fabricated externally authenticated flag cannot flip financial GO",()=>{
 const p=[period({sourceOriginAuthenticated:true,brokerSigned:true})];
 const r=P.assess({sourcePanel:{...base(),
  sourceOriginAuthenticated:true},periods:p,prespecified:prereg(p)});
 A.equal(r.brokerSourceAuthenticatedExternally,false);
 A.equal(r.sixVariantsOutperformedCashAndOriginalCertified,false);
 A.equal(r.alphaFamilywiseAdjustedCertified,false);
});
test("C28 portfolio exposures crossing policy arms without being flat are unattributable",()=>{
 rejects(p=>{p[0].flatAtEnd=false;},
  "CROSS_ARM_CARRY_EXPOSURE_NOT_ATTRIBUTABLE");
});
test("C28 old or mismatched frozen assignment receipt fails source chronology",()=>{
 const p=[period()];
 const pr=prereg(p);pr.assignments[0].arm="CASH";
 A.throws(()=>P.assess({sourcePanel:base(),periods:p,prespecified:pr}),
  /C28P_ASSIGNMENT_NOT_REGISTERED_EX_ANTE/);
});
test("C28 no zero-cost fake outperformance if original and cash blocks absent",()=>{
 const p=[period()];
 const r=P.assess({sourcePanel:base(),periods:p,prespecified:prereg(p)});
 A(r.completenessAndRealExecutionBlockers.includes(
  "NO_ORIGINAL_POLICY_EXECUTED_BASELINE"));
 A(r.completenessAndRealExecutionBlockers.includes(
  "NO_CASH_EXECUTED_CONTROL"));
 A.equal(r.FWN9FinancialGo,undefined);
 A.equal(r.N9S,"NO_GO");
});
