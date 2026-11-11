"use strict";
/**
 * C32 event-level append-only local research journal. Each source-site hook
 * fsyncs BEFORE the original evaluator proceeds to its filters.
 * Restart scans the entire sequence; a stale writer lock is never auto-cleared.
 * No signature, external timestamp, broker origin, or financial GO is claimed.
 */
const fs=require("node:fs");
const path=require("node:path");
const assert=require("node:assert/strict");
const C27=require("./fwn9_c27_prebar_state.cjs");
const W=require("./fwn9_c32_native_prefilter_gate.cjs");
const MANIFEST="HARPOON_FWN9_C32_NATIVE_PREFILTER_MANIFEST_1";
const RECORD="HARPOON_FWN9_C32_NATIVE_PREFILTER_CHAIN_RECORD_1";
const LIMIT=128*1024*1024,MAX_LINE=8192;
function need(x,k){assert.ok(x,"C32J_"+k);}
function hash(x){return C27.digest(x);}
function guarded(dir){
 const d=fs.lstatSync(dir);
 need(d.isDirectory()&&!d.isSymbolicLink()&&
  (d.mode&0o077)===0,"PRIVATE_DIR_0700");
 for(const file of ["manifest.json","events.ndjson"]){
  const st=fs.lstatSync(path.join(dir,file));
  need(st.isFile()&&!st.isSymbolicLink()&&
   (st.mode&0o777)===0o600&&st.size<=LIMIT,
   "PRIVATE_FILE_0600_AND_LIMIT");
 }
 const names=fs.readdirSync(dir);
 need(names.every(n=>["manifest.json","events.ndjson",".writer.lock"].includes(n)),
  "NO_FOREIGN_FILES");
}
function materialize(p,content){
 const f=fs.openSync(p,"wx",0o600);
 try{fs.writeSync(f,content);fs.fsyncSync(f);}finally{fs.closeSync(f);}
 const d=fs.openSync(path.dirname(p),"r");
 try{fs.fsyncSync(d);}finally{fs.closeSync(d);}
}
function create(dir,{runId,sourceFileSha256,policyRegistryHash}={}){
 need(typeof dir==="string"&&dir.length>0&&!fs.existsSync(dir),"CREATE_ONCE");
 need(typeof runId==="string"&&/^[a-zA-Z0-9_-]{1,128}$/.test(runId),
  "RUN_ID");
 need(typeof sourceFileSha256==="string"&&/^[a-f0-9]{64}$/.test(sourceFileSha256)&&
  typeof policyRegistryHash==="string"&&/^[a-f0-9]{64}$/.test(policyRegistryHash),
  "PINNED_SOURCE_AND_REGISTRY");
 const body={schema:MANIFEST,runId,sourceFileSha256,policyRegistryHash,
  sourceScope:"ORIGINAL_NATIVE_SOURCE_SITES_BEFORE_FILTERS",
  externalClockAndBrokerAttestation:false,
  originalSixC22StrategySemanticIdentityProven:false,
  financialOrdersAuthorized:false,N9S:"NO_GO"};
 fs.mkdirSync(dir,{mode:0o700});
 guardedCreate(dir);
 materialize(path.join(dir,"manifest.json"),
  JSON.stringify({...body,manifestHash:hash(body)})+"\n");
 materialize(path.join(dir,"events.ndjson"),"");
 return verify(dir);
}
function guardedCreate(dir){
 const st=fs.lstatSync(dir);
 need(st.isDirectory()&&!st.isSymbolicLink()&&
  (st.mode&0o077)===0,"PRIVATE_DIR_0700");
}
function verify(dir){
 guarded(dir);
 const m=JSON.parse(fs.readFileSync(path.join(dir,"manifest.json"),"utf8"));
 const body={...m};delete body.manifestHash;
 need(m.schema===MANIFEST&&m.manifestHash===hash(body)&&
  m.sourceScope==="ORIGINAL_NATIVE_SOURCE_SITES_BEFORE_FILTERS"&&
  m.externalClockAndBrokerAttestation===false&&
  m.originalSixC22StrategySemanticIdentityProven===false&&
  m.financialOrdersAuthorized===false&&m.N9S==="NO_GO",
  "MANIFEST_NOT_AUTHENTIC");
 const s=fs.readFileSync(path.join(dir,"events.ndjson"),"utf8");
 need(s.length===0||s.endsWith("\n"),"TRUNCATED_EVENT");
 const lines=s.length?s.trimEnd().split("\n"):[];
 let head="GENESIS",last=0;
 for(let i=0;i<lines.length;i++){
  need(Buffer.byteLength(lines[i])<=MAX_LINE,"OVERSIZE_EVENT");
  const row=JSON.parse(lines[i]);const clean={...row};delete clean.hash;
  need(row.schema===RECORD&&row.sequence===i+1&&
   row.previous===head&&row.manifestHash===m.manifestHash&&
   row.source?.schema===W.SCHEMA&&
   row.source.sourceFileSha256===m.sourceFileSha256&&
   row.source.sourceInvocationObserved===true&&
   row.source.sourceProviderExternallyAuthenticated===false&&
   row.source.c22FrozenStrategyIdentityProved===false&&
   row.source.paperOrLiveOrderAuthorized===false&&row.source.N9S==="NO_GO"&&
   row.source.localRecordedAt>=last&&
   row.hash===hash(clean),"CHAIN_HASH_OR_SOURCE");
  last=row.source.localRecordedAt;head=row.hash;
 }
 return {schema:"HARPOON_FWN9_C32_NATIVE_PREFILTER_JOURNAL_VERIFIED_1",
  count:lines.length,head,manifestHash:m.manifestHash,
  sourceFileSha256:m.sourceFileSha256,
  localIntegrityVerified:true,preFilterSourceSitesRecorded:lines.length,
  externallyTimestamped:false,sixFrozenStrategyIdentitiesProven:false,
  financialGO:false,N9S:"NO_GO"};
}
function openWriter(dir){
 const state=verify(dir);
 need(!fs.existsSync(path.join(dir,".writer.lock")),"STALE_LOCK_REQUIRES_REVIEW");
 const lock=path.join(dir,".writer.lock");
 const ld=fs.openSync(lock,"wx",0o600);fs.closeSync(ld);
 let fd,closed=false,count=state.count,head=state.head,last=0;
 try{
  const lines=fs.readFileSync(path.join(dir,"events.ndjson"),"utf8").trim();
  if(lines)last=JSON.parse(lines.split("\n").at(-1)).source.localRecordedAt;
  fd=fs.openSync(path.join(dir,"events.ndjson"),"a");
 }catch(err){ // lock deliberately retained on failed open for investigation
  throw err;
 }
 return {
  append(source){
   need(!closed&&source?.schema===W.SCHEMA&&
    source.sourceFileSha256===state.sourceFileSha256&&
    source.sourceInvocationObserved===true&&
    source.sourceProviderExternallyAuthenticated===false&&
    source.c22FrozenStrategyIdentityProved===false&&
    source.paperOrLiveOrderAuthorized===false&&source.N9S==="NO_GO"&&
    source.localRecordedAt>=last,"APPEND_SOURCE_AND_CLOCK");
   const row={schema:RECORD,sequence:count+1,previous:head,
    manifestHash:state.manifestHash,source};
   const digest=hash(row),encoded=JSON.stringify({...row,hash:digest})+"\n";
   need(Buffer.byteLength(encoded)<=MAX_LINE,"APPEND_LINE_BOUND");
   const n=fs.writeSync(fd,encoded);
   need(n===Buffer.byteLength(encoded),"PARTIAL_WRITE");
   fs.fsyncSync(fd);
   head=digest;count++;last=source.localRecordedAt;
   return {count,head};
  },
  close(){
   need(!closed,"CLOSE_ONCE");
   fs.fsyncSync(fd);fs.closeSync(fd);closed=true;
   fs.unlinkSync(lock);
   return verify(dir);
  }
 };
}
module.exports={create,verify,openWriter};
