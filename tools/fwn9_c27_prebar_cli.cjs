#!/usr/bin/env node
"use strict";
/** C27 PRIVATE local source prebar recorder.
 *
 * Usage:
 * node tools/fwn9_c27_prebar_cli.cjs --init /private/c27-journal --manifest /private/grid.json
 * node tools/fwn9_c27_prebar_cli.cjs --append /private/c27-journal --input /private/prebar.json
 * node tools/fwn9_c27_prebar_cli.cjs --verify /private/c27-journal
 *
 * Does not read secrets, broker APIs, future bars or orders. Local source
 * content hashes do not authenticate a broker/exchange or trusted wall clock.
 */
const fs=require("node:fs"),path=require("node:path");
const J=require("../runtime30/fwn9_c27_prebar_journal.cjs");
function need(x,code){if(!x)throw Error("C27CLI_"+code);}
function guard(p){
 need(typeof p==="string"&&p.length>0&&p.length<4096,"PATH");
 const s=path.resolve(p);
 need(!/(?:^|\/)(?:holdout|M10[_-]?final|modulation9\/final)(?:\/|$)/i.test(s),
  "SEALED_FINAL_PATH");
 return s;
}
function read(p){
 const target=guard(p),st=fs.lstatSync(target);
 need(st.isFile()&&!st.isSymbolicLink()&&st.size>0&&st.size<4*1024*1024&&
  (st.mode&0o077)===0,"PRIVATE_INPUT_0600");
 return JSON.parse(fs.readFileSync(target,"utf8"));
}
function options(argv){
 need(argv.length===2||argv.length===4,"USAGE");
 const op=argv[0],dir=guard(argv[1]);
 need(["--init","--append","--verify"].includes(op),"ACTION");
 if(op==="--verify")need(argv.length===2,"VERIFY_ARGS");
 else need(argv.length===4&&argv[2]===(op==="--init"?"--manifest":"--input"),
  "SOURCE_ARGS");
 return {op,dir,input:argv.length===4?guard(argv[3]):null};
}
function execute(argv){
 const o=options(argv);
 let proof;
 if(o.op==="--init"){
  const m=read(o.input);
  // The user-supplied manifest is a SOURCE schedule, not new market prices.
  proof=J.newJournal(o.dir,m);
 }else if(o.op==="--append"){
  const frame=read(o.input),m=J.verifyJournal(o.dir).manifest;
  if(m.mode==="PROSPECTIVE_LOCAL_CAPTURE"){
   // Do not permit an editable input document to self-certify capture time:
   // assign local wall-clock on the append call, then test all knownAt<=now.
   const now=Date.now();
   frame.capturedAt=now;
   proof=J.append(o.dir,frame,{now});
  }else proof=J.append(o.dir,frame);
 }else proof=J.verifyJournal(o.dir);
 return {schema:"HARPOON_FWN9_C27_REDACTED_SOURCE_CLI_RESULT_1",
  action:o.op,framesVerified:proof.verifiedFrames,
  expectedScheduledBars:proof.expectedFrames,
  sourceFrameCoverageComplete:proof.coverageComplete,
  latestLocalChainHash:proof.finalizedEvidenceHead,
  sourceProviderAuthenticated:false,
  sourceOpportunityGeneratorIndependentlyAttested:false,
  executableBrokerFillsProved:false,
  noAccountIdentifiersOrPortfolioValuesPrinted:true,
  hasTradeOrBrokerAction:false,canOpenM10Final:false,
  N9S:"NO_GO"};
}
if(require.main===module){
 try{const d=execute(process.argv.slice(2));
  process.stdout.write(JSON.stringify(d)+"\n");}
 catch(e){
  process.stderr.write(/^C27(?:J|CLI|_)[A-Z_]+$/.test(e?.message)?
   e.message+"\n":"C27CLI_SOURCE_VALIDATION_FAILED_NO_PRIVATE_FIELDS_PRINTED\n");
  process.exitCode=2;
 }
}
module.exports={guard,read,options,execute};
