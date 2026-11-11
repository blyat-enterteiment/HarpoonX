#!/usr/bin/env node
"use strict";
/** C29 OFFLINE study preregistration. Creates no orders or run-loop.
 *
 * node tools/fwn9_c29_plan_cli.cjs --freeze /private/design.json --out /private/plan.json
 * node tools/fwn9_c29_plan_cli.cjs --verify /private/plan.json
 *
 * Write-once 0600. RegisteredAt is obtained from local process clock, not
 * user-authored retroactively. Independent notarization still REQUIRED.
 */
const fs=require("node:fs"),path=require("node:path");
const P=require("../runtime30/fwn9_c29_frozen_assignments.cjs");
function need(ok,key){if(!ok)throw Error("C29CLI_"+key);}
function safe(p){
 need(typeof p==="string"&&p.length>0&&p.length<4096,"PATH");
 const full=path.resolve(p);
 need(!/(?:^|\/)(?:holdout|M10[_-]?final)(?:\/|$)/i.test(full)&&
  !/\/evidence\/modulation9\/final\//i.test(full),"FINAL_M10_FORBIDDEN");
 return full;
}
function readPrivate(p){
 const file=safe(p),st=fs.lstatSync(file);
 need(st.isFile()&&!st.isSymbolicLink()&&st.size>2&&st.size<=4*1024*1024&&
  (st.mode&0o077)===0,"PRIVATE_0600_FILE");
 return JSON.parse(fs.readFileSync(file,"utf8"));
}
function writeExclusive(p,value){
 const file=safe(p),body=Buffer.from(JSON.stringify(value,null,2)+"\n");
 need(body.length<=4*1024*1024,"OUTPUT_SIZE");
 const fd=fs.openSync(file,"wx",0o600);
 try{fs.writeSync(fd,body);fs.fsyncSync(fd);}
 finally{fs.closeSync(fd);}
 const dir=fs.openSync(path.dirname(file),"r");
 try{fs.fsyncSync(dir);}finally{fs.closeSync(dir);}
}
function run(args,{now=()=>Date.now()}={}){
 need(Array.isArray(args)&&typeof now==="function","INPUT");
 if(args.length===4&&args[0]==="--freeze"&&args[2]==="--out"){
  const design=readPrivate(args[1]),clock=now();
  need(Number.isSafeInteger(clock)&&clock>0,"LOCAL_REGISTERED_CLOCK");
  need(typeof design.studyId==="string"&&
   Number.isSafeInteger(design.startAt)&&
   Number.isInteger(design.cycles)&&
   typeof design.assignmentNonce==="string",
   "STUDY_DESIGN_FIELDS");
  need(design.startAt>=clock+72*3600000,
   "AT_LEAST_72H_PROSPECTIVE_CLOCK");
  const p=P.freeze({studyId:design.studyId,registeredAt:clock,
   startAt:design.startAt,cycles:design.cycles,
   assignmentNonce:design.assignmentNonce});
  P.validate(p);
  writeExclusive(args[3],p);
  return {schema:"HARPOON_FWN9_C29_REDACTED_PREREG_CLI_1",
   phase:"FROZEN_LOCALLY_NOT_INDEPENDENTLY_TIMESTAMPED",
   digest:p.planDigest,plannedBlocks:p.blocks.length,
   registeredAt:clock,firstBlockAt:p.startAt,
   portfolioInitialCapitalUsd:20000,
   nonceNotPrinted:true,brokerKeysNotRead:true,
   accountNotCreated:true,ordersPlaced:0,N9S:"NO_GO",M10Sealed:3200};
 }
 if(args.length===2&&args[0]==="--verify"){
  const p=readPrivate(args[1]),v=P.validate(p);
  return {schema:"HARPOON_FWN9_C29_REDACTED_PREREG_CLI_1",
   phase:"RELOADED_AND_VERIFIED_LOCAL_HASH",
   digest:v.planDigest,plannedBlocks:v.plannedBlocks,
   originalArmsIntact:true,independentTimeAnchorVerified:false,
   portfolioInitialCapitalUsd:20000,
   nonceNotPrinted:true,brokerKeysNotRead:true,
   ordersPlaced:0,N9S:"NO_GO",M10Sealed:3200};
 }
 throw Error("C29CLI_USAGE");
}
if(require.main===module){
 try{process.stdout.write(JSON.stringify(run(process.argv.slice(2)))+"\n");}
 catch(e){
  const msg=/^C29(?:CLI|R)_[A-Z_]+$/.test(e?.message)?
   e.message:"C29CLI_ERROR_PRIVATE_DATA_NOT_PRINTED";
  process.stderr.write(msg+"\n");process.exitCode=2;
 }
}
module.exports={run,safe,readPrivate,writeExclusive};
