"use strict";
// Synthetic software fixtures only. No observed comparison or model is invented.
const test=require("node:test"),assert=require("node:assert/strict"),fs=require("node:fs"),os=require("node:os"),path=require("node:path"),crypto=require("node:crypto");
const execFile=require("node:util").promisify(require("node:child_process").execFile);
const {REQUEST_SCHEMA,parseStrictJSON,assessLevel4,verifyLevel4Readiness,bindMarketSources,brokerAccrualsCover}=require("./level4_readiness.cjs");
const {hash}=require("./coordinator_replay.cjs");
const {runFundedComparison}=require("./funded_comparison.cjs");
const {syntheticComparison}=require("./fixtures/funded_comparison_fixture.cjs");
const {syntheticRequest}=require("./fixtures/coordinator_replay_fixture.cjs");
const {fromObservationExport}=require("./observation_replay_input.cjs");
const ROOT=path.resolve(__dirname,".."),sha=bytes=>crypto.createHash("sha256").update(bytes).digest("hex");
const python=process.env.HARPOON_QUANT_PYTHON||"python3";
function workspace(t){const root=fs.mkdtempSync(path.join(os.tmpdir(),"harpoon-level4-test-"));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));return root;}
function save(root,name,value){const bytes=JSON.stringify(value,null,2)+"\n";fs.writeFileSync(path.join(root,name),bytes);return {path:name,sha256:sha(bytes)};}
function missing(){return {schema:REQUEST_SCHEMA,data:null,comparison:null,ledger:null};}
async function emptyData(root){
  const dataRequest={schema:"HARPOON_CAUSAL_PANEL_REQUEST_1",available_at:"2026-10-18T15:00:00+00:00",config:{horizon_hours:24},observation_exports:[],selection:null,split_contract:"CURRENT_SVR_60_20_20_PURGED"};
  const request=save(root,"data-request.json",dataRequest),reportFile=path.join(root,"data-report.json");
  await execFile(python,["-B",path.join(ROOT,"tools/build_causal_panel.py"),"--input",path.join(root,request.path),"--output",reportFile],{cwd:ROOT,timeout:30000});
  return {request,report:{path:"data-report.json",sha256:sha(fs.readFileSync(reportFile))}};
}
let comparisonFixture;
async function syntheticReport(){if(!comparisonFixture){const input=syntheticComparison();comparisonFixture={input,report:await runFundedComparison(input)};}return structuredClone(comparisonFixture);}

function sourceFixture(root,nature="RUNTIME_OBSERVATION_UNVERIFIED"){
  const original=syntheticRequest(),event=original.events[0],config=structuredClone(original.config);
  config.expected_account_id="SYNTHETIC_TEST_SOURCE_ACCOUNT";
  const raw={now:original.start_at,config,market:{calendar:original.calendar,assets:Object.fromEntries(config.universe.map(a=>[a.symbol,a])),
    quotes:Object.fromEntries(event.quotes.map(q=>[q.symbol,{bid:q.bid,ask:q.ask,at:q.market_at,received:q.market_at}])),bars:event.bars,daily:event.daily},
    observation_coverage:{selected_symbols:["AAPL"],registered_symbols:["AAPL"],complete_registered_universe:true}};
  const frame={schema:"HARPOON_PROSPECTIVE_FRAME_1",account_id:config.expected_account_id,data_origin:nature,external_authenticity_verified:false,
    runtime_input:raw,observation:{execution_allowed:false,liveApproved:false},sampled_execution_depth:null,policy_parity_verified:false,financial_acceptance_allowed:false};
  frame.source_frame_sha256=sha(JSON.stringify(frame));
  const bundle={schema:"HARPOON_OBSERVATION_EXPORT_1",fixture_nature:"SYNTHETIC_UNIT_TEST_DATA",account_id:config.expected_account_id,
    frames:[frame],head:"SYNTHETIC-BOUND-HEAD",offset:0,next_offset:1,total_frames:1,complete_export:true,execution_allowed:false,liveApproved:false};
  const reference=save(root,"market-export.json",bundle),common=fromObservationExport(bundle,{initial_cash_usd:original.initial_cash_usd,execution_model:original.execution_model});
  common.source_evidence.observation_exports=[reference];
  return {input:{common_request:common},bundle,reference};
}

