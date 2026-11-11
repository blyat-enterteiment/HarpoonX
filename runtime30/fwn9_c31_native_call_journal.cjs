"use strict";
/**
 * C31 durable local append-only chain for native POSTFILTER source observations.
 * Does not claim prefilter completeness, broker authenticity or trusted time.
 * A separately controlled external notarization is still required.
 */
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const C27=require("./fwn9_c27_prebar_state.cjs");
const W=require("./fwn9_c31_native_postfilter_witness.cjs");
const MANIFEST="HARPOON_FWN9_C31_NATIVE_WITNESS_MANIFEST_1";
const ENTRY="HARPOON_FWN9_C31_CHAIN_ENTRY_1";
const LIMIT=1048576;
function need(v,k){assert.ok(v,"C31J_"+k);}
function sha(row){return C27.digest(row);}
function privateDir(dir){
 const st=fs.lstatSync(dir);
 need(st.isDirectory()&&!st.isSymbolicLink()&&
  (st.mode&0o077)===0,"PRIVATE_DIRECTORY_0700");
}
function safeFile(p){
 const st=fs.lstatSync(p);
 need(st.isFile()&&!st.isSymbolicLink()&&
  (st.mode&0o777)===0o600&&st.size>0&&st.size<LIMIT,
  "PRIVATE_FILE_0600");
}
function store(p,obj){
 const bytes=Buffer.from(JSON.stringify(obj)+"\n");
 need(bytes.length<LIMIT,"RECORD_LIMIT");
 const fd=fs.openSync(p,"wx",0o600);
 try{fs.writeSync(fd,bytes);fs.fsyncSync(fd);}
 finally{fs.closeSync(fd);}
 const d=fs.openSync(path.dirname(p),"r");
 try{fs.fsyncSync(d);}finally{fs.closeSync(d);}
}
function filename(n,hash){return String(n).padStart(8,"0")+"-"+hash+".json";}
function create(dir,{runId,sourceFileSha256}={}){
 need(typeof dir==="string"&&dir.length>0&&!fs.existsSync(dir),"NEW_DIR_ONLY");
 need(typeof runId==="string"&&/^[A-Za-z0-9._-]{1,128}$/.test(runId),
  "RUN_ID");
 need(typeof sourceFileSha256==="string"&&/^[a-f0-9]{64}$/.test(sourceFileSha256),
  "SOURCE_HASH");
 const m={schema:MANIFEST,runId,sourceFileSha256,
  sourcePhase:"NATIVE_POSTFILTER_ONLY",
  originalC22PrefilterCoverageProven:false,
  brokerOriginIndependentlyAuthenticated:false,
  trustedTimestampExternallyVerified:false,
  permissionToTrade:false,N9S:"NO_GO"};
 fs.mkdirSync(dir,{mode:0o700});privateDir(dir);
 store(path.join(dir,"manifest.json"),{...m,manifestDigest:sha(m)});
 return verify(dir);
}
function verify(dir){
 privateDir(dir);
 const p=path.join(dir,"manifest.json");safeFile(p);
 const m=JSON.parse(fs.readFileSync(p,"utf8"));
 const body={...m};delete body.manifestDigest;
 need(m.schema===MANIFEST&&
  m.manifestDigest===sha(body)&&
  m.sourcePhase==="NATIVE_POSTFILTER_ONLY"&&
  m.originalC22PrefilterCoverageProven===false&&
  m.brokerOriginIndependentlyAuthenticated===false&&
  m.trustedTimestampExternallyVerified===false&&
  m.permissionToTrade===false&&m.N9S==="NO_GO",
  "MANIFEST_INTEGRITY");
 const names=fs.readdirSync(dir).filter(x=>x!=="manifest.json").sort();
 let head="GENESIS",count=0,lastTime=0;
 for(const name of names){
  const match=/^([0-9]{8})-([a-f0-9]{64})\.json$/.exec(name);
  need(match&&Number(match[1])===count+1,"CHAIN_GAP_OR_FOREIGN_FILE");
  const file=path.join(dir,name);safeFile(file);
  const item=JSON.parse(fs.readFileSync(file,"utf8"));
  const clean={...item};delete clean.hash;
  need(item.schema===ENTRY&&item.sequence===count+1&&
   item.previous===head&&item.manifestDigest===m.manifestDigest&&
   item.record?.schema===W.SCHEMA&&
   item.record.pluginSourceFileSha256===m.sourceFileSha256&&
   item.record.sourcePhase==="NATIVE_POSTFILTER_METHOD_RETURN"&&
   item.record.c22SixFrozenPrefilterEvaluationsProved===false&&
   item.record.sourceProviderAuthenticityIndependentlyVerified===false&&
   item.record.financialOrdersAuthorized===false&&
   item.record.N9S==="NO_GO"&&
   Number.isSafeInteger(item.record.startedAt)&&
   Number.isSafeInteger(item.record.finishedAt)&&
   item.record.startedAt>=lastTime&&
   item.record.finishedAt>=item.record.startedAt&&
   item.hash===match[2]&&item.hash===sha(clean),
   "CHAIN_SOURCE_OR_HASH");
  head=item.hash;lastTime=item.record.finishedAt;count++;
 }
 return {schema:"HARPOON_FWN9_C31_NATIVE_POSTFILTER_JOURNAL_AUDIT_1",
  runId:m.runId,entries:count,head,manifestDigest:m.manifestDigest,
  sourceFileSha256:m.sourceFileSha256,
  localFileIntegrityVerified:true,
  sixC22NativePrefilterCallsProven:false,
  independentlyTimeAndBrokerAuthenticated:false,
  financialGO:false,N9S:"NO_GO"};
}
function append(dir,record){
 const before=verify(dir);
 need(record?.schema===W.SCHEMA&&
  record.pluginSourceFileSha256===before.sourceFileSha256&&
  record.c22SixFrozenPrefilterEvaluationsProved===false&&
  record.sourceProviderAuthenticityIndependentlyVerified===false&&
  record.financialOrdersAuthorized===false&&record.N9S==="NO_GO",
  "APPEND_SOURCE_CONTRACT");
 const item={schema:ENTRY,sequence:before.entries+1,
  previous:before.head,manifestDigest:before.manifestDigest,record};
 const hash=sha(item);
 store(path.join(dir,filename(item.sequence,hash)),{...item,hash});
 return verify(dir);
}
module.exports={create,verify,append};
