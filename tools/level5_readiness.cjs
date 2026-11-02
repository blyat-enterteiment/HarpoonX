"use strict";
/** Offline producer for the economic v2 gate. Never supplies order authority. */
const fs=require("node:fs"),path=require("node:path"),crypto=require("node:crypto");
const {hash}=require("./coordinator_replay.cjs");
const {verifyFundedComparison}=require("./funded_comparison.cjs");
const {assessLevel4,parseStrictJSON}=require("./level4_readiness.cjs");
const {verifyNetLedgerHistoryBundle}=require("../runtime30/net_accounting.js");
const ROOT=path.resolve(__dirname,".."),SCHEMA="HARPOON_LEVEL5_DERIVED_EVIDENCE_1",REQUEST_SCHEMA="HARPOON_LEVEL5_DERIVATION_REQUEST_1";
const authority={execution_allowed:false,liveApproved:false,financial_acceptance_allowed:false};
const need=(ok,code)=>{if(!ok)throw Error(code);};
const sha=x=>crypto.createHash("sha256").update(x).digest("hex");
const finite=x=>typeof x==="number"&&Number.isFinite(x);
const copy=x=>JSON.parse(JSON.stringify(x));
const COST_FIELDS=["fees_bps_per_side","fee_per_fill_usd","slippage_bps"];
const bridgeHashes=()=>Object.fromEntries(["tools/level5_readiness.cjs","tools/level4_readiness.cjs"].map(n=>[n,sha(fs.readFileSync(path.join(ROOT,n)))]));
function readRef(ref,base,sources){
  need(ref&&typeof ref.path==="string"&&/^[a-f0-9]{64}$/.test(ref.sha256||""),"BOUND_SOURCE_REFERENCE_REQUIRED");
  const filename=path.resolve(base,ref.path),stat=fs.statSync(filename);
  need(stat.isFile()&&stat.size<=32*1024*1024,"SOURCE_FILE_SIZE_BOUND");
  const raw=fs.readFileSync(filename);need(sha(raw)===ref.sha256,"SOURCE_FILE_HASH_MISMATCH");
  sources.push({sha256:ref.sha256,bytes:raw.length});need(sources.reduce((n,x)=>n+x.bytes,0)<=192*1024*1024,"EVIDENCE_TOTAL_BYTES_BOUND");
  return {value:parseStrictJSON(raw.toString("utf8")),filename};
}
function stressBinding(base,stress){
  const a=copy(base),b=copy(stress),changes={};
  delete a.registration;delete b.registration;delete a.common_request.id;delete b.common_request.id;
  for(const key of COST_FIELDS){
    const before=a.common_request.execution_model[key],after=b.common_request.execution_model[key];
    need(finite(before)&&finite(after)&&after>=before,"STRESS_MUST_NOT_REDUCE_COST:"+key);
    if(after!==before)changes[key]=after;
    delete a.common_request.execution_model[key];delete b.common_request.execution_model[key];
  }
  need(Object.keys(changes).length>0,"STRESS_MUST_CHANGE_EXECUTION_COST");
  need(hash(a)===hash(b),"STRESS_CHANGED_MODEL_SIGNALS_MARKET_RISK_OR_CAPITAL");
  return changes;
}
function applyCostSchedule(rows,schedule,initial,startAt){
  if(schedule===null)return rows;
  const combined=rows.map((r,i)=>({at:r.at,rank:0,index:i,row:r}));
  for(const [i,c]of schedule.entries())combined.push({at:c.at,rank:1,index:i,cost:c});
  combined.sort((a,b)=>a.at-b.at||a.rank-b.rank||a.index-b.index);
  let cumulative=0,previous={event_id:"INITIAL",at:startAt,session_id:rows[0].session_id,cash_usd:initial,
    inventory_value_usd:0,account_equity_usd:initial,cumulative_fees_usd:0,positions:[],external_flow_usd:0,
    buying_power_usd:rows[0].buying_power_usd,non_marginable_buying_power_usd:rows[0].non_marginable_buying_power_usd,
    operating_cash_reserve_usd:rows[0].operating_cash_reserve_usd,operating_reserve_known_at:rows[0].operating_reserve_known_at};
  const out=[];
  for(const item of combined){
    if(item.row)previous=item.row;
    else cumulative+=item.cost.amount_usd;
    const session=item.row?item.row.session_id:(rows.find(r=>r.at>=item.at)||rows.at(-1)).session_id;
    out.push({...copy(previous),event_id:item.row?item.row.event_id:"COST:"+item.cost.id,at:item.at,session_id:session,
      cumulative_external_cost_usd:cumulative,economic_equity_usd:previous.account_equity_usd-cumulative,
      valuation_carried_for_cost_event:!item.row});
  }
  return out;
}
function derivePolicies(input,report,costSchedule=null){
  const common=input.common_request,initial=common.initial_cash_usd,reserve=common.execution_model.operating_cash_reserve??null;
  need(report.curves&&report.reports?.length===3,"COMPLETE_REEXECUTED_COMPARISON_REQUIRED");
  const result={};
  for(const [role,source]of [["NATIVE","C0"],["RIDGE","RIDGE"],["SVR","SVR"]]){
    const rows=report.curves[source].curve,replay=report.reports.find(r=>r.result.candidate===source);
    need(rows.length>0&&replay,"POLICY_TRACE_MISSING");
    const normalized=rows.map((r,i)=>({event_id:r.event_id,at:r.at,session_id:r.session,cash_usd:r.cash_usd,
        inventory_value_usd:r.inventory_value_usd,account_equity_usd:r.account_equity_usd,
        economic_equity_usd:r.economic_equity_usd,cumulative_fees_usd:r.cumulative_fees_usd,
        cumulative_external_cost_usd:r.cumulative_external_cost_usd,external_flow_usd:r.external_flow_usd,
        positions:copy(r.positions),buying_power_usd:Number(replay.result.snapshots[i].account.buying_power),
        non_marginable_buying_power_usd:Number(replay.result.snapshots[i].account.non_marginable_buying_power),
        operating_cash_reserve_usd:replay.result.snapshots[i].account.operating_cash_reserve_usd??null,
        operating_reserve_known_at:replay.result.snapshots[i].account.operating_reserve_known_at??null}));
    let maxHold=0;
    for(const snapshot of replay.result.snapshots)for(const campaign of snapshot.campaigns||[]){
      const end=campaign.closed?campaign.closedAt:snapshot.at;
      need(finite(end)&&finite(campaign.created)&&end>=campaign.created,"CAMPAIGN_AGE_UNVERIFIABLE");
      maxHold=Math.max(maxHold,(end-campaign.created)/3600000);
    }
    result[role]={role,source_policy:source,initial_equity_usd:initial,operating_cash_reserve:copy(reserve),
      events:applyCostSchedule(normalized,costSchedule,initial,common.start_at),maximum_observed_holding_hours:maxHold,
      execution_io_failure_count:replay.result.io_failures.length,
      stale_terminal_valuation_symbols:copy(replay.result.metrics.stale_valuation_symbols),
      execution_trace_hash:hash(replay.result),terminal_inventory_forced_closed:false};
  }
  const template=result.NATIVE.events;
  need(["RIDGE","SVR"].every(p=>hash(result[p].events.map(r=>[r.event_id,r.at,r.session_id]))===hash(template.map(r=>[r.event_id,r.at,r.session_id]))),"EVENT_TIMELINES_NOT_PAIRED");
  // A deterministic no-entry reference incurs the same shared external costs.
  // It has no transaction fees, no invented interest and never borrows capital.
  result.CASH={role:"CASH",source_policy:"DETERMINISTIC_NO_ENTRY",initial_equity_usd:initial,operating_cash_reserve:copy(reserve),
    events:template.map(r=>({event_id:r.event_id,at:r.at,session_id:r.session_id,cash_usd:initial,
      inventory_value_usd:0,account_equity_usd:initial,economic_equity_usd:initial-r.cumulative_external_cost_usd,
      cumulative_fees_usd:0,cumulative_external_cost_usd:r.cumulative_external_cost_usd,external_flow_usd:0,positions:[],
      buying_power_usd:initial-(reserve?.amount_usd??0),non_marginable_buying_power_usd:initial-(reserve?.amount_usd??0),
      operating_cash_reserve_usd:reserve?.amount_usd??null,operating_reserve_known_at:reserve?.known_at??null})),
    stale_terminal_valuation_symbols:[],execution_trace_hash:null,terminal_inventory_forced_closed:false,
    maximum_observed_holding_hours:0,execution_io_failure_count:0,
    research_slots_added:0,cost_scope:"SAME_SHARED_EXTERNAL_COSTS;NO_TRADES_NO_TRANSACTION_FEES;NO_INTEREST_ASSUMED"};
  return result;
}
/** Read identities from already reexecuted numerical receipts, not file metadata.
 * model_hashes and receipt.model_hash bind the original JSON bytes. The plan's
 * model_hash is Python digest(model), which can differ even for the same model.
 * Never recompute that digest in JS or equate it with the source-file hash.
 * This extraction alone does not verify a comparison or authorize forward use.
 */