function twoFrameSourceFixture(root,changeSecondConfig){
  const first=sourceFixture(root),later=structuredClone(first.bundle.frames[0]);
  later.runtime_input.now+=60000;
  for(const q of Object.values(later.runtime_input.market.quotes)){q.at+=60000;q.received+=60000;}
  const seal=frame=>{delete frame.source_frame_sha256;frame.source_frame_sha256=sha(JSON.stringify(frame));};
  seal(later);
  const frames=[first.bundle.frames[0],later],full={...first.bundle,frames,next_offset:2,total_frames:2};
  const common=fromObservationExport(full,{initial_cash_usd:first.input.common_request.initial_cash_usd,
    execution_model:first.input.common_request.execution_model});
  if(changeSecondConfig){changeSecondConfig(later.runtime_input.config,later.runtime_input.now);seal(later);}
  const combined=save(root,"market-combined.json",full);
  const pages=[save(root,"market-first.json",{...full,frames:[frames[0]],offset:0,next_offset:1,complete_export:false}),
    save(root,"market-second.json",{...full,frames:[frames[1]],offset:1,next_offset:2,complete_export:false})];
  const request=refs=>({common_request:{...structuredClone(common),source_evidence:{...structuredClone(common.source_evidence),observation_exports:refs}}});
  return {combined:request([combined]),paginated:request(pages)};
}

