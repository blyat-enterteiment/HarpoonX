"use strict";
/** C28: durable source pre-filter tap archive bound to ORIGINAL C27 snapshots.
 * The sidecar cannot make an untrusted input authentic: its sha256 chain
 * detects accidental/current corruption and provides reproducibility only.
 *
 * Full C27 prefix + each source tap pair is revalidated after restart.
 * No network, no trading, no generator, no private account export.
 */
const fs=require("node:fs"),path=require("node:path");
const C27=require("./fwn9_c27_prebar_state.cjs");
const J=require("./fwn9_c27_prebar_journal.cjs");
const C=require("./fwn9_c28_source_obligations.cjs");
const M="HARPOON_FWN9_C28_SOURCE_TAP_LEDGER_MANIFEST_1";
const R="HARPOON_FWN9_C28_SOURCE_TAP_FRAME_1";
const MAX=4*1024*1024;
function need(x,k){if(!x)throw Error("C28A_"+k);}
function safeDir(dir){
 const s=fs.lstatSync(dir);
 need(s.isDirectory()&&!s.isSymbolicLink()&&(s.mode&0o077)===0,"PRIVATE_DIR_0700");
}
function store(file,body){
 const bytes=Buffer.from(JSON.stringify(body)+"\n");
 need(bytes.length<=MAX,"FRAME_TOO_LARGE");
 const fd=fs.openSync(file,"wx",0o600);
 try{
  fs.writeSync(fd,bytes,0,bytes.length);
  fs.fsyncSync(fd);
 }finally{fs.closeSync(fd);}
 const dd=fs.openSync(path.dirname(file),"r");
 try{fs.fsyncSync(dd);}finally{fs.closeSync(dd);}
}
function filename(i,hash){return String(i+1).padStart(8,"0")+"-"+hash+".json";}
function manifest(dir){
 safeDir(dir);
 const p=path.join(dir,"manifest.json"),stat=fs.lstatSync(p);
 need(stat.isFile()&&!stat.isSymbolicLink()&&(stat.mode&0o777)===0o600,
  "MANIFEST_PERMISSIONS");
 const m=JSON.parse(fs.readFileSync(p,"utf8"));
 need(m.schema===M&&m.originalC27ManifestHash?.length===64&&
  m.registryHash?.length===64&&m.calendarHash?.length===64&&
  typeof m.manifestHash==="string"&&m.manifestHash.length===64,
  "MANIFEST_SCHEMA");
 const clean={...m};delete clean.manifestHash;
 need(C27.digest(clean)===m.manifestHash,"MANIFEST_REWRITTEN");
 return m;
}
function create(dir,{c27Dir,registry,calendar}){
 need(!fs.existsSync(dir),"NO_OVERWRITE");
 const j=J.verifyJournal(c27Dir);
 const assets=C.reg(registry);
 need(Array.isArray(calendar),"CALENDAR");
 const header={schema:M,originalC27ManifestHash:j.manifest.seal,
  registry:assets,registryHash:C27.digest(assets),
  calendar:structuredClone(calendar),calendarHash:C27.digest(calendar),
  expectedBars:j.manifest.expectedBars,
  originalPolicyIds:C27.POLICY_IDS,
  sourceOriginIndependentlyAuthenticated:false,
  originalOrdersExecutableCertified:false,
  N9S:"NO_GO"};
 const m={...header,manifestHash:C27.digest(header)};
 fs.mkdirSync(dir,{mode:0o700});
 safeDir(dir);
 store(path.join(dir,"manifest.json"),m);
 return verify(dir,c27Dir);
}
function verify(dir,c27Dir){
 const m=manifest(dir),j=J.verifyJournal(c27Dir);
 need(m.originalC27ManifestHash===j.manifest.seal&&
  m.registryHash===C27.digest(m.registry)&&
  m.calendarHash===C27.digest(m.calendar)&&
  C27.digest(m.expectedBars)===C27.digest(j.manifest.expectedBars)&&
  C27.digest(m.originalPolicyIds)===C27.digest(C27.POLICY_IDS),
  "MANIFEST_NOT_MATCHING_ORIGINAL_C27");
 const names=fs.readdirSync(dir).filter(x=>x!=="manifest.json").sort();
 need(names.length<=j.verifiedFrames,"TAPS_AHEAD_OF_C27");
 let previous="GENESIS",scanned=0,evaluated=0,skipped=0,emitted=0;
 for(let i=0;i<names.length;i++){
  const name=names[i],match=/^([0-9]{8})-([0-9a-f]{64})\.json$/.exec(name);
  need(match&&Number(match[1])===i+1,"TAP_SEQUENCE_GAP_OR_FOREIGN_FILE");
  const p=path.join(dir,name),st=fs.lstatSync(p);
  need(st.isFile()&&!st.isSymbolicLink()&&
   (st.mode&0o777)===0o600&&st.size>0&&st.size<=MAX,
   "TAP_FILE_PERMISSIONS");
  const row=JSON.parse(fs.readFileSync(p,"utf8"));
  const original=j.entries[i],c27p=path.join(c27Dir,filename(i,original.frameHash));
  const raw=JSON.parse(fs.readFileSync(c27p,"utf8"));
  need(row.schema===R&&row.sequence===i+1&&
   row.originalC27FrameHash===original.frameHash&&
   row.previous===previous&&row.manifestHash===m.manifestHash&&
   row.recordHash===match[2],"TAP_HEADER_C27_LINK");
  const clean={...row};delete clean.recordHash;
  need(C27.digest(clean)===row.recordHash,"TAP_REHASH_MISMATCH");
  const validated=C27.validatePrebar(raw.input,j.manifest);
  const report=C.verifyFrame({frame:validated,registry:m.registry,
   calendar:m.calendar,taps:row.sourceTaps});
  need(report.obligationCount===row.obligationCount&&
   report.rawCandidatesMatched===row.rawCandidateCount,
   "TAP_CANDIDATE_SUMMARY_TAMPER");
  previous=row.recordHash;
  scanned++;evaluated+=report.evaluationsCompleted;
  skipped+=report.explicitIneligible;emitted+=report.rawCandidatesMatched;
 }
 return {schema:"HARPOON_FWN9_C28_RESTART_VERIFIED_SOURCE_TAP_LEDGER_1",
  expectedFrames:j.expectedFrames,c27CommittedFrames:j.verifiedFrames,
  tapCommittedFrames:scanned,
  fullBarsAndSourceTapsComplete:j.coverageComplete&&scanned===j.expectedFrames,
  registeredEligibleEvaluations:evaluated,
  explicitInactiveSlots:skipped,sourceCandidateIdsBoundToC27:emitted,
  verifiedTapChainHead:previous,linkedC27Head:j.finalizedEvidenceHead,
  externalSignerOrMarketDataTruthAuthenticated:false,
  allPotentialMarketOpportunitiesGloballyEnumerated:false,
  independentlyAuthenticatedBrokerFills:false,
  financialGO:false,N9S:"NO_GO",M10Sealed:3200};
}
function append(dir,c27Dir,taps){
 safeDir(dir);
 const lock=dir+".write-lock";
 const fd=fs.openSync(lock,"wx",0o600);
 try{
  const before=verify(dir,c27Dir),m=manifest(dir);
  const index=before.tapCommittedFrames;
  need(index<before.c27CommittedFrames,"PREBAR_FRAME_NOT_YET_SEALED");
  const j=J.verifyJournal(c27Dir),c27row=j.entries[index];
  const raw=JSON.parse(fs.readFileSync(path.join(c27Dir,
   filename(index,c27row.frameHash)),"utf8"));
  const validated=C27.validatePrebar(raw.input,j.manifest);
  const check=C.verifyFrame({frame:validated,registry:m.registry,
   calendar:m.calendar,taps});
  const base={schema:R,sequence:index+1,
   originalC27FrameHash:c27row.frameHash,
   previous:before.verifiedTapChainHead,
   manifestHash:m.manifestHash,
   barStart:validated.barStart,
   sourceTaps:structuredClone(taps),
   obligationCount:check.obligationCount,
   rawCandidateCount:check.rawCandidatesMatched,
   externalOriginAuthenticated:false,
   brokerReceiptAttestation:false,
   financialGO:false,N9S:"NO_GO"};
  const hash=C27.digest(base);
  store(path.join(dir,filename(index,hash)),{...base,recordHash:hash});
  return verify(dir,c27Dir);
 }finally{
  fs.closeSync(fd);
  fs.unlinkSync(lock);
 }
}
module.exports={create,verify,append};
