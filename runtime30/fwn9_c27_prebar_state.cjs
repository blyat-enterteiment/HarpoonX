"use strict";
/** C27: pre-bar input validation against ORIGINAL funded reservation source.
 * No market OHLC from current bar is accepted. Any asserted source/knownAt
 * from a JSON object is NOT independently exchange/broker authenticated.
 * No broker I/O, no signals generated, no execution authority.
 */
const A=require("node:assert/strict");
const crypto=require("node:crypto");
const R=require("./ultimate_reservations.js");
const SCHEMA="HARPOON_FWN9_C27_PREBAR_INPUT_1",MS72=72*3600000;
const POLICY_IDS=Object.freeze([
 "H22_OPENING_CONFIRMATION@RTH_OPEN_30",
 "H22_OPENING_CONFIRMATION@RTH_MORNING_30_120",
 "H22_CRYPTO_UTC_LIQUIDITY@UTC_00_08",
 "H22_CRYPTO_UTC_LIQUIDITY@UTC_16_24",
 "H22_OPTION_ASYMMETRY_RESEARCH_ONLY@RTH_MORNING_30_120",
 "H22_OPTION_ASYMMETRY_RESEARCH_ONLY@RTH_LAST_90",
 "ORIGINAL_BASELINE","CASH"
]);
function need(x,code){A.ok(x,"C27_"+code);}
function obj(x,code){need(x&&typeof x==="object"&&!Array.isArray(x),code);return x;}
function str(x,code){need(typeof x==="string"&&x.length>0&&x.length<=256,code);return x;}
function tick(x,code){need(Number.isSafeInteger(x)&&x>=0,code);return x;}
function nonneg(x,code){need(typeof x==="number"&&Number.isFinite(x)&&x>=0,code);return x;}
function pos(x,code){need(typeof x==="number"&&Number.isFinite(x)&&x>0,code);return x;}
function stable(value){
 if(value===null)return "null";
 if(Array.isArray(value))return "["+value.map(stable).join(",")+"]";
 if(typeof value==="object"){
  need(Object.getPrototypeOf(value)===Object.prototype,"HASH_OBJECT_PROTOTYPE");
  return "{"+Object.keys(value).sort().map(k=>JSON.stringify(k)+":"+stable(value[k])).join(",")+"}";
 }
 need(["string","number","boolean"].includes(typeof value)&&
  (typeof value!=="number"||Number.isFinite(value)),"HASH_VALUE");
 return JSON.stringify(value);
}
function digest(x){return crypto.createHash("sha256").update(stable(x)).digest("hex");}
function validatePrebar(input,manifest){
 obj(input,"INPUT");obj(manifest,"MANIFEST");
 need(input.schema===SCHEMA,"INPUT_SCHEMA");
 const t=tick(input.barStart,"BAR_START");
 need(t===manifest.expectedBars[input.barIndex]&&
  Number.isSafeInteger(input.barIndex)&&input.barIndex>=0,"SCHEDULE_BAR_INDEX");
 need(input.runId===manifest.runId&&input.mode===manifest.mode,
  "RUN_CONTEXT");
 need(tick(input.capturedAt,"CAPTURE_AT")<=t&&
  tick(input.lastPublicKnownAt,"LAST_PUBLISHED_KNOWN_AT")<=t,
  "NO_POSTBAR_INFORMATION");
 need(input.currentBar===undefined&&input.currentOHLC===undefined&&
  input.intrabarPath===undefined&&input.futureReceipt===undefined,
  "CURRENT_BAR_DATA_FORBIDDEN");
 const scope=obj(input.scope,"SOURCE_SCOPE");
 need(scope.originalSource==="ORIGINAL_M9_NATIVE_SOURCE_READONLY"&&
  scope.sourceInputsAuthenticatedExternally===false&&
  scope.allCandidatesIndependentlyAuthenticated===false,
  "NO_FAKE_SOURCE_ATTESTATION");
 const universe=input.universe;
 need(Array.isArray(universe)&&universe.length>0&&universe.length<=48&&
  universe.every(x=>typeof x==="string"&&x.length>0)&&
  new Set(universe).size===universe.length,"COMPLETE_ASSET_UNIVERSE");
 const symbols=new Set(universe);
 const book=obj(input.sourceReservationBook,"NATIVE_RESERVATION_BOOK");
 need(book.schema==="HARPOON_FUNDED_RESERVATIONS_1"&&
  Array.isArray(book.reservations),"ORIGINAL_RESERVATION_SCHEMA");
 // Critically do NOT just use snapshotFundedReservations(), which would
 // silently slice future-dated receipt observations from the supplied book.
 for(const r of book.reservations){
  str(r.id,"RESERVATION_ID");
  need(symbols.has(r.symbol)&&tick(r.decisionAt,"RESERVATION_DECISION")<=t,
   "RESERVATION_FROM_FUTURE");
  need(Array.isArray(r.observations),"RESERVATION_OBSERVATIONS");
  for(const o of r.observations)
   need(tick(o.at,"OBSERVATION_AT")<=t&&
    tick(o.knownAt,"OBSERVATION_KNOWN_AT")<=t&&o.at<=o.knownAt,
    "RESERVATION_FUTURE_RECEIPT");
 }
 const reserved=R.snapshotFundedReservations(book,t);
 const physical=obj(input.physicalBook,"PHYSICAL_BOOK");
 const cash=nonneg(physical.cashUsd,"CASH"),equity=pos(physical.equityUsd,"EQUITY"),
  settled=nonneg(physical.settledCashUsd,"SETTLED_CASH"),
  unsettled=nonneg(physical.unsettledCashUsd,"UNSETTLED_CASH"),
  committed=nonneg(physical.extraCommittedCashUsd,"EXTRA_COMMITTED_CASH");
 need(tick(physical.knownAt,"BOOK_KNOWN_AT")<=t&&
  settled<=cash+0.02,"SETTLED_GREATER_PHYSICAL_CASH");
 need(Array.isArray(input.positions)&&input.positions.length<=5000,"POSITIONS");
 const active=new Map(reserved.reservations.filter(x=>x.state==="OPENED").map(x=>[x.id,x]));
 need(active.size===reserved.opened,"DUPLICATE_OPEN_RESERVATIONS");
 const seen=new Set();let markTotal=0;
 for(const p of input.positions){
  obj(p,"POSITION");
  const id=str(p.reservationId,"POSITION_RESERVATION_ID");
  need(!seen.has(id),"DUPLICATE_POSITION");seen.add(id);
  const r=active.get(id);
  need(r&&p.symbol===r.symbol&&symbols.has(p.symbol)&&
   Number.isSafeInteger(p.quantity)&&p.quantity>0&&
   p.quantity===r.observedRemainingQuantity,
   "POSITION_NOT_SOURCE_OPEN_REMAINING");
  const entryPrice=pos(p.entryPrice,"ENTRY_PRICE");
  need(tick(p.entryAt,"ENTRY_AT")<=t&&p.entryAt>=r.decisionAt&&
   tick(p.positionKnownAt,"POSITION_KNOWN_AT")<=t,
   "POSITION_FROM_FUTURE");
  need(tick(p.deadlineAt,"DEADLINE_AT")>=p.entryAt&&
   p.deadlineAt-p.entryAt<=MS72,"HOLDING_EXCEEDS_72H");
  const stop=obj(p.stop,"STOP");
  // A trailing stop is allowed to rise ABOVE entry after profits. Do not
  // reinterpret such native profit protection as an invalid long entry.
  need(pos(stop.price,"STOP_PRICE")>0&&
   tick(stop.knownAt,"STOP_KNOWN_AT")<=t,
   "STOP_NOT_KNOWN_PREBAR");
  need(tick(p.lastMarkKnownAt,"MARK_KNOWN_AT")<=t,
   "FUTURE_POSITION_MARK");
  const mark=pos(p.lastKnownMarkPrice,"MARK_PRICE");
  markTotal+=mark*p.quantity;
  if(p.pendingStop!==null&&p.pendingStop!==undefined){
   const pending=obj(p.pendingStop,"PENDING_STOP");
   need(pos(pending.price,"PENDING_STOP_PRICE")>=stop.price&&
    tick(pending.knownAt,"PENDING_STOP_KNOWN")<=t&&
    tick(pending.effectiveAt,"PENDING_STOP_EFFECTIVE")>t&&
    pending.knownAt<=pending.effectiveAt,
    "PENDING_STOP_ALREADY_EFFECTIVE_OR_FUTURE_KNOWN");
  }
  need(Array.isArray(p.targets)&&p.targets.length===2&&
   p.targets[0].id==="TP1"&&p.targets[1].id==="TP2",
   "TWO_PERSISTENT_NATIVE_TARGETS");
  let allocations=0;
  for(const tp of p.targets){
   obj(tp,"TARGET");
   need(typeof tp.done==="boolean"&&
    Number.isSafeInteger(tp.quantity)&&tp.quantity>=0&&
    tick(tp.knownAt,"TARGET_KNOWN_AT")<=t,
    "TARGET_KNOWN_PAST_AND_INTEGER");
   if(tp.price!==null){
    need(pos(tp.price,"TARGET_PRICE")>entryPrice,
     "LONG_TARGET_ABOVE_ENTRY");
   }else need(tp.quantity===0,"DISABLED_TARGET_HAS_QUANTITY");
   allocations+=tp.quantity;
  }
  need(allocations<=r.quantity,"TARGET_OVERALLOCATED");
 }
 need(seen.size===reserved.opened,"OPEN_RESERVATION_MISSING_POSITION");
 const pendingCash=reserved.reservations.filter(x=>x.state==="PENDING")
  .reduce((s,x)=>s+x.cashUsd,0);
 const available=Math.max(0,settled-unsettled-committed-pendingCash);
 need(Math.abs(equity-cash-markTotal)<=0.05,"PHYSICAL_EQUITY_NOT_CASH_PLUS_MARKS");
 need(Math.abs(nonneg(physical.availableCashUsd,"AVAILABLE_CASH")-available)<=0.02,
  "AVAILABLE_CASH_VS_PENDING_RESERVATIONS");
 const c=obj(input.opportunityCoverage,"OPPORTUNITY_COVERAGE");
 need(Array.isArray(c.enumeratedIds)&&Array.isArray(c.outcomes)&&
  c.generatorSourceHash===manifest.generatorHash&&
  c.candidateCollectionCompleteDeclared===true&&
  c.outcomes.length===c.enumeratedIds.length&&
  c.enumeratedIds.length<=10000,"CANDIDATE_SOURCE_LIST");
 const enumerated=new Set();
 for(const id of c.enumeratedIds){
  need(typeof id==="string"&&id.length>0&&!enumerated.has(id),"DUPLICATE_ENUMERATED_ID");
  enumerated.add(id);
 }
 const outcomes=new Set(),counts={RESERVED:0,REFUSED:0,NO_FILL:0,NO_SIGNAL:0,OBSERVED_ONLY:0};
 const booked=new Map(book.reservations.map(x=>[x.id,x]));
 for(const row of c.outcomes){
  obj(row,"OPPORTUNITY");
  need(enumerated.has(row.id)&&!outcomes.has(row.id),
   "OPPORTUNITY_NOT_ENUMERATED_OR_DUPLICATE");
  outcomes.add(row.id);
  need(POLICY_IDS.includes(row.policyId)&&symbols.has(row.symbol)&&
   tick(row.decisionAt,"OPPORTUNITY_AT")<=t&&
   tick(row.knownAt,"OPPORTUNITY_KNOWN_AT")<=t&&
   row.knownAt>=row.decisionAt,
   "OPPORTUNITY_CLOCK_POLICY");
  need(Object.hasOwn(counts,row.outcome),"OPPORTUNITY_OUTCOME");
  if(row.outcome==="RESERVED"){
   need(booked.has(row.id)&&
    booked.get(row.id).symbol===row.symbol,
    "RESERVED_MISSING_SOURCE_RESERVATION");
   need(row.reason===null,"RESERVED_HAS_REJECTION");
  }else if(row.outcome==="NO_FILL"){
   const r=booked.get(row.id);
   need(r&&r.observations.some(o=>o.kind==="NO_FILL"&&
    o.knownAt<=t),"NO_FILL_NOT_SOURCE_RECEIPTED");
   need(row.reason==="IOC_NO_FILL","NO_FILL_REASON");
  }else{
   need(!booked.has(row.id),"REFUSED_OR_NO_SIGNAL_WAS_ADMITTED");
   need(typeof row.reason==="string"&&row.reason.length>0,
    "REFUSAL_REASON_MISSING");
  }
  counts[row.outcome]++;
 }
 need(enumerated.size===outcomes.size,"UNACCOUNTED_GENERATED_OPPORTUNITY");
 const sourceBookHash=digest(book);
 return {schema:"HARPOON_FWN9_C27_PREBAR_VALIDATED_FRAME_1",
  originalInput:structuredClone(input),barStart:t,
  positionCount:seen.size,sourceReservationCount:reserved.reservations.length,
  reservedPending:reserved.pending,reservedOpened:reserved.opened,
  sourceBookHash,sourceSnapshotHash:digest(reserved),
  reservedRiskUsd:reserved.riskUsd,reservedGrossAdmissionUsd:reserved.notionalUsd,
  reservedCashUsd:reserved.cashUsd,
  pendingCashUsd:pendingCash,availableCashUsd:available,
  markedEquityUsd:equity,
  newGeneratedOpportunityCount:enumerated.size,
  candidateOutcomes:counts,
  completeGeneratedCandidateCoverageWithinClaimedSource:true,
  sourceCandidateEnumeratorIndependentlyVerified:false,
  sourceProviderTimestampCryptographicallyAuthenticated:false,
  stopTargetStateActualRuntimeAttached:false,
  thisFrameDoesNotContainCurrentOHLC:true,
  financialGO:false,N9S:"NO_GO"};
}
function continuity(before,after){
 need(before.schema==="HARPOON_FWN9_C27_PREBAR_VALIDATED_FRAME_1"&&
  after.schema===before.schema&&after.barStart>before.barStart,
  "CONTINUITY");
 const prev=before.originalInput,now=after.originalInput;
 const left=prev.sourceReservationBook.reservations,
  right=now.sourceReservationBook.reservations;
 need(right.length>=left.length,"RESERVATION_HISTORY_TRUNCATED");
 for(let i=0;i<left.length;i++){
  const a=left[i],b=right[i];
  need(b&&a.id===b.id&&
   digest({...a,observations:[]})===digest({...b,observations:[]})&&
   b.observations.length>=a.observations.length,
   "RESERVATION_HISTORY_REWRITTEN");
  for(let j=0;j<a.observations.length;j++)
   need(digest(a.observations[j])===digest(b.observations[j]),
    "OBSERVED_RECEIPT_RESTATED");
 }
 const previous=new Map(prev.positions.map(p=>[p.reservationId,p]));
 const current=new Map(now.positions.map(p=>[p.reservationId,p]));
 for(const [id,p] of previous){
  const q=current.get(id);
  if(!q)continue; // source OPENED/CLOSED change checked by source snapshot
  need(q.symbol===p.symbol&&q.entryAt===p.entryAt&&
   q.entryPrice===p.entryPrice&&q.quantity<=p.quantity,
   "POSITION_REPLACED_OR_REINFLATED");
  need(q.stop.price+1e-9>=p.stop.price&&
   q.stop.knownAt>=p.stop.knownAt,"LONG_STOP_LOOSENED_OR_CLOCK_REGRESSION");
  for(let j=0;j<2;j++){
   need(q.targets[j].id===p.targets[j].id&&
    q.targets[j].price===p.targets[j].price&&
    q.targets[j].quantity===p.targets[j].quantity&&
    (!p.targets[j].done||q.targets[j].done),
    "TARGET_CHANGED_OR_UNDONE");
  }
 }
 return {sourceReservationHistoryPrefixVerified:true,
  persistentStopAndTargetMonotonic:true,
  bookEventsBeforeNewBar:true,financialGO:false,N9S:"NO_GO"};
}
module.exports={SCHEMA,POLICY_IDS,validatePrebar,continuity,digest};
