"use strict";
const test=require("node:test"),A=require("node:assert/strict");
const fs=require("node:fs"),os=require("node:os"),path=require("node:path");
const F=require("./fwn9_c27_test_fixture.cjs");
const CLI=require("./fwn9_c27_prebar_cli.cjs");
function privateTmp(fn){
 const p=fs.mkdtempSync(path.join(os.tmpdir(),"c27cli-"));
 fs.chmodSync(p,0o700);
 try{return fn(p);}finally{fs.rmSync(p,{recursive:true,force:true});}
}
function privateJson(p,x){fs.writeFileSync(p,JSON.stringify(x)+"\n",{flag:"wx",mode:0o600});}
test("C27 CLI verifies three prebar frames with zero leaked identifiers or capital",()=>privateTmp(dir=>{
 const journal=path.join(dir,"source-journal"),grid=path.join(dir,"grid.json");
 privateJson(grid,F.manifest());
 A.equal(CLI.execute(["--init",journal,"--manifest",grid]).framesVerified,0);
 const frames=F.sample().frames;
 for(let i=0;i<3;i++){
  const file=path.join(dir,"frame-"+i+".json");
  privateJson(file,frames[i]);
  A.equal(CLI.execute(["--append",journal,"--input",file]).framesVerified,i+1);
 }
 const end=CLI.execute(["--verify",journal]);
 A.equal(end.sourceFrameCoverageComplete,true);
 A.equal(end.expectedScheduledBars,3);
 A.equal(end.N9S,"NO_GO");
 A.equal(end.hasTradeOrBrokerAction,false);
 A.equal(end.noAccountIdentifiersOrPortfolioValuesPrinted,true);
 A.equal(JSON.stringify(end).includes("20000"),false);
}));
test("C27 CLI manifest/input must be private mode0600, not group-readable",()=>privateTmp(dir=>{
 const file=path.join(dir,"grid.json");
 privateJson(file,F.manifest());fs.chmodSync(file,0o644);
 A.throws(()=>CLI.execute(["--init",path.join(dir,"journal"),"--manifest",file]),
  /C27CLI_PRIVATE_INPUT_0600/);
}));
test("C27 CLI never reads M10/holdout paths even with valid-looking JSON",()=>{
 A.throws(()=>CLI.guard("/tmp/holdout/secret.json"),
  /C27CLI_SEALED_FINAL_PATH/);
 A.throws(()=>CLI.guard("/tmp/M10_final/secret.json"),
  /C27CLI_SEALED_FINAL_PATH/);
});
test("C27 CLI rejects arbitrary commands, mixed path args and self declared live GO",()=>{
 A.throws(()=>CLI.options(["--trade","/tmp/x"]),/C27CLI_ACTION/);
 A.throws(()=>CLI.options(["--verify","/tmp/x","--input","/tmp/y"]),
  /C27CLI_VERIFY_ARGS/);
 A.throws(()=>CLI.options(["--append","/tmp/x","--manifest","/tmp/y"]),
  /C27CLI_SOURCE_ARGS/);
});
test("C27 CLI prospective capture overwrites user-supplied fake capture timestamp",()=>privateTmp(dir=>{
 const m=F.manifest({mode:"PROSPECTIVE_LOCAL_CAPTURE"});
 const upcoming=Date.now()+60000;
 m.expectedBars=[upcoming];
 const grid=path.join(dir,"grid.json"),frame=path.join(dir,"frame.json"),
  journal=path.join(dir,"journal");
 privateJson(grid,m);
 CLI.execute(["--init",journal,"--manifest",grid]);
 const input=F.sample().frames[0];
 input.mode="PROSPECTIVE_LOCAL_CAPTURE";
 input.barStart=upcoming;input.capturedAt=1;
 privateJson(frame,input);
 const result=CLI.execute(["--append",journal,"--input",frame]);
 A.equal(result.sourceFrameCoverageComplete,true);
 A.equal(result.sourceProviderAuthenticated,false);
}));
test("C27 CLI incomplete schedule reports false until all listed source bars",()=>privateTmp(dir=>{
 const m=F.manifest(),grid=path.join(dir,"grid.json"),
  frame=path.join(dir,"first.json"),journal=path.join(dir,"journal");
 privateJson(grid,m);privateJson(frame,F.sample().frames[0]);
 CLI.execute(["--init",journal,"--manifest",grid]);
 CLI.execute(["--append",journal,"--input",frame]);
 const proof=CLI.execute(["--verify",journal]);
 A.equal(proof.framesVerified,1);
 A.equal(proof.expectedScheduledBars,3);
 A.equal(proof.sourceFrameCoverageComplete,false);
}));
