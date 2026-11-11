"use strict";
/**
 * C32 forward-only, versioned WINDOWED-NATIVE-SOURCE identity.
 * This DEFINES a new prospective composite policy (native enabled plugin set
 * restricted by a C22 clock window). It does NOT retroactively prove the six
 * old C22 strategy identities, and NEVER authorizes broker execution.
 */
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const C27=require("./fwn9_c27_prebar_state.cjs");
const C28=require("./fwn9_c28_source_obligations.cjs");
const W=require("./fwn9_c32_native_prefilter_gate.cjs");
const SCHEMA="HARPOON_FWN9_C32_FUTURE_WINDOWED_NATIVE_BINDING_1";
function need(v,k){assert.ok(v,"C32B_"+k);}
function sha(content){return C27.digest(content);}
function pathHash(name){return require("node:crypto").createHash("sha256")
 .update(fs.readFileSync(path.join(__dirname,name))).digest("hex");}
function freeze({plugins,enabledPluginIds,registeredUniverse,
 calendarSha256,proposedAt}={}){
 W.originalMethodIdentity(plugins);
 need(Array.isArray(enabledPluginIds)&&enabledPluginIds.length>0&&
  new Set(enabledPluginIds).size===enabledPluginIds.length&&
  enabledPluginIds.every(v=>typeof v==="string"&&v.length>0)&&
  Array.isArray(registeredUniverse)&&registeredUniverse.length>0&&
  Number.isSafeInteger(proposedAt)&&proposedAt>0&&
  typeof calendarSha256==="string"&&/^[a-f0-9]{64}$/.test(calendarSha256),
  "SOURCE_AND_FIXED_REGISTRY");
 const universe=C28.reg(registeredUniverse);
 need(sha(universe)===sha(C28.reg(plugins.cfg.universe)),
  "ORIGINAL_SOURCE_UNIVERSE_MUST_MATCH");
 const available=new Map();
 for(const p of plugins.catalog){
  need(p&&typeof p.id==="string"&&p.id.length>0&&
   typeof p.book==="string"&&typeof p.family==="string"&&
   !available.has(p.id),"CATALOG_IDENTITY_UNIQUE");
  available.set(p.id,p);
 }
 const enabled=enabledPluginIds.map(id=>{
  const p=available.get(id);
  need(p&&["equity","etf","crypto","options"].includes(p.book),
   "ENABLED_PLUGIN_MUST_EXIST_NATIVE");
  return {id:p.id,book:p.book,family:p.family,
   version:p.version??"UNVERSIONED",paramsDigest:sha(p.params??{})};
 }).sort((a,b)=>a.id.localeCompare(b.id));
 const groups=C28.EXPECTED.map(v=>{
  const nativePluginsByBook=Object.fromEntries(v.book.map(book=>{
   const ids=enabled.filter(p=>p.book===book).map(p=>p.id);
   need(ids.length>0,"MISSING_ENABLED_NATIVE_PLUGIN_FOR_"+book);
   return [book,ids];
  }));
  need(universe.some(a=>v.book.includes(a.book)),
   "MISSING_ASSETS_FOR_WINDOW");
  return {frozenWindowId:v.policy,window:v.window,
   books:[...v.book],nativePluginsByBook,
   versionedSemantics:"ALL_ENABLED_NATIVE_PLUGINS_WITH_C22_CLOCK_GATE",
   originalC22StrategyIdentityRetrospectivelyProved:false,
   brokerExecutorCertified:false};
 });
 const core={
  schema:SCHEMA,proposedAt,sourceType:"NEW_PROSPECTIVE_POLICY_DEFINITION",
  nativeOriginalCodeSha256:W.sourceHash(),
  nativePolicyCodeSha256:pathHash("policy.js"),
  nativeExitCodeSha256:pathHash("exits.js"),
  nativeCoordinatorCodeSha256:pathHash("coordinator.js"),
  c22WindowImplementationSha256:pathHash("fwn9_c22_session_compound.cjs"),
  c28ObligationImplementationSha256:pathHash("fwn9_c28_source_obligations.cjs"),
  universeDigest:sha(universe),calendarSha256,enabledNativeCatalog:enabled,
  sixProspectiveWindowBindings:groups,
  controls:["ORIGINAL_BASELINE","CASH"],
  originalC22StrategyEquivalent:false,
  independentPreOutcomeRegistration:false,
  privateBrokerReceiptsAuthenticated:false,
  nativeOptionContractExecutionCertified:false,
  financialGO:false,N9S:"NO_GO"
 };
 return {...core,definitionSha256:sha(core)};
}
function validate(definition){
 need(definition?.schema===SCHEMA&&
  typeof definition.definitionSha256==="string",
  "BINDING_MANIFEST_SCHEMA");
 const body={...definition};delete body.definitionSha256;
 need(sha(body)===definition.definitionSha256&&
  body.nativeOriginalCodeSha256===W.sourceHash()&&
  body.nativePolicyCodeSha256===pathHash("policy.js")&&
  body.nativeExitCodeSha256===pathHash("exits.js")&&
  body.nativeCoordinatorCodeSha256===pathHash("coordinator.js")&&
  body.c22WindowImplementationSha256===pathHash("fwn9_c22_session_compound.cjs")&&
  body.c28ObligationImplementationSha256===pathHash("fwn9_c28_source_obligations.cjs"),
  "SOURCE_BINARY_DIGEST_CHANGED");
 need(body.sixProspectiveWindowBindings.length===6&&
  body.sixProspectiveWindowBindings.every((v,i)=>
   v.frozenWindowId===C28.EXPECTED[i].policy&&
   v.window===C28.EXPECTED[i].window&&
   v.originalC22StrategyIdentityRetrospectivelyProved===false&&
   v.brokerExecutorCertified===false)&&
  body.originalC22StrategyEquivalent===false&&
  body.independentPreOutcomeRegistration===false&&
  body.privateBrokerReceiptsAuthenticated===false&&
  body.nativeOptionContractExecutionCertified===false&&
  body.financialGO===false&&body.N9S==="NO_GO",
  "RESEARCH_ONLY_NO_PROMOTION");
 return true;
}
function link({definition,callAudit}={}){
 validate(definition);
 need(callAudit?.schema==="HARPOON_FWN9_C32_NATIVE_TO_C22_CAUSAL_LINEAGE_AUDIT_1"&&
  callAudit.sourceFileSha256===definition.nativeOriginalCodeSha256&&
  callAudit.sourceUniverseDigest===definition.universeDigest&&
  callAudit.nativePairScopeComplete===true&&
  Array.isArray(callAudit.conditionalWindowProjections),
  "VERIFIED_NATIVE_SCOPE_REQUIRED");
 const expected=definition.enabledNativeCatalog.filter(p=>p.book===callAudit.book)
  .map(p=>p.id).sort();
 need(Array.isArray(callAudit.selectedNativePluginIds)&&
  JSON.stringify(expected)===JSON.stringify(callAudit.selectedNativePluginIds),
  "NATIVE_ENABLED_SET_MISMATCH");
 const records=[];
 for(const item of callAudit.conditionalWindowProjections){
  need(item.deterministicResearchWindowProjection===true&&
   Array.isArray(item.candidateFrozenWindowPolicies)&&
   item.candidateFrozenWindowPolicies.length<=1,
   "NONDETERMINISTIC_WINDOW");
  if(!item.candidateFrozenWindowPolicies.length){
   records.push({nativePluginId:item.nativePluginId,symbol:item.symbol,
    matchedWindow:null,status:"OUTSIDE_FROZEN_WINDOW_NO_POLICY_FILL"});
   continue;
  }
  const id=item.candidateFrozenWindowPolicies[0];
  const bind=definition.sixProspectiveWindowBindings.find(v=>v.frozenWindowId===id);
  need(bind&&bind.books.includes(item.nativeBook)&&
   bind.nativePluginsByBook[item.nativeBook]?.includes(item.nativePluginId),
   "NATIVE_PLUGIN_NOT_IN_FROZEN_FORWARD_DEFINITION");
  records.push({nativePluginId:item.nativePluginId,symbol:item.symbol,
   matchedWindow:id,status:"FORWARD_ONLY_WINDOWED_NATIVE_SOURCE_BOUND"});
 }
 return {
  schema:"HARPOON_FWN9_C32_FORWARD_NATIVE_WINDOW_SOURCE_LINK_1",
  definitionSha256:definition.definitionSha256,
  sourceFileSha256:definition.nativeOriginalCodeSha256,
  nativeSourcePairs:records.length,records,
  newCompositeSourceDefinitionLocallyDeterministic:true,
  existingC22SixStrategiesSemanticallyEquivalent:false,
  historicalResultsReclassifiable:false,
  brokerFillsOrPaperOrdersAllowed:false,
  registrationExternallyAnchored:false,
  financialGO:false,N9S:"NO_GO"
 };
}
module.exports={SCHEMA,freeze,validate,link};
