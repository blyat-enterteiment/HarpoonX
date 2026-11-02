"use strict";
// Synthetic inference and provenance tests only. No fitting, orders or trials.
const test=require("node:test"),assert=require("node:assert/strict");
const fs=require("node:fs"),os=require("node:os"),path=require("node:path"),crypto=require("node:crypto");
const {hash,canonical}=require("./coordinator_replay.cjs");
const {runtimePredictorBindings}=require("./level5_readiness.cjs");
const {bindMarketSources}=require("./level4_readiness.cjs");
const {fromObservationExport}=require("./observation_replay_input.cjs");
const {openFixedPredictor}=require("./fixed_predictor_worker.cjs");
const {syntheticComparison}=require("./fixtures/funded_comparison_fixture.cjs");
const {syntheticRequest}=require("./fixtures/coordinator_replay_fixture.cjs");
const sha=bytes=>crypto.createHash("sha256").update(bytes).digest("hex");

function runtimeSnapshot(common){
  const market=common.events[0];
  return {runtime_snapshot:true,now:common.start_at+1,config:structuredClone(common.config),
    account:{equity:20000,cash:20000,buying_power:20000},positions:[],pending:[],daily_pnl:0,drawdown_fraction:0,
    signals:[{symbol:"AAPL",plugin:"synthetic-binding-check",entry:101.11,max_qty:5}],
    market:{assets:{AAPL:common.config.universe[0]},bars:market.bars,
      quotes:{AAPL:{bid:101.1,ask:101.11,at:common.start_at,received:common.start_at}},
      calendar:common.calendar.map(s=>({date:s.date,open:Date.parse(s.date+"T13:30:00Z"),close:Date.parse(s.date+"T20:00:00Z")}))}};
}
function decision(request,receipt){
  return {origin:"REEXECUTED_FIXED_JSON_MODEL",event_id:"SYNTHETIC-INFERENCE",request:structuredClone(request),
    request_hash:receipt.request_hash,model_hash:receipt.model_hash,receipt_hash:hash(receipt),numerical_receipt:receipt};
}
let cached;
async function inferenceFixture(){
  if(!cached)cached=(async()=>{
    const input=syntheticComparison(),report={fixture_nature:"SYNTHETIC_UNIT_TEST_INFERENCE_ONLY",model_hashes:{},reports:[]};
    let mixed;
    for(const role of ["RIDGE","SVR"]){
      const model=input.models[role],model_json=JSON.stringify(model,null,2)+"\n",model_hash=sha(model_json);
      const worker=openFixedPredictor({name:role,model,model_json,model_hash,timeout_ms:8000},canonical);
      try{
        const request=runtimeSnapshot(input.common_request),first=await worker.evaluate(request);
        report.model_hashes[role]=model_hash;
        report.reports.push({result:{candidate:role,decisions:[decision(request,first.receipt)]}});
        if(role==="SVR"){
          const changed=structuredClone(request);changed.config.quant.config.solver_seconds=2;
          mixed=decision(changed,(await worker.evaluate(changed)).receipt);
        }
      }finally{worker.close();}
    }
    return {report,mixed};
  })();
  return structuredClone(await cached);
}
function firstDecision(report,role="SVR"){
  return report.reports.find(r=>r.result.candidate===role).result.decisions[0];
}
function rewritePlan(d,mutate){
  const receipt=d.numerical_receipt,plan=JSON.parse(receipt.result_json);
  mutate(plan);receipt.result_json=JSON.stringify(plan);receipt.result_hash=sha(receipt.result_json);d.receipt_hash=hash(receipt);
}

test("runtime identities come from actual Python result JSON while pretty-file hashes stay distinct",async()=>{
  const {report}=await inferenceFixture(),before=structuredClone(report.model_hashes),out=runtimePredictorBindings(report);
  assert.deepEqual(Object.keys(out),["SVR","RIDGE"]);
  for(const role of ["SVR","RIDGE"]){
    const d=firstDecision(report,role),plan=JSON.parse(d.numerical_receipt.result_json);
    assert.deepEqual(out[role],{model_hash:plan.model_hash,quant_config_hash:plan.config_hash,
      model_available_at:plan.decision_inputs.calibration_available_at});
    assert.notEqual(out[role].model_hash,report.model_hashes[role],"pretty JSON bytes are not Python digest(model)");
    assert.equal(d.numerical_receipt.model_hash,report.model_hashes[role]);
    assert.equal(d.numerical_receipt.training_executed,false);
  }
  assert.deepEqual(report.model_hashes,before,"extraction cannot rewrite source-file identities");
});

test("actual receipts with two quant configurations in one role cannot supply a forward binding",async()=>{
  const {report,mixed}=await inferenceFixture();
  report.reports.find(r=>r.result.candidate==="SVR").result.decisions.push(mixed);
  assert.throws(()=>runtimePredictorBindings(report),/RUNTIME_PREDICTOR_IDENTITY_CHANGED:SVR/);
});

test("a changed runtime model digest is rejected even when enclosing local hashes are recalculated",async()=>{
  const {report}=await inferenceFixture(),second=structuredClone(firstDecision(report));
  rewritePlan(second,plan=>plan.model_hash="f".repeat(64));
  report.reports.find(r=>r.result.candidate==="SVR").result.decisions.push(second);
  assert.throws(()=>runtimePredictorBindings(report),/RUNTIME_PREDICTOR_IDENTITY_CHANGED:SVR/);
});

