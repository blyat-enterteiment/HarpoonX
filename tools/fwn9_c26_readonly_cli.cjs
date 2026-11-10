#!/usr/bin/env node
"use strict";
/** C26: inspect a customer-supplied, private, OFFLINE joined quote/decision
 * and C25 order/FILL bundle. No HTTP, no broker actions, no identifier output.
 *
 * node tools/fwn9_c26_readonly_cli.cjs
 * node tools/fwn9_c26_readonly_cli.cjs --bundle /private/in.json
 * node tools/fwn9_c26_readonly_cli.cjs --bundle /private/in.json --out /private/result.json
 */
const fs=require("node:fs"),path=require("node:path"),crypto=require("node:crypto");
const C=require("../runtime30/fwn9_c26_causal_quote_fill_bridge.cjs");
function need(ok,tag){if(!ok)throw Error("C26_CLI_"+tag);}
function guarded(p){
 need(typeof p==="string"&&p.length>0&&p.length<4096,"PATH");
 const abs=path.resolve(p);
 need(!/(^|\/)(holdout|m10[_-]?final)(\/|$)/i.test(abs)&&
  !/\/evidence\/modulation9\/final\//i.test(abs),"SEALED_M10_PATH");
 return abs;
}
function args(argv){
 if(argv.length===0)return {};
 need(argv.length===2||argv.length===4,"USAGE");
 const p={};
 for(let i=0;i<argv.length;i+=2){
  const k=argv[i],v=argv[i+1];
  need(["--bundle","--out"].includes(k)&&!Object.hasOwn(p,k)&&
   typeof v==="string"&&v.length>0,"ARGUMENT");
  p[k]=guarded(v);
 }
 need(p["--bundle"]!==undefined&&
  (p["--out"]===undefined||p["--out"]!==p["--bundle"]),"REQUIRED_BUNDLE");
 return p;
}
function run(argv){
 const options=args(argv);
 if(!options["--bundle"]){
  process.stdout.write(JSON.stringify(C.absence())+"\n");
  return 0;
 }
 const file=options["--bundle"],stat=fs.lstatSync(file);
 need(stat.isFile()&&!stat.isSymbolicLink()&&stat.size>2&&
  stat.size<=64*1024*1024,"PRIVATE_INPUT_TYPE_AND_BYTES");
 const raw=fs.readFileSync(file);
 const audit=C.classify(JSON.parse(raw.toString("utf8")));
 const hash=crypto.createHash("sha256").update(raw).digest("hex");
 if(options["--out"]){
  const outfile=options["--out"];
  const body=JSON.stringify({...audit,inputFileSha256:hash,
   inputShaAuthenticatesBroker:false},null,2)+"\n";
  need(Buffer.byteLength(body)<=64*1024*1024,"PRIVATE_REPORT_BYTES");
  const fd=fs.openSync(outfile,"wx",0o600);
  try{fs.writeFileSync(fd,body,{encoding:"utf8"});fs.fsyncSync(fd);}
  finally{fs.closeSync(fd);}
 }
 const report={schema:"HARPOON_FWN9_C26_REDACTED_CLI_RESULT_1",
  inputFileSha256:hash,
  matchedFillCount:audit.matchedFillCount,
  brokerageOriginVerified:false,
  economicGainOrOptimalWindowCertified:false,
  savedPrivateReport:options["--out"]!==undefined,
  sourceAccountIdentifierNotPrinted:true,
  noOrdersOrHTTP:true,holdoutM10Sealed:3200,N9S:"NO_GO"};
 process.stdout.write(JSON.stringify(report)+"\n");
 return 0;
}
if(require.main===module){
 try{process.exitCode=run(process.argv.slice(2));}
 catch(e){process.stderr.write(/^C26_CLI_[A-Z_]+$/.test(e?.message)?
  e.message+"\n":"C26_CLI_VALIDATION_FAILED_PRIVATE_FIELDS_NOT_PRINTED\n");
  process.exitCode=2;}
}
module.exports={args,guarded,run};
