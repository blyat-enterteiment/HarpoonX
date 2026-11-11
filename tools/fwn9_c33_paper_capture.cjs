#!/usr/bin/env node
"use strict";
/**
 * PAPER-only C33 wrapper for the existing local C25 capture CLI.
 * Explicit local invocation is required. No Trading API access in CI.
 * No orders or mutations, no crypto secrets or account IDs in the journal.
 */
const path=require("node:path");
const C25CLI=require("./fwn9_c25_capture_readonly_alpaca.cjs");
const W=require("../runtime30/fwn9_c33_broker_get_witness.cjs");
const J=require("../runtime30/fwn9_c33_broker_get_journal.cjs");
function need(x,k){if(!x)throw Error("C33_CLI_"+k);}
function argsOf(argv){
 let journal=null,filtered=[];
 for(let i=0;i<argv.length;i++){
  if(argv[i]==="--get-journal"){
   need(journal===null&&typeof argv[i+1]==="string"&&
    argv[i+1].length>0,"JOURNAL_ARGUMENT");
   journal=argv[++i];continue;
  }
  filtered.push(argv[i]);
 }
 const parsed=C25CLI.argumentsOf(filtered);
 need(parsed["--mode"]==="PAPER"&&journal!==null&&
  !/(^|[\\/])(holdout|final)([\\/]|$)/i.test(path.resolve(journal)),
  "PAPER_ONLY_PRIVATE_NONHOLDOUT_JOURNAL");
 return {journal:path.resolve(journal),filtered,stage:parsed["--stage"]};
}
async function main(argv,options={}){
 const parsed=argsOf(argv);
 const writerId="C33_"+parsed.stage+"_"+process.pid;
 J.create(parsed.journal,{captureId:writerId});
 const writer=J.openWriter(parsed.journal);
 const receipts=W.wrapTransport({
  mode:"PAPER",
  transport:options.transport??fetch,
  now:options.now??Date.now,
  sink:r=>writer.append(r)
 });
 // C25's original parser, export schema, POST-blocking allowlist, account
 // arithmetic and privacy handling remain unchanged.
 await C25CLI.main(parsed.filtered,{env:options.env??process.env,
  fetch:receipts});
 const outcome=writer.close(),audit=W.verifyCoverage({
  witnesses:outcome.witnesses,mode:"PAPER"
 });
 process.stdout.write(JSON.stringify({
  schema:"HARPOON_FWN9_C33_LOCAL_CAPTURE_RESULT_1",
  privateGetResponseCount:audit.witnessedGetResponses,
  missingEndpointKinds:audit.missingRequiredEndpoints,
  sourceReceiptHead:outcome.head,
  accountIdPrinted:false,credentialPrinted:false,
  independentlyAuthenticatedByAlpaca:false,
  independentTimeRegistration:false,
  permissionToTrade:false,N9S:"NO_GO"
 })+"\n");
 return 0;
}
if(require.main===module){
 process.umask(0o077);
 main(process.argv.slice(2)).then(
  ()=>{process.exitCode=0;},
  ()=>{process.stderr.write("C33_CLI_CAPTURE_FAILED_NO_SENSITIVE_DETAILS_PRINTED\n");
   process.exitCode=2;});
}
module.exports={argsOf,main};
