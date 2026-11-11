"use strict";
/**
 * C32 observer: records actual ORIGINAL native source-site hooks BEFORE
 * quote/feature/underlying filters. Never invokes strategy, order, broker,
 * scheduler, or market API. Source-site existence != C22 semantic identity.
 */
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const crypto=require("node:crypto");
const {Plugins}=require("./plugins.js");
const C27=require("./fwn9_c27_prebar_state.cjs");
const C22=require("./fwn9_c22_session_compound.cjs");
const C28=require("./fwn9_c28_source_obligations.cjs");
const SITES=new Set(["EVALUATE_SOURCE_BEFORE_FEATURES","FEATURE_PRE_QUOTE",
 "NATIVE_PAIR_PRE_QUOTE","OPTIONS_UNDERLYING_PRE_FILTERS"]);
const BOOKS=new Set(["equity","etf","crypto","options"]);
const SCHEMA="HARPOON_FWN9_C32_ORIGINAL_PREFILTER_SOURCE_WITNESS_1";
function need(x,code){assert.ok(x,"C32_"+code);}
function digest(x){return crypto.createHash("sha256").update(x).digest("hex");}
function sourceHash(){return digest(fs.readFileSync(path.join(__dirname,"plugins.js")));}
function originalMethodIdentity(plugins){
 need(plugins&&Object.getPrototypeOf(plugins)===Plugins.prototype&&
  plugins.evaluate===Plugins.prototype.evaluate&&
  plugins.features===Plugins.prototype.features&&
  plugins.options===Plugins.prototype.options,"ORIGINAL_NATIVE_METHODS");
 need(Plugins.prototype.evaluate.toString().includes("NATIVE_PAIR_PRE_QUOTE")&&
  Plugins.prototype.evaluate.toString().includes("EVALUATE_SOURCE_BEFORE_FEATURES")&&
  Plugins.prototype.features.toString().includes("FEATURE_PRE_QUOTE")&&
  Plugins.prototype.options.toString().includes("OPTIONS_UNDERLYING_PRE_FILTERS"),
  "PREFILTER_HOOKS_MISSING");
 need(Array.isArray(plugins.cfg?.universe)&&
  Array.isArray(plugins.cfg?.optionUnderlyings)&&
  Array.isArray(plugins.catalog),"SOURCE_REGISTRY");
 return sourceHash();
}
function attach(plugins,{sink,clock=Date.now}={}){
 const hash=originalMethodIdentity(plugins);
 need(plugins.c32PrefilterTap===undefined&&
  typeof sink==="function"&&typeof clock==="function",
  "NO_HOOK_OVERWRITE_AND_SINK_REQUIRED");
 let ordinal=0,last=-1;
 const hook=event=>{
  need(event&&SITES.has(event.site)&&BOOKS.has(event.book)&&
   Number.isSafeInteger(event.asOf)&&event.asOf>=0,
   "NATIVE_SOURCE_SITE");
  need((event.pluginId===null||
    (typeof event.pluginId==="string"&&event.pluginId.length>0))&&
   (event.symbol===null||
    (typeof event.symbol==="string"&&event.symbol.length>0)),
   "NATIVE_ID");
  const knownAt=clock();
  need(Number.isSafeInteger(knownAt)&&knownAt>=last&&
   knownAt>=event.asOf-2000,"RECEIPT_CLOCK_NOT_CAUSAL");
  last=knownAt;
  const row=Object.freeze({
   schema:SCHEMA,sequence:++ordinal,
   source:"ORIGINAL_PLUGINS_SOURCE_SITE",sourceFileSha256:hash,
   site:event.site,book:event.book,pluginId:event.pluginId,
   symbol:event.symbol,sourceAsOf:event.asOf,localRecordedAt:knownAt,
   sourceInvocationObserved:true,sourceProviderExternallyAuthenticated:false,
   sourceKnownBeforeRegisteredBarProved:false,
   c22FrozenStrategyIdentityProved:false,
   brokerFillObserved:false,paperOrLiveOrderAuthorized:false,
   N9S:"NO_GO"
  });
  sink(row); // Any disk failure propagates BEFORE passing this source filter.
 };
 Object.defineProperty(plugins,"c32PrefilterTap",{
  value:hook,writable:false,configurable:true,enumerable:false
 });
 return ()=>{
  need(plugins.c32PrefilterTap===hook,"WITNESS_REPLACED");
  delete plugins.c32PrefilterTap;
 };
}
function auditCall({rows,book,asOf,selectedPlugins,universe,optionUnderlyings=[],
 calendar=[]}={}){
 need(Array.isArray(rows)&&rows.length>0&&BOOKS.has(book)&&
  Number.isSafeInteger(asOf)&&asOf>=0&&
  Array.isArray(selectedPlugins)&&new Set(selectedPlugins).size===selectedPlugins.length&&
  Array.isArray(universe)&&Array.isArray(optionUnderlyings)&&
  Array.isArray(calendar),"RECORDS_AND_CONTEXT");
 need(selectedPlugins.every(p=>p&&typeof p.id==="string"&&p.book===book)&&
  universe.every(a=>a&&typeof a.symbol==="string"&&BOOKS.has(a.book))&&
  new Set(universe.map(a=>a.symbol)).size===universe.length,
  "SELECTED_NATIVE_CATALOG");
 const actualCodeSha=sourceHash();
 need(rows.every(r=>r&&r.source==="ORIGINAL_PLUGINS_SOURCE_SITE"&&
  r.sourceFileSha256===actualCodeSha&&
  r.sourceInvocationObserved===true&&
  r.sourceKnownBeforeRegisteredBarProved===false&&
  r.brokerFillObserved===false),"SOURCE_ORIGINAL_CODE_AND_NOT_FINANCIAL_EVIDENCE");
 const scope=rows.filter(r=>r.site==="EVALUATE_SOURCE_BEFORE_FEATURES");
 need(scope.length===1&&rows[0]===scope[0]&&
  scope[0].pluginId===null&&scope[0].symbol===null,
  "ORIGINAL_SOURCE_SCOPE_FIRST");
 const expected=selectedPlugins.flatMap(p=>
  universe.filter(a=>a.book===book).map(a=>p.id+"|"+a.symbol));
 const actualPairs=rows.filter(r=>r.site==="NATIVE_PAIR_PRE_QUOTE")
  .map(r=>r.pluginId+"|"+r.symbol);
 const expectedSet=new Set(expected),actualSet=new Set(actualPairs);
 const optionExpected=book==="options"?
  selectedPlugins.flatMap(p=>optionUnderlyings.map(s=>p.id+"|"+s)):[];
 const optionActual=rows.filter(r=>r.site==="OPTIONS_UNDERLYING_PRE_FILTERS")
  .map(r=>r.pluginId+"|"+r.symbol);
 const featureExpected=universe.filter(a=>a.book!=="crypto").map(a=>a.symbol);
 const featureActual=rows.filter(r=>r.site==="FEATURE_PRE_QUOTE")
  .map(r=>r.symbol);
 const same=(a,b)=>a.length===b.length&&
   new Set(a).size===a.length&&new Set(b).size===b.length&&
   a.every(x=>new Set(b).has(x));
 // Native options() can call features() again only after its underlying
 // gates succeed. Its zero-or-more complete passes are not contract fills.
 const featureRounds=book==="options"&&featureExpected.length>0?
  featureActual.length/featureExpected.length:
  (book==="equity"||book==="etf")?1:0;
 const featureComplete=Number.isInteger(featureRounds)&&
  featureActual.length===featureRounds*featureExpected.length&&
  Array.from({length:featureRounds},(_,i)=>
   same(featureExpected,featureActual.slice(i*featureExpected.length,
    (i+1)*featureExpected.length))).every(Boolean);
 const siteComplete=same(expected,actualPairs)&&
  same(optionExpected,optionActual)&&featureComplete;
 let prior=0,consistent=true;
 for(const [i,r] of rows.entries()){
  if(!r||r.schema!==SCHEMA||r.book!==book&&
    r.site!=="FEATURE_PRE_QUOTE"||r.sourceAsOf!==asOf||
    r.sequence!==i+1||r.localRecordedAt<prior||
    r.sourceProviderExternallyAuthenticated!==false||
    r.c22FrozenStrategyIdentityProved!==false||
    r.paperOrLiveOrderAuthorized!==false||r.N9S!=="NO_GO")consistent=false;
  if(i>0&&r.sourceFileSha256!==rows[0].sourceFileSha256)consistent=false;
  prior=r?.localRecordedAt??0;
 }
 need(consistent,"SOURCE_CLOCK_SCHEMA_AND_FINGERPRINT");
 const projections=[];
 for(const r of rows.filter(r=>r.site==="NATIVE_PAIR_PRE_QUOTE")){
  const asset=universe.find(a=>a.symbol===r.symbol&&a.book===r.book);
  const window=C22.windowFor({book:r.book,at:asOf,calendar,
   venueOpen:asset?.venueOpen,contractSessionVerified:asset?.contractSessionVerified});
  const candidate=C28.EXPECTED.filter(v=>v.book.includes(r.book)&&
    window.eligible&&v.window===window.window);
  projections.push({nativePluginId:r.pluginId,symbol:r.symbol,
   nativeBook:r.book,window:window.window??null,
   candidateFrozenWindowPolicies:candidate.map(v=>v.policy),
   deterministicResearchWindowProjection:candidate.length<=1,
   semanticallyEquivalentToFrozenC22Strategy:false});
 }
 return {
  schema:"HARPOON_FWN9_C32_NATIVE_TO_C22_CAUSAL_LINEAGE_AUDIT_1",
  book,sourceAsOf:asOf,
  sourceUniverseDigest:C27.digest(C28.reg(universe)),
  selectedNativePluginIds:selectedPlugins.map(p=>p.id).sort(),
  sourceFileSha256:rows[0].sourceFileSha256,
  nativeScopeObserved:true,
  expectedNativePrefilterPairs:expected.length,observedNativePrefilterPairs:actualPairs.length,
  nativePairScopeComplete:siteComplete,
  missingNativePairs:expected.filter(x=>!actualSet.has(x)),
  unexpectedNativePairs:actualPairs.filter(x=>!expectedSet.has(x)),
  nativeOptionUnderlyingScopeComplete:same(optionExpected,optionActual),
  nativeSourceFeaturePassesObserved:featureRounds,
  optionsEvaluatedPerContract:false,
  conditionalWindowProjections:projections,
  c28FrozenSixPolicyIdentityAndExecutionEquivalent:false,
  sourceCapturedPriorToFutureBarVerified:false,
  independentBrokerAndClockAuthentication:false,
  actualProspectiveSourceExperimentStarted:false,
  originalM10Sealed:3200,financialGO:false,N9S:"NO_GO"
 };
}
function auditNextBar({callAudit,rows,nextBarStart}={}){
 need(callAudit?.schema==="HARPOON_FWN9_C32_NATIVE_TO_C22_CAUSAL_LINEAGE_AUDIT_1"&&
  callAudit.nativePairScopeComplete===true&&
  Array.isArray(rows)&&rows.length>0&&
  Number.isSafeInteger(nextBarStart)&&nextBarStart>0,
  "COMPLETE_NATIVE_SOURCE_AND_NEXT_BAR_REQUIRED");
 need(rows.every(r=>r?.schema===SCHEMA&&
  r.sourceFileSha256===callAudit.sourceFileSha256&&
  Number.isSafeInteger(r.sourceAsOf)&&r.sourceAsOf<=nextBarStart&&
  Number.isSafeInteger(r.localRecordedAt)&&
  r.localRecordedAt<=nextBarStart),
  "NATIVE_SOURCE_CAPTURE_AFTER_BAR_START");
 return {
  schema:"HARPOON_FWN9_C32_SOURCE_TIMING_BEFORE_NEXT_BAR_1",
  nativeOriginalPreFilterSitesRecorded:true,
  localSourceKnownBeforeNextBar:true,
  nextBarStart,
  clockSource:"LOCAL_SYSTEM_CLOCK_NOT_INDEPENDENT_TIME_AUTHORITY",
  originalC27FundingPositionStateCaptured:false,
  c28SixOriginalPolicySemanticParityCertified:false,
  thirdPartyTimeOrMarketAuthenticated:false,
  brokerOrderOrFillAuthenticated:false,
  financialGO:false,N9S:"NO_GO"
 };
}
module.exports={SCHEMA,sourceHash,originalMethodIdentity,attach,auditCall,auditNextBar};
