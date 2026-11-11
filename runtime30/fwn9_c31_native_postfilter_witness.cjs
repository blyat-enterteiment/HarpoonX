"use strict";
/**
 * C31: passive witness of ORIGINAL runtime30/Plugins.evaluate calls.
 * It invokes neither evaluate nor any broker method by itself. Attaching does
 * not create entries, signals, market seeds, orders or a runtime scheduler.
 * A returned signal is POSTFILTER, NOT a C22 pre-filter policy evaluation.
 */
const assert=require("node:assert/strict");
const crypto=require("node:crypto");
const fs=require("node:fs");
const path=require("node:path");
const {Plugins}=require("./plugins.js");
const C27=require("./fwn9_c27_prebar_state.cjs");
const C28=require("./fwn9_c28_source_obligations.cjs");
const SCHEMA="HARPOON_FWN9_C31_NATIVE_POSTFILTER_CALL_WITNESS_1";
const BOOKS=new Set(["equity","etf","crypto","options"]);
function need(x,k){assert.ok(x,"C31W_"+k);}
function safeTime(x){need(Number.isSafeInteger(x)&&x>=0,"CLOCK");return x;}
function h(x){return crypto.createHash("sha256").update(x).digest("hex");}
function sourceFingerprint(){
 return {
  runtimeFileSha256:h(fs.readFileSync(path.join(__dirname,"plugins.js"))),
  nativeEvaluateBodySha256:h(Plugins.prototype.evaluate.toString()),
  sourceAuthenticityExternallyAttested:false
 };
}
function inspectLineage(plugins){
 need(plugins&&Object.getPrototypeOf(plugins)===Plugins.prototype&&
  plugins.evaluate===Plugins.prototype.evaluate,"ORIGINAL_NATIVE_METHOD_REQUIRED");
 need(Array.isArray(plugins.catalog)&&Array.isArray(plugins.cfg?.universe),
  "NATIVE_CATALOG_AND_UNIVERSE");
 const ids=plugins.catalog.map(p=>p.id);
 need(ids.every(s=>typeof s==="string"&&s.length>0)&&
  new Set(ids).size===ids.length,"NATIVE_PLUGIN_IDENTITY");
 const families=C28.EXPECTED.map(row=>({
  frozenPolicyId:row.policy,book:[...row.book],window:row.window,
  matchingNativeCatalogIds:plugins.catalog.filter(p=>row.book.includes(p.book)).map(p=>p.id).sort(),
  exactOneToOneNativePolicyBindingCertified:false,
  originalNativePrefilterSiteInstrumented:false,
  executionPolicyCertified:false
 }));
 return {
  schema:"HARPOON_FWN9_C31_NATIVE_POLICY_LINEAGE_AUDIT_1",
  catalogSize:ids.length,frozenC22Policies:families,
  sourceFingerprint:sourceFingerprint(),
  variantIdsAreNativePluginIds:
    C28.EXPECTED.every(row=>ids.includes(row.policy)),
  sixVariantNativePrefilterProved:false,
  originalSelectionUnchanged:true,
  finalFinancialGO:false,N9S:"NO_GO"
 };
}
function attach(plugins,{sink,clock=Date.now}={}){
 need(plugins&&Object.getPrototypeOf(plugins)===Plugins.prototype&&
  plugins.evaluate===Plugins.prototype.evaluate,
  "ORIGINAL_PROTOTYPE_UNWRAPPED_REQUIRED");
 need(typeof sink==="function"&&typeof clock==="function",
  "DURABLE_OBSERVER_AND_CLOCK_REQUIRED");
 need(Array.isArray(plugins.catalog)&&Array.isArray(plugins.cfg?.universe),
  "SOURCE_CATALOG_REQUIRED");
 const original=plugins.evaluate,fp=sourceFingerprint();
 // A checksum of the module is a LOCAL identification, not a remote signature.
 const wrapped=function(...args){
  need(this===plugins,"INSTANCE_BOUND");
  const [book,market,enabled,asof]=args;
  need(BOOKS.has(book)&&market&&typeof market==="object"&&
   Array.isArray(enabled)&&
   enabled.every(p=>typeof p==="string")&&
   (asof===undefined||Number.isSafeInteger(asof)),
   "ORIGINAL_CALL_ARGUMENTS");
  const started=safeTime(clock());
  let result,errorName=null,nativeError=null;
  try{result=original.apply(this,args);}
  catch(error){nativeError=error;errorName=error?.name??"Error";}
  const finished=safeTime(clock());
  need(finished>=started,"CLOCK_REGRESSION");
  need(asof===undefined||asof<=finished,"FUTURE_ASOF");
  if(!errorName)need(Array.isArray(result),"ORIGINAL_RESULT_ARRAY");
  const idRows=[];
  if(!errorName){
   for(const signal of result){
    need(signal&&typeof signal.plugin==="string"&&
     typeof signal.symbol==="string"&&
     signal.plugin.length>0&&signal.symbol.length>0,
     "NATIVE_SIGNAL_IDENTITY");
    idRows.push(signal.plugin+"|"+signal.symbol);
   }
   need(new Set(idRows).size===idRows.length,
    "NATIVE_OUTPUT_DUPLICATED");
  }
  const selected=plugins.catalog.filter(p=>p.book===book&&enabled.includes(p.id))
   .map(p=>p.id).sort();
  const digest=C27.digest({
   nativeBook:book,selectedPluginIds:selected,
   sourceUniverse:plugins.cfg.universe.filter(x=>x.book===book).map(x=>x.symbol).sort()
  });
  const record={
   schema:SCHEMA,sourcePhase:"NATIVE_POSTFILTER_METHOD_RETURN",
   sourceMethod:"Plugins.prototype.evaluate",
   pluginSourceFileSha256:fp.runtimeFileSha256,
   originalMethodSha256:fp.nativeEvaluateBodySha256,
   startedAt:started,finishedAt:finished,
   callAsOf:asof??null,book,
   selectedNativePluginIds:selected,
   sourceInputScopeSha256:digest,
   outputCount:idRows.length,
   emittedNativeIds:idRows,
   resultStatus:errorName?"THREW":"RETURNED",
   errorType:errorName,
   nativeMethodCalledExactlyOnceByWrapper:true,
   allNativeEvaluatorInternalPrefiltersInstrumented:false,
   c22SixFrozenPrefilterEvaluationsProved:false,
   sourceProviderAuthenticityIndependentlyVerified:false,
   financialOrdersAuthorized:false,N9S:"NO_GO"
  };
  // The sink failure aborts any downstream handling of the result (fail closed).
  sink(record);
  if(errorName){
   // Original throw is preserved (exact object) rather than replaced by a
   // fabricated successfully evaluated source record.
   throw nativeError;
  }
  return result;
 };
 // The captured exception is needed after persisting the failure witness.
 // Reassign implementation atomically: defined below in the replacement body.
 plugins.evaluate=wrapped;
 return ()=>{need(plugins.evaluate===wrapped,"WITNESS_REPLACED");
  plugins.evaluate=original;};
}
module.exports={SCHEMA,sourceFingerprint,inspectLineage,attach};
