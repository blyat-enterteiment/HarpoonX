"use strict";
/** C29 fixed engineering-only blocks. No market seed, order or economic trial. */
const test=require("node:test"),A=require("node:assert/strict");
const P=require("../runtime30/fwn9_c29_frozen_assignments.cjs");
const I=require("../runtime30/fwn9_c29_randomization_inference.cjs");
const native=require("../runtime30/fwn9_c29_native_producer_reader.cjs");
const {QuantObservationJournal}=require("../runtime30/quant_observations.js");
const SHA="a".repeat(64),REGISTERED=Date.parse("2026-11-10T00:00:00Z");
const START=REGISTERED+72*3600000;
const NONCE="C29_FIXED_ASSIGNMENTS_NO_MARKET_RNG_RESEARCH_ONLY_001";
const plan=(cycles=4)=>P.freeze({studyId:"PROSPECTIVE_RESEARCH_ONLY",
 registeredAt:REGISTERED,startAt:START,cycles,assignmentNonce:NONCE});
function outcomes(p,{advantage=true}={}){
 let wealth=20000;
 return p.blocks.map(b=>{
  const beginning=wealth;
  const rate=b.arm==="CASH"?0:b.arm==="ORIGINAL_BASELINE"?.001:
   b.arm===p.eightArms[0]?(advantage?.005:-.005):0;
  wealth=beginning*(1+rate);
  return {blockId:b.blockId,arm:b.arm,startAt:b.startAt,
   tradeEndAt:b.tradeEndAt,washoutEndAt:b.washoutEndAt,
   assignmentKnownAt:b.assignmentKnownAt,
   flatAtStart:true,flatAtTradeEnd:true,flatAtWashoutEnd:true,
   receiptKnownAt:b.washoutEndAt+1000,
   accountFingerprint:"C29_SINGLE_SYNTHETIC_ENGINEERING_BOOK",
   beginningEquityUsd:beginning,endingEquityUsd:wealth,
   grossEconomicPnlUsd:wealth-beginning,tradingFeesUsd:0,
   externalCostsUsd:0,externalFlowUsd:0,
   costCoverageComplete:true,ledgerReconciled:true,
   cashReferenceRate:0,cashRateKnownAt:b.startAt-1000,
   sourceFillActivityDigests:b.arm==="CASH"?[]:[SHA],
   brokerReceiptSourceIndependent:false,marketQuoteSourceIndependent:false};
 });
}
function reject(mutation,label){
 const p=plan(),rows=outcomes(p);
 mutation(p,rows);
 A.throws(()=>I.audit({plan:p,observedBlocks:rows}),
  new RegExp("(?:C29R_|C29I_)"+label));
}
test("C29 six variants original and cash exactly once per cycle",()=>{
 const p=plan();
 A.equal(P.validate(p).plannedBlocks,32);
 A.equal(p.eightArms.length,8);
 A.equal(p.initialCapitalUsd,20000);
 A.equal(p.familywiseAlpha,.025);
 for(let c=0;c<4;c++)
  A.deepEqual(new Set(p.blocks.slice(c*8,c*8+8).map(b=>b.arm)),
   new Set(p.eightArms));
});
test("C29 72h holding + 72h washout + one hour review, no broker permission",()=>{
 const b=plan().blocks;
 A.equal(b[0].tradeEndAt-b[0].startAt,72*3600000);
 A.equal(b[0].washoutEndAt-b[0].tradeEndAt,72*3600000);
 A.equal(b[1].startAt-b[0].washoutEndAt,3600000);
 A.equal(b[0].entryAuthorized,false);
});
test("C29 assignment must be preregistered at least 72 hours",()=>{
 A.throws(()=>P.freeze({studyId:"BAD",registeredAt:REGISTERED,
  startAt:REGISTERED+71000000,cycles:4,assignmentNonce:NONCE}),
  /C29R_PREREGISTER_AT_LEAST_72H_BEFORE_FIRST_BLOCK/);
});
test("C29 fewer than four cycles rejected; pilot cannot meet familywise threshold",()=>{
 A.throws(()=>plan(3),/C29R_FOUR_TO_128_CYCLES/);
 const p=plan(4),r=I.audit({plan:p,observedBlocks:outcomes(p)});
 A.equal(r.minimumAttainableExactPvsSingleControl,.0625);
 A.equal(r.canPotentiallyRejectFirstHypothesisAt025,false);
 A.equal(r.tests.every(z=>z.holmFWERAdjustedP>.025),true);
 A.equal(r.finalFinancialGO,false);
});
test("C29 a successful 8-cycle exact test does not certify actual profitability",()=>{
 const p=plan(8),r=I.audit({plan:p,observedBlocks:outcomes(p)});
 A.equal(r.canPotentiallyRejectFirstHypothesisAt025,true);
 const row=r.tests.find(z=>z.arm===p.eightArms[0]);
 A(row.holmFWERAdjustedP<=.025);
 A.equal(r.familywisePopulationAlphaCertified,false);
 A.equal(r.finalFinancialGO,false);
 A.equal(r.holdoutM10Sealed,3200);
});
test("C29 frozen assignment/content changes invalidate registered SHA",()=>{
 const p=plan();p.blocks[0].arm="RETRO_WINNER";
 A.throws(()=>P.validate(p),/C29R_PLAN_TAMPERED/);
 A.equal(plan().planDigest,plan().planDigest);
});
test("C29 no source blocks does not imply zero economic return",()=>{
 A.throws(()=>I.audit({plan:plan(),observedBlocks:[]}),
  /C29I_COMPLETE_INTENTION_TO_TREAT_BLOCKS/);
});
test("C29 single continuous book rejects second independent account",()=>{
 reject((p,r)=>{r[10].accountFingerprint="INDEPENDENT_20K";},
  "SINGLE_PHYSICAL_FUNDED_ACCOUNT");
});
test("C29 cannot select after outcome or carry open inventory between arms",()=>{
 reject((p,r)=>{r[0].assignmentKnownAt=r[0].startAt+1;},
  "BLOCK_OUTCOME_PREASSIGNED");
 reject((p,r)=>{r[0].flatAtTradeEnd=false;},
  "POSITIVE_NO_CARRYOVER_STATE");
});
test("C29 known-after-next-start receipts cannot backfinance next arm",()=>{
 reject((p,r)=>{r[0].receiptKnownAt=r[0].washoutEndAt+4000000;},
  "RECEIPT_FINANCING_GAP");
});
test("C29 forged profits, costs and deposits rejected on single book",()=>{
 reject((p,r)=>{r[0].endingEquityUsd+=1;},
  "ECONOMIC_LEDGER_SELF_FINANCING");
 reject((p,r)=>{r[0].externalFlowUsd=10;},
  "ONE_BOOK_NET_COST_ACCOUNTING");
});
test("C29 absent trading FILL or CASH containing FILL cannot pass",()=>{
 reject((p,r)=>{r.find(x=>x.arm==="CASH").sourceFillActivityDigests=[SHA];},
  "NO_IMPUTED_STRATEGY_FILLS");
 reject((p,r)=>{r.find(x=>x.arm!=="CASH"&&x.grossEconomicPnlUsd!==0)
  .sourceFillActivityDigests=[];}, "NO_IMPUTED_STRATEGY_FILLS");
});
test("C29 cash source available only after block open violates filtration",()=>{
 reject((p,r)=>{r[0].cashRateKnownAt=r[0].startAt+1;},
  "PRIOR_CASH_RATE_REQUIRED");
});
test("C29 target return negative cannot be promoted as best venue",()=>{
 const p=plan(),r=I.audit({plan:p,observedBlocks:outcomes(p,{advantage:false})});
 const winner=r.tests.find(z=>z.arm===p.eightArms[0]);
 A(winner.meanDailyLogDifferenceCash<0);
 A.equal(winner.conditionalSharpNullRejectAt025,false);
});
test("C29 exact pairwise sign flip and six-family Holm values deterministic",()=>{
 A.equal(I.signFlipP([1,1,1,1],"K").p,.0625);
 A.equal(I.signFlipP([-1,-1,-1,-1],"K").p,1);
 A.deepEqual(I.holm([.001,.01,.02,.04,.05,.2]),
  [.006,.05,.08,.12,.12,.2]);
});
