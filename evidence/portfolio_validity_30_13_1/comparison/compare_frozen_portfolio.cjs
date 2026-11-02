"use strict";
// Exactly one candidate correction, frozen opportunities and fold selections.
// Candidate is blocked until an external local registration binds all bytes.
const fs=require("node:fs"),path=require("node:path"),assert=require("node:assert/strict");
const {fileHash,loadBaseline}=require("./frozen_inputs.cjs");
const INPUT=path.join(__dirname,"frozen_study.json");
const RUNTIME_FILES=["runtime30/ultimate_replay.js","runtime30/ultimate_contracts.js","runtime30/ultimate_stats.js","runtime30/ultimate_frequency.js","runtime30/policy.js","runtime30/types.js","runtime30/ultimate_lab.js","runtime30/validators.js","runtime30/scheduler.js"];
function bindings(baseApp,candidateApp){
  const resolveFiles=app=>Object.fromEntries(RUNTIME_FILES.map(f=>[f,fileHash(path.join(app,f))]));
  return {runner_sha256:fileHash(__filename),helper_sha256:fileHash(path.join(__dirname,"frozen_inputs.cjs")),
    frozen_inputs_sha256:fileHash(INPUT),baseline_runtime_sha256:resolveFiles(path.resolve(baseApp)),
    candidate_runtime_sha256:resolveFiles(path.resolve(candidateApp)),
    prepared_sha256:fileHash(path.join(baseApp,"evidence/tp32/prepared.json")),
    baseline_report_sha256:fileHash(path.join(baseApp,"evidence/ultimate/report.json"))};
}
function requireRegistration(baseApp,candidateApp,filename){
  assert(filename,"Candidate requires a local registration file; no financial execution occurred");
  const registration=JSON.parse(fs.readFileSync(filename,"utf8"));
  assert.equal(registration.schema,"HARPOON_EXPLORATORY_CORRECTION_REGISTRATION_1");
  assert.equal(registration.purpose,"ONE_VALIDITY_REPAIR_FIXED_SELECTION");
  assert.equal(registration.new_variant_count,1);
  assert.equal(registration.financial_acceptance_allowed,false);
  assert.equal(registration.fits_allowed,0);
  assert.equal(registration.original_selection_frozen,true);
  assert.equal(typeof registration.trial_id,"string");assert(registration.trial_id.length>0);
  const at=Date.parse(registration.registered_at);
  assert(Number.isFinite(at)&&at<=Date.now(),"Registration time must be valid and not in future");
  assert.deepEqual(registration.bindings,bindings(baseApp,candidateApp),"Registration bytes no longer match");
  return registration;
}
function valueAt(t,at){return at<t.opened?0:at>=t.closed?t.netUsd:(t.marks.findLast(m=>m.at<=at)?.pnl??0);}
function replayFrozen(frozen,data,replayCampaign,metrics,planCalendarHolding=null,causalReferencePrice=null,verifyFundedEntryFill=null){
  const {protocol:p,limits}=frozen,bySymbol=Object.fromEntries(data.series.map(s=>[s.symbol,s]));
  const funded=[],states=[],incidents=[],preEntryRefusals=[],skipped={},pendingReserves=new Map();
  const skip=reason=>{skipped[reason]=(skipped[reason]||0)+1;};
  const equityAt=at=>limits.capitalUsd+funded.reduce((n,t)=>n+valueAt(t,at),0);
  const cashAt=at=>funded.reduce((cash,t)=>{
    if(t.closed<=at)return cash+t.netUsd;
    if(t.opened<=at)return cash-t.quantity*t.entry*bySymbol[t.symbol].pointValue-t.quantity*p.costs.perSideUsd;
    const reserve=pendingReserves.get(t.id);
    assert(Number.isFinite(reserve)&&reserve>=0,"Pending campaign requires a stored ex-ante cash reserve");
    return cash-reserve;
  },limits.capitalUsd);
  let peakEquity=limits.capitalUsd;
  for(const opportunity of frozen.common){
    const fold=frozen.folds.find(f=>opportunity.at>=f.test[0].open&&opportunity.at<=f.test.at(-1).close-p.purgeHours*3600000);
    if(!fold||fold.selected==="CASH"||!fold.selected.startsWith(opportunity.hypothesis+":"))continue;
    if(p.kind==="FUTURES"){skip("HISTORICAL_MARGIN_UNAVAILABLE");continue;}
    const active=funded.filter(t=>t.opened<=opportunity.at&&t.closed>opportunity.at);
    const equity=equityAt(opportunity.at),day=data.sessions.find(s=>opportunity.at>=s.open&&opportunity.at<s.close);
    assert(day,"Opportunity session missing");
    peakEquity=Math.max(peakEquity,equity);
    if(equity<=peakEquity*(1-limits.maxDrawdown)||equity<=equityAt(day.open)*(1-limits.dailyLoss)){skip("LOSS_LIMIT");continue;}
    if(active.some(t=>t.symbol===opportunity.symbol)){skip("SYMBOL_BUSY");continue;}
    const s=bySymbol[opportunity.symbol];
    let reference=null;
    if(causalReferencePrice){
      try{
        reference=causalReferencePrice(opportunity,s);
        assert(reference&&["AVAILABLE","NO_CAUSAL_PRICE"].includes(reference.status),"Unknown causal price status");
        assert.equal(reference.decisionAt,opportunity.at,"Reference decision time binding");
        if(reference.status==="NO_CAUSAL_PRICE"){
          preEntryRefusals.push({opportunity_id:opportunity.id,quantity:null,selected:fold.selected,reference,reason:"NO_CAUSAL_PRICE"});
          skip("PRE_ENTRY:NO_CAUSAL_PRICE");continue;
        }
        assert(Number.isFinite(reference.price)&&reference.price>0&&Number.isFinite(reference.sourceAvailableAt)&&reference.sourceAvailableAt<=opportunity.at,"Price reference must be available before the decision");
      }catch(error){
        incidents.push({code:"CAUSAL_REFERENCE_INVALID",message:error.message,opportunity_id:opportunity.id});
        return {status:"INCOMPLETE_EVALUATION",netUsd:null,portfolio:null,funded,states,skipped,incidents,preEntryRefusals,curve:null};
      }
    }
    // The legacy forensic baseline deliberately retains its original future-open sizing.
    // Candidate quantity uses only the explicitly available reference; fill prices are read later.
    const px=reference?reference.price:s.bars[opportunity.index].o;
    const riskUnit=opportunity.stopDistance*s.pointValue+2*p.costs.perSideUsd+(2*px*s.pointValue*(p.costs.spreadBps/2+p.costs.slippageBps))/10000;
    const notional=active.reduce((n,t)=>n+t.quantity*t.entry,0),openRisk=active.reduce((n,t)=>n+t.riskUsd,0);
    const quantity=Math.floor(Math.min(equity*limits.riskFraction/riskUnit,Math.max(0,equity*limits.openRiskFraction-openRisk)/riskUnit,Math.max(0,equity*limits.grossFraction-notional)/px,equity*limits.assetFraction/px));
    states.push({opportunity:{...opportunity},equity,px,riskUnit,openRisk,notional,quantity,reference,selected:fold.selected,activeCampaignIds:active.map(t=>t.id),day:{...day}});
    if(quantity<1){skip("INTEGER_RISK_OR_EXPOSURE");continue;}
    let trade,budgets=null;
    try{
      if(verifyFundedEntryFill){
        budgets={riskBudgetUsd:Math.min(equity*limits.riskFraction,Math.max(0,equity*limits.openRiskFraction-openRisk)),
          notionalBudgetUsd:Math.min(Math.max(0,equity*limits.grossFraction-notional),equity*limits.assetFraction),
          cashBudgetUsd:cashAt(opportunity.at),plannedQuantity:quantity};
        states.at(-1).ex_ante_budgets=budgets;
      }
      if(planCalendarHolding){
        const plan=planCalendarHolding(opportunity,s.bars[opportunity.index].t,data,p);
        assert(plan&&["NOT_APPLICABLE","REFUSED_BEFORE_ENTRY","SCHEDULED"].includes(plan.status),"Unknown holding admission status");
        assert.equal(plan.positionOpened,false,"Admission must precede exposure");
        assert.equal(plan.decisionAt,opportunity.at,"Admission decision time binding");
        assert.equal(plan.plannedEntryAt,s.bars[opportunity.index].t,"Admission entry time binding");
        states.at(-1).admission_plan=plan;
        if(plan.status==="REFUSED_BEFORE_ENTRY"){
          assert(typeof plan.reason==="string"&&plan.reason.length>0,"Refusal needs explicit cause");
          preEntryRefusals.push({opportunity_id:opportunity.id,quantity,selected:fold.selected,plan});
          skip("PRE_ENTRY:"+plan.reason);
          continue;
        }
        if(plan.status==="SCHEDULED")assert(Number.isFinite(plan.deadlineAt)&&plan.deadlineAt>plan.plannedEntryAt&&plan.deadlineAt<=plan.decisionAt+72*3600000,"Invalid scheduled holding deadline");
      }
      trade=replayCampaign(opportunity,s,data,p,fold.selected.split(":")[1],quantity);
    }
    catch(error){
      incidents.push({code:error.code||"REPLAY_ERROR",message:error.message,opportunity_id:opportunity.id,details:error.details??null,exposure:error.exposure??null});
      return {status:"INCOMPLETE_EVALUATION",netUsd:null,portfolio:null,funded,states,skipped,incidents,preEntryRefusals,curve:null};
    }
    if(trade===null){
      incidents.push({code:"NULL_PATH_IN_FROZEN_COHORT",opportunity_id:opportunity.id,reason:"No explicit REFUSED_BEFORE_ENTRY admission was returned. An unresolved null is not assigned zero PnL and invalidates the portfolio evaluation."});
      return {status:"INCOMPLETE_EVALUATION",netUsd:null,portfolio:null,funded,states,skipped,incidents,preEntryRefusals,curve:null};
    }
    if(!Number.isFinite(trade.netUsd)||trade.closed<trade.opened){
      incidents.push({code:"INVALID_REPLAY_CAMPAIGN",opportunity_id:opportunity.id});
      return {status:"INCOMPLETE_EVALUATION",netUsd:null,portfolio:null,funded,states,skipped,incidents,preEntryRefusals,curve:null};
    }
    if(verifyFundedEntryFill){
      let receipt;
      try{receipt=verifyFundedEntryFill(trade,opportunity,s,p,budgets);}
      catch(error){
        funded.push({...trade,evaluationStatus:"UNVERIFIED_MODELED_FILL",economicPnlUsd:null});
        incidents.push({code:"FILL_VALIDATOR_FAILED",message:error.message,opportunity_id:opportunity.id,
          exposure:{symbol:trade.symbol,opened:trade.opened,quantity:trade.quantity,entry:trade.entry},economicPnlUsd:null});
        return {status:"INCOMPLETE_EVALUATION",netUsd:null,portfolio:null,funded,states,skipped,incidents,preEntryRefusals,curve:null};
      }
      states.at(-1).fill_validation=receipt;
      if(!receipt||receipt.status!=="VERIFIED"){
        funded.push({...trade,evaluationStatus:"NO_FACTIBLE_MODELED_FILL",economicPnlUsd:null});
        incidents.push({code:"FILLED_ENTRY_EXCEEDS_EX_ANTE_BUDGET",opportunity_id:opportunity.id,receipt,economicPnlUsd:null});
        return {status:"NO_FACTIBLE",netUsd:null,portfolio:null,funded,states,skipped,incidents,preEntryRefusals,curve:null};
      }
      pendingReserves.set(trade.id,budgets.notionalBudgetUsd+quantity*p.costs.perSideUsd);
    }
    funded.push(trade);
  }
  const symbols=p.universe,curve=[];let equity=limits.capitalUsd;
  for(const [i,session] of frozen.oos.entries()){
    const previous=i?frozen.oos[i-1].close:session.open-1;
    const assetPnl=Object.fromEntries(symbols.map(symbol=>[symbol,funded.filter(t=>t.symbol===symbol).reduce((n,t)=>n+valueAt(t,session.close)-valueAt(t,previous),0)]));
    const pnl=funded.reduce((n,t)=>n+valueAt(t,session.close)-valueAt(t,previous),0),end=equity+pnl;
    assert(Math.abs(pnl-Object.values(assetPnl).reduce((a,b)=>a+b,0))<1e-9);
    curve.push({session_id:session.date,start_at:previous,end_at:session.close,equity_start_usd:equity,equity_end_usd:end,
      modeled_trading_pnl_usd:pnl,portfolio_return:pnl/equity,portfolio_log_return:equity>0&&end>0?Math.log(end/equity):null,
      asset_pnl_usd:assetPnl,asset_return_contributions:Object.fromEntries(symbols.map(symbol=>[symbol,assetPnl[symbol]/equity])),
      open_campaigns_at_close:funded.filter(t=>t.opened<=session.close&&t.closed>session.close).map(t=>t.id),external_costs_usd:null});
    equity=end;
  }
  const terminal=frozen.oos.at(-1).close;
  if(funded.some(t=>t.closed>terminal)){
    incidents.push({code:"OPEN_EXPOSURE_AT_EVALUATION_END",campaign_ids:funded.filter(t=>t.closed>terminal).map(t=>t.id),terminal_equity_mark_usd:equity});
    return {status:"INCOMPLETE_EVALUATION",netUsd:null,portfolio:null,funded,states,skipped,incidents,preEntryRefusals,curve};
  }
  const netUsd=funded.reduce((n,t)=>n+t.netUsd,0);
  assert(Math.abs(equity-limits.capitalUsd-netUsd)<1e-8,"Terminal account reconciliation");
  const portfolio={scope:"MODELED_SHARED_CAPITAL_INTEGER_LOTS",limits,oos:metrics(curve.map(r=>r.portfolio_return),funded.map(t=>t.netR)),netUsd,skipped};
  return {status:"COMPLETE_EXPLORATORY_ONLY",netUsd,portfolio,funded,states,skipped,incidents,preEntryRefusals,curve,
    holding:{maximum_hours:Math.max(0,...funded.map(t=>(t.closed-t.opened)/3600000)),exceeding72:funded.filter(t=>t.closed-t.opened>72*3600000).map(t=>t.id)}};
}
function main(){
  const [mode,baseArg,candidateArg,registrationArg]=process.argv.slice(2);
  assert(["bindings","baseline","candidate","verify-candidate"].includes(mode),"Mode must be bindings, baseline, candidate, or verify-candidate");
  assert(baseArg,"Baseline app required");
  if(mode==="bindings"){assert(candidateArg,"Candidate app required");console.log(JSON.stringify(bindings(baseArg,candidateArg),null,2));return;}
  const candidateMode=mode==="candidate"||mode==="verify-candidate";
  let registration=null;
  if(candidateMode)registration=requireRegistration(baseArg,candidateArg,registrationArg);
  const frozen=JSON.parse(fs.readFileSync(INPUT,"utf8")),loaded=loadBaseline(baseArg);
  assert.equal(frozen.datasetHash,loaded.report.datasetHash);assert.equal(frozen.protocolHash,loaded.report.protocolHash);
  assert.equal(frozen.baselineReportSha256,fileHash(path.join(loaded.app,"evidence/ultimate/report.json")));
  assert.equal(frozen.baselineReplaySha256,fileHash(path.join(loaded.app,"runtime30/ultimate_replay.js")));
  const output=path.join(__dirname,candidateMode?"candidate":"baseline"),attempt=path.join(__dirname,"candidate_attempt_started.json");
  let originalCandidate=null;
  if(mode==="verify-candidate"){
    const reservation=JSON.parse(fs.readFileSync(attempt,"utf8"));
    assert.equal(reservation.trial_id,registration.trial_id,"Verify must use the original reserved trial");
    assert.equal(reservation.registration_sha256,fileHash(registrationArg));
    assert.deepEqual(reservation.bindings,registration.bindings);
    originalCandidate=JSON.parse(fs.readFileSync(path.join(output,"result.json"),"utf8"));
    assert.equal(originalCandidate.mode,"candidate");
    assert.equal(originalCandidate.registration.trial_id,registration.trial_id);
    assert.equal(originalCandidate.registration.sha256,fileHash(registrationArg));
    assert.equal(originalCandidate.input_sha256,fileHash(INPUT));
    assert.equal(originalCandidate.runner_sha256,fileHash(__filename));
    assert.equal(originalCandidate.implementation_sha256,fileHash(path.join(candidateArg,"runtime30/ultimate_replay.js")));
    assert(originalCandidate.result&&["COMPLETE_EXPLORATORY_ONLY","INCOMPLETE_EVALUATION","NO_FACTIBLE"].includes(originalCandidate.result.status),"Original result must be closed before reproduction");
  }
  if(mode==="candidate"){
    fs.writeFileSync(attempt,JSON.stringify({trial_id:registration.trial_id,started_at:new Date().toISOString(),registration_sha256:fileHash(registrationArg),bindings:registration.bindings},null,2)+"\n",{flag:"wx"});
  }
  if(mode!=="verify-candidate")fs.mkdirSync(output,{recursive:true});
  const implementation=path.resolve(mode==="baseline"?baseArg:candidateArg);
  const {replayCampaign,planCalendarHolding,causalReferencePrice,verifyFundedEntryFill}=require(path.join(implementation,"runtime30/ultimate_replay.js"));
  if(candidateMode)for(const [name,fn] of Object.entries({planCalendarHolding,causalReferencePrice,verifyFundedEntryFill}))assert.equal(typeof fn,"function","Candidate requires "+name);
  const {metrics}=require(path.join(loaded.app,"runtime30/ultimate_stats.js"));
  const started=performance.now(),result=replayFrozen(frozen,loaded.data,replayCampaign,metrics,candidateMode?planCalendarHolding:null,candidateMode?causalReferencePrice:null,candidateMode?verifyFundedEntryFill:null);
  if(mode==="baseline")assert.deepEqual(result.portfolio,loaded.report.fundedPortfolio,"Baseline funded loop must reproduce complete original portfolio");
  if(mode==="verify-candidate"){
    assert.deepEqual(result,originalCandidate.result,"Identical registered candidate did not reproduce");
    console.log(JSON.stringify({mode,verified:true,trial_id:registration.trial_id,new_financial_trials:0,outputs_rewritten:false,netUsd:result.netUsd,status:result.status}));
    return;
  }
  const receipt={schema:"HARPOON_ONE_CORRECTION_FIXED_SELECTION_RESULT_1",mode,scope:"EXPLORATORY_REUSED_HISTORY_MODELED_EXECUTION",financial_acceptance_allowed:false,
    new_financial_variants:mode==="candidate"?1:0,fits:0,fold_selection_frozen:true,opportunities_frozen:true,capital_reexecuted:true,
    registration:registration?{trial_id:registration.trial_id,sha256:fileHash(registrationArg)}:null,
    input_sha256:fileHash(INPUT),runner_sha256:fileHash(__filename),implementation_sha256:fileHash(path.join(implementation,"runtime30/ultimate_replay.js")),
    elapsed_ms:performance.now()-started,result};
  fs.writeFileSync(path.join(output,"result.json"),JSON.stringify(receipt,null,2)+"\n");
  fs.writeFileSync(path.join(output,"continuous_portfolio_curve.json"),JSON.stringify({scope:receipt.scope,initial_capital_usd:frozen.limits.capitalUsd,sessions:result.curve},null,2)+"\n");
  fs.writeFileSync(path.join(output,"funded_campaigns.json"),JSON.stringify({scope:receipt.scope,status:result.status,portfolio_pnl_usd:result.netUsd,financial_acceptance_allowed:false,incidents:result.incidents,campaigns:result.funded},null,2)+"\n");
  fs.writeFileSync(path.join(output,"reproduction_capture.json"),JSON.stringify({scope:receipt.scope,protocolHash:frozen.protocolHash,datasetHash:frozen.datasetHash,
    funded:result.funded,sizing:result.states,oos:frozen.oos,fundedPnl:result.curve?.map(r=>r.modeled_trading_pnl_usd)??null,
    fundedReturns:result.curve?.map(r=>r.portfolio_return)??null,limits:frozen.limits,portfolioSkips:result.skipped,preEntryRefusals:result.preEntryRefusals,folds:frozen.folds},null,2)+"\n");
  console.log(JSON.stringify({mode,status:result.status,netUsd:result.netUsd,campaigns:result.funded.length,sessions:result.curve?.length??null,holding:result.holding??null,financial_acceptance_allowed:false}));
}
module.exports={bindings,requireRegistration,replayFrozen};
if(require.main===module)main();
