"use strict";
/** Test-only ephemeral Ed25519 keypairs; NOT market RNG or account keys. */
const test=require("node:test"),A=require("node:assert/strict");
const crypto=require("node:crypto");
const fs=require("node:fs"),os=require("node:os"),path=require("node:path");
const C27=require("../runtime30/fwn9_c27_prebar_state.cjs");
const J=require("../runtime30/fwn9_c27_prebar_journal.cjs");
const S=require("../runtime30/fwn9_c28_source_obligations.cjs");
const T=require("../runtime30/fwn9_c28_source_tap_archive.cjs");
const K=require("../runtime30/fwn9_c28_external_anchor.cjs");
const F=require("./fwn9_c27_test_fixture.cjs");
const registry=[{symbol:"SYNA",book:"equity"},{symbol:"SYNB",book:"equity"}];
const t=F.BARS[0],calendar=[{date:new Date(t).toISOString().slice(0,10),
 open:t,close:t+78*300000}];
function taps(i){
 const inp=F.sample().frames[i],obs=inp.opportunityCoverage.outcomes;
 return S.obligations({barStart:inp.barStart,registry,calendar}).map(o=>
  S.makeTap({obligation:o,sourceCall:o.requiredEvaluation?()=>
   obs.filter(r=>r.policyId===o.policyId&&r.symbol===o.symbol)
    .map(r=>({id:r.id,policyId:r.policyId,symbol:r.symbol})):null,
   now:()=>inp.barStart-1000}));
}
function makeFixture(fn,{full=true}={}){
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),"c28ed25519-"));
 const c27=path.join(dir,"c27"),tapDir=path.join(dir,"taps");
 try{
  J.newJournal(c27,F.manifest());
  const source=F.sample();
  const n=full?3:1;
  for(let i=0;i<n;i++)J.append(c27,source.frames[i]);
  T.create(tapDir,{c27Dir:c27,registry,calendar});
  for(let i=0;i<n;i++)T.append(tapDir,c27,taps(i));
  const keys=crypto.generateKeyPairSync("ed25519");
  const pem=keys.publicKey.export({type:"spki",format:"pem"});
  const fingerprint=K.fingerprint(pem);
  const p=J.verifyJournal(c27),q=T.verify(tapDir,c27);
  const payload={schema:K.SCHEMA,
   scope:"INTEGRITY_SIGNATURE_NOT_FINANCIAL_ATTESTATION",
   issuer:"SYNTHETIC_TEST_EXTERNAL_SIGNER_NOT_PROVIDER",
   c27Head:p.finalizedEvidenceHead,
   tapHead:q.verifiedTapChainHead,
   c27ManifestSeal:p.manifest.seal,
   barCount:p.verifiedFrames,
   anchoredAt:Date.now()};
  const signature=crypto.sign(null,Buffer.from(C27.digest(payload),"utf8"),
   keys.privateKey).toString("base64");
  const anchor={...payload,signature};
  return fn({c27,tapDir,pem,fingerprint,anchor,keys});
 }finally{fs.rmSync(dir,{recursive:true,force:true});}
}
test("C28 ED25519 valid key-pinned complete chain signs bytes but NOT broker truth",()=>makeFixture(d=>{
 const r=K.verifyAnchor({c27Dir:d.c27,tapDir:d.tapDir,anchor:d.anchor,
  publicKeyPem:d.pem,pinnedKeyFingerprint:d.fingerprint});
 A.equal(r.signatureMatchesPinnedKey,true);
 A.equal(r.sourceGeneratorGlobalMarketOpportunityCoverageProven,undefined);
 A.equal(r.brokerFillReceiptsAuthenticated,false);
 A.equal(r.exchangeSourceAuthenticated,false);
 A.equal(r.signingTimeNotarizedIndependently,false);
 A.equal(r.signerIdentityIndependentlyVetted,false);
 A.equal(r.financialGO,false);
 A.equal(r.N9S,"NO_GO");
}));
test("C28 source anchor signature mutation is rejected despite same content heads",()=>makeFixture(d=>{
 const x=structuredClone(d.anchor);
 x.signature=x.signature.slice(0,-2)+(x.signature.at(-2)==="A"?"B":"A")+"=";
 A.throws(()=>K.verifyAnchor({c27Dir:d.c27,tapDir:d.tapDir,anchor:x,
  publicKeyPem:d.pem,pinnedKeyFingerprint:d.fingerprint}),
  /C28K_ED25519_SIGNATURE_INVALID|C28K_ANCHOR_SIGNATURE_ENCODING/);
}));
test("C28 externally pinned key fingerprint cannot be silently replaced",()=>makeFixture(d=>{
 A.throws(()=>K.verifyAnchor({c27Dir:d.c27,tapDir:d.tapDir,anchor:d.anchor,
  publicKeyPem:d.pem,pinnedKeyFingerprint:"0".repeat(64)}),
  /C28K_PINNED_PUBLIC_KEY_FINGERPRINT/);
}));
test("C28 signing key cannot be swapped without invalidating signature",()=>makeFixture(d=>{
 const fake=crypto.generateKeyPairSync("ed25519").publicKey.export({
  type:"spki",format:"pem"});
 A.throws(()=>K.verifyAnchor({c27Dir:d.c27,tapDir:d.tapDir,anchor:d.anchor,
  publicKeyPem:fake,pinnedKeyFingerprint:K.fingerprint(fake)}),
  /C28K_ED25519_SIGNATURE_INVALID/);
}));
test("C28 anchor may not claim clock timestamp after audit current wall-clock",()=>makeFixture(d=>{
 const x=structuredClone(d.anchor);x.anchoredAt=Date.now()+100000;
 A.throws(()=>K.verifyAnchor({c27Dir:d.c27,tapDir:d.tapDir,anchor:x,
  publicKeyPem:d.pem,pinnedKeyFingerprint:d.fingerprint}),
  /C28K_ANCHOR_SOURCE_HEAD_OR_CLOCK/);
}));
test("C28 incomplete C27 + source taps cannot be signed as final coverage",()=>makeFixture(d=>{
 A.throws(()=>K.verifyAnchor({c27Dir:d.c27,tapDir:d.tapDir,anchor:d.anchor,
  publicKeyPem:d.pem,pinnedKeyFingerprint:d.fingerprint}),
  /C28K_FULL_SCHEDULE_REQUIRED/);
},{full:false}));
test("C28 same signer cannot validate stale head after source chain changes",()=>makeFixture(d=>{
 const x=structuredClone(d.anchor);x.tapHead="f".repeat(64);
 A.throws(()=>K.verifyAnchor({c27Dir:d.c27,tapDir:d.tapDir,anchor:x,
  publicKeyPem:d.pem,pinnedKeyFingerprint:d.fingerprint}),
  /C28K_ANCHOR_SOURCE_HEAD_OR_CLOCK/);
}));
test("C28 unknown claimed broker/financial scope is refused before signature",()=>makeFixture(d=>{
 const x=structuredClone(d.anchor);
 x.scope="BROKER_FILL_AUTHENTICATION_AND_N9S_GO";
 A.throws(()=>K.verifyAnchor({c27Dir:d.c27,tapDir:d.tapDir,anchor:x,
  publicKeyPem:d.pem,pinnedKeyFingerprint:d.fingerprint}),
  /C28K_ANCHOR_CONTRACT/);
}));
