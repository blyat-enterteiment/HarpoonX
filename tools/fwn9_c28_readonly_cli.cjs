#!/usr/bin/env node
"use strict";
/** Offline and private FWN9 C28 source-tap archive auditor.
 * No provider call, no market signal, no broker order, no M10 final read.
 *
 * node tools/fwn9_c28_readonly_cli.cjs --init TAP_DIR --c27 C27_DIR --registry REGISTRY_JSON --calendar CALENDAR_JSON
 * node tools/fwn9_c28_readonly_cli.cjs --append TAP_DIR --c27 C27_DIR --taps TAP_ROWS_JSON
 * node tools/fwn9_c28_readonly_cli.cjs --verify TAP_DIR --c27 C27_DIR
 */
const fs=require("node:fs"),path=require("node:path");
const T=require("../runtime30/fwn9_c28_source_tap_archive.cjs");
function need(ok,tag){if(!ok)throw Error("C28CLI_"+tag);}
function safe(p){
 need(typeof p==="string"&&p.length>0&&p.length<4096,"PATH");
 const v=path.resolve(p);
 need(!/(?:^|\/)(?:holdout|M10[_-]?final)(?:\/|$)/i.test(v)&&
  !/\/evidence\/modulation9\/final\//i.test(v),"SEALED_FINAL_PATH");
 return v;
}
function readPrivate(p){
 const file=safe(p),stat=fs.lstatSync(file);
 need(stat.isFile()&&!stat.isSymbolicLink()&&stat.size>0&&
  stat.size<=4*1024*1024&&(stat.mode&0o077)===0,"PRIVATE_SOURCE_0600");
 return JSON.parse(fs.readFileSync(file,"utf8"));
}
function options(args){
 need(args.length>=4&&args.length%2===0,"ARGS");
 const op=args[0];
 need(["--init","--append","--verify"].includes(op),"OPERATION");
 const d={op,dir:safe(args[1])};
 for(let i=2;i<args.length;i+=2){
  const key=args[i],value=args[i+1];
  need(["--c27","--registry","--calendar","--taps"].includes(key)&&
   d[key]===undefined,"PARAMETER");
  d[key]=safe(value);
 }
 need(d["--c27"]!==undefined,"C27_REQUIRED");
 if(op==="--init")need(d["--registry"]!==undefined&&
  d["--calendar"]!==undefined&&args.length===8,"INIT_ARGUMENTS");
 else if(op==="--append")need(d["--taps"]!==undefined&&
  args.length===6,"APPEND_ARGUMENTS");
 else need(args.length===4,"VERIFY_ARGUMENTS");
 return d;
}
function run(args){
 const v=options(args);
 let proof;
 if(v.op==="--init")proof=T.create(v.dir,{
  c27Dir:v["--c27"],registry:readPrivate(v["--registry"]),
  calendar:readPrivate(v["--calendar"])});
 else if(v.op==="--append")proof=T.append(v.dir,v["--c27"],
  readPrivate(v["--taps"]));
 else proof=T.verify(v.dir,v["--c27"]);
 return {schema:"HARPOON_FWN9_C28_REDACTED_LOCAL_TAP_CLI_1",
  action:v.op,sourceTapFrames:proof.tapCommittedFrames,
  expectedC27Frames:proof.expectedFrames,
  completeSourceTapSchedule:proof.fullBarsAndSourceTapsComplete,
  sourceTapHeadSha256:proof.verifiedTapChainHead,
  originalC27HeadSha256:proof.linkedC27Head,
  brokerSourceAuthenticated:false,
  cashAndOriginalExecutableComparisonCertified:false,
  storedPrivateAccountFieldsPrinted:false,
  noBrokerOrderOrMarketGeneratorCalled:true,
  M10FinalSealed:3200,financialGO:false,N9S:"NO_GO"};
}
if(require.main===module){
 try{process.stdout.write(JSON.stringify(run(process.argv.slice(2)))+"\n");}
 catch(e){
  const msg=/^C28(?:CLI|A|J|_)[A-Z_]+$/.test(e?.message)?
   e.message:"C28CLI_VALIDATION_FAILED_PRIVATE_DETAILS_NOT_PRINTED";
  process.stderr.write(msg+"\n");process.exitCode=2;
 }
}
module.exports={options,safe,readPrivate,run};
