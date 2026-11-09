"use strict";
/** P9L: bounded, atomic, restartable OFFLINE source-evidence checkpoint.
 * Hashes detect accidental mutations, not full-database rewrite by an attacker.
 * No optimizer promotion or market orders. */
const A=require("node:assert/strict");
const fs=require("node:fs"),path=require("node:path");
const crypto=require("node:crypto");
const MAX=64,SCHEMA="HARPOON_FWN9_P9L_CHECKPOINT_1";
const sha=x=>crypto.createHash("sha256").update(JSON.stringify(x)).digest("hex");
function need(ok,label){A.ok(ok,"P9L_JOURNAL_"+label);}
function unpack(file,binding){
 need(/^[a-f0-9]{64}$/.test(binding),"BINDING_SHA_REQUIRED");
 if(!fs.existsSync(file))return {schema:SCHEMA,binding,entries:[],head:"GENESIS"};
 const stat=fs.lstatSync(file);
 need(stat.isFile()&&!stat.isSymbolicLink()&&stat.nlink===1 &&
   stat.size>0&&stat.size<=4*1024*1024,"FILE_UNSAFE");
 const r=JSON.parse(fs.readFileSync(file,"utf8"));
 need(r?.schema===SCHEMA&&r.binding===binding&&
   Array.isArray(r.entries)&&r.entries.length<=MAX,"SCHEMA_OR_BINDING");
 let prior="GENESIS";
 const ids=new Set();
 for(let i=0;i<r.entries.length;i++){
   const e=r.entries[i];
   need(e.seq===i+1&&typeof e.id==="string"&&!ids.has(e.id)&&
     /^[a-f0-9]{64}$/.test(e.evidenceHash) &&
     e.prev===prior,"ENTRY_INTEGRITY");
   ids.add(e.id);
   need(e.hash===sha({seq:e.seq,id:e.id,evidenceHash:e.evidenceHash,prev:prior}),
     "ENTRY_CHECKSUM");
   prior=e.hash;
 }
 need(r.head===prior,"HEAD_CHECKSUM");
 return r;
}
function storeAtomic(file,data){
 const dir=path.dirname(path.resolve(file));
 need(fs.statSync(dir).isDirectory(),"DIRECTORY_MISSING");
 const tmp=path.join(dir,"."+path.basename(file)+"."+crypto.randomUUID()+".tmp");
 let fd;
 try{
   fd=fs.openSync(tmp,"wx",0o600);
   fs.writeFileSync(fd,JSON.stringify(data)+"\n",{encoding:"utf8"});
   fs.fsyncSync(fd);
   fs.closeSync(fd);fd=undefined;
   if(fs.existsSync(file)){
     const stat=fs.lstatSync(file);
     need(stat.isFile()&&!stat.isSymbolicLink()&&stat.nlink===1,"TARGET_NOT_SAFE");
   }
   fs.renameSync(tmp,file);
   try{const d=fs.openSync(dir,"r");try{fs.fsyncSync(d);}finally{fs.closeSync(d);}}
   catch{/* directory sync optional; file sync and rename already completed */}
 }finally{
   if(fd!==undefined)fs.closeSync(fd);
   if(fs.existsSync(tmp))fs.unlinkSync(tmp);
 }
}
function commit(file,binding,id,evidence){
 need(typeof id==="string"&&/^[A-Za-z0-9:_-]{3,120}$/.test(id),
   "ENTRY_ID");
 need(evidence?.schema==="HARPOON_FWN9_P9L_NATIVE_EVENT_BRIDGE_1"&&
   evidence.optimizerEligible===false&&evidence.executionAllowed===false&&
   evidence.nativePriceExecutability===false&&
   evidence.nativeRiskClockParity===true&&
   evidence.all_source_acceptances_checked===true&&
   Math.abs(evidence.sourceWealthUsd-evidence.p9kWealthUsd)<1e-6,
   "PROOF_INCOMPLETE_OR_UNPROMOTABLE");
 const existing=unpack(file,binding);
 const evidenceHash=sha({schema:evidence.schema,
   accepted:evidence.source_accepted,events:evidence.bridge_events,
   sourceWealthUsd:evidence.sourceWealthUsd,
   p9kWealthUsd:evidence.p9kWealthUsd,
   noFill:evidence.source_nofill,
   receiptTape:evidence.sourceReceiptTape});
 const older=existing.entries.find(e=>e.id===id);
 if(older){
   need(older.evidenceHash===evidenceHash,"ID_REUSED_WITH_DIFFERENT_EVIDENCE");
   return {status:"UNCHANGED",entries:existing.entries.length,head:existing.head};
 }
 need(existing.entries.length<MAX,"JOURNAL_BUDGET_EXHAUSTED");
 const seq=existing.entries.length+1,prev=existing.head;
 const row={seq,id,evidenceHash,prev,hash:sha({seq,id,evidenceHash,prev})};
 const next={...existing,entries:[...existing.entries,row],head:row.hash};
 storeAtomic(file,next);
 const checked=unpack(file,binding);
 need(checked.head===row.hash,"READ_AFTER_WRITE_MISMATCH");
 return {status:"COMMITTED",entries:checked.entries.length,head:checked.head};
}
function holdoutGate(data){
 // An offline modeled source trace can populate provenance but is not a
 // completed observed, independently validated opportunity panel.
 need(data?.sourceNature==="HISTORICAL_MODELED_OHLCV_NOT_BROKER_RECEIPTS",
   "SOURCE_NATURE_REQUIRED");
 return {schema:"HARPOON_FWN9_P9L_OPTIMIZER_HANDOFF_1",
   status:"WAIT_OBSERVED_COMPLETED_OPPORTUNITIES",
   reason:"MODELED_SOURCE_HAS_NO_OBSERVED_EXECUTABLE_LABELS",
   selected:[],execution_allowed:false,trade_authorization:false,
   optimizer_input_validated:false,profit_improvement_certified:false};
}
module.exports={commit,unpack,sha,holdoutGate};
