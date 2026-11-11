"use strict";
/** C29 immutable eight-arm prospective study DESIGN (not an execution plan).
 * Creates no market RNG seed, trading signal, order, economic account,
 * optimization loop or M10 access. Deterministic assignments from a
 * user-supplied pre-outcome registration nonce; no random seed is sampled.
 * Signing this locally does NOT prove independent preregistration time.
 */
const A=require("node:assert/strict");
const crypto=require("node:crypto");
const C27=require("./fwn9_c27_prebar_state.cjs");
const C28=require("./fwn9_c28_one_book_prospective_comparator.cjs");
const SCHEMA="HARPOON_FWN9_C29_FIXED_EIGHT_ARM_PROSPECTIVE_PLAN_1";
const HOUR=3600000,TRADE_MS=72*HOUR,WASH_MS=72*HOUR;
function need(ok,tag){A.ok(ok,"C29R_"+tag);}
function safe(v,k){need(Number.isSafeInteger(v)&&v>=0,k);return v;}
function scalar(s,k){need(typeof s==="string"&&s.length>=1&&s.length<=500,k);return s;}
function hash(s){return crypto.createHash("sha256").update(s).digest("hex");}
function uniform(seed,cycle,step,upper){
 need(Number.isInteger(upper)&&upper>0&&upper<=8,"RNG_DOMAIN");
 const max=2**32-((2**32)%upper);
 for(let retry=0;retry<10;retry++){
  const digest=crypto.createHash("sha256")
   .update("C29_ASSIGNMENT_V1|"+seed+"|"+cycle+"|"+step+"|"+retry).digest();
  const v=digest.readUInt32BE(0);
  if(v<max)return v%upper;
 }
 throw Error("C29R_UNBIASED_REJECTION_BUDGET");
}
function permutation(seed,cycle){
 const order=C28.ARMS.slice();
 for(let i=order.length-1;i>0;i--){
  const j=uniform(seed,cycle,i,i+1);
  [order[i],order[j]]=[order[j],order[i]];
 }
 return order;
}
function canonical(row){return C27.digest(row);}
function freeze({studyId,registeredAt,startAt,cycles=4,assignmentNonce,
  registrarPublicKeyFingerprint=null}={}){
 const name=scalar(studyId,"STUDY_ID");
 const registered=safe(registeredAt,"REGISTRATION_TIME"),
  start=safe(startAt,"STUDY_START");
 need(registered+WASH_MS<=start,"PREREGISTER_AT_LEAST_72H_BEFORE_FIRST_BLOCK");
 need(Number.isInteger(cycles)&&cycles>=4&&cycles<=128,"FOUR_TO_128_CYCLES");
 const nonce=scalar(assignmentNonce,"ASSIGNMENT_NONCE");
 need(nonce.length>=32&&nonce.length<=256&&
  /^[A-Za-z0-9._:-]+$/.test(nonce),"NONCE_LENGTH_AND_DOMAIN");
 need(registrarPublicKeyFingerprint===null||
  /^[a-f0-9]{64}$/.test(registrarPublicKeyFingerprint),
  "REGISTRAR_FINGERPRINT");
 const blocks=[];
 for(let cycle=0;cycle<cycles;cycle++){
  const arms=permutation(nonce,cycle);
  for(let slot=0;slot<arms.length;slot++){
   const index=cycle*arms.length+slot,at=start+index*(TRADE_MS+WASH_MS);
   need(Number.isSafeInteger(at+TRADE_MS+WASH_MS),"SCHEDULE_SAFE_EPOCH");
   blocks.push({
    index,blockId:"C29_"+name+"_"+String(index+1).padStart(5,"0"),
    cycle,slot,arm:arms[slot],assignmentKnownAt:registered,
    startAt:at,tradeEndAt:at+TRADE_MS,
    washoutEndAt:at+TRADE_MS+WASH_MS,
    tradeHours:72,washoutHours:72,
    accountDesign:"ONE_SHARED_USD_20000_FUNDED_ACCOUNT",
    entryAuthorized:false,liveApproved:false});
  }
 }
 const body={schema:SCHEMA,studyId:name,registeredAt:registered,
  startAt:start,cycles,initialCapitalUsd:20000,
  holdingMaximumHours:72,washoutHours:72,
  eightArms:[...C28.ARMS],blocks,
  assignmentAlgorithm:"SHA256_DOMAIN_SEPARATED_UNBIASED_FISHER_YATES",
  assignmentNonceCommitment:hash("C29_NONCE_V1|"+nonce),
  publicationOrIndependentTimeAnchorVerified:false,
  actualRandomizationExogeneityProved:false,
  baselinePolicyVersion:"FROZEN_C28_ORIGINAL_BASELINE",
  consentToTrade:false,paperOrLiveOrdersAuthorized:false,
  prospectiveStudyActuallyStarted:false,
  evidenceFromIndependentBroker:false,
  initialCapitalNotIncreasedByCompounding:true,
  noRetrospectiveVariantSelection:true,
  registrarPublicKeyFingerprint,
  sixContrastsAgainstCashAndOriginal:true,
  familywiseAlpha:.025,
  originalHoldoutM10Sealed:3200,
  N9S:"NO_GO"};
 return {...body,planDigest:canonical(body)};
}
function validate(plan){
 need(plan&&plan.schema===SCHEMA,"PLAN_SCHEMA");
 const body={...plan};delete body.planDigest;
 need(canonical(body)===plan.planDigest,"PLAN_TAMPERED");
 need(plan.eightArms.length===8&&
  plan.eightArms.every((x,i)=>x===C28.ARMS[i])&&
  Number.isInteger(plan.cycles)&&plan.cycles>=4&&
  plan.blocks.length===plan.cycles*8&&
  plan.familywiseAlpha===.025&&plan.initialCapitalUsd===20000,
  "FROZEN_ARMS_AND_CAPITAL");
 const prev=new Set();
 for(let i=0;i<plan.blocks.length;i++){
  const b=plan.blocks[i];
  need(b.index===i&&b.cycle===Math.floor(i/8)&&b.slot===i%8&&
   C28.ARMS.includes(b.arm)&&!prev.has(b.blockId)&&
   b.startAt===plan.startAt+i*(TRADE_MS+WASH_MS)&&
   b.tradeEndAt-b.startAt===TRADE_MS&&
   b.washoutEndAt-b.tradeEndAt===WASH_MS&&
   b.assignmentKnownAt===plan.registeredAt&&
   b.entryAuthorized===false&&b.liveApproved===false,
   "FROZEN_BLOCK_GEOMETRY");
  prev.add(b.blockId);
 }
 for(let c=0;c<plan.cycles;c++)
  need(new Set(plan.blocks.slice(c*8,c*8+8).map(x=>x.arm)).size===8,
   "EXACT_EIGHT_ARM_COUNTERBALANCE");
 need(plan.registeredAt+WASH_MS<=plan.startAt&&
  plan.consentToTrade===false&&plan.paperOrLiveOrdersAuthorized===false&&
  plan.prospectiveStudyActuallyStarted===false&&
  plan.N9S==="NO_GO"&&plan.originalHoldoutM10Sealed===3200,
  "ORIGINAL_SAFETY_RESTRICTIONS");
 return {schema:"HARPOON_FWN9_C29_PREOUTCOME_PLAN_VERIFIED_1",
  planDigest:plan.planDigest,cycles:plan.cycles,plannedBlocks:plan.blocks.length,
  eachArmAssignedExactlyOncePerCycle:true,
  holdoutM10Sealed:3200,independentlyTimeAttested:false,
  studyHasActuallyRun:false,
  ordersAllowed:false,N9S:"NO_GO"};
}
module.exports={SCHEMA,freeze,validate,permutation};
