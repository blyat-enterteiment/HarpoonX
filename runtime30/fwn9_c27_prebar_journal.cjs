"use strict";
/** C27 private immutable prebar journal.
 *
 * Each source-validated prebar frame is committed as a new fsynced 0600
 * content-addressed file. On restart every prior frame, filename, schedule,
 * original reservation history and causal state is independently rechecked.
 * No network / broker / execution / strategy generation.
 * A local SHA256 chain does not authenticate original event source or provide
 * a trusted time stamp: prospective deployment needs external attestation.
 */
const fs=require("node:fs"),path=require("node:path");
const S=require("./fwn9_c27_prebar_state.cjs");
const MANIFEST="HARPOON_FWN9_C27_SCHEDULE_MANIFEST_1";
const ARCHIVE="HARPOON_FWN9_C27_IMMUTABLE_FRAME_1";
const MAX_BARS=60000,MAX_FRAME_BYTES=4*1024*1024;
const ORIGINAL_M9_WEAK_SHA256="9d4afa402d2b70791f175e79219495f9bbbe25eb3cd0b7e9212cef6bccbd68ab";
function need(x,code){if(!x)throw Error("C27J_"+code);}
function safeDir(folder){
 need(typeof folder==="string"&&folder.length>0,"DIRECTORY");
 const st=fs.lstatSync(folder);
 need(st.isDirectory()&&!st.isSymbolicLink()&&(st.mode&0o077)===0,
  "DIRECTORY_MUST_BE_PRIVATE_0700");
}
function writeExclusive(file,value){
 const bytes=Buffer.from(JSON.stringify(value)+"\n","utf8");
 need(bytes.length<=MAX_FRAME_BYTES,"FRAME_SIZE");
 const fd=fs.openSync(file,"wx",0o600);
 try{
  let sent=0;
  while(sent<bytes.length)sent+=fs.writeSync(fd,bytes,sent,bytes.length-sent);
  fs.fsyncSync(fd);
 }finally{fs.closeSync(fd);}
 const st=fs.lstatSync(file);
 need(st.isFile()&&!st.isSymbolicLink()&&(st.mode&0o777)===0o600,
  "FILE_NOT_PRIVATE");
 const dirfd=fs.openSync(path.dirname(file),"r");
 try{fs.fsyncSync(dirfd);}finally{fs.closeSync(dirfd);}
}
function openManifest(dir){
 safeDir(dir);
 const names=fs.readdirSync(dir);
 need(names.includes("manifest.json")&&names.length<=MAX_BARS+1,
  "MANIFEST_MISSING_OR_EXTRA_ENTRIES");
 const m=JSON.parse(fs.readFileSync(path.join(dir,"manifest.json"),"utf8"));
 need(m.schema===MANIFEST&&typeof m.runId==="string"&&m.runId.length>0&&
  ["ENGINEERING_REPLAY","PROSPECTIVE_LOCAL_CAPTURE"].includes(m.mode)&&
  Array.isArray(m.expectedBars)&&m.expectedBars.length>0&&
  m.expectedBars.length<=MAX_BARS&&
  m.generatorHash===ORIGINAL_M9_WEAK_SHA256&&
  m.policyIds.join("|")===S.POLICY_IDS.join("|")&&
  typeof m.seal==="string","MANIFEST_CONTRACT");
 let last=-1;
 for(const t of m.expectedBars){
  need(Number.isSafeInteger(t)&&t>0&&t>last,"MANIFEST_NONMONOTONE_GRID");
  last=t;
 }
 const copy={...m};delete copy.seal;
 need(S.digest(copy)===m.seal,"MANIFEST_DIGEST");
 need((fs.lstatSync(path.join(dir,"manifest.json")).mode&0o777)===0o600,
  "MANIFEST_PRIVATE");
 return m;
}
function newJournal(dir,{runId,mode="ENGINEERING_REPLAY",expectedBars,generatorHash}){
 need(!fs.existsSync(dir),"NO_OVERWRITE_JOURNAL_DIRECTORY");
 need(typeof runId==="string"&&runId.length>0&&runId.length<=100,
  "RUN_ID");
 need(["ENGINEERING_REPLAY","PROSPECTIVE_LOCAL_CAPTURE"].includes(mode),
  "CAPTURE_MODE");
 need(Array.isArray(expectedBars)&&expectedBars.length>0&&
  expectedBars.length<=MAX_BARS,"BAR_SCHEDULE_REQUIRED");
 need(generatorHash===ORIGINAL_M9_WEAK_SHA256,"SOURCE_GENERATOR_HASH");
 fs.mkdirSync(dir,{recursive:true,mode:0o700});
 safeDir(dir);
 const base={schema:MANIFEST,runId,mode,
  expectedBars:[...expectedBars],generatorHash,
  policyIds:[...S.POLICY_IDS],
  fullSourceAuthenticityProven:false,
  originalCashBookSource:"ORIGINAL_M9_NATIVE_SOURCE_READONLY",
  realBrokerMarketFillAttestation:false,
  capitalSharedNotIndependentPerPolicy:true,
  N9S:"NO_GO"};
 const m={...base,seal:S.digest(base)};
 writeExclusive(path.join(dir,"manifest.json"),m);
 return verifyJournal(dir);
}
function entries(dir){
 return fs.readdirSync(dir).filter(x=>x!=="manifest.json");
}
function verifyJournal(dir){
 const manifest=openManifest(dir),names=entries(dir).sort();
 let previous="GENESIS",last=null;
 const frames=[];
 for(let i=0;i<names.length;i++){
  const filename=names[i],pattern=/^([0-9]{8})-([a-f0-9]{64})\.json$/;
  const match=pattern.exec(filename);
  need(match!==null&&Number(match[1])===i+1,"FILE_SEQUENCE_GAP_OR_FOREIGN_FILE");
  const full=path.join(dir,filename),st=fs.lstatSync(full);
  need(st.isFile()&&!st.isSymbolicLink()&&(st.mode&0o777)===0o600&&
   st.size>0&&st.size<=MAX_FRAME_BYTES,"FRAME_FILE_PERMISSIONS_OR_SIZE");
  const row=JSON.parse(fs.readFileSync(full,"utf8"));
  need(row.schema===ARCHIVE&&row.sequence===i+1&&
   row.previous===previous&&row.manifestSeal===manifest.seal&&
   row.frameHash===match[2],"FRAME_HEADER_OR_HISTORY");
  const copy={...row};delete copy.frameHash;
  need(S.digest(copy)===row.frameHash,"FRAME_TAMPERED");
  const validated=S.validatePrebar(row.input,manifest);
  need(validated.sourceBookHash===row.sourceBookHash&&
   validated.sourceSnapshotHash===row.sourceSnapshotHash&&
   validated.newGeneratedOpportunityCount===row.candidateCount,
   "FRAME_SOURCE_STATE_NOT_VERIFIED");
  if(last)S.continuity(last.validated,validated);
  frames.push({sequence:row.sequence,barStart:validated.barStart,
   frameHash:row.frameHash,previousHash:previous,
   positions:validated.positionCount,
   newCandidates:validated.newGeneratedOpportunityCount,
   candidateOutcomes:validated.candidateOutcomes,
   validated});
  last=frames.at(-1);previous=row.frameHash;
 }
 need(frames.length<=manifest.expectedBars.length,"EXCESS_FRAMES");
 return {schema:"HARPOON_FWN9_C27_JOURNAL_PROOF_1",
  manifest,verifiedFrames:frames.length,
  expectedFrames:manifest.expectedBars.length,
  coverageComplete:frames.length===manifest.expectedBars.length,
  expectedGridClaimAuthenticatedExternally:false,
  actualSourceProducedAllGeneratedCandidatesProved:false,
  receiptSourceAuthenticatedExternally:false,
  exactNativeOriginalOHLCBrokerFillEquivalenceProved:false,
  finalizedEvidenceHead:previous,
  entries:frames.map(({validated,...rest})=>rest),
  sourceFinancialGO:false,canTrade:false,canOpenM10Final:false,
  N9S:"NO_GO"};
}
function append(dir,input,{now=Date.now()}={}){
 safeDir(dir);
 // An exclusive external lock serializes appenders in DIFFERENT Node processes.
 // Crash leaves the lock behind intentionally: manual repair is required,
 // never silently re-acquire a stale lock and risk rewriting history.
 const lock=dir+".write-lock";
 const fd=fs.openSync(lock,"wx",0o600);
 try{
 const initial=verifyJournal(dir),m=initial.manifest,index=initial.verifiedFrames;
 need(index<m.expectedBars.length,"ALREADY_FULLY_CAPTURED");
 need(input?.barIndex===index,"EXPECTED_NEXT_SCHEDULED_BAR");
 if(m.mode==="PROSPECTIVE_LOCAL_CAPTURE"){
  need(Number.isSafeInteger(now)&&now>0&&
   input.capturedAt===now&&input.barStart>=now&&
   input.barStart-now<=300000,"NOT_ACTUALLY_PREBAR_LOCAL_CAPTURE");
 }
 const checked=S.validatePrebar(input,m);
 if(index>0){
  // Read the previous full original input again. verifyJournal() already
  // checked every older frame and the immutable reservation event prefix.
  const old=initial.entries.at(-1);
  const filename=String(index).padStart(8,"0")+"-"+old.frameHash+".json";
  const raw=JSON.parse(fs.readFileSync(path.join(dir,filename),"utf8"));
  const before=S.validatePrebar(raw.input,m);
  S.continuity(before,checked);
 }
 const body={schema:ARCHIVE,sequence:index+1,previous:initial.finalizedEvidenceHead,
  manifestSeal:m.seal,input:structuredClone(input),
  sourceBookHash:checked.sourceBookHash,
  sourceSnapshotHash:checked.sourceSnapshotHash,
  candidateCount:checked.newGeneratedOpportunityCount,
  captureMode:m.mode,locallyRecordedAt:now,
  brokerOriginIndependentlyVerified:false,
  currentBarFutureDataUsed:false,
  auditScope:"SOURCE_CONTRACT_ONLY_NOT_RUNTIME_TAMPERPROOF_TIMESTAMP",
  executionAllowed:false,N9S:"NO_GO"};
 const hash=S.digest(body),filename=String(index+1).padStart(8,"0")+"-"+hash+".json";
 writeExclusive(path.join(dir,filename),{...body,frameHash:hash});
 return verifyJournal(dir);
 }finally{
  fs.closeSync(fd);
  fs.unlinkSync(lock);
 }
}

