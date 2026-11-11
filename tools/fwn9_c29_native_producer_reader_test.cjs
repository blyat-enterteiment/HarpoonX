"use strict";
/** Original source native observation-only test, NOT C22 execution signals. */
const test=require("node:test"),A=require("node:assert/strict");
const crypto=require("node:crypto");
const N=require("../runtime30/fwn9_c29_native_producer_reader.cjs");
const {QuantObservationJournal}=require("../runtime30/quant_observations.js");
const NOW=Date.parse("2026-11-10T20:00:00Z");
function fixture(){
 const account_id="C29_SYNTHETIC_OBSERVATION_ONLY";
 const runtime_input={now:NOW,signals:[{plugin:"observation-only",symbol:"SYNA"}],
  observation_coverage:{complete_registered_universe:false}};
 const observation={schema:"HARPOON_RUNTIME_OBSERVATION_1",
  asof:new Date(NOW).toISOString(),execution_allowed:false,liveApproved:false,
  selected:[],observations:[],rejected:{"observation-only|SYNA":"WAIT_FEATURE_DATA"}};
 const payload={schema:"HARPOON_PROSPECTIVE_FRAME_1",account_id,
  data_origin:"RUNTIME_OBSERVATION_UNVERIFIED",
  external_authenticity_verified:false,runtime_input,
  observation,session_context:{},sampled_execution_depth:null,
  policy_parity_verified:false,financial_acceptance_allowed:false};
 const source_frame_sha256=crypto.createHash("sha256")
  .update(JSON.stringify(payload)).digest("hex");
 return {schema:"HARPOON_OBSERVATION_EXPORT_1",
  liveApproved:false,execution_allowed:false,
  account_id,total_frames:1,offset:0,next_offset:1,
  complete_export:true,frames:[{...payload,source_frame_sha256}]};
}
test("C29 truly native QuantObservationJournal shape is only sampled observation-only",()=>{
 const r=N.inspect(fixture());
 A.equal(r.nativeObservationFramesVerified,1);
 A.equal(r.sourceType,"OBSERVATION_ONLY_ROTATING_SYMBOLS");
 A.equal(r.c22SixOriginalVariantPrefilterEvaluationsProved,false);
 A.equal(r.framesWithPartialUniverseRotation,1);
 A.equal(r.N9S,"NO_GO");
});
test("C29 original source SHA256 of frame mismatches if payload changed later",()=>{
 const f=fixture();f.frames[0].observation.rejected["observation-only|SYNA"]="NEW";
 A.throws(()=>N.inspect(f),/C29O_NATIVE_FRAME_BYTE_SHA_MISMATCH/);
});
test("C29 original native output cannot be relabeled as C22 strategy execution",()=>{
 const f=fixture();f.frames[0].runtime_input.signals[0].plugin="H22_OPENING_CONFIRMATION@RTH_OPEN_30";
 delete f.frames[0].source_frame_sha256;
 A.throws(()=>N.inspect(f),/C29O_NATIVE_IS_ROTATING_OBSERVATION_ONLY/);
});
test("C29 source journal refused plus feature union must exactly cover all requests",()=>{
 const f=fixture();f.frames[0].observation.rejected={};
 delete f.frames[0].source_frame_sha256;
 A.throws(()=>N.inspect(f),/C29O_NATIVE_CANDIDATE_OMISSION/);
});
test("C29 source export must be complete, not a sampled first page",()=>{
 const f=fixture();f.complete_export=false;
 A.throws(()=>N.inspect(f),/C29O_NATIVE_COMPLETE_IMMUTABLE_EXPORT_REQUIRED/);
});
test("C29 readNative consumes original QuantObservationJournal exportFrames/view only",async()=>{
 const mem=new Map(),store={
  async get(k){return mem.has(k)?structuredClone(mem.get(k)):null;},
  async put(k,v){mem.set(k,structuredClone(v));}
 };
 const id="C29_NATIVE_JOURNAL_SYNTHETIC_ONLY";
 const journal=new QuantObservationJournal(store,"C29_ORIGINAL",id,
  {maxFrames:10,maxArchives:0,maxStoredBytes:1024*1024});
 await journal.load();
 const now=Date.now()-10000,asof=new Date(now).toISOString();
 const runtime_input={now,config:{expected_account_id:id},
  market:{calendar:[]},
  signals:[{plugin:"observation-only",symbol:"SYNA"}],
  observation_coverage:{complete_registered_universe:true}};
 const observation={schema:"HARPOON_RUNTIME_OBSERVATION_1",
  asof,status:"WAIT_FEATURE_DATA",execution_allowed:false,
  liveApproved:false,selected:[],observations:[],
  rejected:{"observation-only|SYNA":"NO_FEATURE"}};
 await journal.capture(runtime_input,observation);
 const x=await N.readNative(journal);
 A.equal(x.nativeObservationFramesVerified,1);
 A.equal(x.readFromOriginalQuantObservationJournalInterface,true);
 A.equal(x.marketSignalCandidatesGenerated,0);
 A.equal(x.c22SixOriginalVariantPrefilterEvaluationsProved,false);
 A.equal(x.noSourceJournalWritesDuringRead,true);
});
test("C29 actual native source zero-frame export is economic evidence BLOCKED",async()=>{
 const journal={
  view(){return {schema:"HARPOON_OBSERVATION_STATUS_1",
   frames:0,head:"GENESIS"}},
  async exportFrames(){throw Error("READ_SHOULD_NOT_CALL_EXPORT");}
 };
 const r=await N.readNative(journal);
 A.equal(r.nativeObservationFramesVerified,0);
 A.equal(r.economicObservationSampleReady,false);
 A.equal(r.N9S,"NO_GO");
});
test("C29 native source change during page export must fail closed",async()=>{
 let version=0;
 const journal={
  view(){return {schema:"HARPOON_OBSERVATION_STATUS_1",
   frames:1,head:version++===0?"H1":"H2"}},
  async exportFrames(){return fixture();}
 };
 await A.rejects(()=>N.readNative(journal),
  /C29O_NATIVE_JOURNAL_CHANGED_DURING_EXPORT/);
});