test("strict JSON rejects overwritten evidence and nonfinite numbers",()=>{
  assert.throws(()=>parseStrictJSON('{"score":3,"score":4}'),/DUPLICATE_JSON_KEY/);
  assert.throws(()=>parseStrictJSON('{"x":{"a":0,"\\u0061":1}}'),/DUPLICATE_JSON_KEY/);
  for(const raw of ['{"x":NaN}','{"x":Infinity}','{"x":1e999}','[1,]'])assert.throws(()=>parseStrictJSON(raw));
  assert.deepEqual(parseStrictJSON('{"known":0,"missing":null,"label":"a\\\"b"}'),{known:0,missing:null,label:'a"b'});
});
test("missing inputs stay at3 despite caller claims of readiness or profit",async()=>{
  const input={...missing(),score:4,verified:true,financial_profitability_demonstrated:true,all_checks_pass:true};
  const result=await assessLevel4(input);
  assert.equal(result.score,3);assert(result.blockers.includes("APPLICABLE_BROKER_ACCRUALS_NOT_VERIFIED"));
  assert(result.blockers.includes("MODEL_PANEL_HASH_OR_CHRONOLOGY_BINDING_MISSING"));
  assert.equal(result.observed.causal_data,false);assert.equal(result.execution_allowed,false);assert.equal(result.financial_profitability_demonstrated,false);
});
test("valid data artifact is reconstructed but an empty panel cannot qualify",async t=>{
  const root=workspace(t),input=missing();input.data=await emptyData(root);
  const result=await assessLevel4(input,root);
  assert.equal(result.components.data.verified,true);assert.equal(result.score,3);
  assert.equal(result.checks.find(c=>c.id==="observed_admissible_panel").passed,false);
});
test("tampered JSON report remains invalid even with a new outer file checksum",async t=>{
  const root=workspace(t),input=missing();input.data=await emptyData(root);
  const report=JSON.parse(fs.readFileSync(path.join(root,input.data.report.path),"utf8"));
  report.counts.causal_rows_admissible=1000;report.readiness.accepted_rows=1000;report.financial_acceptance_allowed=true;
  input.data.report=save(root,"data-report.json",report);
  const result=await assessLevel4(input,root);
  assert.equal(result.components.data.verified,false);assert.equal(result.score,3);
});
test("mismatched source checksum cannot be treated as a verified component",async t=>{
  const root=workspace(t),input=missing();input.data=await emptyData(root);input.data.report.sha256="0".repeat(64);
  const result=await assessLevel4(input,root);assert.equal(result.score,3);
  assert.match(result.components.data.reason,/SOURCE_FILE_HASH_MISMATCH/);
});
test("a declared reconciled ledger without reconstructible pages is rejected",async t=>{
  const root=workspace(t),input=missing();input.ledger={bundle:save(root,"ledger.json",{pages:[],expected_integrity:"0".repeat(64),verified:true,reconciled:true,economicComplete:true,executionNature:"PAPER"})};
  const result=await assessLevel4(input,root);assert.equal(result.components.ledger.verified,false);
  assert.equal(result.score,3);assert.equal(result.observed.account_and_costs,false);
});
test("real three-policy synthetic reexecution is engineering evidence and stays at3",async t=>{
  const root=workspace(t),fixture=await syntheticReport(),input=missing();
  input.comparison={request:save(root,"comparison-request.json",fixture.input),report:save(root,"comparison-report.json",fixture.report)};
  const result=await assessLevel4(input,root);
  assert.equal(result.components.comparison.verified,true);assert.equal(result.components.comparison.status,"ENGINEERING_ONLY");
  assert.equal(result.score,3);assert.equal(result.observed.three_policy_comparison,false);
  assert(result.blockers.includes("COMPARISON_MARKET_RECEIPT_BINDING_MISSING"));
});
test("relabeling and resealing synthetic comparison cannot promote it",async t=>{
  const root=workspace(t),fixture=await syntheticReport(),input=missing();
  fixture.report.status="REGISTERED_MODELED_MEASUREMENT";fixture.report.data_origin="HISTORICAL";
  fixture.report.artifact_hash=hash({...fixture.report,artifact_hash:undefined});
  input.comparison={request:save(root,"comparison-request.json",fixture.input),report:save(root,"comparison-report.json",fixture.report)};
  const result=await assessLevel4(input,root);assert.equal(result.components.comparison.verified,false);assert.equal(result.score,3);
});
test("market binding reads original local frames, and changed quote or bar cannot match",t=>{
  const root=workspace(t),f=sourceFixture(root);
  const bound=bindMarketSources(f.input,root,[]);assert.equal(bound.verified,true);assert.equal(bound.external_authenticity_verified,false);
  let changed=structuredClone(f.input);changed.common_request.events[0].quotes[0].ask+=.01;
  assert.throws(()=>bindMarketSources(changed,root,[]),/QUOTE_NOT_BOUND/);
  changed=structuredClone(f.input);changed.common_request.events[0].bars.AAPL[0].c+=.01;
  assert.throws(()=>bindMarketSources(changed,root,[]),/BAR_NOT_BOUND/);
});
test("fixed source configuration has the same binding across page partitions",t=>{
  const root=workspace(t),f=twoFrameSourceFixture(root);
  const combined=bindMarketSources(f.combined,root,[]),paginated=bindMarketSources(f.paginated,root,[]);
  assert.deepEqual(paginated,combined);
  assert.equal(combined.verified,true);assert.equal(combined.frames,2);
  assert(combined.quotes_bound>0&&combined.bars_bound>0);
});
test("configuration changes cannot be hidden across a source page boundary",t=>{
  const root=workspace(t);
  for(const change of [
    (config,at)=>config.universe.push({...structuredClone(config.universe[0]),symbol:"NEW",discovered_at:at}),
    config=>{config.slippageBps+=1;},
  ]){
    const f=twoFrameSourceFixture(root,change);
    for(const request of [f.combined,f.paginated])
      assert.throws(()=>bindMarketSources(request,root,[]),/SOURCE_CONFIG_CHANGED_SPLIT_REPLAY/);
  }
});
test("comparison configuration must match documented source normalization",t=>{
  const root=workspace(t),f=twoFrameSourceFixture(root);
  for(const request of [f.combined,f.paginated])for(const change of [
    config=>{config.slippageBps+=1;},
    config=>{config.dailyLoss+=.01;},
    config=>{config.universe[0].symbol="NEW";},
    config=>{config.nativeProtection="none";},
  ]){
    const changed=structuredClone(request);change(changed.common_request.config);
    assert.throws(()=>bindMarketSources(changed,root,[]),/COMPARISON_CONFIGURATION_NOT_BOUND_TO_SOURCE/);
  }
});
test("mixed source capture uses exactly the funded equity ETF scope without cherry picking",t=>{
  const root=workspace(t),f=sourceFixture(root),frame=f.bundle.frames[0],config=frame.runtime_input.config;
  const crypto=structuredClone(require("../config/examples/xxx.json").universe.find(a=>a.book==="crypto"));
  assert(crypto);
  config.universe.push({...structuredClone(config.universe[0]),symbol:"MSFT"},crypto);
  delete frame.source_frame_sha256;frame.source_frame_sha256=sha(JSON.stringify(frame));
  const reference=save(root,"market-mixed.json",f.bundle);
  const common=fromObservationExport(f.bundle,{initial_cash_usd:f.input.common_request.initial_cash_usd,
    execution_model:f.input.common_request.execution_model});
  assert(common.config.universe.some(a=>a.book==="crypto"));
  common.config.universe=common.config.universe.filter(a=>["equity","etf"].includes(a.book)&&a.multiplier===1);
  common.source_evidence.observation_exports=[reference];
  const input={common_request:common};
  assert.equal(bindMarketSources(input,root,[]).verified,true);
  const selected=structuredClone(input);
  selected.common_request.config.universe=selected.common_request.config.universe.filter(a=>a.symbol!=="MSFT");
  assert.throws(()=>bindMarketSources(selected,root,[]),/COMPARISON_CONFIGURATION_NOT_BOUND_TO_SOURCE/);
});
test("explicitly synthetic frames and incomplete page sets never claim observed receipts",t=>{
  const root=workspace(t),f=sourceFixture(root,"SYNTHETIC_ENGINEERING_ONLY");
  assert.throws(()=>bindMarketSources(f.input,root,[]),/SYNTHETIC_OR_UNKNOWN/);
  const fresh=sourceFixture(root);fresh.bundle.total_frames=2;
  fresh.input.common_request.source_evidence.observation_exports=[save(root,"market-export.json",fresh.bundle)];
  assert.throws(()=>bindMarketSources(fresh.input,root,[]),/COMPLETE_COMPARISON_SOURCE_EXPORT_REQUIRED/);
});
test("self-resealed level4 score is checked by complete reexecution",async()=>{
  const input=missing(),original=await assessLevel4(input),altered=structuredClone(original);
  altered.score=4;altered.blockers=[];for(const c of altered.checks)c.passed=true;
  altered.artifact_hash=hash({...altered,artifact_hash:undefined});
  assert.equal((await verifyLevel4Readiness(input,altered)).verified,false);
  assert.equal((await verifyLevel4Readiness(input,original)).verified,true);
});
test("closed documentary coverage is usable only inside its verified period despite an unknown current tail",()=>{
  // Synthetic verifier-result fixture for this interval predicate only; not a
  // ledger input to assessLevel4 and never evidence of observed completeness.
  const start=Date.UTC(2026,9,15,13,30),minute=60000;
  const reconstructed={verified:true,brokerAccrualsVerified:false,brokerAccrualsUsd:null,
    state:{accounting:{unreportedBrokerAccrualsVerified:false,unreportedBrokerAccrualsUsd:null}},
    closedBrokerAccruals:{verified:true,amountUsd:0,from:start,through:start+5*minute-1,comparedFrom:start,comparedThrough:start+4*minute}};
  assert.equal(brokerAccrualsCover(reconstructed,start,start+4*minute),true);
  assert.equal(brokerAccrualsCover(reconstructed,start,start+4*minute+1),false);
  assert.equal(brokerAccrualsCover(reconstructed,start-1,start+4*minute),false);
  const claimed=structuredClone(reconstructed);delete claimed.closedBrokerAccruals;
  claimed.brokerAccrualsVerified=true;claimed.state.accounting.unreportedBrokerAccrualsVerified=true;
  assert.equal(brokerAccrualsCover(claimed,start,start+4*minute),false);
  const unknown=structuredClone(reconstructed);unknown.closedBrokerAccruals.amountUsd=null;
  assert.equal(brokerAccrualsCover(unknown,start,start+4*minute),false);
});
