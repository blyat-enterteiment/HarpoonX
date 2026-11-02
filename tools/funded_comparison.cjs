"use strict";
/** Continuous funded comparison using the real isolated coordinator.
 * C0 retains its native entry selection. RIDGE/SVR use the same numerical
 * allocator with fixed JSON models and the same coordinator exits/risk caps.
 * No model fitting, strategy search, broker transport or promotion is provided.
 */
const fs=require("node:fs"),path=require("node:path"),crypto=require("node:crypto");
const replay=require("./coordinator_replay.cjs");
const {canonical,hash}=replay;
const ROOT=path.resolve(__dirname,".."),SCHEMA="HARPOON_FUNDED_COMPARISON_1",REQUEST_SCHEMA="HARPOON_FUNDED_COMPARISON_REQUEST_1";
const POLICIES=["C0","RIDGE","SVR"],clone=x=>JSON.parse(JSON.stringify(x));
const bytesHash=x=>crypto.createHash("sha256").update(x).digest("hex");
const need=(ok,reason)=>{if(!ok)throw Error(reason);};
const near=(a,b)=>Math.abs(a-b)<=1e-7*Math.max(1,Math.abs(a),Math.abs(b));
const authority={execution_allowed:false,liveApproved:false,financial_acceptance_allowed:false};
function comparisonSourceHashes(){
  const result=replay.sourceHashes(),name="tools/measurement_registration.py";
  if(fs.existsSync(path.join(ROOT,name)))result[name]=crypto.createHash("sha256").update(fs.readFileSync(path.join(ROOT,name))).digest("hex");
  return result;
}
function registrationBinding(input){
  const request={...input};delete request.registration;
  return {request_canonical:canonical(request),binding_hash:hash(request)};
}
function variants(input){
  const common=clone(input.common_request);
  return POLICIES.map(name=>({...clone(common),id:common.id+"-"+name,predictor:name==="C0"?{name,mode:"NATIVE"}:
    {name,mode:"NUMERICAL_OFFLINE",model:clone(input.models[name]),model_json:input.model_json?.[name]??canonical(input.models[name]),model_hash:bytesHash(input.model_json?.[name]??canonical(input.models[name])),external_execution_allowed:false,timeout_ms:input.predictor_timeout_ms??8000}}));
}
function comparisonReadiness(input){
  const blockers=[],missing=[];
  const issue=(field,reason)=>{blockers.push(reason);missing.push({field,value:null,reason});};
  if(!input||input.schema!==REQUEST_SCHEMA)issue("schema","FUNDED_COMPARISON_SCHEMA");
  if(!["SYNTHETIC_SOFTWARE_TEST","PREREGISTERED_FIXED_MODEL_MEASUREMENT"].includes(input?.purpose))issue("purpose","EXPLICIT_COMPARISON_PURPOSE_REQUIRED");
  if(input?.account_scope!=="CASH_ONLY_COUNTERFACTUAL_NO_EXTERNAL_FLOWS")issue("account_scope","EXPLICIT_CASH_ONLY_COUNTERFACTUAL_SCOPE_REQUIRED");
  const common=input?.common_request;
  if(!common||typeof common!=="object")issue("common_request","COMMON_COORDINATOR_REQUEST_REQUIRED");
  else{
    if(common.predictor)issue("common_request.predictor","COMMON_REQUEST_MUST_NOT_CONTAIN_PREDICTOR");
    if(common.initial_positions?.length||common.external_flows?.length)issue("common_request.initial_positions","NONCASH_INITIAL_STATE_OR_EXTERNAL_FLOWS_OUTSIDE_SCOPE");
    if(!Array.isArray(common.events)||!common.events.some(e=>e.type==="entries"))issue("common_request.events","FUNDED_ENTRY_EVENTS_REQUIRED");
    if(common.config?.universe?.some(a=>!["equity","etf"].includes(a.book)||a.multiplier!==1))issue("common_request.config.universe","COMPARISON_EQUITY_ETF_SHARE_SCOPE");
    try{replay.validateRequest(common);}catch(error){issue("common_request",String(error.message));}
    if(input.purpose==="SYNTHETIC_SOFTWARE_TEST"&&common.data_origin!=="SYNTHETIC")issue("purpose","OBSERVED_DATA_CANNOT_USE_SYNTHETIC_TEST_AUTHORITY");
  }
  for(const name of POLICIES.slice(1)){
    const model=input?.models?.[name];
    if(!model||typeof model!=="object"||Array.isArray(model)){issue("models."+name,"FIXED_MODEL_REQUIRED:"+name);continue;}
    if(!["OBSERVED","SYNTHETIC_ENGINEERING_ONLY"].includes(model.origin))issue("models."+name+".origin","MODEL_ORIGIN_REQUIRED:"+name);
    if(input.purpose==="SYNTHETIC_SOFTWARE_TEST"&&model.origin!=="SYNTHETIC_ENGINEERING_ONLY")issue("models."+name+".origin","SYNTHETIC_TEST_REQUIRES_SYNTHETIC_MODEL:"+name);
    if(input.purpose==="PREREGISTERED_FIXED_MODEL_MEASUREMENT"&&model.origin!=="OBSERVED")issue("models."+name+".origin","OBSERVED_MEASUREMENT_REQUIRES_OBSERVED_MODEL:"+name);
    if(input.purpose==="PREREGISTERED_FIXED_MODEL_MEASUREMENT"&&typeof input.model_json?.[name]!=="string")issue("model_json."+name,"ORIGINAL_MODEL_JSON_BYTES_REQUIRED:"+name);
    if(input.model_json?.[name]!==undefined){try{if(typeof input.model_json[name]!=="string"||hash(JSON.parse(input.model_json[name]))!==hash(model))throw Error("CONTENT");}catch{issue("model_json."+name,"MODEL_JSON_CONTENT_MISMATCH:"+name);}}
  }
  if(!blockers.length){
    try{for(const v of variants(input))replay.validateRequest(v);}catch(error){issue("models",String(error.message));}
  }
  if(input?.purpose==="PREREGISTERED_FIXED_MODEL_MEASUREMENT"){
    if(common?.data_origin!=="HISTORICAL")issue("common_request.data_origin","HISTORICAL_MEASUREMENT_ORIGIN_REQUIRED");
    if(hash(input.source_hashes)!==hash(comparisonSourceHashes()))issue("source_hashes","REGISTERED_SOURCE_BINDING_REQUIRED");
    if(!input.registration)issue("registration","VERIFIED_JOURNAL_RESERVATION_REQUIRED");
    if(!fs.existsSync(path.join(ROOT,"tools/measurement_registration.py")))issue("registration","JOURNAL_VERIFIER_UNAVAILABLE");
  }
  return {schema:"HARPOON_FUNDED_COMPARISON_READINESS_1",computable:blockers.length===0,
    status:blockers.length?"MEDICION_BLOQUEADA":"READY_FOR_LOCAL_REPRODUCTION",blockers,missing,
    registration_requires_journal_verification:input?.purpose==="PREREGISTERED_FIXED_MODEL_MEASUREMENT",
    source_authenticity_verified:false,...authority};
}
async function verifyRegistration(input){
  if(input.purpose==="SYNTHETIC_SOFTWARE_TEST")return {required:false,verified:false,scope:"SYNTHETIC_SOFTWARE_TEST_ONLY",...authority};
  const {request_canonical,binding_hash}=registrationBinding(input);
  const python=process.env.HARPOON_QUANT_PYTHON||"python3";
  need(python==="python3"||path.isAbsolute(python)&&/^python(?:\d+(?:\.\d+)*)?$/.test(path.basename(python)),"LOCAL_PYTHON_EXECUTABLE_REQUIRED");
  const payload=JSON.stringify({registration:input.registration,request_canonical});
  need(Buffer.byteLength(payload)<=32*1024*1024,"REGISTRATION_INPUT_LIMIT");
  const result=await new Promise((resolve,reject)=>{
    const child=require("node:child_process").spawn(python,["-B",path.join(ROOT,"tools/measurement_registration.py"),"--verify-stdin"],{cwd:ROOT,shell:false,stdio:["pipe","pipe","pipe"],env:{PATH:process.env.PATH||"/usr/bin:/bin",LANG:"C.UTF-8",OPENBLAS_NUM_THREADS:"1",OMP_NUM_THREADS:"1"}});
    let text="",error="",done=false;
    const finish=(err,value)=>{if(done)return;done=true;clearTimeout(timer);err?reject(err):resolve(value);};
    const timer=setTimeout(()=>{child.kill("SIGKILL");finish(Error("JOURNAL_VERIFIER_TIMEOUT"));},30000);
    child.on("error",e=>finish(Error("JOURNAL_VERIFIER_UNAVAILABLE:"+e.message)));
    child.stdin.on("error",e=>finish(Error("JOURNAL_VERIFIER_INPUT:"+e.message)));
    child.stdout.on("data",d=>{text+=d;if(Buffer.byteLength(text)>1024*1024){child.kill("SIGKILL");finish(Error("JOURNAL_VERIFIER_OUTPUT_LIMIT"));}});
    child.stderr.on("data",d=>{error=(error+d).slice(-1000);});
    child.on("close",code=>{try{need(code===0,"JOURNAL_VERIFIER_FAILED:"+error);finish(null,JSON.parse(text));}catch(e){finish(e);}});
    child.stdin.end(payload);
  });
  need(result.verified===true&&result.binding_hash===binding_hash&&result.slots===3&&result.execution_allowed===false&&result.external_authentication===false,"JOURNAL_REGISTRATION_NOT_VERIFIED");
  need(Number.isInteger(result.budget_before)&&Number.isInteger(result.budget_after)&&result.budget_after===result.budget_before+3,"JOURNAL_BUDGET_COUNTER_MISMATCH");
  // Later valid journal appends do not change the reserved computation. Keep
  // the immutable reservation head, not a mutable current-head observation.
  const stable={...result};delete stable.journal_current_head;
  return {...stable,audit_head_at_reservation:input.registration.audit_head_at_reservation,required:true,scope:"LOCAL_JOURNAL_INTEGRITY_NOT_EXTERNAL_PREREGISTRATION",...authority};
}
function dateNY(at){return new Intl.DateTimeFormat("en-CA",{timeZone:"America/New_York",year:"numeric",month:"2-digit",day:"2-digit"}).format(new Date(at));}
function fundedCurves(report,input){
  const initial=input.initial_cash_usd,external=input.execution_model.external_cost_usd;
  need(near(report.result.metrics.external_cost_usd,external),"FUNDED_EXTERNAL_COST_BINDING");
  const curves=[];let priorAccount=initial,priorEconomic=initial;
  for(const [index,s]of report.result.snapshots.entries()){
    const equity=Number(s.account.equity),cash=Number(s.account.cash),inventory=s.positions.reduce((n,p)=>n+Number(p.market_value),0);
    need([equity,cash,inventory].every(Number.isFinite)&&near(equity,cash+inventory),"FUNDED_CURVE_ACCOUNT_IDENTITY");
    const cost=index===report.result.snapshots.length-1?external:0;
    const economic=equity-cost;
    const row={event_id:s.event_id,at:s.at,session:dateNY(s.at),cash_usd:cash,inventory_value_usd:inventory,
      account_equity_usd:equity,economic_equity_usd:economic,external_flow_usd:0,cumulative_external_cost_usd:cost,
      cumulative_fees_usd:report.result.fills.slice(0,s.fill_count).reduce((n,f)=>n+f.fee_usd,0),
      account_return:priorAccount>0?equity/priorAccount-1:null,economic_return:priorEconomic>0?economic/priorEconomic-1:null,
      insolvency:equity<=0||economic<=0,positions:clone(s.positions),fill_count:s.fill_count};
    curves.push(row);priorAccount=equity;priorEconomic=economic;
  }
  const final=curves.at(-1);
  need(near(final.cumulative_fees_usd,report.result.metrics.fees_usd),"FUNDED_FEE_RECONCILIATION");
  need(near(final.account_equity_usd-initial,report.result.metrics.account_pnl_net_usd)&&near(final.economic_equity_usd-initial,report.result.metrics.economic_pnl_net_usd),"FUNDED_TERMINAL_RECONCILIATION");
  const bySession=new Map();for(const row of curves)bySession.set(row.session,row);
  const sessions=[];let account=initial,economic=initial,peak=initial,maxDD=0;
  for(const row of bySession.values()){
    sessions.push({...clone(row),account_return:account>0?row.account_equity_usd/account-1:null,economic_return:economic>0?row.economic_equity_usd/economic-1:null});
    account=row.account_equity_usd;economic=row.economic_equity_usd;
  }
  for(const row of curves){peak=Math.max(peak,row.economic_equity_usd);maxDD=Math.max(maxDD,peak>0?1-row.economic_equity_usd/peak:1);}
  return {curve:curves,session_curve:sessions,metrics:{...report.result.metrics,economic_max_drawdown_fraction:maxDD,
    economic_total_return:final.economic_equity_usd/initial-1,geometric_mean_per_session:curves.some(x=>x.insolvency)?null:Math.expm1(Math.log(final.economic_equity_usd/initial)/sessions.length),
    terminal_inventory_included:true,external_cost_timing:"EXPLICIT_LUMP_SUM_AT_FINAL_EVENT_PAID_OUTSIDE_BROKER_ACCOUNT",cash_flows_scope:"EXPLICITLY_NONE_COUNTERFACTUAL",session_count:sessions.length,accounting_reconciled:true}};
}
async function runFundedComparison(input){
  const readiness=comparisonReadiness(input),source_hashes=comparisonSourceHashes();
  const base={schema:SCHEMA,input_hash:hash(input),source_hashes,data_origin:input?.common_request?.data_origin??null,execution_origin:"MODELED",dictamen:"VENTAJA_NO_DEMOSTRADA",...authority};
  if(!readiness.computable){const blocked={...base,status:"MEDICION_BLOQUEADA",readiness,reports:[],curves:null,paired_differences:null,parity:null};blocked.artifact_hash=hash(blocked);return blocked;}
  let registration;
  try{registration=await verifyRegistration(input);}catch(error){const blocked={...base,status:"MEDICION_BLOQUEADA",readiness:{...readiness,computable:false,blockers:[String(error.message)]},reports:[],curves:null,paired_differences:null,parity:null};blocked.artifact_hash=hash(blocked);return blocked;}
  const inputs=variants(input),reports=[];
  for(const variant of inputs)reports.push(await replay.runReplay(variant));
  need(hash(source_hashes)===hash(comparisonSourceHashes()),"COMPARISON_SOURCE_CHANGED_DURING_REPLAY");
  const common=r=>({...r,id:undefined,predictor:undefined}),commonHash=hash(common(inputs[0]));
  need(inputs.every(r=>hash(common(r))===commonHash),"COMPARISON_CONTROLS_DIFFER");
  const curves=Object.fromEntries(reports.map((report,i)=>[POLICIES[i],fundedCurves(report,inputs[i])]));
  const sessionIds=curves.C0.session_curve.map(x=>x.session);
  need(POLICIES.every(p=>hash(curves[p].session_curve.map(x=>x.session))===hash(sessionIds)),"PAIRED_SESSION_MISMATCH");
  const differences={};
  for(const [candidate,benchmark]of [["RIDGE","C0"],["SVR","C0"],["SVR","RIDGE"]]){
    differences[candidate+"_minus_"+benchmark]={economic_pnl_difference_usd:curves[candidate].metrics.economic_pnl_net_usd-curves[benchmark].metrics.economic_pnl_net_usd,
      session_return_differences:sessionIds.map((session,i)=>({session,difference:curves[candidate].session_curve[i].economic_return===null||curves[benchmark].session_curve[i].economic_return===null?null:curves[candidate].session_curve[i].economic_return-curves[benchmark].session_curve[i].economic_return})),
      confidence_interval:null,confidence_interval_null_reason:"No inference, model selection or additional financial experiment is performed by this producer."};
  }
  const complete=reports.length===3&&reports.every(r=>r.policy_parity_verified&&r.predictor_parity_verified);
  const report={...base,status:input.purpose==="SYNTHETIC_SOFTWARE_TEST"?"ENGINEERING_ONLY":"REGISTERED_MODELED_MEASUREMENT",
    readiness,registration,common_input_hash:commonHash,model_hashes:Object.fromEntries(POLICIES.slice(1).map(p=>[p,bytesHash(input.model_json?.[p]??canonical(input.models[p]))])),
    model_content_hashes:Object.fromEntries(POLICIES.slice(1).map(p=>[p,hash(input.models[p])])),
    period:{start_at:input.common_request.start_at,end_at:input.common_request.events.at(-1).at,session_ids:sessionIds},
    reports,curves,paired_differences:differences,
    parity:{covered_policies:reports.map(r=>r.result.candidate),complete_policy_coverage:complete,common_controls_verified:true,
      predictor_reexecution_verified:reports.every(r=>r.predictor_parity_verified),model_source_bindings_verified:reports.slice(1).every(r=>r.result.decisions.some(d=>d.numerical_receipt)),
      training_provenance_verified:false,external_source_authenticity_verified:false,
      scope:"SAME_COORDINATOR_EXITS_RISK_LIMITS_CAPITAL_UNIVERSE_EVENTS_AND_COSTS; NATIVE_C0_ENTRY_SELECTION_VS_QUANT_ALLOCATION_OVERLAYS; RIDGE_VS_SVR_CHANGES_FIXED_ESTIMATOR"},
    limitations:["All executions and their liquidity are modeled. An observed quote is not an observed fill.","C0 retains native sizing; Ridge/SVR use the existing shared allocator. Their comparison against C0 is the whole entry overlay, not an isolated predictor effect.","No training or hyperparameter search is performed. Reproduced inference cannot certify fitted-model provenance.","The shared capital account starts in cash and has no external capital flows or adopted source-account positions.","External cost is an explicitly supplied lump sum charged at the final event; an unknown cost blocks rather than becomes zero.","Positions remaining open are marked at the modeled bid; they are not force-closed to improve the result.","No statistical confidence interval, financial approval, PAPER activation or LIVE authority follows from this report."]};
  report.artifact_hash=hash(report);return report;
}
async function verifyFundedComparison(input,report){
  const mismatches=[];
  if(report?.schema!==SCHEMA)mismatches.push("schema");
  if(report?.artifact_hash!==hash({...report,artifact_hash:undefined}))mismatches.push("artifact_hash");
  if(report?.input_hash!==hash(input))mismatches.push("input_hash");
  const reproduced=await runFundedComparison(input);
  if(hash(report)!==hash(reproduced))mismatches.push("reproduced_report");
  return {schema:"HARPOON_FUNDED_COMPARISON_VERIFICATION_1",verified:mismatches.length===0,mismatches,input_hash:hash(input),
    expected_artifact_hash:reproduced.artifact_hash,observed_artifact_hash:report?.artifact_hash??null,
    real_coordinator_and_predictors_reexecuted:reproduced.status!=="MEDICION_BLOQUEADA",...authority};
}
async function main(argv){
  const args={};for(let i=0;i<argv.length;i+=2){need(["--input","--output","--verify","--registration-binding"].includes(argv[i])&&argv[i+1],"USAGE --input request.json --output report.json [--verify report.json] OR --registration-binding request.json --output binding.json");args[argv[i]]=argv[i+1];}
  need(args["--output"]&&(args["--input"]||args["--registration-binding"]),"INPUT_AND_OUTPUT_REQUIRED");
  const input=JSON.parse(fs.readFileSync(args["--input"]||args["--registration-binding"],"utf8"));
  const result=args["--registration-binding"]?{...registrationBinding(input),source_hashes:comparisonSourceHashes(),...authority}:
    args["--verify"]?await verifyFundedComparison(input,JSON.parse(fs.readFileSync(args["--verify"],"utf8"))):await runFundedComparison(input);
  fs.mkdirSync(path.dirname(path.resolve(args["--output"])),{recursive:true});fs.writeFileSync(args["--output"],JSON.stringify(result,null,2)+"\n");
  process.stdout.write(JSON.stringify({schema:result.schema||"HARPOON_REGISTRATION_BINDING_1",output:path.resolve(args["--output"]),status:result.status||null,verified:result.verified??null,...authority})+"\n");
  if(result.verified===false||result.status==="MEDICION_BLOQUEADA")process.exitCode=2;
}
module.exports={SCHEMA,REQUEST_SCHEMA,comparisonSourceHashes,registrationBinding,comparisonReadiness,runFundedComparison,verifyFundedComparison,fundedCurves};
if(require.main===module)main(process.argv.slice(2)).catch(error=>{process.stderr.write(String(error)+"\n");process.exitCode=1;});
