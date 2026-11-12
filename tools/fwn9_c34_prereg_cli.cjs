#!/usr/bin/env node
"use strict";
/** C34 local, offline RFC3161 preregistration; never requests a token
 * on the network, handles API keys or sends broker orders. */
const C=require("../runtime30/fwn9_c34_rfc3161_prereg.cjs");
function need(x,k){if(!x)throw Error("C34CLI_"+k);}
function argsOf(argv){
 need(Array.isArray(argv)&&argv.length>=7,"ARGUMENTS");
 const [action,...pairs]=argv;
 need(["--prepare","--verify"].includes(action)&&
  pairs.length%2===0,"ACTION");
 const out={action};
 for(let i=0;i<pairs.length;i+=2){
  const k=pairs[i],v=pairs[i+1];
  need(["--plan","--binding","--out","--envelope","--query","--response",
   "--ca","--ca-sha256","--signer"].includes(k)&&
   !Object.hasOwn(out,k)&&typeof v==="string"&&v.length>0,"FLAG");
  out[k]=v;
 }
 const fields=action==="--prepare"?["--plan","--binding","--out"]:
  ["--plan","--binding","--envelope","--query","--response","--ca","--ca-sha256"];
 need(fields.every(x=>typeof out[x]==="string")&&
  (action!=="--prepare"||Object.keys(out).length===4)&&
  (action!=="--verify"||Object.keys(out).length>=8),
  "REQUIRED_PATHS");
 return out;
}
function main(argv){
 const a=argsOf(argv);
 if(a.action==="--prepare"){
  const envelope=C.make({planFile:a["--plan"],bindingFile:a["--binding"]});
  const save=C.saveNew(a["--out"],envelope);
  return {schema:"HARPOON_FWN9_C34_PREPARED_UNANCHORED_ENVELOPE_1",
   rawEnvelopeSha256:save.rawSha256,
   signedTimestampVerified:false,externalTrustVerified:false,
   brokerOrdersPermitted:false,N9S:"NO_GO",M10Sealed:3200};
 }
 const result=C.verifyTimestamp({
  envelopeFile:a["--envelope"],planFile:a["--plan"],bindingFile:a["--binding"],
  queryFile:a["--query"],responseFile:a["--response"],caPemFile:a["--ca"],
  pinnedCaFileSha256:a["--ca-sha256"],untrustedSignerFile:a["--signer"]??null
 });
 return result;
}
if(require.main===module){
 process.umask(0o077);
 try{process.stdout.write(JSON.stringify(main(process.argv.slice(2)))+"\n");}
 catch(error){
  const message=/^C34(?:CLI)?_[A-Z_0-9]+$/.test(error?.message)?
   error.message:"C34CLI_INVALID_PRIVATE_PREREGISTRATION_EVIDENCE";
  process.stderr.write(message+"\n");process.exitCode=2;
 }
}
module.exports={argsOf,main};
