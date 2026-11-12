"use strict";
/**
 * C34 chronological late-activity census: C25's GET after/until activity
 * windows filter by record CREATION, not guaranteed trade/settlement date.
 * A later requery may reveal fees/fills unavailable at first closing NAV.
 * This validates a declared requery; it does not authenticate broker source
 * and never certifies final economic account closure from absent rows alone.
 */
const A=require("node:assert/strict");
const C25=require("./fwn9_c25_broker_export_ingest.cjs");
const {netLedgerDigest}=require("./net_accounting.js");
const SCHEMA="HARPOON_FWN9_C34_DELAYED_ACCOUNT_ACTIVITY_REQUERY_1";
function need(x,k){A.ok(x,"C34L_"+k);}
function time(x,k){
 need(typeof x==="string","ISO_"+k);
 const t=Date.parse(x);
 need(Number.isSafeInteger(t)&&t>0&&
  x.includes("T"),"ISO_"+k);
 return t;
}
function all(bundle){
 need(bundle?.activities&&Array.isArray(bundle.activities.pages)&&
  Number.isSafeInteger(bundle.activities.page_size),
  "PAGINATED_ACTIVITY_EXPORT");
 return C25.flattenPages(bundle.activities.pages,bundle.activities.page_size);
}
function inspect({initialBundle,requery}={}){
 const first=C25.certify(initialBundle);
 need(first.mode==="PAPER"&&requery&&requery.schema===SCHEMA&&
  requery.mode==="PAPER"&&requery.account_id===initialBundle.account_id&&
  requery.from===initialBundle.from&&
  requery.capture_basis==="ALPACA_ACTIVITY_CREATED_AT_NOT_SETTLEMENT_DATE",
  "SAME_INITIAL_ACCOUNT_AND_CREATION_WINDOW");
 const from=time(initialBundle.from,"START"),
  end=time(initialBundle.through,"ORIGINAL_END"),
  expandedEnd=time(requery.through,"EXPANDED_END"),
  rechecked=time(requery.collected_at,"REQUERY_COLLECTED"),
  firstCollected=time(initialBundle.collected_at,"FIRST_COLLECTED");
 need(from<end&&end<expandedEnd&&
  expandedEnd<=rechecked&&firstCollected<rechecked,
  "EXPANDED_QUERY_MUST_OCCUR_AFTER_ORIGINAL");
 const original=all(initialBundle),later=all(requery);
 const seen=new Map(original.map(x=>[x.id,netLedgerDigest(x)]));
 const replayed=new Set(),late=[];
 for(const r of later){
  const was=seen.get(r.id);
  if(was!==undefined){
   need(was===netLedgerDigest(r),"REQUERY_ALTERED_PRIOR_ACTIVITIES");
   replayed.add(r.id);continue;
  }
  const createdAt=time(r.created_at,"NEW_ACTIVITY_CREATED_AT");
  need(createdAt>from&&createdAt<=expandedEnd,
   "NEW_ACTIVITY_OUTSIDE_CREATED_AT_QUERY");
  late.push({idSha256:netLedgerDigest({activityId:r.id}),
   recordSha256:netLedgerDigest(r),
   activityType:r.activity_type,
   recordCreatedAt:r.created_at,
   createdAfterOriginalClose:createdAt>end,
   belongsToPreviouslyClosedBlockUnknown:true});
 }
 need(replayed.size===seen.size,
  "REQUERY_MISSING_PREVIOUS_ACTIVITY");
 const hasLate=late.length>0;
 return {
  schema:"HARPOON_FWN9_C34_DELAYED_ACTIVITY_CENSUS_RESULT_1",
  C25OriginalAccountReconciled:true,
  accountIdRedacted:true,
  startingActivityCount:original.length,
  expandedActivityCount:later.length,
  previouslyObservedActivitiesUnmodified:true,
  lateDiscoveredActivities:late,
  activitiesCreatedAfterOriginalClose:late.filter(x=>x.createdAfterOriginalClose).length,
  importedActivityHistoryExactSubsetVerified:true,
  requiresReconciliationRestatement:hasLate,
  originalC25NAVCannotBePromotedAsFinalFromThisCensus:true,
  singleAdditionalRequeryProvesNoFutureLateActivities:false,
  brokerOriginationAuthenticityIndependentlyVerified:false,
  lateAccountChargesFullyReconciled:false,
  validProspectiveTradingEdge:false,
  financialGO:false,N9S:"NO_GO",M10Sealed:3200
 };
}
module.exports={SCHEMA,inspect};
