"use strict";
const test=require("node:test"),assert=require("node:assert/strict"),fs=require("node:fs"),os=require("node:os"),path=require("node:path");
const {deriveLevel5,verifyLevel5Derivation,derivePolicies,stressBinding,applyCostSchedule}=require("./level5_readiness.cjs");
const {makeLevel5Fixture,write}=require("./fixtures/level5_fixture.cjs");
const {hash}=require("./coordinator_replay.cjs");
let root,fixture;
test.after(()=>{if(root)fs.rmSync(root,{recursive:true,force:true});});
test("synthetic complete base and stress reexecute all policies and preserve authority",async()=>{
  root=fs.mkdtempSync(path.join(os.tmpdir(),"hx-l5-"));fixture=await makeLevel5Fixture(root);
  const d=fixture.derived;assert.equal(d.complete_derived_comparison,true);assert.equal(d.stress.length,1);
  assert.deepEqual(Object.keys(d.policies),["NATIVE","RIDGE","SVR","CASH"]);
  assert(d.stress[0].verification.real_coordinator_and_predictors_reexecuted);assert.equal(d.financial_acceptance_allowed,false);
  assert.equal(d.readiness.score,3);assert(d.financial_blockers.includes("OBSERVED_REGISTERED_MEASUREMENT_REQUIRED"));
  assert(d.financial_blockers.includes("STRESS_SIX_SLOT_RESERVATIONS_NOT_VERIFIED"));
});
test("NATIVE remains invested while CASH has same costs and no fictitious interest",()=>{
  const p=fixture.derived.policies;assert(p.NATIVE.events.at(-1).positions.length>0);
  const c=p.CASH.events.at(-1);assert.equal(c.positions.length,0);assert.equal(c.cumulative_fees_usd,0);
  assert.equal(c.cumulative_external_cost_usd,p.SVR.events.at(-1).cumulative_external_cost_usd);
  assert.equal(c.economic_equity_usd,c.account_equity_usd-c.cumulative_external_cost_usd);
  assert.equal(p.CASH.research_slots_added,0);
});
test("stress cannot alter predictor, signals, timestamps, capital or reduce costs",()=>{
  for(const mutate of [x=>x.models.RIDGE.intercept=123,x=>x.common_request.events[0].at++,x=>x.common_request.initial_cash_usd++,x=>x.common_request.execution_model.external_cost_usd++]){
    const s=structuredClone(fixture.stress);mutate(s);assert.throws(()=>stressBinding(fixture.base,s),/STRESS_CHANGED/);
  }
  const s=structuredClone(fixture.stress);s.common_request.execution_model.slippage_bps=-1;
  assert.throws(()=>stressBinding(fixture.base,s),/STRESS_MUST_NOT_REDUCE/);
});
test("a rehashed forged profit is rejected by complete replay",async()=>{
  const request=structuredClone(fixture.request),report=structuredClone(fixture.baseReport);
  report.curves.SVR.curve.at(-1).economic_equity_usd+=1000;report.artifact_hash=hash({...report,artifact_hash:undefined});
  const l4=JSON.parse(fs.readFileSync(path.join(root,"level4_request.json"),"utf8"));l4.comparison.report=write(root,"forged_report.json",report);
  request.level4.request=write(root,"forged_level4.json",l4);
  const out=await deriveLevel5(request,root);assert.equal(out.policies,null);assert.equal(out.complete_derived_comparison,false);
});
test("cash insolvency is retained without borrowing or a terminal forced sale",()=>{
  const r=structuredClone(fixture.baseReport),input=structuredClone(fixture.base);
  for(const curve of Object.values(r.curves)){curve.curve.at(-1).cumulative_external_cost_usd=30000;curve.curve.at(-1).economic_equity_usd-=29999;}
  const p=derivePolicies(input,r);assert.equal(p.CASH.events.at(-1).economic_equity_usd,-10000);
  assert.equal(p.CASH.events.at(-1).cash_usd,20000);assert.equal(p.SVR.terminal_inventory_forced_closed,false);
});
test("weekend accrual preserves its timestamp and belongs to next observed session",()=>{
  const friday=Date.parse("2026-10-16T20:00:00Z"),saturday=Date.parse("2026-10-17T12:00:00Z"),monday=Date.parse("2026-10-19T20:00:00Z");
  const rows=[{event_id:"f",at:friday,session_id:"2026-10-16",cash_usd:100,inventory_value_usd:0,account_equity_usd:100,cumulative_fees_usd:0,positions:[],external_flow_usd:0},
    {event_id:"m",at:monday,session_id:"2026-10-19",cash_usd:100,inventory_value_usd:0,account_equity_usd:100,cumulative_fees_usd:0,positions:[],external_flow_usd:0}];
  const out=applyCostSchedule(rows,[{id:"hosting",at:saturday,amount_usd:3}],100,friday);
  assert.equal(out[1].at,saturday);assert.equal(out[1].session_id,"2026-10-19");assert.equal(out[1].economic_equity_usd,97);
  assert.equal(out[1].valuation_carried_for_cost_event,true);assert.equal(out.at(-1).cumulative_external_cost_usd,3);
});
test("cost schedule deducts fees once and keeps original account NAV",()=>{
  const report=fixture.baseReport,rows=report.curves.SVR.curve,last=rows.at(-1),at=rows[2].at;
  const p=derivePolicies(fixture.base,report,[{id:"infra",at,amount_usd:1}]);
  assert.equal(p.SVR.events.at(-1).account_equity_usd,last.account_equity_usd);
  assert.equal(p.SVR.events.at(-1).economic_equity_usd,last.account_equity_usd-1);
  assert.equal(p.SVR.events.at(-1).cumulative_fees_usd,last.cumulative_fees_usd);
  assert(p.SVR.events.find(r=>r.event_id==="COST:infra"));
});
test("unknown evidence stays null and caller curves or a seventh slot are rejected",async()=>{
  const empty={schema:"HARPOON_LEVEL5_DERIVATION_REQUEST_1",level4:{request:null},stress:[]};
  const out=await deriveLevel5(empty,root);assert.equal(out.policies,null);assert.equal(out.bindings,null);assert.equal(out.execution_allowed,false);
  await assert.rejects(deriveLevel5({...empty,curves:{}},root),/CALLER_CURVES_NOT_ACCEPTED/);
  const tooMany=structuredClone(fixture.request);tooMany.stress.push(tooMany.stress[0]);
  const blocked=await deriveLevel5(tooMany,root);assert(blocked.financial_blockers.some(x=>x.includes("STRESS_FAMILY_MAXIMUM")));
});
test("derivation verification reproduces source artifacts and rejects fabricated approval",async()=>{
  const report=structuredClone(fixture.derived);report.financial_acceptance_allowed=true;report.artifact_hash=hash({...report,artifact_hash:undefined});
  const out=await verifyLevel5Derivation(fixture.request,report,root);assert.equal(out.verified,false);assert.equal(out.financial_acceptance_allowed,false);
});
