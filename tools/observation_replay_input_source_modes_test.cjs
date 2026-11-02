"use strict";
// Invented observations and constant predictors; no financial evidence or orders.
const test=require("node:test"),assert=require("node:assert/strict");
const fs=require("node:fs"),os=require("node:os"),path=require("node:path"),crypto=require("node:crypto");
const execFile=require("node:util").promisify(require("node:child_process").execFile);
const {fromObservationExport}=require("./observation_replay_input.cjs");
const {hash,canonical,validateRequest,executeReplay}=require("./coordinator_replay.cjs");
const {bindMarketSources}=require("./level4_readiness.cjs");
const {openFixedPredictor}=require("./fixed_predictor_worker.cjs");
const {syntheticRequest}=require("./fixtures/coordinator_replay_fixture.cjs");
const {syntheticModels}=require("./fixtures/funded_comparison_fixture.cjs");
const sha=x=>crypto.createHash("sha256").update(x).digest("hex");
function seal(frame){delete frame.source_frame_sha256;frame.source_frame_sha256=sha(JSON.stringify(frame));}
function fixture(mode="live",quantConfig={horizon_hours:24,scenarios:64,max_positions:2,solver_seconds:1,gross_fraction:.4,seed:7}){
  const original=syntheticRequest(),market=original.events[0],config=structuredClone(original.config);
  config.mode=mode;config.expected_account_id="SYNTHETIC-SOURCE-ACCOUNT";config.streaming=true;config.nativeProtection="oco";
  config.quant={enabled:true,config:structuredClone(quantConfig),calibrationFile:"/never-open/source-model.json",python:"/never-run/python",
    timeoutMs:8000,optimizer:{enabled:true,statePath:"/never-open/optimizer"},microstructure:{enabled:true,modelFile:"/never-open/micro"},
    accounting:{costReceiptFile:"/never-open/costs"},endpoint:"https://unused.invalid/quant"};
  const raw={now:original.start_at,config,
    account:{equity:123456,cash:100000,buying_power:100000},positions:[{symbol:"AAPL",qty:50}],pending:[],daily_pnl:0,drawdown_fraction:0,
    market:{calendar:original.calendar.map(s=>({date:s.date,open:Date.parse(s.date+"T13:30:00Z"),close:Date.parse(s.date+"T20:00:00Z")})),
      assets:Object.fromEntries(config.universe.map(a=>[a.symbol,a])),
      quotes:Object.fromEntries(market.quotes.map(q=>[q.symbol,{bid:q.bid,ask:q.ask,at:q.market_at,received:q.market_at}])),
      bars:market.bars,daily:market.daily},
    observation_coverage:{selected_symbols:["AAPL"],registered_symbols:["AAPL"],complete_registered_universe:true}};
  const frame={schema:"HARPOON_PROSPECTIVE_FRAME_1",account_id:config.expected_account_id,data_origin:"RUNTIME_OBSERVATION_UNVERIFIED",
    external_authenticity_verified:false,runtime_input:raw,observation:{execution_allowed:false,liveApproved:false},
    sampled_execution_depth:null,policy_parity_verified:false,financial_acceptance_allowed:false};seal(frame);
  return {bundle:{schema:"HARPOON_OBSERVATION_EXPORT_1",fixture_nature:"SYNTHETIC_UNIT_TEST_DATA",account_id:config.expected_account_id,
    frames:[frame],head:"SYNTHETIC-BOUND-HEAD",offset:0,next_offset:1,total_frames:1,complete_export:true,execution_allowed:false,liveApproved:false},
    assumptions:{initial_cash_usd:original.initial_cash_usd,execution_model:original.execution_model}};
}
function mutateConfig(f,mutate){mutate(f.bundle.frames[0].runtime_input.config);seal(f.bundle.frames[0]);return f;}