test("empty, duplicated or non-reexecuted predictor roles cannot fall back to declared identities",async()=>{
  const {report}=await inferenceFixture();
  let changed=structuredClone(report);changed.reports=changed.reports.filter(r=>r.result.candidate!=="RIDGE");
  assert.throws(()=>runtimePredictorBindings(changed),/RUNTIME_PREDICTOR_ROLE_NOT_UNIQUE:RIDGE/);
  changed=structuredClone(report);changed.reports.push(structuredClone(changed.reports[0]));
  assert.throws(()=>runtimePredictorBindings(changed),/RUNTIME_PREDICTOR_ROLE_NOT_UNIQUE:RIDGE/);
  changed=structuredClone(report);changed.reports.find(r=>r.result.candidate==="SVR").result.decisions=[];
  changed.runtime_predictor_bindings={SVR:{model_hash:"f".repeat(64),quant_config_hash:"e".repeat(64)}};
  assert.throws(()=>runtimePredictorBindings(changed),/RUNTIME_PREDICTOR_RECEIPTS_MISSING:SVR/);
  changed=structuredClone(report);firstDecision(changed).origin="CALLER_PROVIDED_RECEIPT";
  assert.throws(()=>runtimePredictorBindings(changed),/RUNTIME_PREDICTOR_RECEIPT_SCHEMA:SVR/);
});

test("missing plan identity or calibration time is not reconstructed from enclosing model metadata",async()=>{
  for(const field of ["model_hash","config_hash","calibration_available_at"]){
    const {report}=await inferenceFixture();
    rewritePlan(firstDecision(report),plan=>{
      if(field==="calibration_available_at")delete plan.decision_inputs.calibration_available_at;
      else delete plan[field];
    });
    assert.throws(()=>runtimePredictorBindings(report),/RUNTIME_PREDICTOR_(PLAN_IDENTITY|AVAILABILITY)_REQUIRED:SVR/);
  }
});

test("changed receipt bytes, ambiguous JSON and changed source-model bindings are rejected",async()=>{
  const {report}=await inferenceFixture();
  let changed=structuredClone(report);firstDecision(changed).numerical_receipt.result_json+=" ";
  assert.throws(()=>runtimePredictorBindings(changed),/RUNTIME_PREDICTOR_RECEIPT_BINDING:SVR/);
  changed=structuredClone(report);
  let d=firstDecision(changed),r=d.numerical_receipt;
  r.result_json='{"config_hash":"'+'a'.repeat(64)+'",'+r.result_json.slice(1);
  r.result_hash=sha(r.result_json);d.receipt_hash=hash(r);
  assert.throws(()=>runtimePredictorBindings(changed),/DUPLICATE_JSON_KEY:config_hash/);
  changed=structuredClone(report);changed.model_hashes.SVR=JSON.parse(firstDecision(changed).numerical_receipt.result_json).model_hash;
  assert.throws(()=>runtimePredictorBindings(changed),/RUNTIME_PREDICTOR_SOURCE_MODEL_MISMATCH:SVR/);
});

test("source configuration binding retains the observed original before offline replay projection",t=>{
  const root=fs.mkdtempSync(path.join(os.tmpdir(),"hx-forward-config-binding-"));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
  const original=syntheticRequest(),event=original.events[0],config=structuredClone(original.config);
  config.expected_account_id="SYNTHETIC_ORIGINAL_ACCOUNT";
  const raw={now:original.start_at,config,market:{calendar:original.calendar,
    assets:Object.fromEntries(config.universe.map(a=>[a.symbol,a])),
    quotes:Object.fromEntries(event.quotes.map(q=>[q.symbol,{bid:q.bid,ask:q.ask,at:q.market_at,received:q.market_at}])),
    bars:event.bars,daily:event.daily},
    observation_coverage:{selected_symbols:["AAPL"],registered_symbols:["AAPL"],complete_registered_universe:true}};
  const frame={schema:"HARPOON_PROSPECTIVE_FRAME_1",account_id:config.expected_account_id,
    data_origin:"RUNTIME_OBSERVATION_UNVERIFIED",external_authenticity_verified:false,runtime_input:raw,
    observation:{execution_allowed:false,liveApproved:false},sampled_execution_depth:null,policy_parity_verified:false,financial_acceptance_allowed:false};
  frame.source_frame_sha256=sha(JSON.stringify(frame));
  const bundle={schema:"HARPOON_OBSERVATION_EXPORT_1",fixture_nature:"SYNTHETIC_UNIT_TEST_DATA",account_id:config.expected_account_id,
    frames:[frame],head:"SYNTHETIC-BOUND-HEAD",offset:0,next_offset:1,total_frames:1,complete_export:true,execution_allowed:false,liveApproved:false};
  const rawBundle=JSON.stringify(bundle),file="source.json";fs.writeFileSync(path.join(root,file),rawBundle);
  const common=fromObservationExport(bundle,{initial_cash_usd:original.initial_cash_usd,execution_model:original.execution_model});
  common.source_evidence.observation_exports=[{path:file,sha256:sha(rawBundle)}];
  const bound=bindMarketSources({common_request:common},root,[]);
  assert.equal(bound.source_config_hash,hash(config));
  assert.notEqual(bound.source_config_hash,hash(common.config));
  assert.equal(bound.account_id,"SYNTHETIC_ORIGINAL_ACCOUNT");
  assert.equal(bound.external_authenticity_verified,false);
});
