"use strict";
// Only synthetic regression tests, not additional financial research attempts.
const test=require("node:test"),assert=require("node:assert/strict");
const fs=require("node:fs"),path=require("node:path"),crypto=require("node:crypto");
const {hash,canonical,executeReplay}=require("./coordinator_replay.cjs");
const {comparisonReadiness,runFundedComparison,verifyFundedComparison,registrationBinding,fundedCurves}=require("./funded_comparison.cjs");
const {syntheticComparison}=require("./fixtures/funded_comparison_fixture.cjs");
function runtimeSnapshot(common,symbol="AAPL",ask=101.11){
  const market=common.events[0];
  return {runtime_snapshot:true,now:common.start_at+1,config:common.config,account:{equity:20000,cash:20000,buying_power:20000},positions:[],pending:[],daily_pnl:0,drawdown_fraction:0,
    signals:[{symbol,plugin:"synthetic-saved-model-check",entry:ask,max_qty:5}],
    market:{assets:{[symbol]:{...common.config.universe[0],symbol}},bars:{...market.bars,[symbol]:market.bars.AAPL},
      quotes:{[symbol]:{bid:101.1,ask,at:common.start_at,received:common.start_at}},
      calendar:common.calendar.map(s=>({date:s.date,open:Date.parse(s.date+"T13:30:00Z"),close:Date.parse(s.date+"T20:00:00Z")}))}};
}
let completed;
async function fixtureResult(){if(!completed)completed=await runFundedComparison(syntheticComparison());return structuredClone(completed);}
test("real C0 and fixed Ridge/SVR share continuous funded coordinator accounting",async()=>{
  const report=await fixtureResult();assert.equal(report.status,"ENGINEERING_ONLY");
  assert.deepEqual(report.parity.covered_policies,["C0","RIDGE","SVR"]);
  assert.equal(report.parity.complete_policy_coverage,true);assert.equal(report.parity.predictor_reexecution_verified,true);
  assert.equal(report.execution_allowed,false);assert.equal(report.liveApproved,false);assert.equal(report.financial_acceptance_allowed,false);
  for(const name of ["C0","RIDGE","SVR"]){
    const c=report.curves[name];assert(c.curve.length>1);assert.equal(c.metrics.accounting_reconciled,true);
    assert.equal(c.metrics.economic_pnl_net_usd,c.metrics.account_pnl_net_usd-1);
    assert.equal(c.curve.at(-1).economic_equity_usd-20000,c.metrics.economic_pnl_net_usd);
    assert.equal(c.metrics.terminal_inventory_included,true);assert(c.metrics.open_inventory.length>0);
  }
});
test("SVR actual numerical receipt retains shadow authority and is not precomputed selection",async()=>{
  const report=await fixtureResult(),svr=report.reports.find(r=>r.result.candidate==="SVR");
  const d=svr.result.decisions.find(r=>r.origin==="REEXECUTED_FIXED_JSON_MODEL");assert(d);
  assert.equal(d.request_hash,d.numerical_receipt.request_hash);assert.equal(d.model_hash,d.numerical_receipt.model_hash);
  const result=JSON.parse(d.numerical_receipt.result_json);
  assert.equal(result.status,"SHADOW_RESEARCH_ONLY");assert.equal(result.execution_allowed,false);assert.equal(result.liveApproved,false);
  assert(result.selected.length>0);assert.equal(d.numerical_receipt.training_executed,false);
  assert.equal(d.numerical_receipt.training_provenance_verified,false);
  assert.notEqual(result.expected_net_usd,svr.result.metrics.economic_pnl_net_usd);
});
test("verification reruns predictors and coordinator instead of trusting a rehashed fabricated profit",async()=>{
  const input=syntheticComparison(),report=await fixtureResult();
  report.curves.SVR.metrics.economic_pnl_net_usd=123456;report.artifact_hash=hash({...report,artifact_hash:undefined});
  const checked=await verifyFundedComparison(input,report);assert.equal(checked.verified,false);
  assert(checked.mismatches.includes("reproduced_report"));assert.equal(checked.real_coordinator_and_predictors_reexecuted,true);
});
test("missing models and unknown costs block rather than manufacture a zero-cost curve",async()=>{
  const input=syntheticComparison();input.models.RIDGE=null;input.common_request.execution_model.external_cost_usd=null;
  const report=await runFundedComparison(input);assert.equal(report.status,"MEDICION_BLOQUEADA");
  assert.equal(report.curves,null);assert(report.readiness.blockers.some(r=>r.includes("UNKNOWN_COST")));
  assert(report.readiness.blockers.some(r=>r.includes("FIXED_MODEL_REQUIRED:RIDGE")));
});
test("model identities, availability and SVR guard cannot be relabeled to satisfy readiness",()=>{
  let input=syntheticComparison();input.models.RIDGE=input.models.SVR;assert.equal(comparisonReadiness(input).computable,false);
  input=syntheticComparison();input.models.SVR.available_at="2027-01-01T00:00:00Z";assert.equal(comparisonReadiness(input).computable,false);
  input=syntheticComparison();input.models.SVR.research_only=false;assert.equal(comparisonReadiness(input).computable,false);
});
test("observed replay cannot use synthetic purpose or a self-declared journal approval",async()=>{
  let input=syntheticComparison();input.common_request.data_origin="HISTORICAL";
  assert(comparisonReadiness(input).blockers.includes("OBSERVED_DATA_CANNOT_USE_SYNTHETIC_TEST_AUTHORITY"));
  input.purpose="PREREGISTERED_FIXED_MODEL_MEASUREMENT";input.registration={verified:true};
  const report=await runFundedComparison(input);assert.equal(report.status,"MEDICION_BLOQUEADA");
  assert(report.readiness.blockers.includes("REGISTERED_SOURCE_BINDING_REQUIRED"));
});
test("registration binds exact request, models and policy but excludes only the receipt",()=>{
  const input=syntheticComparison(),first=registrationBinding(input);input.registration={anything:"receipt"};
  assert.deepEqual(registrationBinding(input),first);
  input.common_request.execution_model.fee_per_fill_usd+=1;assert.notEqual(registrationBinding(input).binding_hash,first.binding_hash);
});
test("native C0 remains independent of the numerical worker",async()=>{
  const input=syntheticComparison(),old=process.env.HARPOON_QUANT_PYTHON;
  process.env.HARPOON_QUANT_PYTHON="/does/not/exist/python";
  try{const result=await executeReplay(input.common_request);assert(result.fills.length>0);}
  finally{if(old===undefined)delete process.env.HARPOON_QUANT_PYTHON;else process.env.HARPOON_QUANT_PYTHON=old;}
});
test("curve validator rejects forged holdings and does not clip economic insolvency",async()=>{
  const report=await fixtureResult(),input=syntheticComparison(),c0=structuredClone(report.reports[0]);
  c0.result.snapshots.at(-1).account.cash="999999";assert.throws(()=>fundedCurves(c0,input.common_request),/ACCOUNT_IDENTITY/);
  const original=structuredClone(report.reports[0]);input.common_request.execution_model.external_cost_usd=50000;
  original.result.metrics.external_cost_usd=50000;
  original.result.metrics.economic_pnl_net_usd=original.result.metrics.account_pnl_net_usd-50000;
  const curve=fundedCurves(original,input.common_request);assert.equal(curve.curve.at(-1).insolvency,true);
  assert.equal(curve.metrics.geometric_mean_per_session,null);assert(curve.metrics.economic_total_return<-1);
  const recovered=structuredClone(report.reports[0]),mid=recovered.result.snapshots[1];
  mid.account.cash="-1";mid.account.equity=String(-1+mid.positions.reduce((n,p)=>n+Number(p.market_value),0));
  const recoveredCurve=fundedCurves(recovered,syntheticComparison().common_request);
  assert(recoveredCurve.curve.at(-1).economic_equity_usd>0);assert.equal(recoveredCurve.metrics.geometric_mean_per_session,null);
});
test("future feature availability and modified source/model bytes cannot produce a bound receipt",async()=>{
  const input=syntheticComparison();input.common_request.events[0].bars.AAPL.at(-1).known_at=input.common_request.start_at+1;
  assert.equal(comparisonReadiness(input).computable,false);
  const valid=syntheticComparison(),variant={...valid.common_request,predictor:{name:"RIDGE",mode:"NUMERICAL_OFFLINE",model:valid.models.RIDGE,model_hash:"0".repeat(64),external_execution_allowed:false}};
  await assert.rejects(executeReplay(variant),/MODEL_HASH_MISMATCH/);
});
test("historical Python fixture preserves its artifact hash and correctly rejects a changed implementation",async()=>{
  const {openFixedPredictor}=require("./fixed_predictor_worker.cjs"),input=syntheticComparison(),common=input.common_request;
  const model_json=fs.readFileSync(path.join(__dirname,"../quant/examples/svr/model.synthetic.json"),"utf8"),model=JSON.parse(model_json);
  const model_hash=crypto.createHash("sha256").update(model_json).digest("hex");
  const request=runtimeSnapshot(common,"SYNTHSVR",101.2012);
  const worker=openFixedPredictor({name:"SVR",model,model_json,model_hash,timeout_ms:8000},canonical);
  try{
    const {receipt,result}=await worker.evaluate(request);assert.equal(receipt.model_hash,model_hash);
    assert.equal(receipt.forecast_checks[0].status,"BLOCKED");assert.equal(receipt.forecast_checks[0].reason,"SVR_IMPLEMENTATION_CHANGED");assert.equal(result.execution_allowed,false);
    assert.equal(model.artifact_hash,JSON.parse(model_json).artifact_hash);
  }finally{worker.close();}
});
test("Python-compatible JSON float spelling survives transport and the actual Python artifact validator",async()=>{
  const input=syntheticComparison();
  // Define a fresh artificial constant model, not a repair of a saved artifact.
  // Its exact JSON body uses Python's 1.0 spelling and is checked by the actual
  // Python predictor below. No fixture-generation subprocess or fitting occurs.
  const body=canonical({...input.models.SVR,artifact_hash:undefined}).replace(/"target_scale":1(?=[,}])/,'"target_scale":1.0').replace('"scale":[1,1,1,1,1,1,1,1]','"scale":[1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0]');
  const artifact=crypto.createHash("sha256").update(body).digest("hex"),model_json=body.slice(0,-1)+',"artifact_hash":"'+artifact+'"}';
  assert(model_json.includes('"target_scale":1.0'));assert.notEqual(hash(JSON.parse(body)),artifact);
  const model=JSON.parse(model_json),model_hash=crypto.createHash("sha256").update(model_json).digest("hex");
  const worker=require("./fixed_predictor_worker.cjs").openFixedPredictor({name:"SVR",model,model_json,model_hash,timeout_ms:8000},canonical);
  try{const {receipt,result}=await worker.evaluate(runtimeSnapshot(input.common_request));
    assert.equal(receipt.model_hash,model_hash);assert.equal(receipt.forecast_checks[0].status,"COMPUTED",JSON.stringify(receipt.forecast_checks));
    assert.equal(result.execution_allowed,false);assert(result.selected.length>0);
  }finally{worker.close();}
});
test("different JSON text and object model contents cannot be silently substituted",()=>{
  const input=syntheticComparison();input.model_json={RIDGE:JSON.stringify({...input.models.RIDGE,horizon_hours:72})};
  assert(comparisonReadiness(input).blockers.includes("MODEL_JSON_CONTENT_MISMATCH:RIDGE"));
});
