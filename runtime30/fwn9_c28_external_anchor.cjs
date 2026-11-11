"use strict";
/** Optional ED25519 external integrity anchor for C27+C28 chain heads.
 * Verifies a pinned public key signature, not real exchange/BBO/broker origin.
 * Signing keys belong to independent custodian and are never used/loaded here.
 * The date inside a signature is NOT a trusted timestamp authority receipt.
 */
const A=require("node:assert/strict");
const crypto=require("node:crypto");
const C27=require("./fwn9_c27_prebar_state.cjs");
const J=require("./fwn9_c27_prebar_journal.cjs");
const T=require("./fwn9_c28_source_tap_archive.cjs");
const SCHEMA="HARPOON_FWN9_C28_EXTERNAL_ED25519_CHAIN_ANCHOR_1";
function need(ok,c){A.ok(ok,"C28K_"+c);}
function fingerprint(pem){
 const pub=crypto.createPublicKey(pem);
 need(pub.asymmetricKeyType==="ed25519","ED25519_PUBLIC_KEY_ONLY");
 return crypto.createHash("sha256").update(
  pub.export({type:"spki",format:"der"})).digest("hex");
}
function verifyAnchor({c27Dir,tapDir,anchor,publicKeyPem,
  pinnedKeyFingerprint,now=Date.now()}={}){
 need(anchor&&anchor.schema===SCHEMA&&
  anchor.scope==="INTEGRITY_SIGNATURE_NOT_FINANCIAL_ATTESTATION"&&
  typeof anchor.issuer==="string"&&anchor.issuer.length>0&&
  anchor.issuer.length<=200,"ANCHOR_CONTRACT");
 const expected=fingerprint(publicKeyPem);
 need(typeof pinnedKeyFingerprint==="string"&&
  pinnedKeyFingerprint===expected,"PINNED_PUBLIC_KEY_FINGERPRINT");
 const a=J.verifyJournal(c27Dir),b=T.verify(tapDir,c27Dir);
 need(a.coverageComplete===true&&
  b.fullBarsAndSourceTapsComplete===true,"FULL_SCHEDULE_REQUIRED");
 need(anchor.c27Head===a.finalizedEvidenceHead&&
  anchor.tapHead===b.verifiedTapChainHead&&
  anchor.c27ManifestSeal===a.manifest.seal&&
  anchor.barCount===a.verifiedFrames&&
  Number.isSafeInteger(anchor.anchoredAt)&&
  Number.isSafeInteger(now)&&anchor.anchoredAt>=a.manifest.expectedBars.at(-1)&&
  anchor.anchoredAt<=now,"ANCHOR_SOURCE_HEAD_OR_CLOCK");
 need(typeof anchor.signature==="string"&&
  /^[A-Za-z0-9+/]+={0,2}$/.test(anchor.signature)&&
  anchor.signature.length<=256,"ANCHOR_SIGNATURE_ENCODING");
 const payload={...anchor};delete payload.signature;
 const raw=Buffer.from(C27.digest(payload),"utf8");
 let okay=false;
 try{
  okay=crypto.verify(null,raw,crypto.createPublicKey(publicKeyPem),
   Buffer.from(anchor.signature,"base64"));
 }catch(e){okay=false;}
 need(okay,"ED25519_SIGNATURE_INVALID");
 return {schema:"HARPOON_FWN9_C28_EXTERNAL_SIGNATURE_VERIFICATION_1",
  pinnedPublicKeyFingerprint:expected,
  signedC27Head:a.finalizedEvidenceHead,
  signedTapHead:b.verifiedTapChainHead,
  signatureMatchesPinnedKey:true,
  signerIdentityIndependentlyVetted:false,
  signingTimeNotarizedIndependently:false,
  exchangeSourceAuthenticated:false,
  brokerFillReceiptsAuthenticated:false,
  fullSourceGeneratorMarketOpportunityCoverageProven:false,
  contentIntegritySinceTrustedIndependentSigningConditional:true,
  financialGO:false,N9S:"NO_GO",M10FinalSealed:3200};
}
module.exports={SCHEMA,fingerprint,verifyAnchor};
