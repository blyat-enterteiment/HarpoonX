"use strict";
const test=require("node:test");
const A=require("node:assert/strict");
const N=require("../runtime30/profit8_replay.js");
const C=require("../runtime30/ultimate_contracts.js");
const {extract,bridge}=require("../runtime30/fwn9_p9l_native_bridge.cjs");
const DAY=86400000,BAR=300000;
function fixture(){
 const sessions=[0,3,4,5,6,7].map(k=>{
  const open=Date.UTC(2025,0,3,14,30)+k*DAY;
  return {date:new Date(open).toISOString().slice(0,10),open,close:open+78*BAR};});
 const series=["SYNA","SYNB"].map(symbol=>({
   symbol,root:symbol,tick:.01,pointValue:1,
   bars:sessions.flatMap(s=>Array.from({length:78},(_,i)=>({
     t:s.open+i*BAR,end:s.open+(i+1)*BAR,availableAt:s.open+(i+1)*BAR+1000,
     o:100,h:100.1,l:99.9,c:100,v:1000
   })))
 }));
 const data={schema:"HARPOON-ULTIMATE-DATA-1",kind:"ALPACA_PROXY",
   sessions,series,splitEvents:[],cashDividends:[],
   provenance:{execution:"MODELED_OHLCV",source:"SYNTHETIC_ENGINEERING_ONLY",
     feed:"SYNTHETIC_FIXTURE",files:[{name:"p9l",sha256:"0".repeat(64)}]}};
 const protocol={...C.defaultProtocol("ALPACA_PROXY"),universe:["SYNA","SYNB"],
   costs:{spreadBps:2,slippageBps:2,perSideUsd:.005}};
 const signal=(symbol,m)=>{
  const at=sessions[0].open+m*60000+1000;
  return {id:symbol+":0:"+m,symbol,at,index:0,
    hypothesis:"CLOSED_CHANNEL",direction:1,
    plannedEntryAt:N.planSignalEntryAt(at,sessions),
    stopDistance:2,regime:.4,
    metadata:{roadmapHorizonHours:72,modulation9:{profile:"NATIVE72"}}};};
 const signals=[signal("SYNA",60),signal("SYNB",90)];
 const limits={...N.PROFIT8_REPLAY_LIMITS,riskFraction:.00125};
 const opts={continuous:true,cashDividends:true,
   entryExecution:"IOC_LIMIT_COMMON_CAUSAL_30BPS",
   externalCostPerSessionUsd:0,calendarCostPerDayUsd:1,
   profit8:{mode:"NATIVE_MAX"},researchModulation:true};
 function tape(symbol,at,open,points){
   let b=series.find(x=>x.symbol===symbol).bars.find(x=>x.t===at);
   A(b);b.o=open;b.h=Math.max(open,...points);b.l=Math.min(open,...points);
   b.c=points[7];
 }
 const run=()=>N.replayFundedPortfolio(signals,data,protocol,
   [{test:sessions,selected:"ALL:BASELINE"}],sessions,limits,opts);
 const args=()=>({native:run(),signals,data,protocol,limits});
 return {data,protocol,limits,opts,signals,sessions,series,tape,run,args};
}
test("P9L L0: exact source reservations and model nature extracted, no invented fills",()=>{
 const f=fixture(),r=extract(f.args());
 A.equal(r.sourceAccepted.length,2);
 A.equal(r.sourceReservations.size,2);
 A(r.operations.some(e=>e.type==="ENTRY_FILL"));
 A(r.operations.some(e=>e.type==="EXIT_FILL"));
 A(r.operations.every(e=>e.knownAt>=e.effectiveAt));
});
test("P9L L1: baseline source native to P9K shared book reconciles",()=>{
 const f=fixture(),r=bridge(f.args());
 A.equal(r.all_source_acceptances_checked,true);
 A.equal(r.source_accepted,2);
 A.equal(r.nativeRiskClockParity,true);
 A.equal(r.nativePriceExecutability,false);
 A.equal(r.optimizerEligible,false);
 A(Math.abs(r.sourceWealthUsd-r.p9kWealthUsd)<1e-6);
});
test("P9L L2: partial source stop/target remains fully reserved",()=>{
 const f=fixture(),at=f.signals[0].plannedEntryAt;
 f.tape("SYNA",at,100,[100.2,102,104,104,104,104,104,104]);
 const r=bridge(f.args());
 A.equal(r.source_accepted,2);
 A.equal(r.nativePriceExecutability,false);
});
test("P9L L3: true native modeled IOC NO_FILL releases without P9K phantom",()=>{
 const f=fixture(),at=f.signals[0].plannedEntryAt;
 f.tape("SYNA",at,150,[150.1,149.9,150,150,150,150,150,150]);
 const r=bridge(f.args());
 A.equal(r.source_nofill,1);
 A.equal(r.source_funded,1);
 A.equal(r.finalSnapshot.positions,0);
});
test("P9L L4: both source IOC NO_FILL reconcile without modeled PnL",()=>{
 const f=fixture();
 for(const s of f.signals)
   f.tape(s.symbol,s.plannedEntryAt,150,[150.1,149.9,150,150,150,150,150,150]);
 const r=bridge(f.args());
 A.equal(r.source_nofill,2);A.equal(r.source_funded,0);
 A.equal(r.finalSnapshot.positions,0);
});
test("P9L L5: tampered source exit quantity rejected before ledger",()=>{
 const f=fixture(),a=f.args(),t=a.native.funded[0];
 const x=t.inventoryEvents.find(x=>x.kind==="EXIT");
 A(x);x.quantityDelta-=1;
 A.throws(()=>bridge(a),/P9L_SOURCE_EXIT_QUANTITY_NOT_CONSERVED|P9K_/);
});
test("P9L L6: unregistered fee or risk source refused",()=>{
 const f=fixture(),a=f.args();
 A.throws(()=>extract({...a,protocol:{...a.protocol,
   costs:{...a.protocol.costs,perSideUsd:0}}}),
   /P9L_REGISTERED_ENGINEERING_SCOPE_ONLY/);
 A.throws(()=>extract({...a,limits:{...a.limits,grossFraction:.13}}),
   /P9L_ORIGINAL_RISK_LIMITS_REQUIRED/);
});
test("P9L L7: source reservation mutation caught by immutable commitment check",()=>{
 const f=fixture(),a=f.args();
 a.native.reservationBook.reservations[0].riskUsd+=1;
 A.throws(()=>bridge(a),/P9L_SOURCE_RESERVATION_CONTRACT_MISMATCH/);
});
test("P9L L8: deliberate missing signal disposition causes rejection",()=>{
 const f=fixture(),a=f.args();
 a.native.states=[];a.native.preEntryRefusals=[];
 A.throws(()=>extract(a),/P9L_MISSING_SOURCE_DISPOSITION/);
});
if(process.argv.includes("--emit-audit")){
 const f=fixture(),r=bridge(f.args());
 console.log("P9L_AUDIT="+JSON.stringify({
    schema:r.schema,sourceNature:r.sourceNature,
    accepted:r.source_accepted,funded:r.source_funded,receiptTape:r.sourceReceiptTape,
    nofill:r.source_nofill,events:r.bridge_events,
    sourceWealthUsd:r.sourceWealthUsd,shadowWealthUsd:r.p9kWealthUsd,
    decisions:r.native_ledger_decisions,
    noBroker:true,noFutureFills:true,optimizerEligible:r.optimizerEligible,
    nativePriceExecutability:r.nativePriceExecutability,
    finalSnapshot:r.finalSnapshot
  }));
}

