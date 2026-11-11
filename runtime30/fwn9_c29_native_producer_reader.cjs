"use strict";
/** C29 actual native QuantObservationJournal READ adapter.
 * Only uses native exportFrames()/view(); never calls observe(), capture(),
 * plugins.evaluate(), coordinator.entries(), workers, broker or orders.
 * Original runtime/quant_bridge.cjs captures "observation-only" rotating
 * symbols, not the six executable C22 registered strategies. Therefore
 * this reader CANNOT independently satisfy C28 six-arm prefilter coverage.
 */
const crypto=require("node:crypto");
const A=require("node:assert/strict");
const C27=require("./fwn9_c27_prebar_state.cjs");
function need(ok,c){A.ok(ok,"C29O_"+c);}
function digest(s){return crypto.createHash("sha256").update(s).digest("hex");}
function inspect(source){
 need(source&&source.schema==="HARPOON_OBSERVATION_EXPORT_1"&&
  source.liveApproved===false&&source.execution_allowed===false&&
  Number.isSafeInteger(source.total_frames)&&source.total_frames>=0&&
  source.offset===0&&source.next_offset===source.total_frames&&
  source.complete_export===true&&
  Array.isArray(source.frames)&&source.frames.length===source.total_frames,
  "NATIVE_COMPLETE_IMMUTABLE_EXPORT_REQUIRED");
 let previous=-1,accepted=0,rejected=0,missed=0;
 const files=[];
 for(const f of source.frames){
  need(f.schema==="HARPOON_PROSPECTIVE_FRAME_1"&&
   f.account_id===source.account_id&&
   f.data_origin==="RUNTIME_OBSERVATION_UNVERIFIED"&&
   f.external_authenticity_verified===false&&
   f.financial_acceptance_allowed===false&&
   f.sampled_execution_depth===null&&
   f.policy_parity_verified===false,
   "NATIVE_OBSERVATION_NOT_MARKET_EXECUTION");
  const raw={...f},claimed=raw.source_frame_sha256;
  delete raw.source_frame_sha256;
  if(claimed!==undefined)
   need(/^[a-f0-9]{64}$/.test(claimed)&&
    digest(JSON.stringify(raw))===claimed,"NATIVE_FRAME_BYTE_SHA_MISMATCH");
  const runtime=f.runtime_input,obs=f.observation;
  need(runtime&&obs&&Number.isSafeInteger(runtime.now)&&runtime.now>previous&&
   Array.isArray(runtime.signals)&&
   obs.schema==="HARPOON_RUNTIME_OBSERVATION_1"&&
   Date.parse(obs.asof)===runtime.now&&
   obs.execution_allowed===false&&obs.liveApproved===false&&
   Array.isArray(obs.selected)&&obs.selected.length===0&&
   Array.isArray(obs.observations)&&
   obs.rejected&&typeof obs.rejected==="object"&&!Array.isArray(obs.rejected),
   "NATIVE_SOURCE_CLOCK_OR_SIGNAL_CONTRACT");
  const requested=new Set();
  for(const s of runtime.signals){
   need(s.plugin==="observation-only"&&
    typeof s.symbol==="string"&&s.symbol.length>0,
    "NATIVE_IS_ROTATING_OBSERVATION_ONLY");
   const id=s.plugin+"|"+s.symbol;
   need(!requested.has(id),"NATIVE_SOURCE_DUPLICATE_REQUEST");
   requested.add(id);
  }
  const seen=new Set();
  for(const q of obs.observations){
   need(requested.has(q.id)&&!seen.has(q.id)&&
    Array.isArray(q.features)&&q.features.length===8&&
    q.features.every(v=>typeof v==="number"&&Number.isFinite(v))&&
    Date.parse(q.asof)===runtime.now&&
    Date.parse(q.known_at)<=runtime.now,
    "NATIVE_FEATURE_OUTPUT_OR_FUTURE");
   seen.add(q.id);accepted++;
  }
  for(const [id,reason] of Object.entries(obs.rejected)){
   need(requested.has(id)&&!seen.has(id)&&
    typeof reason==="string"&&reason.trim().length>0,
    "NATIVE_REJECTED_ID_OR_REASON");
   seen.add(id);rejected++;
  }
  need(seen.size===requested.size,"NATIVE_CANDIDATE_OMISSION");
  const rotation=runtime.observation_coverage;
  if(rotation?.complete_registered_universe!==true)missed++;
  files.push({at:runtime.now,featureCount:obs.observations.length,
   rejectionCount:Object.keys(obs.rejected).length,
   requested:requested.size,
   sourceFrameHash:claimed??null,
   fullRegisteredUniverseAtThisCapture:rotation?.complete_registered_universe===true});
  previous=runtime.now;
 }
 return {schema:"HARPOON_FWN9_C29_NATIVE_PRODUCER_EXPORT_AUDIT_1",
  nativeObservationFramesVerified:files.length,
  originalNativeQuantObservationReadOnlyContract:true,
  sourceType:"OBSERVATION_ONLY_ROTATING_SYMBOLS",
  requestedSourceRows:accepted+rejected,acceptedFeatures:accepted,
  sourceRejectedRows:rejected,framesWithPartialUniverseRotation:missed,
  allRequestedNativeRowsCovered:true,
  c22SixOriginalVariantPrefilterEvaluationsProved:false,
  c27PrebarPositionsReservationsCapturedByThisExport:false,
  cashAndBrokerFillsVerified:false,
  externalProviderOriginAuthenticated:false,
  originalNativeExecutorsInvoked:false,
  marketSignalCandidatesGenerated:0,
  sourceCompletenessScope:"ONLY_ORIGINAL_JOURNAL_REQUESTED_OBSERVATION_ONLY_ROWS",
  frames:files,N9S:"NO_GO",M10FinalSealed:3200};
}
async function readNative(journal,{maxFrames=10000}={}){
 need(journal&&typeof journal.exportFrames==="function"&&
  typeof journal.view==="function"&&
  Number.isSafeInteger(maxFrames)&&maxFrames>=1&&maxFrames<=10000,
  "REAL_NATIVE_JOURNAL_REQUIRED");
 const before=journal.view();
 need(before.schema==="HARPOON_OBSERVATION_STATUS_1"&&
  Number.isSafeInteger(before.frames)&&before.frames<=maxFrames,
  "SOURCE_FRAME_CAP");
 const total=before.frames,frames=[];
 let offset=0,account=null,head=null;
 while(offset<total){
  const page=await journal.exportFrames(offset,Math.min(100,total-offset));
  need(page.schema==="HARPOON_OBSERVATION_EXPORT_1"&&
   page.offset===offset&&page.next_offset>offset&&
   page.total_frames===total&&Array.isArray(page.frames)&&
   page.frames.length===page.next_offset-offset&&
   (head===null||page.head===head)&&
   (account===null||page.account_id===account),
   "NATIVE_PAGINATION_OR_MIXED_SOURCE");
  head=page.head;account=page.account_id;
  frames.push(...page.frames);offset=page.next_offset;
 }
 const after=journal.view();
 need(after.head===before.head&&after.frames===before.frames,
  "NATIVE_JOURNAL_CHANGED_DURING_EXPORT");
 if(total===0)return {schema:"HARPOON_FWN9_C29_NATIVE_PRODUCER_EXPORT_AUDIT_1",
  nativeObservationFramesVerified:0,
  sourceType:"OBSERVATION_ONLY_ROTATING_SYMBOLS",
  c22SixOriginalVariantPrefilterEvaluationsProved:false,
  economicObservationSampleReady:false,
  N9S:"NO_GO",M10FinalSealed:3200};
 const r=inspect({schema:"HARPOON_OBSERVATION_EXPORT_1",
  liveApproved:false,execution_allowed:false,
  account_id:account,total_frames:total,offset:0,next_offset:total,
  complete_export:true,frames});
 return {...r,readFromOriginalQuantObservationJournalInterface:true,
  noSourceJournalWritesDuringRead:true};
}
module.exports={inspect,readNative};
