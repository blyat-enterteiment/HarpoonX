"use strict";
/** C29 source-span proof: every scheduled five-minute slot throughout each
 * 72h active + 72h washout + 1h funding-check interval. Supports multiple
 * 60k-frame C27 journals; reads original journals and C28 sidecars only.
 * No generator, broker, strategy, market data or new account calls.
 */
const A=require("node:assert/strict");
const R=require("./fwn9_c29_frozen_assignments.cjs");
const J=require("./fwn9_c27_prebar_journal.cjs");
const T=require("./fwn9_c28_source_tap_archive.cjs");
const FIVE=300000;
function need(x,k){A.ok(x,"C29G_"+k);}
function auditGrids(plan,grids){
 R.validate(plan);
 need(Array.isArray(grids)&&grids.length>0&&grids.length<=32,
  "SEGMENT_COUNT");
 const first=plan.startAt,last=plan.blocks.at(-1).fundingReviewEndAt;
 need(first%FIVE===0&&last%FIVE===0&&last>first,
  "FIVE_MINUTE_ALIGNED_PREREGISTRATION");
 const count=(last-first)/FIVE;
 need(Number.isSafeInteger(count),"EXPECTED_M5_COUNT");
 let cursor=0;
 const metadata=[];
 for(let i=0;i<grids.length;i++){
  const g=grids[i];
  need(Array.isArray(g.expectedBars)&&g.expectedBars.length>0&&
   g.expectedBars.length<=60000&&g.completeC27===true&&
   g.completeC28===true,"SOURCE_C27_C28_BOTH_COMPLETE");
  for(const ts of g.expectedBars){
   need(ts===first+cursor*FIVE,"MISSING_OR_DUPLICATED_FIVE_MINUTE_BAR");
   cursor++;
  }
  metadata.push({segment:i,frames:g.expectedBars.length});
 }
 need(cursor===count,"UNOBSERVED_FINAL_SOURCE_BAR_RANGE");
 return {schema:"HARPOON_FWN9_C29_C27_C28_ALL_FIVE_MINUTES_VERIFIED_1",
  segmentCount:grids.length,
  expectedBars:count,sourceVerifiedBars:cursor,
  allUTCClockSlotsPrespecified:true,
  fullCalendarVerifiedAgainstPreregisteredUTCGrid:true,
  stocksAndOptionsSessionEligibleOnlyByC28Rules:true,
  globalUniverseDeclaredSourceNotIndependentlyAuthenticated:true,
  sourceFromRealProductionAuthenticated:false,
  noMarketOHLCUsedInProof:true,
  offlineEconomicGO:false,N9S:"NO_GO",segments:metadata};
}
function verifySegments(plan,dirs){
 R.validate(plan);
 need(Array.isArray(dirs)&&dirs.length>0&&dirs.length<=32,
  "JOURNAL_PATHS");
 const inputs=[];
 let priorC27=null,priorC28=null;
 for(const pair of dirs){
  need(pair&&typeof pair.c27Dir==="string"&&
   typeof pair.tapDir==="string","SOURCE_PATHS");
  const c=J.verifyJournal(pair.c27Dir),t=T.verify(pair.tapDir,pair.c27Dir);
  need(c.coverageComplete&&t.fullBarsAndSourceTapsComplete&&
   t.expectedFrames===c.expectedFrames,"INCOMPLETE_C27_C28_SEGMENT");
  if(priorC27!==null)
   need(c.manifest.expectedBars[0]>priorC27,
    "JOURNAL_SEQUENCES_OVERLAP");
  priorC27=c.manifest.expectedBars.at(-1);
  priorC28=t.verifiedTapChainHead;
  inputs.push({expectedBars:c.manifest.expectedBars,
   completeC27:c.coverageComplete,
   completeC28:t.fullBarsAndSourceTapsComplete});
 }
 const proof=auditGrids(plan,inputs);
 return {...proof,allC27ArchiveHeadsIndependentlySigned:false,
  allC28ArchiveHeadsIndependentlySigned:false,
  crossSegmentExternalCounterSignatureRequired:true,
  brokerOriginAttestationNotEquivalentToHashChain:true,
  lastLocalTapHead:priorC28,
  usableForRealNetGrowthCertification:false};
}
module.exports={auditGrids,verifySegments};
