"use strict";
// Local source assembly/verification only. No network, broker, model fitting or order API.
const fs=require("node:fs"),path=require("node:path"),crypto=require("node:crypto");
const {digest}=require("../runtime30/ultimate_contracts.js");
const {parseStrictJSON}=require("./level4_readiness.cjs");
const SCHEMA="HARPOON_OBSERVATION_STREAM_MANIFEST_1",MAX_BYTES=128*1024*1024;
const need=(ok,code)=>{if(!ok)throw Error(code);};
const sha=bytes=>crypto.createHash("sha256").update(bytes).digest("hex");
function read(file){const size=fs.statSync(file).size;need(size<=32*1024*1024,"SNAPSHOT_SOURCE_SIZE_BOUND");const bytes=fs.readFileSync(file);return {body:parseStrictJSON(bytes.toString("utf8")),bytes:size,sha256:sha(bytes)};}
function descriptor(input){const {snapshot_id,...body}=input||{};need(body.schema==="HARPOON_OBSERVATION_SNAPSHOT_1"&&snapshot_id===digest(body)&&body.execution_allowed===false&&body.liveApproved===false,"SNAPSHOT_DESCRIPTOR_BINDING");need(Number.isSafeInteger(body.total_frames)&&body.total_frames>=0,"SNAPSHOT_COUNT");return {snapshot_id,body};}
function assemble(snapshot,pages,selection,baseDir){
  const pin=descriptor(snapshot);need(Array.isArray(pages)&&pages.length<=512,"SNAPSHOT_PAGE_COUNT_BOUND");
  need(selection&&typeof selection==="object"&&!Array.isArray(selection),"SNAPSHOT_SELECTION_REQUIRED");
  let offset=0,previous="GENESIS",lastAt=-1,totalBytes=0,staticHash=null;
  const epochs=[],references=[];
  for(const ref of pages){
    need(ref&&typeof ref.path==="string"&&typeof ref.sha256==="string","SNAPSHOT_PAGE_REFERENCE");
    const p=read(path.resolve(baseDir,ref.path)),b=p.body;totalBytes+=p.bytes;
    need(p.sha256===ref.sha256,"SNAPSHOT_PAGE_HASH");need(totalBytes<=MAX_BYTES,"SNAPSHOT_TOTAL_SOURCE_BYTES_BOUND");
    need(b.schema==="HARPOON_OBSERVATION_EXPORT_1"&&b.execution_allowed===false&&b.liveApproved===false&&
      b.snapshot_id===pin.snapshot_id&&digest(b.snapshot_descriptor)===pin.snapshot_id&&
      b.account_id===pin.body.account_id&&b.head===pin.body.head&&b.total_frames===pin.body.total_frames,
      "SNAPSHOT_PAGE_BINDING");
    need(b.offset===offset&&Array.isArray(b.frames)&&b.frames.length>0&&b.frames.length<=100&&
      b.next_offset===offset+b.frames.length&&Array.isArray(b.chain_records)&&b.chain_records.length===b.frames.length,
      "SNAPSHOT_PAGE_CONTINUITY");
    for(let i=0;i<b.frames.length;i++){
      const f=b.frames[i],{source_frame_sha256,...payload}=f,r=b.chain_records[i],{chain_hash,...record}=r;
      need(source_frame_sha256===sha(Buffer.from(JSON.stringify(payload)))&&r.frame_hash===source_frame_sha256,
        "SNAPSHOT_FRAME_HASH");
      need(r.sequence===offset+i+1&&r.previous===previous&&chain_hash===digest(record)&&r.at===f.runtime_input?.now&&
        Number.isSafeInteger(r.at)&&r.at>lastAt,"SNAPSHOT_CHAIN_CONTINUITY");
      need(f.account_id===pin.body.account_id&&f.runtime_input?.config?.expected_account_id===pin.body.account_id,
        "SNAPSHOT_FRAME_ACCOUNT");
      const config=f.runtime_input.config,{universe,...fixed}=config,cfgHash=digest(config),fixedHash=digest(fixed);
      need(Array.isArray(universe),"SNAPSHOT_UNIVERSE_REQUIRED");
      need(staticHash===null||staticHash===fixedHash,"SIGNAL_CONFIGURATION_CHANGED_SPLIT_DATASET");staticHash=fixedHash;
      for(const asset of universe)need(asset?.discovered_at===undefined||Number.isSafeInteger(asset.discovered_at)&&asset.discovered_at<=r.at,"UNIVERSE_NOT_KNOWN_AT_CAPTURE");
      const prior=epochs.at(-1);
      if(!prior||prior.configuration_hash!==cfgHash){need(epochs.length<512,"SNAPSHOT_CONFIGURATION_EPOCH_BOUND");epochs.push({first_sequence:r.sequence,last_sequence:r.sequence,configuration_hash:cfgHash});}
      else prior.last_sequence=r.sequence;
      previous=chain_hash;lastAt=r.at;
    }
    references.push({path:ref.path,sha256:ref.sha256,offset,next_offset:b.next_offset});offset=b.next_offset;
  }
  need(offset===pin.body.total_frames&&previous===pin.body.head,"SNAPSHOT_INCOMPLETE_PREFIX");
  return {schema:SCHEMA,snapshot,pages:references,selection,selection_hash:digest(selection),
    configuration_epochs:epochs,strategy_configuration_hash:staticHash,total_source_bytes:totalBytes,
    total_frames:offset,source_scope:"COMPLETE_PINNED_PREFIX_FROM_GENESIS",universe_policy:"OBSERVED_AT_CAPTURE_ONLY",
    limits:{page_count:512,page_bytes:32*1024*1024,total_source_bytes:MAX_BYTES},
    execution_allowed:false,liveApproved:false,financial_acceptance_allowed:false,
    limitations:["LOCAL_INTEGRITY_IS_NOT_PROVIDER_AUTHENTICITY","CAPTURED_QUOTES_DO_NOT_ESTABLISH_EXECUTABLE_DEPTH",
      "NO_TRAINING_OR_FUNDED_PATHS","MANIFEST_SELECTION_BINDING_IS_NOT_MARKET_TIME_PREREGISTRATION",
      "RUNTIME_STORAGE_512_MIB_AND_REAL_RETENTION_REMAIN_SEPARATE_LIMITS"]};
}
function verifyManifest(input,baseDir){need(input?.schema===SCHEMA,"SNAPSHOT_MANIFEST_SCHEMA");const rebuilt=assemble(input.snapshot,input.pages,input.selection,baseDir);need(digest(rebuilt)===digest(input),"SNAPSHOT_MANIFEST_RECONSTRUCTION");return {verified:true,total_frames:rebuilt.total_frames,total_source_bytes:rebuilt.total_source_bytes,snapshot_id:rebuilt.snapshot.snapshot_id,configuration_epochs:rebuilt.configuration_epochs,execution_allowed:false,financial_acceptance_allowed:false};}
function main(argv){
  const get=k=>{const i=argv.indexOf(k);return i<0?null:argv[i+1];};
  if(get("--verify")){const file=path.resolve(get("--verify"));console.log(JSON.stringify(verifyManifest(read(file).body,path.dirname(file))));return;}
  const input=get("--input"),output=get("--output");need(input&&output,"USAGE_INPUT_REQUEST_OUTPUT_MANIFEST_OR_VERIFY_MANIFEST");
  const file=path.resolve(input),spec=read(file).body;
  const manifest=assemble(spec.snapshot,spec.pages,spec.selection,path.dirname(file));
  const target=path.resolve(output);need(path.dirname(target)===path.dirname(file),"MANIFEST_AND_REQUEST_MUST_SHARE_REFERENCE_BASE");
  fs.writeFileSync(target,JSON.stringify(manifest,null,2)+"\n");console.log(JSON.stringify({output:target,total_frames:manifest.total_frames,execution_allowed:false}));
}
module.exports={assemble,verifyManifest,SCHEMA};
if(require.main===module){try{main(process.argv.slice(2));}catch(e){console.error(e.message);process.exitCode=1;}}
