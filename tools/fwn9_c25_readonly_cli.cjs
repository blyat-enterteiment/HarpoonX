#!/usr/bin/env node
"use strict";
/** Offline C25 export command. No network transport, credentials, order methods
 * or copy of private broker account identifiers in printed report.
 *
 * node tools/fwn9_c25_readonly_cli.cjs
 * node tools/fwn9_c25_readonly_cli.cjs --bundle /private/path/export.json
 */
const fs=require("node:fs");
const path=require("node:path");
const crypto=require("node:crypto");
const C=require("../runtime30/fwn9_c25_broker_export_ingest.cjs");
function main(argv){
 if(argv.length===0){
  process.stdout.write(JSON.stringify(C.missingEvidence())+"\n");
  return 0;
 }
 if(argv.length!==2||argv[0]!=="--bundle"||!argv[1]||argv[1].startsWith("--"))
  throw Error("C25_USAGE_BUNDLE_PATH_ONLY");
 const file=path.resolve(argv[1]);
 if(/[\/]evidence[\/]modulation9[\/]final[\/]/i.test(file)||
    /[\/]holdout[\/]/i.test(file))
  throw Error("C25_FINAL_HOLDOUT_NOT_ALLOWED_AS_EXPORT");
 const st=fs.statSync(file);
 if(!st.isFile()||st.size<2||st.size>16*1024*1024)
  throw Error("C25_BUNDLE_SIZE_BOUND");
 const bytes=fs.readFileSync(file);
 const parsed=JSON.parse(bytes.toString("utf8"));
 const output=C.certify(parsed);
 output.inputFileSha256=crypto.createHash("sha256").update(bytes).digest("hex");
 output.inputFileHashAuthenticatesBrokerOrigin=false;
 output.providerAccountIdentifierPrinted=false;
 process.stdout.write(JSON.stringify(output)+"\n");
 return 0;
}
if(require.main===module){
 try{process.exitCode=main(process.argv.slice(2));}
 catch(e){
  const msg=e?.message??"UNKNOWN";
  const safe=/^C25_[A-Z_]+$/.test(msg)?msg:"C25_OFFLINE_VALIDATION_FAILED_NO_BROKER_ACCOUNT_DISCLOSED";
  process.stderr.write(safe+"\n");process.exitCode=2;
 }
}
module.exports={main};
