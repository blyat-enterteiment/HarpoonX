"use strict";
/** No clock manipulation outside synthetic local fixtures, no broker or market. */
const test=require("node:test"),A=require("node:assert/strict");
const fs=require("node:fs"),os=require("node:os"),path=require("node:path");
const CLI=require("./fwn9_c29_plan_cli.cjs");
const TEST_NOW=Date.parse("2026-11-10T20:00:00Z");
function privateFixture(fn){
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),"fwn9-c29-local-"));
 try{
  const plan=path.join(dir,"frozen.json"),design=path.join(dir,"design.json");
  fs.writeFileSync(design,JSON.stringify({
   studyId:"ENGINEERING_ONLY_C29",cycles:4,
   startAt:TEST_NOW+73*3600000,
   assignmentNonce:"SYNTHETIC_EXPERIMENTAL_ASSIGNMENT_NOT_MARKET_SEED_2026"
  }),{mode:0o600});
  return fn({dir,plan,design});
 }finally{fs.rmSync(dir,{recursive:true,force:true});}
}
test("C29 CLI --freeze uses local clock not user editable registration timestamp",()=>privateFixture(d=>{
 const x=CLI.run(["--freeze",d.design,"--out",d.plan],{now:()=>TEST_NOW});
 A.equal(x.phase,"FROZEN_LOCALLY_NOT_INDEPENDENTLY_TIMESTAMPED");
 A.equal(x.registeredAt,TEST_NOW);
 A.equal(x.plannedBlocks,32);
 A.equal(x.ordersPlaced,0);
 A.equal(x.nonceNotPrinted,true);
 A.equal(fs.statSync(d.plan).mode&0o777,0o600);
 const body=fs.readFileSync(d.plan,"utf8");
 A.equal(body.includes("SYNTHETIC_EXPERIMENTAL_ASSIGNMENT_NOT"),false);
}));
test("C29 CLI reloads and validates full block hash at restart",()=>privateFixture(d=>{
 const initial=CLI.run(["--freeze",d.design,"--out",d.plan],{now:()=>TEST_NOW});
 const x=CLI.run(["--verify",d.plan]);
 A.equal(x.digest,initial.digest);
 A.equal(x.independentTimeAnchorVerified,false);
 A.equal(x.N9S,"NO_GO");
}));
test("C29 CLI never overwrites registered study plan",()=>privateFixture(d=>{
 CLI.run(["--freeze",d.design,"--out",d.plan],{now:()=>TEST_NOW});
 A.throws(()=>CLI.run(["--freeze",d.design,"--out",d.plan],
  {now:()=>TEST_NOW}),/EEXIST/);
}));
test("C29 CLI rejects retroactive or too-soon first block",()=>privateFixture(d=>{
 const body=JSON.parse(fs.readFileSync(d.design,"utf8"));
 body.startAt=TEST_NOW+60*3600000;
 fs.writeFileSync(d.design,JSON.stringify(body));
 A.throws(()=>CLI.run(["--freeze",d.design,"--out",d.plan],
  {now:()=>TEST_NOW}),/C29CLI_AT_LEAST_72H_PROSPECTIVE_CLOCK/);
}));
test("C29 CLI refuses sealed M10 paths and public group-readable design",()=>privateFixture(d=>{
 A.throws(()=>CLI.safe("/tmp/holdout/heads.json"),/C29CLI_FINAL_M10_FORBIDDEN/);
 fs.chmodSync(d.design,0o644);
 A.throws(()=>CLI.run(["--freeze",d.design,"--out",d.plan],
  {now:()=>TEST_NOW}),/C29CLI_PRIVATE_0600_FILE/);
}));
test("C29 CLI does not leak account, nonce or credentials in results",()=>privateFixture(d=>{
 const x=CLI.run(["--freeze",d.design,"--out",d.plan],{now:()=>TEST_NOW});
 const v=JSON.stringify(x);
 A.equal(x.portfolioInitialCapitalUsd,20000);
 A.equal(x.brokerKeysNotRead,true);
 A.equal(x.accountNotCreated,true);
 A.equal(v.includes("SYNTHETIC_EXPERIMENTAL_ASSIGNMENT"),false);
 A.equal(v.includes("APCA_API_KEY_ID"),false);
}));