test("live and real source modes preserve source identity and only produce non-authorizing PAPER replay",async()=>{
  for(const mode of ["live","real"]){
    const {bundle,assumptions}=fixture(mode),before=JSON.stringify(bundle),original=bundle.frames[0].runtime_input.config;
    const input=fromObservationExport(bundle,assumptions);
    assert.equal(JSON.stringify(bundle),before,"source frames must remain byte-identical");
    assert.equal(input.mode,"OFFLINE");assert.equal(input.execution_origin,"MODELED");assert.equal(input.data_origin,"HISTORICAL");
    assert.equal(input.config.mode,"paper");assert(input.config.expected_account_id.startsWith("OFFLINE-"));
    assert.equal(input.config.streaming,false);assert.equal(input.config.nativeProtection,"stop");
    assert.deepEqual(input.config.quant,{enabled:false,config:original.quant.config});
    assert.equal(input.source_evidence.source_config_mode,mode);assert.equal(input.source_evidence.source_account_id,bundle.account_id);
    assert.equal(input.source_evidence.source_config_hash,hash(original));assert.notEqual(hash(input.config),hash(original));
    assert.equal(input.source_evidence.external_authenticity_verified,false);assert.equal(input.source_evidence.source_execution_nature_verified,false);
    for(const field of ["execution_allowed","liveApproved","financial_acceptance_allowed"])assert.equal(input[field],false);
    assert(input.events.every(e=>["market","sessions","evaluate"].includes(e.type)));
    assert(input.events.filter(e=>e.type==="market").every(e=>e.quotes.every(q=>q.executable_qty===0)));
    const replay=await executeReplay(input);
    assert.equal(replay.order_actions.length,0);assert.equal(replay.fills.length,0);assert.deepEqual(replay.final_state.positions,[]);
    assert.equal(replay.metrics.initial_cash_usd,assumptions.initial_cash_usd);assert.equal(input.source_evidence.source_account_positions_adopted,false);
  }
});

test("paper imports retain their safety projection and the same numeric predictor settings",()=>{
  const paper=fixture("paper"),live=fixture("live"),a=fromObservationExport(paper.bundle,paper.assumptions),b=fromObservationExport(live.bundle,live.assumptions);
  assert.deepEqual(a.config,b.config);assert.deepEqual(a.events,b.events);
  assert.notEqual(a.source_evidence.source_config_hash,b.source_evidence.source_config_hash);
  const noSettings=mutateConfig(fixture("paper"),cfg=>delete cfg.quant.config),out=fromObservationExport(noSettings.bundle,noSettings.assumptions);
  assert.deepEqual(out.config.quant,{enabled:false});
});

test("preserved numeric settings reach the actual Python predictor without copied paths or SVR authority",async()=>{
  const f=fixture("live"),input=fromObservationExport(f.bundle,f.assumptions),models=syntheticModels();
  const request=structuredClone(f.bundle.frames[0].runtime_input);request.config=input.config;request.runtime_snapshot=true;
  request.account={equity:20000,cash:20000,buying_power:20000};request.positions=[];
  request.signals=[{symbol:"AAPL",plugin:"synthetic-source-mode-test",entry:101.11,max_qty:5}];
  const expected=JSON.parse((await execFile(process.env.HARPOON_QUANT_PYTHON||"python3",["-B","-c",
    "import json,sys;from dataclasses import asdict;from harpoon_quant.core import digest;from harpoon_quant.bridge import runtime_config;p=json.loads(sys.argv[1]);print(json.dumps({k:digest(asdict(runtime_config(v))) for k,v in p.items()}))",
    JSON.stringify({original:f.bundle.frames[0].runtime_input.config,projected:input.config,
      without_overrides:{...input.config,quant:{enabled:false}}})],
    {cwd:path.resolve(__dirname,"../quant"),encoding:"utf8",timeout:30000,
      env:{PATH:process.env.PATH||"/usr/bin:/bin",LANG:"C.UTF-8",OPENBLAS_NUM_THREADS:"1",OMP_NUM_THREADS:"1"}})).stdout);
  assert.equal(expected.original,expected.projected,"source and PAPER copy must resolve the same effective runtime predictor configuration");
  assert.notEqual(expected.projected,expected.without_overrides,"dropping the numeric settings must not pass this fixture");
  const hashes=[];
  for(const role of ["RIDGE","SVR"]){
    const model=models[role],model_json=JSON.stringify(model),model_hash=sha(model_json);
    const worker=openFixedPredictor({name:role,model,model_json,model_hash,timeout_ms:8000},canonical);
    try{const {receipt,result}=await worker.evaluate(request);
      assert.equal(receipt.training_executed,false);assert.equal(receipt.execution_allowed,false);hashes.push(result.config_hash);
      assert.equal(result.config_hash,expected.original,"actual predictor config hash must include the runtime intersection with account limits");
      if(role==="SVR"){assert.equal(result.execution_allowed,false);assert.equal(result.status,"SHADOW_RESEARCH_ONLY",JSON.stringify(result));}
    }finally{worker.close();}
  }
  assert.equal(hashes[0],hashes[1]);assert.deepEqual(Object.keys(input.config.quant).sort(),["config","enabled"]);
  assert(!JSON.stringify(input.config).includes("/never-"));assert(!JSON.stringify(input.config).includes("https://unused.invalid"));
});