function checkScheduleComplete(dir){
 const proof=verifyJournal(dir);
 const pending=proof.manifest.expectedBars.slice(proof.verifiedFrames);
 return {schema:"HARPOON_FWN9_C27_EXHAUSTIVE_BAR_COVERAGE_GATE_1",
  observed:proof.verifiedFrames,planned:proof.expectedFrames,
  missingBars:pending,complete:pending.length===0,
  allOriginalSignalCandidatesIndependentlyAttested:false,
  allPrebarSourceStatesPresentAsCallerProvided:pending.length===0,
  noBarFutureInformationInCommittedFrames:true,
  sourceAttestationAndWallClockIntegrityStillRequired:true,
  originalM10Sealed:3200,
  financialAcceptance:false,N9S:"NO_GO"};
}
/** Exhaustive ORIGINAL M9 synthetic 5-minute grid derived from source sessions,
 * without reading any market OHLC, hidden final account or new seed.
 * Live equity must instead use a verified exchange holiday/DST calendar.
 */
function originalM9Grid(sessions){
 need(Array.isArray(sessions)&&sessions.length>0&&sessions.length<=126,
  "ORIGINAL_M9_SESSION_LIST");
 const bars=[],seen=new Set();
 let priorClose=-1;
 for(const x of sessions){
  need(Number.isSafeInteger(x.open)&&Number.isSafeInteger(x.close)&&
   x.open>0&&x.open>priorClose&&x.close-x.open===78*300000,
   "ORIGINAL_M9_SESSION_78_BARS");
  for(let i=0;i<78;i++){
   const start=x.open+i*300000;
   need(!seen.has(start),"ORIGINAL_M9_DUPLICATE_BAR");
   seen.add(start);bars.push(start);
  }
  priorClose=x.close;
 }
 return {schema:"HARPOON_FWN9_C27_ORIGINAL_REGISTERED_BAR_GRID_1",
  expectedBars:bars,source:"ORIGINAL_M9_SYNTHETIC_SESSION_OPEN_CLOSE_ONLY",
  sourceDataExternallyAuthenticated:false,
  accountPolicySignalDataConsumed:false,
  noMarketSeedOrBarOHLCRead:true,N9S:"NO_GO"};
}
module.exports={newJournal,append,verifyJournal,checkScheduleComplete,originalM9Grid};
