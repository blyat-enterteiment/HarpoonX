"use strict";
/** C28 sidecar tests use C27 original immutable engineered 3-bar fixture.
 * No broker, real account, market RNG or C22 strategy signal generation.
 */
const test=require("node:test"),A=require("node:assert/strict");
const fs=require("node:fs"),os=require("node:os"),path=require("node:path");
const F=require("./fwn9_c27_test_fixture.cjs");
const J=require("../runtime30/fwn9_c27_prebar_journal.cjs");
const C=require("../runtime30/fwn9_c28_source_obligations.cjs");
const T=require("../runtime30/fwn9_c28_source_tap_archive.cjs");
const base=F.BARS[0],calendar=[{
 date:new Date(base).toISOString().slice(0,10),
 open:base,close:base+78*300000
}];
const registry=[{symbol:"SYNA",book:"equity"},{symbol:"SYNB",book:"equity"}];
function taps(i){
 const f=F.sample().frames[i],rows=f.opportunityCoverage.outcomes;
 return C.obligations({barStart:f.barStart,registry,calendar}).map(o=>
  C.makeTap({obligation:o,
   sourceCall:o.requiredEvaluation?()=>rows.filter(x=>
    x.policyId===o.policyId&&x.symbol===o.symbol).map(x=>({
     id:x.id,policyId:x.policyId,symbol:x.symbol
    })):null,
   now:()=>f.barStart-1000}));
}
function withPrivate(fn,{frameCount=3}={}){
 const tmp=fs.mkdtempSync(path.join(os.tmpdir(),"c28-taps-"));
 const c27=path.join(tmp,"c27"),tapDir=path.join(tmp,"source-taps");
 try{
  J.newJournal(c27,F.manifest());
  const source=F.sample();
  for(let i=0;i<frameCount;i++)J.append(c27,source.frames[i]);
  return fn({tmp,c27,tapDir});
 }finally{fs.rmSync(tmp,{recursive:true,force:true});}
}
function create({c27,tapDir}){
 return T.create(tapDir,{c27Dir:c27,registry,calendar});
}
function list(dir){return fs.readdirSync(dir).filter(x=>x!=="manifest.json").sort();}
test("C28 sidecar manifest seals source registry, original C27 chain and all expected bars",()=>withPrivate(d=>{
 const result=create(d);
 A.equal(result.expectedFrames,3);
 A.equal(result.tapCommittedFrames,0);
 A.equal(result.fullBarsAndSourceTapsComplete,false);
 A.equal(result.N9S,"NO_GO");
 A.equal(fs.statSync(d.tapDir).mode&0o777,0o700);
 A.equal(fs.statSync(path.join(d.tapDir,"manifest.json")).mode&0o777,0o600);
}));
test("C28 each frame requires exact source taps and reaches full original C27 3-bar schedule",()=>withPrivate(d=>{
 create(d);
 for(let i=0;i<3;i++)T.append(d.tapDir,d.c27,taps(i));
 const result=T.verify(d.tapDir,d.c27);
 A.equal(result.tapCommittedFrames,3);
 A.equal(result.fullBarsAndSourceTapsComplete,true);
 A.equal(result.registeredEligibleEvaluations,12);
 A.equal(result.explicitInactiveSlots,6);
 A.equal(result.sourceCandidateIdsBoundToC27,2);
 A.equal(result.allPotentialMarketOpportunitiesGloballyEnumerated,false);
 A.equal(result.independentlyAuthenticatedBrokerFills,false);
 A.equal(result.financialGO,false);
}));
test("C28 restart from disk validates all source taps and original prior C27 head",()=>withPrivate(d=>{
 create(d);
 T.append(d.tapDir,d.c27,taps(0));
 T.append(d.tapDir,d.c27,taps(1));
 const before=T.verify(d.tapDir,d.c27);
 A.equal(before.tapCommittedFrames,2);
 T.append(d.tapDir,d.c27,taps(2));
 const after=T.verify(d.tapDir,d.c27);
 A.equal(after.tapCommittedFrames,3);
 A.notEqual(before.verifiedTapChainHead,after.verifiedTapChainHead);
 A.equal(after.linkedC27Head,J.verifyJournal(d.c27).finalizedEvidenceHead);
}));
test("C28 missing tap frame is visible and does not grant full coverage",()=>withPrivate(d=>{
 create(d);T.append(d.tapDir,d.c27,taps(0));
 const proof=T.verify(d.tapDir,d.c27);
 A.equal(proof.tapCommittedFrames,1);
 A.equal(proof.fullBarsAndSourceTapsComplete,false);
}));
test("C28 source tap cannot precede sealed original C27 frame",()=>withPrivate(d=>{
 create(d);
 A.throws(()=>T.append(d.tapDir,d.c27,taps(2)),
  /C28_INDEPENDENT_SLOT_ORIGINAL_REGISTRY_MISMATCH|C28_PREBAR_FRAME/);
},{frameCount:1}));
test("C28 changing stored candidate enumeration without resealing is detected",()=>withPrivate(d=>{
 create(d);T.append(d.tapDir,d.c27,taps(0));
 const file=path.join(d.tapDir,list(d.tapDir)[0]);
 const row=JSON.parse(fs.readFileSync(file,"utf8"));
 row.sourceTaps[0].reason="AFTER_THE_FACT";
 fs.writeFileSync(file,JSON.stringify(row)+"\n");
 A.throws(()=>T.verify(d.tapDir,d.c27),/C28A_TAP_REHASH_MISMATCH/);
}));
test("C28 deleting a middle tap frame fails even if C27 journal is complete",()=>withPrivate(d=>{
 create(d);for(let i=0;i<3;i++)T.append(d.tapDir,d.c27,taps(i));
 fs.unlinkSync(path.join(d.tapDir,list(d.tapDir)[1]));
 A.throws(()=>T.verify(d.tapDir,d.c27),/C28A_TAP_SEQUENCE_GAP_OR_FOREIGN_FILE/);
}));
test("C28 unknown foreign archive file invalidates restart verification",()=>withPrivate(d=>{
 create(d);T.append(d.tapDir,d.c27,taps(0));
 fs.writeFileSync(path.join(d.tapDir,"UNTRACKED.txt"),"bad");
 A.throws(()=>T.verify(d.tapDir,d.c27),/C28A_TAP_SEQUENCE_GAP_OR_FOREIGN_FILE/);
}));
test("C28 manifest altered after registration fails before accepting new taps",()=>withPrivate(d=>{
 create(d);
 const p=path.join(d.tapDir,"manifest.json"),row=JSON.parse(fs.readFileSync(p,"utf8"));
 row.registry[0].book="crypto";
 fs.writeFileSync(p,JSON.stringify(row)+"\n");
 A.throws(()=>T.verify(d.tapDir,d.c27),/C28A_MANIFEST_REWRITTEN/);
}));
test("C28 two independent processes may not append while external source lock held",()=>withPrivate(d=>{
 create(d);
 const lock=d.tapDir+".write-lock";
 fs.writeFileSync(lock,"MANUAL_SOURCE_RECOVERY_REQUIRED",{flag:"wx",mode:0o600});
 A.throws(()=>T.append(d.tapDir,d.c27,taps(0)),/EEXIST/);
 A.equal(T.verify(d.tapDir,d.c27).tapCommittedFrames,0);
 fs.unlinkSync(lock);
 A.equal(T.append(d.tapDir,d.c27,taps(0)).tapCommittedFrames,1);
}));
test("C28 rejected raw candidate missing from C27 is refused without a sidecar record",()=>withPrivate(d=>{
 create(d);
 const x=taps(1);
 const found=x.find(r=>r.symbol==="SYNA"&&r.policyId.endsWith("RTH_OPEN_30"));
 found.emittedIds=["HIDDEN_RAW_GENERATOR_OPPORTUNITY"];
 A.throws(()=>T.append(d.tapDir,d.c27,x),
  /C28_PRE_FILTER_GENERATED_SIGNAL_OMITTED_FROM_C27|C28_INDEPENDENT_SLOT_ORIGINAL_REGISTRY_MISMATCH/);
 A.equal(T.verify(d.tapDir,d.c27).tapCommittedFrames,0);
}));
test("C28 source digest remains local consistency, NEVER broker or exchange authentication",()=>withPrivate(d=>{
 create(d);T.append(d.tapDir,d.c27,taps(0));
 const p=T.verify(d.tapDir,d.c27);
 A.match(p.verifiedTapChainHead,/^[a-f0-9]{64}$/);
 A.equal(p.externalSignerOrMarketDataTruthAuthenticated,false);
 A.equal(p.sourceGeneratorGlobalMarketOpportunitiesProved,undefined);
 A.equal(p.N9S,"NO_GO");
}));
