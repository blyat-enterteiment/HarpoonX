"use strict";
/** C27 journal crash/restart/tamper tests only, no broker or market work. */
const test=require("node:test"),A=require("node:assert/strict");
const fs=require("node:fs"),os=require("node:os"),path=require("node:path");
const J=require("../runtime30/fwn9_c27_prebar_journal.cjs");
const S=require("../runtime30/fwn9_c27_prebar_state.cjs");
const F=require("./fwn9_c27_test_fixture.cjs");
function temp(action){
 const parent=fs.mkdtempSync(path.join(os.tmpdir(),"c27-private-"));
 const root=path.join(parent,"journal");
 try{return action(root,parent);}finally{fs.rmSync(parent,{recursive:true,force:true});}
}
function start(root,opts={}){return J.newJournal(root,{...F.manifest(),...opts});}
function fill(root,n=3){const data=F.sample();start(root);
 for(let i=0;i<n;i++)J.append(root,data.frames[i]);
 return data;
}
function names(root){return fs.readdirSync(root).filter(x=>x!=="manifest.json").sort();}
test("C27 creation seals exact source hash, six C22 variants plus CASH/original",()=>temp(dir=>{
 const r=start(dir);
 A.equal(r.verifiedFrames,0);
 A.equal(r.expectedFrames,3);
 A.equal(r.coverageComplete,false);
 A.equal(r.manifest.generatorHash,F.SOURCE_HASH);
 A.equal(r.manifest.policyIds.length,8);
 A.equal(r.N9S,"NO_GO");
 A.equal(fs.statSync(dir).mode&0o777,0o700);
 A.equal(fs.statSync(path.join(dir,"manifest.json")).mode&0o777,0o600);
}));
test("C27 append all three causal bars reaches exact expected grid, nothing future",()=>temp(dir=>{
 const sample=fill(dir);
 const r=J.verifyJournal(dir),gate=J.checkScheduleComplete(dir);
 A.equal(r.verifiedFrames,3);
 A.equal(r.coverageComplete,true);
 A.equal(gate.complete,true);
 A.equal(gate.missingBars.length,0);
 A.equal(gate.financialAcceptance,false);
 A.equal(r.expectedGridClaimAuthenticatedExternally,false);
 A.equal(r.actualSourceProducedAllGeneratedCandidatesProved,false);
 A.deepEqual(r.entries.map(x=>x.barStart),F.BARS);
 A.equal(r.entries[1].candidateOutcomes.REFUSED,1);
 A.equal(r.entries[2].candidateOutcomes.RESERVED,0);
 A.equal(sample.sourceBooks.length,3);
}));
test("C27 restart validates entire chain without needing live in-memory state",()=>temp(dir=>{
 fill(dir,2);
 const after=J.verifyJournal(dir);
 A.equal(after.verifiedFrames,2);
 J.append(dir,F.sample().frames[2]);
 const now=J.verifyJournal(dir);
 A.equal(now.verifiedFrames,3);
 A.equal(now.entries[1].previousHash,now.entries[0].frameHash);
 A.equal(now.entries[2].previousHash,now.entries[1].frameHash);
}));
test("C27 partial period reports exactly missing scheduled bars, never full proof",()=>temp(dir=>{
 fill(dir,1);
 const r=J.checkScheduleComplete(dir);
 A.deepEqual(r.missingBars,F.BARS.slice(1));
 A.equal(r.complete,false);
 A.equal(r.originalM10Sealed,3200);
}));
test("C27 cannot insert a third bar before second, or duplicate first bar",()=>temp(dir=>{
 const f=F.sample();start(dir);
 A.throws(()=>J.append(dir,f.frames[2]),/C27J_EXPECTED_NEXT_SCHEDULED_BAR/);
 J.append(dir,f.frames[0]);
 A.throws(()=>J.append(dir,f.frames[0]),/C27J_EXPECTED_NEXT_SCHEDULED_BAR/);
}));
test("C27 cannot append an extra unregistered bar after complete period",()=>temp(dir=>{
 fill(dir);
 A.throws(()=>J.append(dir,F.sample().frames[2]),/C27J_ALREADY_FULLY_CAPTURED/);
}));
test("C27 cannot create second journal atop existing manifest",()=>temp(dir=>{
 start(dir);
 A.throws(()=>start(dir),/C27J_NO_OVERWRITE_JOURNAL_DIRECTORY/);
}));
test("C27 edits to JSON without resealing SHA are detected on reload",()=>temp(dir=>{
 fill(dir,2);
 const file=path.join(dir,names(dir)[1]);
 const row=JSON.parse(fs.readFileSync(file,"utf8"));
 row.input.positions[0].stop.price=10;
 fs.writeFileSync(file,JSON.stringify(row)+"\n",{mode:0o600});
 A.throws(()=>J.verifyJournal(dir),/C27J_FRAME_TAMPERED/);
}));
test("C27 tampered source-book reservation fails as hash/content mismatch",()=>temp(dir=>{
 fill(dir,2);
 const file=path.join(dir,names(dir)[1]),row=JSON.parse(fs.readFileSync(file,"utf8"));
 row.input.sourceReservationBook.reservations[0].notionalUsd=300;
 fs.writeFileSync(file,JSON.stringify(row)+"\n");
 A.throws(()=>J.verifyJournal(dir),/C27J_FRAME_TAMPERED/);
}));
test("C27 deletion of any middle frame cannot silently count complete",()=>temp(dir=>{
 fill(dir);
 fs.unlinkSync(path.join(dir,names(dir)[1]));
 A.throws(()=>J.verifyJournal(dir),/C27J_FILE_SEQUENCE_GAP_OR_FOREIGN_FILE/);
}));
test("C27 truncated interrupted frame fails closed rather than auto-repair",()=>temp(dir=>{
 fill(dir,1);
 const index="00000002-"+"a".repeat(64)+".json";
 fs.writeFileSync(path.join(dir,index),"{",{mode:0o600});
 A.throws(()=>J.verifyJournal(dir),/SyntaxError|C27J_FRAME_HEADER_OR_HISTORY/);
 A.throws(()=>J.append(dir,F.sample().frames[1]),/SyntaxError|C27J_FRAME_HEADER_OR_HISTORY/);
}));
test("C27 unknown file in journal is not silently ignored",()=>temp(dir=>{
 fill(dir,1);
 fs.writeFileSync(path.join(dir,"altered.txt"),"PLACEHOLDER");
 A.throws(()=>J.verifyJournal(dir),/C27J_FILE_SEQUENCE_GAP_OR_FOREIGN_FILE/);
}));
test("C27 world-readable frame invalidates private journal recovery",()=>temp(dir=>{
 fill(dir,1);
 const file=path.join(dir,names(dir)[0]);
 fs.chmodSync(file,0o644);
 A.throws(()=>J.verifyJournal(dir),/C27J_FRAME_FILE_PERMISSIONS_OR_SIZE/);
}));
test("C27 world-readable directory invalidates entire journal",()=>temp(dir=>{
 fill(dir,1);
 fs.chmodSync(dir,0o755);
 A.throws(()=>J.verifyJournal(dir),/C27J_DIRECTORY_MUST_BE_PRIVATE_0700/);
 fs.chmodSync(dir,0o700);
}));
test("C27 first previous pointer and source SHA are cryptographically checked",()=>temp(dir=>{
 fill(dir,1);
 const file=path.join(dir,names(dir)[0]),row=JSON.parse(fs.readFileSync(file,"utf8"));
 A.equal(row.previous,"GENESIS");
 A.match(row.frameHash,/^[0-9a-f]{64}$/);
 A.equal(row.manifestSeal,J.verifyJournal(dir).manifest.seal);
}));
test("C27 manifests reject unauthorized source hash and nonmonotone clocks",()=>temp(dir=>{
 A.throws(()=>J.newJournal(dir,{...F.manifest(),generatorHash:"b".repeat(64)}),
  /C27J_SOURCE_GENERATOR_HASH/);
 const y=path.join(path.dirname(dir),"journal-good");
 A.throws(()=>J.newJournal(y,{...F.manifest(),expectedBars:[F.BARS[0],F.BARS[0]]}),
  /C27J_MANIFEST_NONMONOTONE_GRID/);
}));
test("C27 mandatory live capture clock rejects retroactive claimed prebar",()=>temp(dir=>{
 start(dir,{mode:"PROSPECTIVE_LOCAL_CAPTURE"});
 const x=F.sample().frames[0];
 x.mode="PROSPECTIVE_LOCAL_CAPTURE";
 A.throws(()=>J.append(dir,x,{now:Date.now()}),
  /C27J_NOT_ACTUALLY_PREBAR_LOCAL_CAPTURE/);
}));
test("C27 locally prospective bar can be recorded only at a future planned time",()=>temp(dir=>{
 const bar=Date.now()+30000;
 const m={...F.manifest({mode:"PROSPECTIVE_LOCAL_CAPTURE"}),expectedBars:[bar]};
 J.newJournal(dir,m);
 const x=F.sample().frames[0];
 x.mode="PROSPECTIVE_LOCAL_CAPTURE";x.barStart=bar;
 x.capturedAt=bar-30000;x.lastPublicKnownAt=bar-30000;
 // source book empty, physical book matches; this only tests time plumbing.
 J.append(dir,x,{now:bar-30000});
 const r=J.checkScheduleComplete(dir);
 A.equal(r.complete,true);
 A.equal(r.sourceAttestationAndWallClockIntegrityStillRequired,true);
 A.equal(r.financialAcceptance,false);
}));
test("C27 appended source history may not retrospectively loosen a stop",()=>temp(dir=>{
 const x=F.sample();start(dir);
 J.append(dir,x.frames[0]);J.append(dir,x.frames[1]);
 const third=structuredClone(x.frames[2]);
 third.positions[0].stop.price=90;
 A.throws(()=>J.append(dir,third),/C27_LONG_STOP_LOOSENED_OR_CLOCK_REGRESSION/);
}));
test("C27 source event history append-only: disappearing old observations rejected",()=>temp(dir=>{
 const x=F.sample();start(dir);
 J.append(dir,x.frames[0]);J.append(dir,x.frames[1]);
 const third=structuredClone(x.frames[2]);
 third.sourceReservationBook.reservations[0].observations.splice(0,1);
 A.throws(()=>J.append(dir,third),
  /C27_RESERVATION_HISTORY_REWRITTEN|C27_OBSERVED_RECEIPT_RESTATED|C27_POSITION_NOT_SOURCE_OPEN_REMAINING/);
}));
test("C27 local SHA journaling cannot certify complete broker source coverage",()=>temp(dir=>{
 fill(dir);
 const r=J.verifyJournal(dir);
 A.equal(r.receiptSourceAuthenticatedExternally,false);
 A.equal(r.sourceFinancialGO,false);
 A.equal(r.canTrade,false);
 A.equal(r.canOpenM10Final,false);
 A.equal(r.originalM10FinalSealed,undefined);
}));
