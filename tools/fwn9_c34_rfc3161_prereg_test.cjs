"use strict";
const test=require("node:test");
const A=require("node:assert/strict");
const fs=require("node:fs"),os=require("node:os"),path=require("node:path");
const crypto=require("node:crypto");
const cp=require("node:child_process");
const P=require("../runtime30/fwn9_c29_frozen_assignments.cjs");
const F=require("../runtime30/fwn9_c32_forward_binding.cjs");
const C=require("../runtime30/fwn9_c34_rfc3161_prereg.cjs");
const {Plugins}=require("../runtime30/plugins.js");
const HOUR=3600000;
const temp=fs.mkdtempSync(path.join(os.tmpdir(),"harpoon-c34-"));
const p=name=>path.join(temp,name);
const run=(...args)=>cp.execFileSync("openssl",args,{cwd:temp,
 stdio:["ignore","pipe","pipe"],timeout:15000});
const write=(name,bytes)=>fs.writeFileSync(p(name),bytes,{mode:0o600});
const sha=buffer=>crypto.createHash("sha256").update(buffer).digest("hex");
function fixture({prefix="study",startDelta=10*24*HOUR,
 registerDelta=-1*HOUR,proposedDelta=-2*HOUR}={}){
 const base=Date.now(),registeredAt=base+registerDelta;
 const original=P.freeze({studyId:prefix,
  registeredAt,startAt:base+startDelta,cycles:4,
  assignmentNonce:"C34_TEST_ONLY_RANDOMIZATION_NONCE_NOT_A_MARKET_SEED_123"});
 const plugins=Object.create(Plugins.prototype);
 plugins.cfg={universe:[
  {symbol:"SPY",book:"equity",venueOpen:true},
  {symbol:"QQQ",book:"etf",venueOpen:true},
  {symbol:"BTC/USD",book:"crypto",venueOpen:true},
  {symbol:"SPY270618C00600000",book:"options",venueOpen:true,contractSessionVerified:true}
 ],optionUnderlyings:["SPY"]};
 plugins.catalog=[
  {id:"frozen-native-equity",book:"equity",family:"trend",version:"30.0.0",params:{}},
  {id:"frozen-native-etf",book:"etf",family:"trend",version:"30.0.0",params:{}},
  {id:"frozen-native-crypto",book:"crypto",family:"breakout",version:"30.0.0",params:{}},
  {id:"frozen-native-options",book:"options",family:"call-breakout",version:"30.0.0",params:{}}
 ];
 const binding=F.freeze({plugins,
  enabledPluginIds:plugins.catalog.map(x=>x.id),
  registeredUniverse:plugins.cfg.universe,
  calendarSha256:"b".repeat(64),proposedAt:base+proposedDelta});
 const planFile=p(prefix+".plan.json"),bindingFile=p(prefix+".binding.json"),
  envelopeFile=p(prefix+".envelope.json");
 write(prefix+".plan.json",JSON.stringify(original)+"\n");
 write(prefix+".binding.json",JSON.stringify(binding)+"\n");
 C.saveNew(envelopeFile,C.make({planFile,bindingFile}));
 return {base,original,binding,planFile,bindingFile,envelopeFile,
  queryFile:p(prefix+".request.tsq"),responseFile:p(prefix+".response.tsr")};
}
function makeTsa(){
 run("req","-new","-x509","-newkey","rsa:2048",
  "-nodes","-days","2","-subj","/CN=LOCAL_TEST_ONLY_CA",
  "-keyout","ca.key","-out","ca.pem",
  "-addext","basicConstraints=critical,CA:TRUE",
  "-addext","keyUsage=critical,keyCertSign,cRLSign");
 run("req","-new","-newkey","rsa:2048","-nodes",
  "-subj","/CN=LOCAL_TEST_ONLY_TSA",
  "-keyout","tsa.key","-out","tsa.csr");
 write("tsa.ext","basicConstraints=critical,CA:FALSE\n"+
  "keyUsage=critical,digitalSignature\n"+
  "extendedKeyUsage=critical,timeStamping\n"+
  "subjectKeyIdentifier=hash\n"+
  "authorityKeyIdentifier=keyid,issuer\n");
 run("x509","-req","-in","tsa.csr","-CA","ca.pem",
  "-CAkey","ca.key","-CAcreateserial","-days","2",
  "-out","tsa.pem","-extfile","tsa.ext");
 write("tsa.serial","01\n");
 write("tsa.cnf","[tsa]\ndefault_tsa = tsa_config1\n"+
  "[tsa_config1]\nserial = tsa.serial\ncrypto_device = builtin\n"+
  "signer_cert = tsa.pem\ncerts = ca.pem\nsigner_key = tsa.key\n"+
  "signer_digest = sha256\ndefault_policy = 1.2.3.4\n"+
  "digests = sha256\naccuracy = secs:1\nordering = yes\n"+
  "tsa_name = yes\ness_cert_id_chain = yes\n");
 return {caPemFile:p("ca.pem"),untrustedSignerFile:p("tsa.pem"),
  pinnedCaFileSha256:sha(fs.readFileSync(p("ca.pem")))};
}
function timestamp(e){
 run("ts","-query","-data",e.envelopeFile,"-sha256","-cert",
  "-out",e.queryFile);
 run("ts","-reply","-config","tsa.cnf","-queryfile",e.queryFile,
  "-out",e.responseFile);
 return e;
}
function verify(e){
 return C.verifyTimestamp({envelopeFile:e.envelopeFile,
  planFile:e.planFile,bindingFile:e.bindingFile,
  queryFile:e.queryFile,responseFile:e.responseFile,
  ...authority,now:Date.now()+10000});
}
let authority,valid;
test.before(()=>{
 authority=makeTsa();
 valid=timestamp(fixture({prefix:"valid"}));
});
test.after(()=>fs.rmSync(temp,{recursive:true,force:true}));
test("C34 verifies real RFC3161 signature, nonce, and exact envelope",()=>{
 const result=verify(valid);
 A.equal(result.requestNonceAndEnvelopeMessageImprintCryptographicallyVerified,true);
 A.equal(result.timestampBeforeFrozenStartMinus72Hours,true);
 A.equal(result.originalRegisteredAtAndWindowChecks,true);
 A.equal(result.tsaSignerAndTrustRootIndependentlyVetted,false);
 A.equal(result.independentlyAuditedPreregistration,false);
 A.equal(result.paperOrLiveOrdersAllowed,false);
 A.equal(result.financialGO,false);
 A.equal(result.N9S,"NO_GO");
});
test("C34 envelope freezes all eight arms and actual source module identities",()=>{
 const obj=C.verifyEnvelope({envelopeFile:valid.envelopeFile,
  planFile:valid.planFile,bindingFile:valid.bindingFile});
 A.equal(obj.originalEightArmOrder.length,8);
 A.equal(obj.originalStartingCapitalUsd,20000);
 A.equal(obj.originalDailyHurdleBps,1);
 A.equal(obj.originalFamilywiseAlpha,.025);
 A.equal(obj.c22OriginalSixPolicyIdentityNotRetroactivelyProven,true);
 A.equal(obj.originalFinalM10AccountsSealed,3200);
 A.ok(Object.keys(obj.sourceCodeSha256).length>=8);
});
test("C34 rejects changed exact plan bytes even with unchanged JSON meaning",()=>{
 const original=fs.readFileSync(valid.planFile,"utf8");
 fs.appendFileSync(valid.planFile," ");
 try{
  A.throws(()=>C.verifyEnvelope({envelopeFile:valid.envelopeFile,
   planFile:valid.planFile,bindingFile:valid.bindingFile}),
   /C34_ENVELOPE_EXACT_BYTES_PLAN_BINDING_OR_CODE_CHANGED/);
 }finally{fs.writeFileSync(valid.planFile,original);}
});
test("C34 rejects altered forward strategy definition",()=>{
 const original=fs.readFileSync(valid.bindingFile,"utf8");
 fs.appendFileSync(valid.bindingFile,"\n");
 try{
  A.throws(()=>C.verifyEnvelope({envelopeFile:valid.envelopeFile,
   planFile:valid.planFile,bindingFile:valid.bindingFile}),
   /C34_ENVELOPE_EXACT_BYTES_PLAN_BINDING_OR_CODE_CHANGED/);
 }finally{fs.writeFileSync(valid.bindingFile,original);}
});
test("C34 rejects a self-chosen root that differs from pinned hash",()=>{
 A.throws(()=>C.verifyTimestamp({
  envelopeFile:valid.envelopeFile,planFile:valid.planFile,
  bindingFile:valid.bindingFile,queryFile:valid.queryFile,
  responseFile:valid.responseFile,caPemFile:authority.caPemFile,
  untrustedSignerFile:authority.untrustedSignerFile,
  pinnedCaFileSha256:"0".repeat(64),now:Date.now()+10000}),
  /C34_PINNED_CA_BYTES_MISMATCH/);
});
test("C34 rejects altered actual TSA response signature bytes",()=>{
 const out=p("altered.tsr"),raw=fs.readFileSync(valid.responseFile);
 const changed=Buffer.from(raw);changed[changed.length-40]^=1;
 fs.writeFileSync(out,changed);
 A.throws(()=>C.verifyTimestamp({
  envelopeFile:valid.envelopeFile,planFile:valid.planFile,
  bindingFile:valid.bindingFile,queryFile:valid.queryFile,
  responseFile:out,...authority,now:Date.now()+10000}),
  /C34_OPENSSL_RFC3161_VERIFICATION_FAILED/);
});
test("C34 rejects a different RFC3161 request nonce against valid response",()=>{
 const other=p("other-nonce.tsq");
 run("ts","-query","-data",valid.envelopeFile,"-sha256","-cert","-out",other);
 A.throws(()=>C.verifyTimestamp({
  envelopeFile:valid.envelopeFile,planFile:valid.planFile,
  bindingFile:valid.bindingFile,queryFile:other,
  responseFile:valid.responseFile,...authority,now:Date.now()+10000}),
  /C34_OPENSSL_RFC3161_VERIFICATION_FAILED/);
});
test("C34 denies timestamp obtained too late for frozen start minus 72 h",()=>{
 const late=timestamp(fixture({prefix:"too-late",
  registerDelta:-10*24*HOUR,proposedDelta:-11*24*HOUR,
  startDelta:36*HOUR}));
 A.throws(()=>verify(late),/C34_TSA_TIME_NOT_BEFORE_72H_CUTOFF/);
});
test("C34 rejects local files with readable private permissions",()=>{
 const st=fs.statSync(valid.planFile).mode&0o777;
 fs.chmodSync(valid.planFile,0o644);
 try{A.throws(()=>C.make({planFile:valid.planFile,
  bindingFile:valid.bindingFile}),/C34_FILE_INTEGRITY_AND_PRIVATE_PERMISSIONS/);}
 finally{fs.chmodSync(valid.planFile,st);}
});
test("C34 never treats a synthetic self-signed local CA as an independently vetted third party",()=>{
 const v=verify(valid);
 A.equal(v.tsaSignerAndTrustRootIndependentlyVetted,false);
 A.equal(v.originalBrokerAccountAuthenticated,false);
 A.equal(v.sixFrozenC22StrategiesRetrospectivelyEquivalent,false);
 A.equal(v.canPromoteToN9,false);
});
