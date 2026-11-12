"use strict";
/**
 * C34: offline RFC3161 pre-outcome timestamp verification of an EXACT frozen
 * experiment envelope. No network, market data, broker or trading operations.
 * A locally supplied CA + a cryptographically valid TSA signature is NOT by
 * itself proof that the CA/operator is independent from the researcher.
 */
const A=require("node:assert/strict");
const fs=require("node:fs"),path=require("node:path");
const crypto=require("node:crypto");
const {execFileSync}=require("node:child_process");
const C29=require("./fwn9_c29_frozen_assignments.cjs");
const F=require("./fwn9_c32_forward_binding.cjs");
const SCHEMA="HARPOON_FWN9_C34_RFC3161_EXACT_PREREG_ENVELOPE_1";
const HOUR=3600000,MAX=5*1024*1024;
const SOURCES=Object.freeze([
 "fwn9_c29_frozen_assignments.cjs",
 "fwn9_c29_randomization_inference.cjs",
 "fwn9_c28_one_book_prospective_comparator.cjs",
 "fwn9_c32_forward_binding.cjs",
 "fwn9_c32_native_prefilter_gate.cjs",
 "fwn9_c25_broker_export_ingest.cjs",
 "fwn9_c26_causal_quote_fill_bridge.cjs",
 "fwn9_c33_broker_get_witness.cjs"
]);
function need(x,k){A.ok(x,"C34_"+k);}
function sha(x){return crypto.createHash("sha256").update(x).digest("hex");}
function rejectFinal(file){
 const v=path.resolve(file);
 need(typeof file==="string"&&file.length>0&&file.length<4096&&
  !/(?:^|\/)(?:holdout|M10[_-]?final)(?:\/|$)/i.test(v),
  "PATH_MUST_NOT_TOUCH_FINAL_HOLDOUT");
 return v;
}
function readFile(file,{secret=false,binary=false,max=MAX}={}){
 const p=rejectFinal(file),s=fs.lstatSync(p);
 need(s.isFile()&&!s.isSymbolicLink()&&s.size>0&&s.size<=max&&
  (!secret||(s.mode&0o077)===0),"FILE_INTEGRITY_AND_PRIVATE_PERMISSIONS");
 return fs.readFileSync(p,binary?undefined:"utf8");
}
function readJSON(file){return JSON.parse(readFile(file,{secret:true}));}
function sourceHashes(){
 return Object.fromEntries(SOURCES.map(name=>[
  "runtime30/"+name,sha(fs.readFileSync(path.join(__dirname,name)))
 ]));
}
function make({planFile,bindingFile}={}){
 const planBytes=readFile(planFile,{secret:true});
 const bindingBytes=readFile(bindingFile,{secret:true});
 const plan=JSON.parse(planBytes),binding=JSON.parse(bindingBytes);
 C29.validate(plan);F.validate(binding);
 need(binding.proposedAt<=plan.registeredAt&&
  binding.sixProspectiveWindowBindings.length===6&&
  plan.registeredAt+72*HOUR<=plan.startAt,
  "BINDING_MUST_PRECEDE_UNMODIFIED_PLAN");
 const body={
  schema:SCHEMA,
  originalC29PlanDigest:plan.planDigest,
  frozenC29PlanBytesSha256:sha(Buffer.from(planBytes)),
  forwardC32BindingDigest:binding.definitionSha256,
  forwardC32BindingBytesSha256:sha(Buffer.from(bindingBytes)),
  originalStartingCapitalUsd:20000,
  originalDailyHurdleBps:1,
  originalRiskPerEntry:0.0025,
  originalGrossAdmission:0.12,
  originalMaxHoldingHours:72,
  originalFamilywiseAlpha:0.025,
  originalEightArmOrder:[...plan.eightArms],
  plannedFirstBlockAt:plan.startAt,
  planLocalRegisteredAt:plan.registeredAt,
  c22OriginalSixPolicyIdentityNotRetroactivelyProven:true,
  forwardSixCompositePolicyDefinitionOnly:true,
  sourceCodeSha256:sourceHashes(),
  noTradeAuthorized:true,
  sourceBrokerReceiptsExternallyAuthenticated:false,
  externalRegistrarIdentityIndependentlyVerified:false,
  originalFinalM10AccountsSealed:3200,
  N9S:"NO_GO"
 };
 return {...body,envelopeDigestSha256:sha(Buffer.from(JSON.stringify(body)))};
}
function verifyEnvelope({envelopeFile,planFile,bindingFile}={}){
 const envelope=readJSON(envelopeFile),
  regenerated=make({planFile,bindingFile});
 need(JSON.stringify(envelope)===JSON.stringify(regenerated),
  "ENVELOPE_EXACT_BYTES_PLAN_BINDING_OR_CODE_CHANGED");
 need(envelope.originalEightArmOrder.length===8&&
  envelope.N9S==="NO_GO"&&envelope.noTradeAuthorized===true,
  "NO_FINANCIAL_PROMOTION");
 return envelope;
}
function saveNew(file,object){
 const p=rejectFinal(file),buf=Buffer.from(JSON.stringify(object,null,2)+"\n");
 need(buf.length<=MAX,"ENVELOPE_OUTPUT_BUDGET");
 const fd=fs.openSync(p,"wx",0o600);
 try{fs.writeSync(fd,buf);fs.fsyncSync(fd);}
 finally{fs.closeSync(fd);}
 const d=fs.openSync(path.dirname(p),"r");
 try{fs.fsyncSync(d);}finally{fs.closeSync(d);}
 return {file:p,rawSha256:sha(buf)};
}
function openssl(args,{bin="openssl"}={}){
 need(bin==="openssl"||bin==="/usr/bin/openssl",
  "OPENSSL_BINARY_ALLOWLIST");
 try{
  return execFileSync(bin,args,{encoding:"utf8",timeout:15000,
   maxBuffer:512*1024,stdio:["ignore","pipe","pipe"]});
 }catch(error){throw Error("C34_OPENSSL_RFC3161_VERIFICATION_FAILED");}
}
function signedGenTime(text){
 need(/Status:\s*Granted\./.test(text),"TSA_RESPONSE_NOT_GRANTED");
 const m=/Time stamp:\s*(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2})\s+(\d\d:\d\d:\d\d)\s+(\d{4})\s+GMT\b/.exec(text);
 need(m!==null,"SIGNED_GENTIME_MISSING");
 const value=Date.parse(m[1]+" "+m[2]+", "+m[4]+" "+m[3]+" GMT");
 need(Number.isSafeInteger(value)&&value>0,"SIGNED_GENTIME_INVALID");
 return value;
}
function verifyTimestamp({
  envelopeFile,planFile,bindingFile,queryFile,responseFile,
  caPemFile,untrustedSignerFile=null,pinnedCaFileSha256,
  now=Date.now(),bin="openssl"
}={}){
 const envelope=verifyEnvelope({envelopeFile,planFile,bindingFile});
 readFile(queryFile,{binary:true,max:65536});
 readFile(responseFile,{binary:true,max:1024*1024});
 const ca=readFile(caPemFile,{binary:true,max:1024*1024});
 need(typeof pinnedCaFileSha256==="string"&&
  /^[a-f0-9]{64}$/.test(pinnedCaFileSha256)&&
  sha(ca)===pinnedCaFileSha256,"PINNED_CA_BYTES_MISMATCH");
 if(untrustedSignerFile!==null)
  readFile(untrustedSignerFile,{binary:true,max:1024*1024});
 need(Number.isSafeInteger(now)&&now>0,"CLOCK");
 const verifyFlags=["-CAfile",rejectFinal(caPemFile)];
 if(untrustedSignerFile!==null)
  verifyFlags.push("-untrusted",rejectFinal(untrustedSignerFile));
 // 1. Signed token must commit to EXACT envelope bytes, not a JSON summary.
 openssl(["ts","-verify","-data",rejectFinal(envelopeFile),
  "-in",rejectFinal(responseFile),...verifyFlags],{bin});
 // 2. The original RFC3161 request (including its nonce and policy)
 // must match the response. This closes the data-only nonce gap.
 openssl(["ts","-verify","-queryfile",rejectFinal(queryFile),
  "-in",rejectFinal(responseFile),...verifyFlags],{bin});
 const printed=openssl(["ts","-reply","-in",rejectFinal(responseFile),
  "-text"],{bin});
 const stampedAt=signedGenTime(printed);
 need(stampedAt>=envelope.planLocalRegisteredAt&&
  stampedAt+72*HOUR<=envelope.plannedFirstBlockAt&&
  stampedAt<=now,"TSA_TIME_NOT_BEFORE_72H_CUTOFF");
 return {
  schema:"HARPOON_FWN9_C34_RFC3161_OFFLINE_VERIFICATION_RESULT_1",
  exactExperimentEnvelopeSha256:
   sha(fs.readFileSync(rejectFinal(envelopeFile))),
  originalC29PlanDigest:envelope.originalC29PlanDigest,
  forwardC32BindingDigest:envelope.forwardC32BindingDigest,
  pinnedCaFileSha256,
  signedRfc3161GenTimeUtc:new Date(stampedAt).toISOString(),
  requestNonceAndEnvelopeMessageImprintCryptographicallyVerified:true,
  timestampBeforeFrozenStartMinus72Hours:true,
  originalRegisteredAtAndWindowChecks:true,
  // An operator-supplied CA can even be self-issued; CI generates one.
  // No host can infer independent custodianship from signature bytes alone.
  tsaSignerAndTrustRootIndependentlyVetted:false,
  independentlyAuditedPreregistration:false,
  originalBrokerAccountAuthenticated:false,
  optionExecutionAndSettlementCertified:false,
  sixFrozenC22StrategiesRetrospectivelyEquivalent:false,
  paperOrLiveOrdersAllowed:false,
  canPromoteToN9:false,financialGO:false,
  M10FinalSealed:3200,N9S:"NO_GO"
 };
}
module.exports={
 SCHEMA,SOURCES,make,verifyEnvelope,verifyTimestamp,saveNew,
 signedGenTime,sourceHashes
};
