"use strict";
/**
 * C35 private append-only event journal for Alpaca PAPER trade_updates.
 * No API credentials or raw websocket frames. Contains private order IDs:
 * never commit, upload or print raw journal files.
 */
const fs=require("node:fs"),path=require("node:path");
const A=require("node:assert/strict");
const C27=require("./fwn9_c27_prebar_state.cjs");
const W=require("./fwn9_c35_paper_trade_updates.cjs");
const MANIFEST="HARPOON_FWN9_C35_PAPER_STREAM_MANIFEST_1";
const ROW="HARPOON_FWN9_C35_PAPER_STREAM_JOURNAL_ROW_1";
function need(x,k){A.ok(x,"C35J_"+k);}
function hash(x){return C27.digest(x);}
function privateDir(d){
 const st=fs.lstatSync(d);
 need(st.isDirectory()&&!st.isSymbolicLink()&&(st.mode&0o077)===0,
  "PRIVATE_DIR_0700");
}
function privateFile(p){
 const st=fs.lstatSync(p);
 need(st.isFile()&&!st.isSymbolicLink()&&
  (st.mode&0o777)===0o600&&st.size<=64*1024*1024,
  "PRIVATE_FILE_0600");
}
function exclusive(p,content){
 const fd=fs.openSync(p,"wx",0o600);
 try{fs.writeSync(fd,content);fs.fsyncSync(fd);}
 finally{fs.closeSync(fd);}
}
function create(dir,{captureId}={}){
 need(typeof dir==="string"&&dir.length>0&&!fs.existsSync(dir)&&
  typeof captureId==="string"&&/^[a-zA-Z0-9_-]{8,100}$/.test(captureId)&&
  !/(?:^|\/)(?:holdout|M10[_-]?final)(?:\/|$)/i.test(path.resolve(dir)),
  "NEW_PRIVATE_NONFINAL_DIRECTORY");
 fs.mkdirSync(dir,{mode:0o700});privateDir(dir);
 const body={schema:MANIFEST,captureId,origin:"wss://paper-api.alpaca.markets/stream",
  stream:"trade_updates",source:"PASSIVE_LOCAL_RECEIPT_JOURNAL",
  claimOfFullNetworkContinuity:false,
  upstreamBrokerSignatureVerified:false,
  orderAuthority:false,N9S:"NO_GO"};
 exclusive(path.join(dir,"manifest.json"),
  JSON.stringify({...body,manifestHash:hash(body)})+"\n");
 exclusive(path.join(dir,"events.ndjson"),"");
 const d=fs.openSync(dir,"r");
 try{fs.fsyncSync(d);}finally{fs.closeSync(d);}
 return verify(dir);
}
function verify(dir){
 privateDir(dir);
 const names=fs.readdirSync(dir);
 need(names.every(n=>["manifest.json","events.ndjson",".writer.lock"].includes(n)),
  "FOREIGN_FILES");
 const mfile=path.join(dir,"manifest.json"),file=path.join(dir,"events.ndjson");
 privateFile(mfile);privateFile(file);
 const m=JSON.parse(fs.readFileSync(mfile,"utf8"));
 const body={...m};delete body.manifestHash;
 need(m.schema===MANIFEST&&m.manifestHash===hash(body)&&
  m.stream==="trade_updates"&&m.origin==="wss://paper-api.alpaca.markets/stream"&&
  m.claimOfFullNetworkContinuity===false&&
  m.upstreamBrokerSignatureVerified===false&&m.orderAuthority===false&&
  m.N9S==="NO_GO","MANIFEST_NOT_AUTHENTICATED");
 const raw=fs.readFileSync(file,"utf8");
 need(raw.length===0||raw.endsWith("\n"),"TRUNCATED_STREAM_RECORD");
 const lines=raw.length?raw.trimEnd().split("\n"):[];
 let count=0,head="GENESIS",last=0,auth=0,listen=0,events=0,closed=0;
 const executions=new Set();
 for(const line of lines){
  need(Buffer.byteLength(line)<32*1024,"ROW_TOO_LONG");
  const r=JSON.parse(line),clean={...r};delete clean.chainHash;
  need(r.schema===ROW&&r.index===count+1&&
   r.previous===head&&r.manifestHash===m.manifestHash&&
   r.chainHash===hash(clean)&&
   Number.isSafeInteger(r.localAt)&&r.localAt>=last,
   "SEQUENCE_HASH_OR_CLOCK");
  if(r.kind==="AUTHORIZED"){
   need(auth===0&&listen===0&&events===0&&closed===0&&r.data===null,
    "AUTH_SEQUENCE");auth++;
  }else if(r.kind==="LISTENING"){
   need(auth===1&&listen===0&&events===0&&closed===0&&r.data===null,
    "LISTEN_SEQUENCE");listen++;
  }else if(r.kind==="EVENT"){
   need(auth===1&&listen===1&&closed===0&&
    r.data?.schema===W.SCHEMA&&
    r.data.receivedAtMs===r.localAt&&
    r.data.tradingAuthority===false&&r.data.N9S==="NO_GO",
    "EVENT_WHILE_UNAUTHORIZED");
   if(r.data.executionId){
    need(!executions.has(r.data.executionId),"DUPLICATE_EXECUTION");
    executions.add(r.data.executionId);
   }
   events++;
  }else if(r.kind==="CLOSED"){
   need(auth===1&&listen===1&&closed===0&&r.data===null,
    "CLOSE_SEQUENCE");closed++;
  }else need(false,"UNKNOWN_JOURNAL_KIND");
  last=r.localAt;head=r.chainHash;count++;
 }
 return {schema:"HARPOON_FWN9_C35_PRIVATE_STREAM_JOURNAL_AUDIT_1",
  captureId:m.captureId,manifestHash:m.manifestHash,count,head,
  authRecorded:auth===1,subscriptionRecorded:listen===1,
  eventsRecorded:events,closedLocally:closed===1,
  sourceOriginIndependentlyAuthenticated:false,
  reconnectionGapsProvenAbsent:false,
  sourceNetworkStreamReproducibleAfterDisconnect:false,
  ordersCreated:0,financialGO:false,N9S:"NO_GO"};
}
function openWriter(dir){
 const current=verify(dir);
 need(current.count===0,"NEW_CAPTURE_WRITER_ONLY");
 const lock=path.join(dir,".writer.lock");
 need(!fs.existsSync(lock),"STALE_LOCK_REQUIRES_REVIEW");
 fs.closeSync(fs.openSync(lock,"wx",0o600));
 const fd=fs.openSync(path.join(dir,"events.ndjson"),"a");
 let index=0,head="GENESIS",last=0,phase="START",closed=false;
 const write=(kind,localAt,data=null)=>{
  need(!closed&&Number.isSafeInteger(localAt)&&localAt>=last,
   "WRITER_CLOCK");
  if(kind==="AUTHORIZED")need(phase==="START"&&data===null,"WRITER_AUTH");
  else if(kind==="LISTENING")need(phase==="AUTHORIZED"&&data===null,
   "WRITER_LISTEN");
  else if(kind==="EVENT")need(phase==="LISTENING"&&
   data?.schema===W.SCHEMA&&data.receivedAtMs===localAt&&
   data.tradingAuthority===false,"WRITER_EVENT");
  else if(kind==="CLOSED")need(phase==="LISTENING"&&data===null,
   "WRITER_CLOSE");
  else need(false,"WRITER_KIND");
  const body={schema:ROW,index:index+1,previous:head,
   manifestHash:current.manifestHash,localAt,kind,data};
  const bytes=Buffer.from(JSON.stringify({...body,chainHash:hash(body)})+"\n");
  need(bytes.length<32*1024,"WRITER_ROW_LIMIT");
  need(fs.writeSync(fd,bytes)===bytes.length,"WRITER_SHORT_WRITE");
  fs.fsyncSync(fd);index++;head=hash(body);last=localAt;
  if(kind==="AUTHORIZED")phase="AUTHORIZED";
  if(kind==="LISTENING")phase="LISTENING";
  if(kind==="CLOSED")phase="CLOSED";
  return {index,head};
 };
 return {
  authorized:at=>write("AUTHORIZED",at),
  listening:at=>write("LISTENING",at),
  event:r=>write("EVENT",r.receivedAtMs,r),
  close:at=>{
   write("CLOSED",at);
   fs.fsyncSync(fd);fs.closeSync(fd);closed=true;
   fs.unlinkSync(lock);return verify(dir);
  }
 };
}
module.exports={create,verify,openWriter};
