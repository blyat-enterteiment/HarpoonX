"use strict";
// Synthetic protocol test only: no model fit, financial trial or external API.
const fs=require("node:fs"),path=require("node:path"),os=require("node:os"),crypto=require("node:crypto");
const app=path.resolve(process.argv[2]||"consolidation_work/HARPOON_XXXUltimate_30_12_1");
const {syntheticRequest}=require(path.join(app,"tools/fixtures/coordinator_replay_fixture.cjs"));
const {fromObservationExport}=require(path.join(app,"tools/observation_replay_input.cjs"));
const {bindMarketSources}=require(path.join(app,"tools/level4_readiness.cjs"));
const sha=x=>crypto.createHash("sha256").update(x).digest("hex");
const root=fs.mkdtempSync(path.join(os.tmpdir(),"harpoon-pagination-adversary-"));
try {
  const original=syntheticRequest(),event=original.events[0],config=structuredClone(original.config);
  config.expected_account_id="SYNTHETIC_PAGINATION_ONLY";
  const raw={now:original.start_at,config,market:{calendar:original.calendar,
    assets:Object.fromEntries(config.universe.map(a=>[a.symbol,a])),
    quotes:Object.fromEntries(event.quotes.map(q=>[q.symbol,{bid:q.bid,ask:q.ask,at:q.market_at,received:q.market_at}])),
    bars:event.bars,daily:event.daily},
    observation_coverage:{selected_symbols:["AAPL"],registered_symbols:["AAPL"],complete_registered_universe:true}};
  function frame(input){
    const f={schema:"HARPOON_PROSPECTIVE_FRAME_1",account_id:config.expected_account_id,
      data_origin:"RUNTIME_OBSERVATION_UNVERIFIED",external_authenticity_verified:false,
      runtime_input:input,observation:{execution_allowed:false,liveApproved:false},
      sampled_execution_depth:null,policy_parity_verified:false,financial_acceptance_allowed:false};
    f.source_frame_sha256=sha(JSON.stringify(f));return f;
  }
  const later=structuredClone(raw);later.now+=60000;
  for(const q of Object.values(later.market.quotes)){q.at+=60000;q.received+=60000;}
  const initial=[frame(raw),frame(later)];
  function bundle(frames,offset=0){return {
    schema:"HARPOON_OBSERVATION_EXPORT_1",fixture_nature:"SYNTHETIC_SOFTWARE_TEST_ONLY",
    account_id:config.expected_account_id,frames,head:"SYNTHETIC-PAGINATION-HEAD",
    offset,next_offset:offset+frames.length,total_frames:2,complete_export:frames.length===2,
    execution_allowed:false,liveApproved:false};}
  const common=fromObservationExport(bundle(initial),{
    initial_cash_usd:original.initial_cash_usd,execution_model:original.execution_model});
  const save=(name,x)=>{const bytes=JSON.stringify(x);fs.writeFileSync(path.join(root,name),bytes);return {path:name,sha256:sha(bytes)};};
  function check(frames,label){
    const variants={one_page:[save(label+"-both.json",bundle(frames))],
      two_pages:[save(label+"-first.json",bundle([frames[0]],0)),save(label+"-second.json",bundle([frames[1]],1))]};
    const results={};
    for(const [name,refs] of Object.entries(variants)){
      const req=structuredClone(common);req.source_evidence.observation_exports=refs;
      try{results[name]={passed:true,result:bindMarketSources({common_request:req},root,[])};}
      catch(e){results[name]={passed:false,error:e.message};}
    }
    return results;
  }
  const stable=check(initial,"stable");
  later.config.universe.push({...structuredClone(config.universe[0]),symbol:"NEW",discovered_at:later.now});
  const rotating=check([initial[0],frame(later)],"rotating");
  console.log(JSON.stringify({nature:"SYNTHETIC_SOFTWARE_COUNTEREXAMPLE_NOT_FINANCIAL_DATA",
    same_frames_within_each_pair:true,only_page_partition_changed_within_pair:true,
    stable_configuration:stable,causal_universe_change:rotating,
    code_hashes:Object.fromEntries(["tools/level4_readiness.cjs","tools/observation_replay_input.cjs"].map(name=>[name,sha(fs.readFileSync(path.join(app,name)))]))},null,2));
} finally {fs.rmSync(root,{recursive:true,force:true});}
