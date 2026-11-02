"use strict";
/** Offline native historical bank. No broker, model selection or LIVE route. */
const fs = require("node:fs"), path = require("node:path"), crypto = require("node:crypto");
const {spawnSync} = require("node:child_process");
const ROOT = path.resolve(__dirname, "..");
const {defaultProtocol, assertProtocol, assertDataset} = require("../runtime30/ultimate_contracts.js");
const {opportunities, replayCampaign, replayFundedPortfolio} = require("../runtime30/ultimate_replay.js");
const need = (ok, reason) => {if (!ok) throw Error(reason);};
const read = file => JSON.parse(fs.readFileSync(file, "utf8"));
const sha = value => crypto.createHash("sha256").update(value).digest("hex");
function write(file, value) {fs.mkdirSync(path.dirname(file), {recursive:true}); fs.writeFileSync(file, JSON.stringify(value) + "\n");}
function researchProtocol(protocol, scenario="NOMINAL") {
  const cost = protocol.scenarios[scenario];
  need(cost && ["NOMINAL", "STRESS"].includes(scenario), "FROZEN_SCENARIO_REQUIRED");
  return assertProtocol({...defaultProtocol("ALPACA_PROXY"), universe:protocol.universe,
    costs:{spreadBps:cost.spread_bps, slippageBps:cost.slippage_bps, perSideUsd:cost.commission_usd_per_share_per_side}});
}
function verifyRegistration(directory, scenario, protocolPath, datasetPath) {
  const binding = read(path.join(directory, scenario + ".binding.json"));
  const registration = read(path.join(directory, scenario + ".registration.json"));
  registration.journal_path = path.join(directory, "optimizer.descendant.sqlite3");
  const request = JSON.parse(binding.request_canonical);
  need(request.common_request.scenario===scenario,"REGISTERED_SCENARIO_MISMATCH");
  const python = process.env.HARPOON_QUANT_PYTHON || "python3";
  const result = spawnSync(python, ["-B", path.join(ROOT,"tools/measurement_registration.py"), "--verify-stdin"], {
    cwd:ROOT, input:JSON.stringify({registration, request_canonical:binding.request_canonical}), encoding:"utf8",
    timeout:30000, maxBuffer:1024*1024, env:{...process.env, OPENBLAS_NUM_THREADS:"1", OMP_NUM_THREADS:"1"}});
  need(result.status === 0, "REGISTRATION_VERIFIER_FAILED:" + (result.stdout || result.stderr));
  const receipt = JSON.parse(result.stdout);
  need(receipt.verified && receipt.slots === 3 && receipt.binding_hash === binding.binding_hash, "REGISTRATION_BINDING");
  const actualProtocolHash = sha(fs.readFileSync(protocolPath)), actualDatasetHash = sha(fs.readFileSync(datasetPath));
  // The canonical request carries exact bytes of these inputs, independently of
  // the path where an integral archive is unpacked.
  const hashValues = Object.values(request.source_hashes);
  need(hashValues.includes(actualProtocolHash) && hashValues.includes(actualDatasetHash), "UNREGISTERED_PROTOCOL_OR_DATASET");
  for (const [relative, expected] of Object.entries(request.source_hashes)) {
    const filename = path.resolve(ROOT, relative);
    need(filename.startsWith(ROOT + path.sep) && fs.existsSync(filename), "REGISTERED_SOURCE_UNAVAILABLE:" + relative);
    need(sha(fs.readFileSync(filename)) === expected, "REGISTERED_SOURCE_CHANGED:" + relative);
  }
  return {binding_hash:binding.binding_hash, registered_at:receipt.registered_at,
    budget_before:receipt.budget_before, budget_after:receipt.budget_after,
    audit_head_at_reservation:registration.audit_head_at_reservation,
    scope:"LOCAL_FIXED_RECIPE_BEFORE_COMPUTATION_OVER_PAST_DATA", independent_preregistration:false};
}
function prepare(data, protocol) {
  const p = researchProtocol(protocol), checked = assertDataset(data, p);
  const generated = opportunities(checked, p, {windows:protocol.windows});
  const bySymbol = Object.fromEntries(checked.series.map(s => [s.symbol,s]));
  const labels = [], cutoff = Date.parse(protocol.periods.training_label_known_before);
  for (const signal of generated.signals) {
    const date = new Date(signal.at).toISOString().slice(0,10);
    if (date < protocol.periods.training_start || date > protocol.periods.training_end || signal.at >= cutoff) continue;
    const trade = replayCampaign(signal, bySymbol[signal.symbol], checked, p, "BASELINE", protocol.target.quantity, 1, {cashDividends:true});
    if (!trade) {labels.push({signal_id:signal.id, status:"REFUSED_BEFORE_ENTRY", reason:"CALENDAR_HOLDING_REFUSAL"}); continue;}
    const known = Math.max(trade.closed, trade.marks.at(-1)?.at ?? trade.closed);
    labels.push({signal_id:signal.id, symbol:signal.symbol, hypothesis:signal.hypothesis,
      status:"OBSERVED_MODELED_PATH", label_end:new Date(trade.closed).toISOString(), label_known_at:new Date(known).toISOString(),
      target_return:trade.netEconomicUsd/(trade.quantity*trade.entry), entry_notional_usd:trade.quantity*trade.entry,
      quantity:trade.quantity, modeled_trading_pnl_usd:trade.netUsd,
      dividend_entitlement_usd:trade.dividendAccruedUsd, net_economic_label_usd:trade.netEconomicUsd,
      purge_required:known>=cutoff, origin:"HISTORICAL", execution:"MODELED_OHLCV"});
  }
  return {signals:{schema:"HARPOON_HISTORICAL_SIGNALS_1", origin:"HISTORICAL", ...generated},
    labels:{schema:"HARPOON_HISTORICAL_LABELS_1", origin:"HISTORICAL", labels,
      scope:"Independent fixed quantity training targets, not account returns or additional funded policy trials",
      label_execution:"NATIVE_BASELINE_WITHOUT_PORTFOLIO_ALLOCATION_OR_IOC_ACCOUNT_CEILING", cutoff:protocol.periods.training_label_known_before,
      financial_acceptance_allowed:false}};
}
function summarize(report, protocol) {
  const result = {};
  for (const [phase, start, end] of [["VALIDATION",protocol.periods.validation_start,protocol.periods.validation_end],
      ["TEST",protocol.periods.test_start,protocol.periods.test_end],["CONTINUOUS",protocol.periods.evaluation_start,protocol.periods.evaluation_end]]) {
    const rows = report.curve.filter(r=>start<=r.session_id&&r.session_id<=end);
    need(rows.length>0, "EMPTY_REPORT_PHASE");
    const initial = rows[0].equity_start_usd, final = rows.at(-1).equity_end_usd;
    let peak=initial, dd=0;
    for (const row of rows) {peak=Math.max(peak,row.equity_end_usd); dd=Math.max(dd,1-row.equity_end_usd/peak);}
    const startAt=rows[0].start_at,endAt=rows.at(-1).end_at;
    const trades = report.funded.filter(t=>t.closed>startAt&&t.closed<=endAt);
    const trading = trades.reduce((n,t)=>n+t.netUsd,0);
    const external = rows.reduce((n,r)=>n+(r.external_costs_usd??0),0);
    const div = rows.reduce((n,r)=>n+(r.dividend_income_usd??0),0);
    const assets=Object.fromEntries(protocol.universe.map(symbol=>[symbol,rows.reduce((n,r)=>n+(r.asset_pnl_usd[symbol]??0),0)]));
    const sessions = rows.length;
    result[phase]={period:[rows[0].session_id,rows.at(-1).session_id],sessions,capital_at_phase_start:initial,final_equity:final,
      economic_pnl_modeled_usd:final-initial,total_return_fraction:final/initial-1,
      geometric_mean_per_session:Math.expm1(Math.log(final/initial)/sessions),max_drawdown_close_fraction:dd,
      closed_campaigns:trades.length,closed_campaign_trading_pnl_usd:trading,
      external_costs_modeled_usd:external,dividend_income_usd:div,
      contribution_by_asset_usd:assets,
      contribution_residual_usd:Object.values(assets).reduce((a,b)=>a+b,0)-external-(final-initial),
      positions_carried_in:report.funded.filter(t=>t.opened<=startAt&&t.closed>startAt).length,
      positions_carried_out:report.funded.filter(t=>t.opened<=endAt&&t.closed>endAt).length,
      closing_valuation_scope:"Latest known campaign marks at exchange session close; full terminal inventory reconciled",
      closed_trade_concentration:{largest_net_trade_usd:trades.length?Math.max(...trades.map(t=>t.netUsd)):null,
        net_excluding_largest_trade_usd:trades.length?trading-Math.max(...trades.map(t=>t.netUsd)):null},
      return_is_after_tax:false, real_profitability:null};
  }
  const placed=report.states.filter(s=>["MODELED_CAMPAIGN","MODELED_IOC_NO_FILL"].includes(s.status));
  const requested=placed.reduce((n,s)=>n+s.quantity,0),executed=report.funded.reduce((n,t)=>n+t.quantity,0);
  result.execution={orders_placed_modeled:placed.length,filled_campaigns:report.funded.length,
    requested_shares_modeled:requested,filled_shares_modeled:executed,fill_ratio_modeled:requested?executed/requested:null,
    pending_or_open_terminal:0,
    real_fill_ratio:null, real_fill_ratio_null_reason:"No historical broker executions; IOC open-price model only"};
  const windows={};
  const states=new Map(report.states.map(s=>[s.opportunity.id,s]));
  for(const trade of report.funded){const state=states.get(trade.id);if(!state)continue;
    const window=state.opportunity.at<=state.day.open+90*60000?"OPEN90":"CLOSE90";
    const key=trade.symbol+":"+window;
    windows[key]??={campaigns:0,modeled_trading_pnl_usd:0,dividend_income_usd:0};
    windows[key].campaigns++;windows[key].modeled_trading_pnl_usd+=trade.netUsd;
    windows[key].dividend_income_usd+=trade.dividendAccruedUsd??0;
  }
  result.window_attribution=windows;
  result.window_attribution_scope="Entire continuous account, by entry window; no separately reset capital or standalone window strategy";
  result.exposure={maximum_reserved_notional_usd:Math.max(0,...report.states.map(s=>s.reservationAfter?.notionalUsd??0)),
    maximum_reserved_risk_usd:Math.max(0,...report.states.map(s=>s.reservationAfter?.riskUsd??0)),
    actual_market_depth:null,actual_market_depth_null_reason:"OHLCV only"};
  return result;
}
function runOne(data, protocol, signalArtifact, admissions, policy, scenario) {
  need(["C0","RIDGE","SVR"].includes(policy), "FIXED_POLICY");
  const p=researchProtocol(protocol,scenario),checked=assertDataset(data,p);
  const periods=protocol.periods;
  const sessions=checked.sessions.filter(s=>periods.evaluation_start<=s.date&&s.date<=periods.evaluation_end);
  const validation=sessions.filter(s=>s.date<=periods.validation_end), test=sessions.filter(s=>s.date>=periods.test_start);
  const options={continuous:true,cashDividends:true,entryExecution:protocol.entry_execution,
    externalCostPerSessionUsd:protocol.scenarios[scenario].external_cost_usd_per_session,
    ...(policy==="C0"?{}:{admissions:admissions.admissions[policy]})};
  const result=replayFundedPortfolio(signalArtifact.signals,checked,p,
    [{test:validation,selected:"ALL:BASELINE"},{test,selected:"ALL:BASELINE"}],sessions,protocol.limits,options);
  const report={schema:"HARPOON_HISTORICAL_PORTFOLIO_1",origin:"HISTORICAL",execution:"MODELED_OHLCV",policy,scenario,
    native_control:protocol.native_control,native_control_is_production_coordinator:false,
    parameter_selection:false,...result,financial_acceptance_allowed:false,liveApproved:false};
  report.summary=summarize(report,protocol);
  return report;
}
function main(argv) {
  const mode=argv.shift(),args={};
  for(let i=0;i<argv.length;i+=2){need(argv[i].startsWith("--")&&argv[i+1],"KEY_VALUE_ARGUMENTS");args[argv[i].slice(2)]=argv[i+1];}
  need(["prepare","replay"].includes(mode),"MODE_PREPARE_OR_REPLAY");
  const protocolPath=path.resolve(args.protocol), datasetPath=path.resolve(args.dataset), directory=path.resolve(args["registration-dir"]),out=path.resolve(args["output-dir"]);
  const protocol=read(protocolPath),data=read(datasetPath);
  need(protocol.origin==="HISTORICAL"&&protocol.live_approved===false,"HISTORICAL_ONLY");
  const registration=Object.fromEntries(["NOMINAL","STRESS"].map(s=>[s,verifyRegistration(directory,s,protocolPath,datasetPath)]));
  const started=process.hrtime.bigint();
  if(mode==="prepare"){
    const prepared=prepare(data,protocol);
    write(path.join(out,"signals.json"),prepared.signals);write(path.join(out,"training_labels.json"),prepared.labels);
    process.stdout.write(JSON.stringify({mode,signals:prepared.signals.signals.length,training_labels:prepared.labels.labels.length})+"\n");
  }else{
    const signalArtifact=read(path.join(out,"signals.json")),admissions=read(path.join(out,"admissions.json"));
    const prepared=prepare(data,protocol);
    need(JSON.stringify(prepared.signals)===JSON.stringify(signalArtifact),"SIGNAL_DERIVATION_MISMATCH");
    need(JSON.stringify(prepared.labels)===JSON.stringify(read(path.join(out,"training_labels.json"))),"LABEL_DERIVATION_MISMATCH");
    const verify=spawnSync(process.env.HARPOON_QUANT_PYTHON||"python3",["-B","-m","harpoon_quant.historical_bank","verify",
      "--protocol",protocolPath,"--dataset",datasetPath,"--signals",path.join(out,"signals.json"),
      "--labels",path.join(out,"training_labels.json"),"--panel",path.join(out,"feature_panel.json"),
      "--models",path.join(out,"models.json"),"--admissions",path.join(out,"admissions.json"),
      "--output",path.join(out,"derivation_verification.json")],{cwd:ROOT,encoding:"utf8",timeout:1800000,maxBuffer:1024*1024,
      env:{...process.env,PYTHONPATH:path.join(ROOT,"quant"),OPENBLAS_NUM_THREADS:"1",OMP_NUM_THREADS:"1"}});
    need(verify.status===0,"DERIVATION_VERIFIER_FAILED:"+(verify.stdout||verify.stderr));
    need(read(path.join(out,"derivation_verification.json")).verified===true,"DERIVATION_NOT_VERIFIED");
    const reportPaths={};
    for(const scenario of ["NOMINAL","STRESS"])for(const policy of ["C0","RIDGE","SVR"]){
      const file=scenario+"_"+policy+".json";
      try{
        const report=runOne(data,protocol,signalArtifact,admissions,policy,scenario);
        report.registration=registration[scenario];write(path.join(out,file),report);reportPaths[scenario+":"+policy]=file;
        process.stdout.write(JSON.stringify({scenario,policy,summary:report.summary.CONTINUOUS,test:report.summary.TEST})+"\n");
      }catch(error){
        write(path.join(out,scenario+"_"+policy+".incident.json"),{schema:"HARPOON_HISTORICAL_INCIDENT_1",scenario,policy,
          error:error.message,details:error.details??null,economic_pnl_usd:null,financial_acceptance_allowed:false});
        throw error;
      }
    }
    write(path.join(out,"reports.json"),reportPaths);
  }
  write(path.join(out,mode+"_benchmark.json"),{schema:"HARPOON_HISTORICAL_LOCAL_BENCHMARK_1",mode,
    elapsed_seconds:Number(process.hrtime.bigint()-started)/1e9,max_rss_kib:process.resourceUsage().maxRSS,
    node_version:process.version,platform:process.platform,architecture:process.arch,
    nature:"LOCAL_OFFLINE_COMPUTATION_NOT_TRADING_LATENCY"});
}
module.exports={prepare,runOne,summarize,researchProtocol,verifyRegistration};
if(require.main===module)try{main(process.argv.slice(2));}catch(error){process.stderr.write(String(error.stack||error)+"\n");process.exitCode=2;}
