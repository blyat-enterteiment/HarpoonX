#!/usr/bin/env node
"use strict";
/** Locally invoked capture of READ-ONLY Alpaca GET account data.
 * Never sends POST/PATCH/DELETE, never displays account IDs or credentials,
 * never changes HarpoonX runtime, and writes private files with mode 0600.
 */
const fs=require("node:fs"),path=require("node:path");
const api=require("../runtime30/fwn9_c25_alpaca_readonly_exporter.cjs");
function need(cond,code){if(!cond)throw Error("C25_CAPTURE_"+code);}
function argumentsOf(argv){
 need(argv.length>=6&&argv.length%2===0,"USAGE");
 const p={};
 for(let i=0;i<argv.length;i+=2){
  const k=argv[i],v=argv[i+1];
  need(["--stage","--mode","--out","--baseline","--cost"].includes(k)&&
   !Object.hasOwn(p,k)&&typeof v==="string"&&v.length>0,"ARGUMENTS");
  p[k]=v;
 }
 need(["baseline","finish"].includes(p["--stage"])&&
  ["PAPER","LIVE"].includes(p["--mode"])&&
  typeof p["--out"]==="string","STAGE_MODE_OUTPUT");
 if(p["--stage"]==="finish")need(typeof p["--baseline"]==="string",
  "FINISH_NEEDS_BASELINE");
 else need(!p["--baseline"]&&!p["--cost"],"BASELINE_UNEXPECTED_INPUT");
 return p;
}
function filePath(p){
 need(typeof p==="string"&&p.length>0,"FILE_PATH");
 const abs=path.resolve(p);
 need(!/(^|\/)(holdout|final)(\/|$)/i.test(abs)&&
  !/\/evidence\/modulation9\/final\//i.test(abs),
  "M10_HOLDOUT_CANNOT_BE_CAPTURE");
 return abs;
}
function loadPrivate(p){
 const file=filePath(p),st=fs.lstatSync(file);
 need(st.isFile()&&!st.isSymbolicLink()&&st.size>0&&st.size<=16*1024*1024,
  "PRIVATE_INPUT_SIZE_AND_TYPE");
 return JSON.parse(fs.readFileSync(file,"utf8"));
}
function writePrivate(p,obj){
 const file=filePath(p);
 const raw=JSON.stringify(obj,null,2)+"\n";
 need(Buffer.byteLength(raw)<16*1024*1024,"PRIVATE_OUTPUT_SIZE");
 // wx refuses overwrite or symlinks; process umask and file mode preserve
 // source material locally. Never publish these files to GitHub by default.
 const fd=fs.openSync(file,"wx",0o600);
 try{fs.writeFileSync(fd,raw,{encoding:"utf8"});fs.fsyncSync(fd);}
 finally{fs.closeSync(fd);}
 fs.chmodSync(file,0o600);
 return {bytes:Buffer.byteLength(raw),fileMode:"0600"};
}
async function main(argv,options={}){
 const args=argumentsOf(argv);
 const get=api.readOnlyTransport({
  mode:args["--mode"],env:options.env??process.env,
  transport:options.fetch??fetch
 });
 let report;
 if(args["--stage"]==="baseline")
  report=await api.baseline(get,args["--mode"]);
 else{
  const source=loadPrivate(args["--baseline"]);
  need(source.mode===args["--mode"],"BASELINE_MODE_MISMATCH");
  const costs=args["--cost"]?loadPrivate(args["--cost"]):null;
  report=await api.finish(get,source,undefined,costs);
 }
 const saved=writePrivate(args["--out"],report);
 process.stdout.write(JSON.stringify({status:"CAPTURED_READ_ONLY_PRIVATE_LOCAL",
  mode:args["--mode"],stage:args["--stage"],
  schema:report.schema,bytes:saved.bytes,fileMode:saved.fileMode,
  accountIdPrinted:false,credentialPrinted:false,
  brokerOriginIndependentlyAttested:false,
  economicGO:false,ordersCreated:0,N9S:"NO_GO"})+"\n");
 return 0;
}
if(require.main===module){
 process.umask(0o077);
 main(process.argv.slice(2)).then(()=>{process.exitCode=0;},
  e=>{
   const code=/^C25_(?:GET_|CAPTURE_)[A-Z_]+$/.test(e?.message) ?
    e.message:"C25_CAPTURE_FAILED_NO_SENSITIVE_DETAILS_PRINTED";
   process.stderr.write(code+"\n");process.exitCode=2;
  });
}
module.exports={argumentsOf,filePath,loadPrivate,writePrivate,main};
