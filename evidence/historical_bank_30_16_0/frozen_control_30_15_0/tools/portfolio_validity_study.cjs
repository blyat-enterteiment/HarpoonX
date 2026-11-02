"use strict";
/** One registered validity correction. This is neither a selector nor a promotion gate. */
const fs=require("node:fs"),path=require("node:path"),crypto=require("node:crypto"),assert=require("node:assert/strict");
const ROOT=path.resolve(__dirname,".."),DIR=path.join(ROOT,"evidence/portfolio_30_14_0");
const PREVIOUS=path.join(ROOT,"evidence/portfolio_validity_30_13_1/comparison");
const FILES=["ultimate_replay.js","ultimate_reservations.js","ultimate_contracts.js","ultimate_stats.js","ultimate_frequency.js","policy.js","types.js","validators.js","scheduler.js","ultimate_lab.js"];
const sha=v=>crypto.createHash("sha256").update(v).digest("hex");
const fileHash=f=>sha(fs.readFileSync(f));
const read=f=>JSON.parse(fs.readFileSync(f,"utf8"));
const save=(f,v)=>fs.writeFileSync(f,JSON.stringify(v,null,2)+"\n",{flag:"wx"});
function bindings(){
  const relative=["tools/portfolio_validity_study.cjs",...FILES.map(x=>"runtime30/"+x),
    "evidence/tp32/prepared.json","evidence/ultimate/report.json","evidence/ultimate/protocol.json",
    "evidence/portfolio_validity_30_13_1/comparison/frozen_study.json",
    "evidence/portfolio_validity_30_13_1/comparison/frozen_inputs.cjs",
    "evidence/portfolio_validity_30_13_1/comparison/compare_frozen_portfolio.cjs",
    "evidence/portfolio_validity_30_13_1/comparison/candidate/result.json",
    "evidence/portfolio_validity_30_13_1/comparison/registration.json",
    "evidence/portfolio_validity_30_13_1/comparison/continuation_journal.jsonl",
    ...FILES.filter(x=>x!=="ultimate_reservations.js").map(x=>"evidence/portfolio_30_14_0/control_30_13_1/runtime30/"+x)];
  return Object.fromEntries(relative.map(f=>[f,fileHash(path.join(ROOT,f))]));
}
function validateJournal(text,expected=null){
  const previous=text.trim().split("\n").filter(Boolean).map(JSON.parse);
  assert(previous.length<=2,"Only REGISTER and COMPLETE belong to this single attempt.");
  let head=null;
  for(const [index,r] of previous.entries()){const {hash,...body}=r;assert.equal(body.sequence,index+1);assert.equal(body.previous_hash,head);assert.equal(hash,sha(JSON.stringify(body)));assert.equal(body.kind,index===0?"REGISTER":"COMPLETE");head=hash;}
  if(expected){
    assert(previous.length>=1,"Missing REGISTER event.");
    assert(previous.every(r=>r.trial_id===expected.trial_id));
    assert.equal(previous[0].registration_sha256,expected.registration_sha256);
    if(expected.result_sha256){assert.equal(previous.length,2);assert.equal(previous[1].result_sha256,expected.result_sha256);}
  }
  return previous;
}
function appendJournal(event){
  const filename=path.join(DIR,"journal.jsonl");
  const previous=validateJournal(fs.existsSync(filename)?fs.readFileSync(filename,"utf8"):"");
  const head=previous.at(-1)?.hash??null;
  const body={sequence:previous.length+1,previous_hash:head,...event};
  const record={...body,hash:sha(JSON.stringify(body))};
  validateJournal([...previous,record].map(x=>JSON.stringify(x)).join("\n"));
  fs.appendFileSync(filename,JSON.stringify(record)+"\n");
  return record;
}
function register(){
  const filename=path.join(DIR,"registration.json");
  const r={schema:"HARPOON_PORTFOLIO_VALIDITY_REGISTRATION_2",trial_id:"HARPOON_PORTFOLIO_CAUSAL_RESERVATIONS_20261101_01",
    registered_at:new Date().toISOString(),purpose:"ONE_JOINT_CORRECTION_WITH_FROZEN_SELECTIONS",
    requested_target:7,financial_acceptance_allowed:false,execution_allowed:false,liveApproved:false,
    new_candidate_variants:1,fits_allowed:0,retuning_allowed:false,independent_external_preregistration:false,
    previous_continuation_variants:1,continuation_variants_after_this_attempt:2,legacy_counters_reset:false,
    global_deduplicated_search_count:null,global_count_reason:"Legacy studies use different units and overlapping histories; preserve every prior journal without inventing a combined budget.",
    known_data_use:{out_of_sample:["2025-03-11","2026-07-13"],previously_examined_holdout:["2026-07-21","2026-10-16"],history_known_through:"2026-10-17"},
    data_scope:"REUSED_PREPARED_HISTORY_MODELED_EXECUTION",primary_period:["2025-03-11","2026-07-13"],
    control:"Exactly reproduce the stored 30.13.1 candidate with its original frozen runner and inputs.",
    candidate:"Regenerate causal opportunities and use one shared reservation book; retain all sixteen original fold selections, universe, costs and risk coefficients.",
    corrections:["Future suffix cannot erase a past signal; missing execution remains an unresolved incident.","Pending and open campaigns reserve cash, risk, notional and symbol from decision until a known complete close."],
    primary_outputs:["evaluation_status","portfolio_net_model_pnl_usd","continuous_geometric_growth","difference_from_30_13_1","unresolved_exposure","risk_and_capital_feasibility"],
    diagnostics:["asset_contributions","entry_and_exit_time_cohorts","concentration","drawdown","planned_vs_open_reservations"],
    uncertainty:{method:"Existing circular block bootstrap of joint-portfolio log returns; descriptive lower bound only",runs:2000,block_sessions:5,legacy_family_parameter:72,confidence_nominal:0.95,
      limitations:["Reused data; not an independent holdout.","Legacy family parameter is not a reconciled total of all searches.","With 2000 replicates the family-adjusted tail is sparsely resolved.","No confidence interval is a guaranteed probability of future profits."]},
    interpretations:{unknown_external_costs:"Economic PnL remains null, not zero expenses.",unresolved_exposure:"Return null total result and retain incident and reservation state.",
      negative_or_unchanged_result:"Publish without tuning; correctness is not selected by PnL.",
      rating:"No profitability-level promotion is authorized by this reused-history correction."},
    recent_data:{period:["2026-10-19","2026-10-30"],financial_execution_in_this_record:false,
      reason:"Raw bars were captured, but a complete corporate-action manifest by effective date and account/cost receipts are not established; do not replace unknowns with an empty event list."},
    bindings:bindings()};
  save(filename,r);appendJournal({kind:"REGISTER",at:r.registered_at,trial_id:r.trial_id,registration_sha256:fileHash(filename)});
  console.log(JSON.stringify({registered:true,trial_id:r.trial_id,registration_sha256:fileHash(filename),financial_acceptance_allowed:false}));
}
function requireRegistration(mode="run"){
  const filename=path.join(DIR,"registration.json"),r=read(filename);
  assert.equal(r.schema,"HARPOON_PORTFOLIO_VALIDITY_REGISTRATION_2");assert.equal(r.new_candidate_variants,1);
  assert.equal(r.fits_allowed,0);assert.equal(r.retuning_allowed,false);assert.equal(r.financial_acceptance_allowed,false);
  assert(Date.parse(r.registered_at)<=Date.now());assert.deepEqual(r.bindings,bindings(),"Registered bytes changed; do not silently rerun or reseal.");
  const journal=validateJournal(fs.readFileSync(path.join(DIR,"journal.jsonl"),"utf8"),{
    trial_id:r.trial_id,registration_sha256:fileHash(filename),
    ...(mode==="verify"?{result_sha256:fileHash(path.join(DIR,"result.json"))}:{})});
  if(mode==="run")assert.equal(journal.length,1,"The registered attempt is already completed.");
  return r;
}
function compute(){
  const {loadBaseline}=require(path.join(PREVIOUS,"frozen_inputs.cjs"));
  const {replayFrozen}=require(path.join(PREVIOUS,"compare_frozen_portfolio.cjs"));
  const frozen=read(path.join(PREVIOUS,"frozen_study.json"));
  const {data,protocol}=loadBaseline(ROOT);
  const old=require(path.join(DIR,"control_30_13_1/runtime30/ultimate_replay.js"));
  const stats=require(path.join(ROOT,"runtime30/ultimate_stats.js"));
  const control=replayFrozen(frozen,data,old.replayCampaign,stats.metrics,old.planCalendarHolding,old.causalReferencePrice,old.verifyFundedEntryFill);
  assert.deepEqual(control,read(path.join(PREVIOUS,"candidate/result.json")).result,"Stored 30.13.1 control must reproduce exactly before evaluating the new code.");
  const candidateCore=require(path.join(ROOT,"runtime30/ultimate_replay.js"));
  let candidate,signalDiagnostics;
  try{
    const generated=candidateCore.opportunities(data,protocol);
    signalDiagnostics={funnel:generated.funnel,generated_total:generated.signals.length,previous_frozen_common:frozen.common.length,
      original_fold_selections:frozen.folds.map(f=>f.selected),selection_changed:false};
    const result=candidateCore.replayFundedPortfolio(generated.signals,data,protocol,frozen.folds,frozen.oos,frozen.limits);
    const logs=result.curve.map(x=>x.portfolio_log_return);
    candidate={status:"COMPLETE_EXPLORATORY_ONLY",result,uncertainty:{descriptive_log_growth_lower:logs.every(Number.isFinite)?stats.bootstrapLower(logs,2000,5,72):null,
      method:"LEGACY_CIRCULAR_BLOCK_BOOTSTRAP",sessions:logs.length,runs:2000,block_sessions:5,legacy_family_parameter:72,
      global_multiple_testing_correction_verified:false,independent_holdout:false,financial_acceptance_allowed:false}};
  }catch(error){
    candidate={status:"INCOMPLETE_EVALUATION",result:null,net_model_pnl_usd:null,incident:{code:error.code||error.name||"ERROR",message:error.message,details:error.details??null,economicPnlUsd:null}};
  }
  return {schema:"HARPOON_PORTFOLIO_VALIDITY_RESULT_2",scope:"REUSED_HISTORY_MODELED_EXECUTION",control,signalDiagnostics:signalDiagnostics??null,candidate,
    difference_usd:candidate.result?candidate.result.portfolio.netUsd-control.netUsd:null,
    economic_pnl_complete_usd:null,external_operating_costs_usd:null,financial_acceptance_allowed:false,
    real_profitability_grade:null,target_seven_accredited:false,new_fits:0,new_candidate_variants:1};
}
function execute(mode){
  const r=requireRegistration(mode),attempt=path.join(DIR,"attempt_started.json"),output=path.join(DIR,"result.json");
  if(mode==="run")save(attempt,{trial_id:r.trial_id,started_at:new Date().toISOString(),registration_sha256:fileHash(path.join(DIR,"registration.json"))});
  else{assert.equal(read(attempt).trial_id,r.trial_id);assert.equal(read(attempt).registration_sha256,fileHash(path.join(DIR,"registration.json")));assert(fs.existsSync(output));}
  const result=compute();
  if(mode==="verify"){
    assert.deepEqual(result,read(output));console.log(JSON.stringify({verified:true,new_financial_trials:0,outputs_rewritten:false,status:result.candidate.status}));return;
  }
  save(output,result);appendJournal({kind:"COMPLETE",at:new Date().toISOString(),trial_id:r.trial_id,result_sha256:fileHash(output),status:result.candidate.status});
  console.log(JSON.stringify({trial_id:r.trial_id,status:result.candidate.status,control_net_usd:result.control.netUsd,candidate_net_usd:result.candidate.result?.portfolio.netUsd??null,difference_usd:result.difference_usd,target_seven_accredited:false}));
}
if(require.main===module){const mode=process.argv[2];if(mode==="register")register();else if(mode==="run"||mode==="verify")execute(mode);else throw Error("Use register, run or verify; no implicit search or execution.");}
module.exports={bindings,requireRegistration,compute,validateJournal};
