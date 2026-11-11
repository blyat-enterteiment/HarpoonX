"use strict";
/**
 * Private local append-only C33 HTTP GET receipt journal. No secrets,
 * account identifiers, response bodies, or order actions are stored.
 * A hash chain prevents accidental alteration but is NOT an external notary.
 */
const fs=require("node:fs"),path=require("node:path");
const assert=require("node:assert/strict");
const C27=require("./fwn9_c27_prebar_state.cjs");
const W=require("./fwn9_c33_broker_get_witness.cjs");
const SCHEMA="HARPOON_FWN9_C33_LOCAL_GET_JOURNAL_MANIFEST_1";
function need(x,k){assert.ok(x,"C33J_"+k);}
function hash(x){return C27.digest(x);}
function privateDir(dir){
 const s=fs.lstatSync(dir);
 need(s.isDirectory()&&!s.isSymbolicLink()&&
  (s.mode&0o077)===0,"PRIVATE_0700_DIRECTORY");
}
function privateFile(file){
 const s=fs.lstatSync(file);
 need(s.isFile()&&!s.isSymbolicLink()&&
  (s.mode&0o777)===0o600&&s.size<=2*1024*1024,
  "PRIVATE_0600_FILE");
}
function makeFile(file,content){
 const fd=fs.openSync(file,"wx",0o600);
 try{fs.writeSync(fd,content);fs.fsyncSync(fd);}
 finally{fs.closeSync(fd);}
}
function create(dir,{captureId}={}){
 need(typeof dir==="string"&&dir.length>0&&!fs.existsSync(dir)&&
  typeof captureId==="string"&&/^[a-zA-Z0-9._-]{4,100}$/.test(captureId),
  "NEW_PRIVATE_CAPTURE_ID");
 fs.mkdirSync(dir,{mode:0o700});privateDir(dir);
 const body={schema:SCHEMA,captureId,mode:"PAPER",
  source:"LOCAL_C25_RAW_HTTP_GET_RECEIPTS",
  accountIdsAndCredentialsStored:false,
  trustedExternalTimeOrBrokerAttestation:false,
  tradingPermitted:false,N9S:"NO_GO"};
 makeFile(path.join(dir,"manifest.json"),
  JSON.stringify({...body,manifestHash:hash(body)})+"\n");
 makeFile(path.join(dir,"receipts.ndjson"),"");
 const d=fs.openSync(dir,"r");
 try{fs.fsyncSync(d);}finally{fs.closeSync(d);}
 return verify(dir);
}
function verify(dir){
 privateDir(dir);
 const names=fs.readdirSync(dir);
 need(names.every(n=>["manifest.json","receipts.ndjson",".writer.lock"].includes(n)),
  "UNEXPECTED_FILE");
 const manifestFile=path.join(dir,"manifest.json");
 const receiptFile=path.join(dir,"receipts.ndjson");
 privateFile(manifestFile);privateFile(receiptFile);
 const manifest=JSON.parse(fs.readFileSync(manifestFile,"utf8"));
 const copy={...manifest};delete copy.manifestHash;
 need(manifest.schema===SCHEMA&&manifest.manifestHash===hash(copy)&&
  manifest.mode==="PAPER"&&
  manifest.trustedExternalTimeOrBrokerAttestation===false&&
  manifest.tradingPermitted===false&&manifest.N9S==="NO_GO",
  "MANIFEST_INTEGRITY");
 const content=fs.readFileSync(receiptFile,"utf8");
 need(!content||content.endsWith("\n"),"TRUNCATED_RECEIPT_LOG");
 const lines=content?content.trimEnd().split("\n"):[];
 let last=0,head="GENESIS",rows=[];
 for(const [i,line] of lines.entries()){
  need(Buffer.byteLength(line)<=2048,"RECEIPT_LINE_SIZE");
  const record=JSON.parse(line),candidate={...record};delete candidate.chainHash;
  W.acceptWitness(record.witness);
  need(record.schema==="HARPOON_FWN9_C33_LOCAL_CHAIN_RECEIPT_1"&&
   record.sequence===i+1&&record.previous===head&&
   record.manifestHash===manifest.manifestHash&&
   record.witness.sequence===i+1&&
   record.witness.completedAt>=last&&
   record.chainHash===hash(candidate),"CHAIN_INTEGRITY");
  head=record.chainHash;last=record.witness.completedAt;rows.push(record.witness);
 }
 return {schema:"HARPOON_FWN9_C33_GET_LOCAL_JOURNAL_AUDIT_1",
  count:rows.length,head,manifestHash:manifest.manifestHash,
  witnesses:rows,
  localSHAChainVerified:true,
  sourceExternallyAuthenticated:false,financialGO:false,N9S:"NO_GO"};
}
function openWriter(dir){
 const state=verify(dir);
 const lock=path.join(dir,".writer.lock");
 need(!fs.existsSync(lock),"STALE_LOCK_REQUIRES_MANUAL_REVIEW");
 fs.closeSync(fs.openSync(lock,"wx",0o600));
 const fd=fs.openSync(path.join(dir,"receipts.ndjson"),"a");
 let index=state.count,head=state.head,closed=false;
 let last=state.witnesses.at(-1)?.completedAt??0;
 return {
  append(witness){
   W.acceptWitness(witness);
   need(!closed&&witness.sequence===index+1&&
    witness.completedAt>=last&&
    witness.origin==="https://paper-api.alpaca.markets",
    "WRITER_CLOCK_AND_SEQUENCE");
   const data={schema:"HARPOON_FWN9_C33_LOCAL_CHAIN_RECEIPT_1",
    sequence:index+1,previous:head,manifestHash:state.manifestHash,witness};
   const line=JSON.stringify({...data,chainHash:hash(data)})+"\n";
   need(Buffer.byteLength(line)<=2048,"WRITE_LINE_BOUND");
   const written=fs.writeSync(fd,line);
   need(written===Buffer.byteLength(line),"INCOMPLETE_WRITE");
   fs.fsyncSync(fd);
   head=hash(data);index++;last=witness.completedAt;
   return {count:index,head};
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