function runtimePredictorBindings(report){
  need(Array.isArray(report?.reports),"RUNTIME_PREDICTOR_REPORTS_REQUIRED");
  const validHash=value=>typeof value==="string"&&/^[a-f0-9]{64}$/.test(value);
  const result={};
  for(const role of ["SVR","RIDGE"]){
    const matches=report.reports.filter(r=>r?.result?.candidate===role);
    need(matches.length===1,"RUNTIME_PREDICTOR_ROLE_NOT_UNIQUE:"+role);
    const decisions=matches[0].result.decisions;
    need(Array.isArray(decisions),"RUNTIME_PREDICTOR_DECISIONS_REQUIRED:"+role);
    const numerical=decisions.filter(d=>d?.origin==="REEXECUTED_FIXED_JSON_MODEL"||d?.numerical_receipt!==undefined);
    need(numerical.length>0,"RUNTIME_PREDICTOR_RECEIPTS_MISSING:"+role);
    need(validHash(report.model_hashes?.[role]),"RUNTIME_PREDICTOR_SOURCE_HASH_REQUIRED:"+role);
    let identity=null;
    for(const decision of numerical){
      const receipt=decision.numerical_receipt;
      need(decision.origin==="REEXECUTED_FIXED_JSON_MODEL"&&receipt?.schema==="HARPOON_FIXED_PREDICTOR_RECEIPT_1"&&
        receipt.status==="COMPUTED"&&receipt.predictor===role,"RUNTIME_PREDICTOR_RECEIPT_SCHEMA:"+role);
      need(receipt.model_hash===report.model_hashes[role]&&decision.model_hash===receipt.model_hash,
        "RUNTIME_PREDICTOR_SOURCE_MODEL_MISMATCH:"+role);
      need(decision.request&&receipt.request_hash===decision.request_hash&&hash(decision.request)===receipt.request_hash&&
        decision.receipt_hash===hash(receipt),"RUNTIME_PREDICTOR_RECEIPT_BINDING:"+role);
      need(receipt.training_executed===false&&receipt.execution_allowed===false&&receipt.liveApproved===false&&
        receipt.financial_acceptance_allowed===false,"RUNTIME_PREDICTOR_AUTHORITY_CHANGED:"+role);
      need(typeof receipt.result_json==="string"&&Buffer.byteLength(receipt.result_json)<=2*1024*1024&&
        receipt.result_hash===sha(receipt.result_json),"RUNTIME_PREDICTOR_RESULT_HASH:"+role);
      const plan=parseStrictJSON(receipt.result_json),available=plan?.decision_inputs?.calibration_available_at;
      need(plan?.engine==="HARPOON_QUANT_1"&&validHash(plan.model_hash)&&validHash(plan.config_hash),
        "RUNTIME_PREDICTOR_PLAN_IDENTITY_REQUIRED:"+role);
      need(typeof available==="string"&&/T.*(?:Z|[+-]\d\d:\d\d)$/.test(available)&&Number.isFinite(Date.parse(available))&&
        available===receipt.model_available_at&&Number.isSafeInteger(decision.request.now)&&Date.parse(available)<decision.request.now,
        "RUNTIME_PREDICTOR_AVAILABILITY_REQUIRED:"+role);
      const current={model_hash:plan.model_hash,quant_config_hash:plan.config_hash,model_available_at:available};
      need(identity===null||hash(identity)===hash(current),"RUNTIME_PREDICTOR_IDENTITY_CHANGED:"+role);
      identity=current;
    }
    result[role]=identity;
  }
  return result;
}
function binding(input,report,readiness){
  const common=input.common_request;
  const implementation={...report.source_hashes};
  for(const name of ["tools/level5_readiness.cjs","tools/level4_readiness.cjs"])
    implementation[name]=sha(fs.readFileSync(path.join(ROOT,name)));
  // This readiness object was reconstructed above. In particular, the market
  // identity precedes the deterministic offline configuration projection.
  const marketCheck=readiness?.checks?.find(c=>c.id==="comparison_market_receipts_bound"&&c.passed===true);
  const market=marketCheck?.evidence?.verified===true?marketCheck.evidence:null,ledger=readiness?.components?.ledger;
  const sourceConfigHash=market?.source_config_hash??null;
  need(sourceConfigHash===null||/^[a-f0-9]{64}$/.test(sourceConfigHash),"OBSERVED_RUNTIME_CONFIG_HASH_INVALID");
  const accountId=market&&ledger?.verified===true&&typeof market.account_id==="string"&&market.account_id.trim()&&
    market.account_id===ledger.account_id?market.account_id:null;
  return {policy_hash:hash({config:common.config,models:report.model_hashes}),risk_hash:hash(common.config),
    cost_hash:hash({...common.execution_model,external_cost_usd:undefined,external_cost_method:"VERIFIED_LEDGER_ACCRUAL_TIMESTAMPS"}),code_hash:hash(implementation),model_hashes:report.model_hashes,
    observed_runtime_config_hash:sourceConfigHash,observed_account_id:accountId,runtime_predictor_bindings:runtimePredictorBindings(report),
    universe:common.config.universe.map(x=>x.symbol),initial_equity_usd:common.initial_cash_usd,
    period:{start_at:common.start_at,end_at:common.events.at(-1).at},maximum_holding_hours:common.config.exit.maxHoldHours,
    execution_model:copy(common.execution_model),common_request_hash:hash(common),implementation_hashes:implementation};
}
async function deriveLevel5(input,baseDir=process.cwd()){
  need(input?.schema===REQUEST_SCHEMA,"LEVEL5_DERIVATION_REQUEST_SCHEMA");
  need(!Object.hasOwn(input,"policies")&&!Object.hasOwn(input,"curves"),"CALLER_CURVES_NOT_ACCEPTED");
  const initialBridge=bridgeHashes(),sources=[],blockers=[],out={schema:SCHEMA,input_hash:hash(input),...authority,readiness:null,
    comparison:null,bindings:null,policies:null,stress:[],financial_blockers:blockers,
    limitations:["All fills and executable liquidity remain modeled.","Risk is observed at replay-event resolution; unobserved intraperiod paths are not certified.","Local hashes and journals do not independently authenticate a provider, clock or research history.","CASH is a deterministic no-entry reference, not another searched strategy; it pays the same shared external costs."]};
  try{
    const readiness=readRef(input.level4.request,baseDir,sources),base=path.dirname(readiness.filename);
    out.readiness=await assessLevel4(readiness.value,base);
    if(out.readiness.score!==4)blockers.push("LEVEL4_OBSERVED_MEASUREMENT_INCOMPLETE");
    const request=readRef(readiness.value.comparison.request,base,sources),report=readRef(readiness.value.comparison.report,base,sources);
    // assessLevel4 already reran exactly these inputs; bind them, do not trust an exported score.
    const verified=out.readiness.components?.comparison;
    need(verified?.verified===true&&verified.verification?.real_coordinator_and_predictors_reexecuted===true&&
      verified.artifact_hash===report.value.artifact_hash,"BASE_COMPARISON_NOT_REEXECUTED");
    need(report.value.execution_allowed===false&&report.value.liveApproved===false&&report.value.financial_acceptance_allowed===false,"PRODUCER_AUTHORITY_CHANGED");
    out.comparison={artifact_hash:report.value.artifact_hash,input_hash:report.value.input_hash,
      status:report.value.status,data_origin:report.value.data_origin,execution_origin:report.value.execution_origin,
      registration:report.value.registration,request_sha256:readiness.value.comparison.request.sha256};
    let schedule=null;
    try{
      const ledgerRef=readRef(readiness.value.ledger.bundle,base,sources),bundle=ledgerRef.value;
      const ledger=verifyNetLedgerHistoryBundle(bundle.pages,bundle.expected_integrity);
      need(ledger.verified===true,"COST_LEDGER_NOT_REEXECUTED");
      const common=request.value.common_request;
      schedule=ledger.externalCosts.filter(c=>c.already_in_account===false&&c.at>common.start_at&&c.at<=common.events.at(-1).at)
        .map(c=>({id:c.id,at:c.at,amount_usd:c.amount_usd})).sort((a,b)=>a.at-b.at||a.id.localeCompare(b.id));
      need(Math.abs(schedule.reduce((n,c)=>n+c.amount_usd,0)-common.execution_model.external_cost_usd)<1e-7,"COST_SCHEDULE_TOTAL_MISMATCH");
      out.external_cost_schedule={origin:"REEXECUTED_LEDGER",entries:schedule,source_sha256:readiness.value.ledger.bundle.sha256};
    }catch(error){blockers.push("OBSERVED_COST_TIMING_NOT_RECONCILED:"+String(error.message));out.external_cost_schedule=null;}
    out.bindings=binding(request.value,report.value,out.readiness);out.policies=derivePolicies(request.value,report.value,schedule);
    if(report.value.status!=="REGISTERED_MODELED_MEASUREMENT"||report.value.data_origin!=="HISTORICAL")blockers.push("OBSERVED_REGISTERED_MEASUREMENT_REQUIRED");
    need(Array.isArray(input.stress)&&input.stress.length<=1,"STRESS_FAMILY_MAXIMUM_ONE_ADDITIONAL_COMPARISON");
    if(input.stress.length===0)blockers.push("PREREGISTERED_STRESS_MISSING");
    for(const scenario of input.stress){
      try{
        need(typeof scenario.id==="string"&&scenario.id.length>0,"STRESS_ID_REQUIRED");
        const sr=readRef(scenario.request,baseDir,sources),sp=readRef(scenario.report,baseDir,sources);
        const changes=stressBinding(request.value,sr.value),verification=await verifyFundedComparison(sr.value,sp.value);
        need(verification.verified&&verification.real_coordinator_and_predictors_reexecuted,"STRESS_COMPARISON_NOT_REEXECUTED");
        const a=report.value.registration,b=sp.value.registration;
        const reservationVerified=a?.verified===true&&b?.verified===true&&a.slots===3&&b.slots===3&&
          b.budget_before===a.budget_after&&b.budget_after===a.budget_before+6&&
          path.resolve(request.value.registration.journal_path)===path.resolve(sr.value.registration.journal_path);
        if(!reservationVerified)blockers.push("STRESS_SIX_SLOT_RESERVATIONS_NOT_VERIFIED");
        out.stress.push({id:scenario.id,scope:"HYPOTHETICAL_COST_AND_SLIPPAGE_STRESS",changes,verification,
          artifact_hash:sp.value.artifact_hash,registration:sp.value.registration,reservation_verified:reservationVerified,
          policies:derivePolicies(sr.value,sp.value,schedule),bindings:binding(sr.value,sp.value,out.readiness)});
      }catch(error){blockers.push("STRESS_EVIDENCE:"+String(error.message));}
    }
  }catch(error){blockers.push("DERIVATION_EVIDENCE:"+String(error.message));}
  if(hash(initialBridge)!==hash(bridgeHashes())){out.policies=null;out.bindings=null;blockers.push("BRIDGE_IMPLEMENTATION_CHANGED_DURING_REEXECUTION");}
  out.sources=sources;out.complete_derived_comparison=out.policies!==null;
  out.artifact_hash=hash(out);return out;
}
async function verifyLevel5Derivation(input,report,baseDir=process.cwd()){
  const expected=await deriveLevel5(input,baseDir);
  return {schema:"HARPOON_LEVEL5_DERIVATION_VERIFICATION_1",verified:hash(report)===hash(expected),
    expected_artifact_hash:expected.artifact_hash,observed_artifact_hash:report?.artifact_hash??null,...authority};
}
async function main(args){
  const opts={};for(let i=0;i<args.length;i+=2){need(["--input","--output","--verify"].includes(args[i])&&args[i+1],"USAGE --input request.json [--output report.json] [--verify report.json]");opts[args[i]]=args[i+1];}
  need(opts["--input"],"INPUT_REQUIRED");const input=path.resolve(opts["--input"]),request=parseStrictJSON(fs.readFileSync(input,"utf8"));
  const result=opts["--verify"]?await verifyLevel5Derivation(request,parseStrictJSON(fs.readFileSync(opts["--verify"],"utf8")),path.dirname(input)):await deriveLevel5(request,path.dirname(input));
  if(opts["--output"]){fs.writeFileSync(opts["--output"],JSON.stringify(result,null,2)+"\n");process.stdout.write(JSON.stringify({output:path.resolve(opts["--output"]),financial_blockers:result.financial_blockers??null,...authority})+"\n");}
  else process.stdout.write(JSON.stringify(result)+"\n");
}
if(require.main===module)main(process.argv.slice(2)).catch(e=>{process.stderr.write(String(e.message)+"\n");process.exitCode=2;});
module.exports={SCHEMA,REQUEST_SCHEMA,deriveLevel5,verifyLevel5Derivation,derivePolicies,stressBinding,applyCostSchedule,runtimePredictorBindings};