test("unknown source modes, missing identity and extra broker configuration fields fail closed",()=>{
  for(const mode of ["demo","LIVE","REAL","",null]){
    const f=fixture(mode);assert.throws(()=>fromObservationExport(f.bundle,f.assumptions),/SOURCE_CONFIGURATION_MODE_UNSUPPORTED/);
  }
  let f=mutateConfig(fixture(),cfg=>cfg.expected_account_id="");assert.throws(()=>fromObservationExport(f.bundle,f.assumptions),/SOURCE_ACCOUNT_CONFIGURATION_REQUIRED/);
  for(const key of ["brokerUrl","endpoint","python","apiKey"]){
    f=mutateConfig(fixture(),cfg=>cfg[key]="https://unused.invalid");
    assert.throws(()=>fromObservationExport(f.bundle,f.assumptions),/SOURCE_CONFIGURATION_FIELD_UNSUPPORTED/);
  }
});

test("quant projection accepts only known numeric parameters within the existing inference contract",()=>{
  const invalid=[{modelFile:"/tmp/model"},{endpoint:1},{horizon_hours:73},{horizon_hours:0},{cvar_alpha:1},{scenarios:31},
    {scenarios:64.5},{max_positions:49},{solver_seconds:0},{seed:1.5},{min_robust_return_bps:101},{risk_penalty:-1},
    {slippage_bps:"10"},{risk_penalty:true},{seed:null},{risk_penalty:{value:1}}];
  for(const patch of invalid){
    const f=mutateConfig(fixture(),cfg=>Object.assign(cfg.quant.config,patch));
    assert.throws(()=>fromObservationExport(f.bundle,f.assumptions),/SOURCE_QUANT_/);
  }
  for(const value of [null,[],"config"]){
    const f=mutateConfig(fixture(),cfg=>cfg.quant.config=value);
    assert.throws(()=>fromObservationExport(f.bundle,f.assumptions),/SOURCE_QUANT_CONFIG_OBJECT_REQUIRED/);
  }
});

test("source mode or predictor configuration changes cannot be hidden by resealing later frames",()=>{
  for(const mutate of [cfg=>cfg.mode="real",cfg=>cfg.quant.config.solver_seconds=2]){
    const f=fixture(),later=structuredClone(f.bundle.frames[0]);later.runtime_input.now+=1000;mutate(later.runtime_input.config);seal(later);
    f.bundle.frames.push(later);f.bundle.next_offset=2;f.bundle.total_frames=2;
    assert.throws(()=>fromObservationExport(f.bundle,f.assumptions),/SOURCE_CONFIG_CHANGED_SPLIT_REPLAY/);
  }
});

test("existing runtime PAPER and risk guards remain effective after source-mode import",()=>{
  const f=fixture(),input=fromObservationExport(f.bundle,f.assumptions);
  assert.throws(()=>validateRequest({...input,config:{...input.config,mode:"live"}}),/SCOPE_REQUIRES_PAPER_STOP_AND_STREAMING_OFF/);
  assert.throws(()=>validateRequest({...input,config:{...input.config,quant:{...input.config.quant,enabled:true}}}),/PRODUCTION_QUANT_GUARDS/);
  const invalid=mutateConfig(fixture(),cfg=>cfg.totalExposure=.51);
  assert.throws(()=>fromObservationExport(invalid.bundle,invalid.assumptions),/Config out of bounds: totalExposure/);
});

test("readiness binds the original live configuration and account instead of the PAPER projection",t=>{
  const root=fs.mkdtempSync(path.join(os.tmpdir(),"hx-live-source-projection-"));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
  const f=fixture(),bytes=JSON.stringify(f.bundle),filename="source.json";fs.writeFileSync(path.join(root,filename),bytes);
  const common=fromObservationExport(f.bundle,f.assumptions);
  common.source_evidence.observation_exports=[{path:filename,sha256:sha(bytes)}];
  const result=bindMarketSources({common_request:common},root,[]);
  assert.equal(result.source_config_hash,hash(f.bundle.frames[0].runtime_input.config));
  assert.notEqual(result.source_config_hash,hash(common.config));assert.equal(result.account_id,f.bundle.account_id);
  assert.equal(result.external_authenticity_verified,false);
});
