"use strict";
/** C28 test fixtures are independent local source-account examples only. */
const test=require("node:test"),A=require("node:assert/strict");
const fs=require("node:fs"),os=require("node:os"),path=require("node:path");
const F=require("./fwn9_c27_test_fixture.cjs");
const J=require("../runtime30/fwn9_c27_prebar_journal.cjs");
const S=require("../runtime30/fwn9_c28_source_obligations.cjs");
const CLI=require("./fwn9_c28_readonly_cli.cjs");
const registry=[{symbol:"SYNA",book:"equity"},{symbol:"SYNB",book:"equity"}];
const t=F.BARS[0],calendar=[{date:new Date(t).toISOString().slice(0,10),
 open:t,close:t+78*300000}];
function writePrivate(p,v){fs.writeFileSync(p,JSON.stringify(v)+"\n",{flag:"wx",mode:0o600});}
function withC27(fn){
 const tmp=fs.mkdtempSync(path.join(os.tmpdir(),"c28cli-private-"));
 const c27=path.join(tmp,"c27"),tap=path.join(tmp,"sidecar");
 try{
  const f=F.sample();J.newJournal(c27,F.manifest());
  for(const r of f.frames)J.append(c27,r);
  const reg=path.join(tmp,"registry.json"),cal=path.join(tmp,"calendar.json");
  writePrivate(reg,registry);writePrivate(cal,calendar);
  return fn({tmp,c27,tap,reg,cal,frames:f.frames});
 }finally{fs.rmSync(tmp,{recursive:true,force:true});}
}
function makeTaps(r){
 const source=r.opportunityCoverage.outcomes;
 return S.obligations({barStart:r.barStart,registry,calendar}).map(o=>
  S.makeTap({obligation:o,sourceCall:o.requiredEvaluation?()=>
   source.filter(x=>x.symbol===o.symbol&&x.policyId===o.policyId)
    .map(x=>({id:x.id,policyId:x.policyId,symbol:x.symbol})):null,
   now:()=>r.barStart-1000}));
}
test("C28 CLI initializes private fixed source manifest and reports no financial GO",()=>withC27(d=>{
 const r=CLI.run(["--init",d.tap,"--c27",d.c27,
  "--registry",d.reg,"--calendar",d.cal]);
 A.equal(r.sourceTapFrames,0);
 A.equal(r.completeSourceTapSchedule,false);
 A.equal(r.noBrokerOrderOrMarketGeneratorCalled,true);
 A.equal(r.financialGO,false);
 A.equal(r.N9S,"NO_GO");
}));
test("C28 CLI complete three prebar tap chain and reload after cold restart",()=>withC27(d=>{
 CLI.run(["--init",d.tap,"--c27",d.c27,
  "--registry",d.reg,"--calendar",d.cal]);
 for(let i=0;i<3;i++){
  const file=path.join(d.tmp,"source-"+i+".json");
  writePrivate(file,makeTaps(d.frames[i]));
  const r=CLI.run(["--append",d.tap,"--c27",d.c27,"--taps",file]);
  A.equal(r.sourceTapFrames,i+1);
 }
 const result=CLI.run(["--verify",d.tap,"--c27",d.c27]);
 A.equal(result.sourceTapFrames,3);
 A.equal(result.completeSourceTapSchedule,true);
 A.equal(result.storedPrivateAccountFieldsPrinted,false);
 A.match(result.sourceTapHeadSha256,/^[a-f0-9]{64}$/);
}));
test("C28 CLI refuses a group-readable raw source-tap JSON",()=>withC27(d=>{
 CLI.run(["--init",d.tap,"--c27",d.c27,
  "--registry",d.reg,"--calendar",d.cal]);
 const p=path.join(d.tmp,"untrusted.json");writePrivate(p,makeTaps(d.frames[0]));
 fs.chmodSync(p,0o644);
 A.throws(()=>CLI.run(["--append",d.tap,"--c27",d.c27,"--taps",p]),
  /C28CLI_PRIVATE_SOURCE_0600/);
}));
test("C28 CLI never reads a sealed final/holdout path",()=>{
 for(const p of ["/tmp/holdout/accounts.json",
  "/tmp/M10_final/account.json",
  "/tmp/evidence/modulation9/final/ACCOUNT.json"])
  A.throws(()=>CLI.safe(p),/C28CLI_SEALED_FINAL_PATH/);
});
test("C28 CLI refuses missing source registry or arbitrary command",()=>{
 A.throws(()=>CLI.options(["--merge","/tmp/sidecar","--c27","/tmp/c27"]),
  /C28CLI_OPERATION/);
 A.throws(()=>CLI.options(["--init","/tmp/sidecar","--c27","/tmp/c27"]),
  /C28CLI_INIT_ARGUMENTS/);
 A.throws(()=>CLI.options(["--verify","/tmp/taps","--c27","/tmp/c27",
  "--taps","/tmp/false"]),/C28CLI_VERIFY_ARGUMENTS/);
});
test("C28 CLI unknown or extra source taps fail without writing a sidecar frame",()=>withC27(d=>{
 CLI.run(["--init",d.tap,"--c27",d.c27,
  "--registry",d.reg,"--calendar",d.cal]);
 const p=path.join(d.tmp,"bad-taps.json"),taps=makeTaps(d.frames[0]);
 taps.pop();
 writePrivate(p,taps);
 A.throws(()=>CLI.run(["--append",d.tap,"--c27",d.c27,"--taps",p]),
  /C28_SLOT_COUNT_MISMATCH/);
 const proof=CLI.run(["--verify",d.tap,"--c27",d.c27]);
 A.equal(proof.sourceTapFrames,0);
}));