const fs=require("node:fs"),os=require("node:os"),path=require("node:path");
const {spawnSync}=require("node:child_process");
const Journal=require("./fwn9_p9l_checkpoint.cjs");
test("P9L L9: bounded read-only checkpoint commits once and validates on restart",()=>{
 const r=bridge(fixture().args()),dir=fs.mkdtempSync(path.join(os.tmpdir(),"p9l-"));
 try{
   const file=path.join(dir,"research.json"),proof=path.join(dir,"proof.json");
   fs.writeFileSync(proof,JSON.stringify(r));
   const binding=Journal.sha({source:"M9-frozen",phase:"P9L"});
   const first=Journal.commit(file,binding,"M11_P9L_NATIVE_FIXTURE",r);
   A.equal(first.status,"COMMITTED");
   A.equal(Journal.commit(file,binding,"M11_P9L_NATIVE_FIXTURE",r).status,"UNCHANGED");
   const script='const J=require(process.argv[1]);const fs=require("node:fs");'+
      'const r=JSON.parse(fs.readFileSync(process.argv[4],"utf8"));'+
      'const result=J.commit(process.argv[2],process.argv[3],'+
      '"M11_P9L_NATIVE_FIXTURE",r);'+
      'process.stdout.write(JSON.stringify(result));';
   const p=spawnSync(process.execPath,["-e",script,
     path.resolve(__dirname,"fwn9_p9l_checkpoint.cjs"),file,binding,proof],{
     encoding:"utf8",timeout:10000});
   A.equal(p.status,0,p.stderr);
   A.equal(JSON.parse(p.stdout).status,"UNCHANGED");
   A.equal(Journal.unpack(file,binding).entries.length,1);
 }finally{fs.rmSync(dir,{recursive:true,force:true});}
});
test("P9L L10: changed proof or corrupted committed journal fails closed",()=>{
 const r=bridge(fixture().args()),dir=fs.mkdtempSync(path.join(os.tmpdir(),"p9l-"));
 try{
   const file=path.join(dir,"checkpoint.json"),binding=Journal.sha("source");
   Journal.commit(file,binding,"case-1",r);
   const different=structuredClone(r);different.sourceReceiptTape[0].price+=.01;
   A.throws(()=>Journal.commit(file,binding,"case-1",different),
     /P9L_JOURNAL_ID_REUSED_WITH_DIFFERENT_EVIDENCE/);
   const corrupt=JSON.parse(fs.readFileSync(file));
   corrupt.entries[0].evidenceHash="f".repeat(64);
   fs.writeFileSync(file,JSON.stringify(corrupt));
   A.throws(()=>Journal.unpack(file,binding),/P9L_JOURNAL_ENTRY_CHECKSUM/);
 }finally{fs.rmSync(dir,{recursive:true,force:true});}
});
test("P9L L11: modeled source cannot auto-feed recursive optimizer or place orders",()=>{
 const r=bridge(fixture().args());
 const gate=Journal.holdoutGate(r);
 A.equal(gate.execution_allowed,false);
 A.equal(gate.optimizer_input_validated,false);
 A.equal(gate.status,"WAIT_OBSERVED_COMPLETED_OPPORTUNITIES");
 A.throws(()=>Journal.holdoutGate({...r,sourceNature:"OBSERVED_BROKER_FILL"}),
   /P9L_JOURNAL_SOURCE_NATURE_REQUIRED/);
});
