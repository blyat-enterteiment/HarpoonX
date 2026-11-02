"use strict";
/** Offline evidence integration only. A score of 4 never grants order authority. */
const fs=require("node:fs"),path=require("node:path"),crypto=require("node:crypto");
const {hash}=require("./coordinator_replay.cjs");
const {verifyFundedComparison}=require("./funded_comparison.cjs");
const {fromObservationExport}=require("./observation_replay_input.cjs");
const ROOT=path.resolve(__dirname,".."),REQUEST_SCHEMA="HARPOON_LEVEL4_READINESS_REQUEST_1",SCHEMA="HARPOON_LEVEL4_READINESS_1";
const authority={execution_allowed:false,liveApproved:false,financial_acceptance_allowed:false};
const need=(v,code)=>{if(!v)throw Error(code);};
const sha=bytes=>crypto.createHash("sha256").update(bytes).digest("hex");
const finite=v=>typeof v==="number"&&Number.isFinite(v);
const instant=v=>typeof v==="number"&&Number.isSafeInteger(v)?v:typeof v==="string"&&/T.*(?:Z|[+-]\d\d:\d\d)$/.test(v)?Date.parse(v):NaN;
const near=(a,b)=>finite(a)&&finite(b)&&Math.abs(a-b)<=1e-8*Math.max(1,Math.abs(a),Math.abs(b));

// Detect repeated keys before JSON.parse can overwrite evidence. No eval.
function parseStrictJSON(raw){
  need(typeof raw==="string","JSON_TEXT_REQUIRED");let i=0;
  const ws=()=>{while(/\s/.test(raw[i]||"")&&i<raw.length)i++;};
  const string=()=>{const start=i++;for(;i<raw.length;i++){if(raw[i]==="\\"){i++;continue;}if(raw[i]==='"')return JSON.parse(raw.slice(start,++i));}throw Error("JSON_STRING_UNTERMINATED");};
  const value=(depth=0)=>{need(depth<=100,"JSON_DEPTH_BOUND");ws();
    if(raw[i]==='"')return string();
    if(raw[i]==="{"||raw[i]==="["){
      const object=raw[i++]==="{",end=object?"}":"]",seen=new Set();ws();if(raw[i]===end){i++;return;}
      while(i<raw.length){if(object){ws();need(raw[i]==='"',"JSON_OBJECT_KEY");const key=string();need(!seen.has(key),"DUPLICATE_JSON_KEY:"+key);seen.add(key);ws();need(raw[i++]===':',"JSON_COLON");}value(depth+1);ws();if(raw[i]===end){i++;return;}need(raw[i++]===",","JSON_SEPARATOR");}
      throw Error("JSON_CONTAINER_UNTERMINATED");
    }
    const match=raw.slice(i).match(/^(?:true|false|null|-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?)/);
    need(match,"JSON_VALUE");const parsed=JSON.parse(match[0]);need(typeof parsed!=="number"||Number.isFinite(parsed),"NONFINITE_JSON");i+=match[0].length;
  };value();ws();need(i===raw.length,"JSON_TRAILING_DATA");return JSON.parse(raw);
}
function readRef(ref,base,sources){
  need(ref&&typeof ref.path==="string"&&/^[a-f0-9]{64}$/.test(ref.sha256||""),"BOUND_SOURCE_REFERENCE_REQUIRED");
  const filename=path.resolve(base,ref.path),stat=fs.statSync(filename);need(stat.isFile()&&stat.size<=32*1024*1024,"SOURCE_FILE_SIZE_BOUND");
  const bytes=fs.readFileSync(filename);need(sha(bytes)===ref.sha256,"SOURCE_FILE_HASH_MISMATCH:"+path.basename(filename));
  const relative=path.relative(base,filename),logical=relative.startsWith("..")||path.isAbsolute(relative)?"external/"+ref.sha256+"/"+path.basename(filename):relative.split(path.sep).join("/");
  sources.push({path:logical,sha256:ref.sha256,bytes:bytes.length});
  need(sources.reduce((n,s)=>n+s.bytes,0)<=192*1024*1024,"EVIDENCE_TOTAL_BYTES_BOUND");
  return {value:parseStrictJSON(bytes.toString("utf8")),filename};
}
async function verifyData(requestFile,reportFile){
  const python=process.env.HARPOON_QUANT_PYTHON||"python3";
  need(python==="python3"||path.isAbsolute(python)&&/^python(?:\d+(?:\.\d+)*)?$/.test(path.basename(python)),"LOCAL_PYTHON_EXECUTABLE_REQUIRED");
  const code="import sys,json;from pathlib import Path;sys.path.insert(0,str(Path(sys.argv[3])/'quant'));from harpoon_quant.causal_panel import verify;from harpoon_quant.study_integrity import _json;print(json.dumps(verify(_json(Path(sys.argv[2]).read_bytes()),_json(Path(sys.argv[1]).read_bytes()),Path(sys.argv[1]).resolve().parent),allow_nan=False))";
  return await new Promise((resolve,reject)=>{
    const child=require("node:child_process").spawn(python,["-B","-c",code,requestFile,reportFile,ROOT],{cwd:ROOT,shell:false,stdio:["ignore","pipe","pipe"],env:{PATH:process.env.PATH||"/usr/bin:/bin",LANG:"C.UTF-8",OPENBLAS_NUM_THREADS:"1",OMP_NUM_THREADS:"1"}});
    let out="",err="",done=false;
    const finish=(error,result)=>{if(done)return;done=true;clearTimeout(timer);error?reject(error):resolve(result);};
    const timer=setTimeout(()=>{child.kill("SIGKILL");finish(Error("DATA_REEXECUTION_TIMEOUT"));},30000);
    child.on("error",e=>finish(Error("DATA_VERIFIER_UNAVAILABLE:"+e.message)));
    child.stdout.on("data",d=>{out+=d;if(Buffer.byteLength(out)>2*1024*1024){child.kill("SIGKILL");finish(Error("DATA_VERIFIER_OUTPUT_BOUND"));}});
    child.stderr.on("data",d=>{err=(err+d).slice(-1500);});
    child.on("close",status=>{try{need(status===0,"DATA_VERIFIER_FAILED:"+err);finish(null,parseStrictJSON(out));}catch(e){finish(e);}});
  });
}
function barBinding(row){return {t:row.t,o:row.o,h:row.h,l:row.l,c:row.c,v:row.v,vw:row.vw??null,known_at:row.known_at};}
function quoteBinding(q){return {symbol:q.symbol,market_at:q.market_at,received_at:q.received_at,bid:q.bid,ask:q.ask};}
function bindMarketSources(input,base,sources){
  const common=input.common_request,refs=common?.source_evidence?.observation_exports;
  need(Array.isArray(refs)&&refs.length>0&&refs.length<=512,"COMPARISON_MARKET_RECEIPT_BINDING_MISSING");
  const quotes=new Map(),bars=new Map(),calendar=new Set();let account=null,head=null,total=null,offset=0,frames=0,sourceConfigHash=null;
  for(const ref of refs){
    const {value:bundle}=readRef(ref,base,sources);
    need(bundle.schema==="HARPOON_OBSERVATION_EXPORT_1"&&bundle.offset===offset&&bundle.next_offset===offset+bundle.frames.length,"MARKET_SOURCE_PAGINATION");
    if(account===null){account=bundle.account_id;head=bundle.head;total=bundle.total_frames;}
    need(bundle.account_id===account&&bundle.head===head&&bundle.total_frames===total,"MARKET_SOURCE_REVISION_OR_ACCOUNT");
    need(bundle.frames.every(f=>f.data_origin==="RUNTIME_OBSERVATION_UNVERIFIED"),"SYNTHETIC_OR_UNKNOWN_MARKET_RECEIPTS");
    // This replay contract has one fixed configuration. A page boundary must
    // not erase configuration history or admit an otherwise rejected change.
    for(const frame of bundle.frames){
      const config=frame.runtime_input?.config;
      need(config&&typeof config==="object"&&!Array.isArray(config),"COMPARISON_SOURCE_CONFIGURATION_MISSING");
      const currentHash=hash(config);
      if(sourceConfigHash===null)sourceConfigHash=currentHash;
      need(currentHash===sourceConfigHash,"SOURCE_CONFIG_CHANGED_SPLIT_REPLAY");
    }
    const normalized=fromObservationExport(bundle,{initial_cash_usd:common.initial_cash_usd,execution_model:common.execution_model});
    // The generic replay also supports crypto; this funded comparison admits
    // all and only the source's unleveraged equity/ETF shares. This deterministic
    // projection is the sole additional override; it cannot select winners.
    const comparisonConfig={...normalized.config,universe:normalized.config.universe.filter(a=>["equity","etf"].includes(a.book)&&a.multiplier===1)};
    need(hash(common.config)===hash(comparisonConfig),"COMPARISON_CONFIGURATION_NOT_BOUND_TO_SOURCE");
    for(const event of normalized.events.filter(e=>e.type==="market")){
      for(const q of event.quotes){const key=hash(quoteBinding(q));quotes.set(key,Math.min(event.at,quotes.get(key)??Infinity));}
      for(const resolution of ["bars","minutes","daily"])for(const [symbol,rows]of Object.entries(event[resolution]||{}))for(const row of rows){const key=hash({symbol,resolution,row:barBinding(row)});bars.set(key,Math.min(event.at,bars.get(key)??Infinity));}
    }
    for(const row of normalized.calendar)calendar.add(hash(row));
    offset=bundle.next_offset;frames+=bundle.frames.length;
  }
  need(offset===total,"COMPLETE_COMPARISON_SOURCE_EXPORT_REQUIRED");
  let quoteCount=0,barCount=0;
  for(const event of common.events.filter(e=>e.type==="market")){
    for(const q of event.quotes){const received=quotes.get(hash(quoteBinding(q)));need(finite(received)&&received<=event.at,"COMPARISON_QUOTE_NOT_BOUND_TO_ORIGINAL_RECEIPT");quoteCount++;}
    for(const resolution of ["bars","minutes","daily"])for(const [symbol,rows]of Object.entries(event[resolution]||{}))for(const row of rows){const received=bars.get(hash({symbol,resolution,row:barBinding(row)}));need(finite(received)&&received<=event.at,"COMPARISON_BAR_NOT_BOUND_TO_ORIGINAL_RECEIPT");barCount++;}
  }
  need(quoteCount>0&&barCount>0&&common.calendar.every(c=>calendar.has(hash(c))),"COMPARISON_MARKET_HISTORY_OR_CALENDAR_MISSING");
  return {verified:true,account_id:account,source_config_hash:sourceConfigHash,frames,quotes_bound:quoteCount,bars_bound:barCount,availability:"OBSERVED_RUNTIME_RECEIPTS",executable_depth_observed:false,external_authenticity_verified:false};
}
function implementationHashes(){
  const names=["tools/level4_readiness.cjs","tools/funded_comparison.cjs","tools/coordinator_replay.cjs","tools/observation_replay_input.cjs",
    "runtime30/net_accounting.js","runtime30/net_ledger_verify.js","runtime30/net_ledger_archive.js","runtime30/cost_receipts.js","quant/harpoon_quant/causal_panel.py"];
  return Object.fromEntries(names.map(name=>[name,fs.existsSync(path.join(ROOT,name))?sha(fs.readFileSync(path.join(ROOT,name))):null]));
}
// Called only on the ledger verifier's reconstruction, never on request claims.
function brokerAccrualsCover(ledger,start,end){
  const proof=ledger?.closedBrokerAccruals,accounting=ledger?.state?.accounting;
  return ledger?.verified===true&&proof?.verified===true&&finite(proof.amountUsd)&&finite(start)&&finite(end)&&end>start&&
    instant(proof.from)<=start&&instant(proof.through)>=end&&instant(proof.comparedFrom)<=start&&instant(proof.comparedThrough)>=end&&
    (accounting?.unreportedBrokerAccrualsVerified!==true||near(proof.amountUsd,accounting.unreportedBrokerAccrualsUsd));
}
async function assessLevel4(input,baseDir=process.cwd()){
  need(input?.schema===REQUEST_SCHEMA,"LEVEL4_REQUEST_SCHEMA");
  const sources=[],checks=[],components={data:null,comparison:null,ledger:null},failures=[];
  const check=(id,passed,evidence,reason)=>{checks.push({id,passed:passed===true,evidence});if(passed!==true)failures.push(reason||id);};
  let data=null,comparison=null,comparisonInput=null,ledger=null,market=null,dataVerification=null,comparisonVerification=null;
  if(input.data){try{
    const req=readRef(input.data.request,baseDir,sources),report=readRef(input.data.report,baseDir,sources);
    dataVerification=await verifyData(req.filename,report.filename);
    need(dataVerification.schema==="HARPOON_CAUSAL_PANEL_VERIFICATION_1"&&dataVerification.verified===true,"CAUSAL_DATA_REEXECUTION_FAILED");
    data=report.value;components.data={verified:true,verification:dataVerification,artifact_hash:data.artifact_hash,counts:data.counts,readiness:data.readiness};
  }catch(error){components.data={verified:false,reason:String(error.message)};}}
  check("data_sources_reexecuted",!!data,components.data,"CAUSAL_DATA_ARTIFACT_MISSING_OR_INVALID");
  check("observed_admissible_panel",!!data&&data.panel?.origin==="OBSERVED"&&data.panel.provenance?.availability==="OBSERVED_TIMESTAMPS"&&
    dataVerification.causal_rows_admissible>0&&data.panel.rows.length===dataVerification.causal_rows_admissible&&data.readiness?.accepted_rows===data.panel.rows.length,
    data?{origin:data.panel.origin,causal_rows:dataVerification.causal_rows_admissible,reconstructed_rows:dataVerification.reconstructed_feature_rows,accepted_rows:data.readiness?.accepted_rows}:null,
    "OBSERVED_CAUSAL_CALIBRATION_PANEL_NOT_AVAILABLE");
  if(input.comparison){try{
    const req=readRef(input.comparison.request,baseDir,sources),report=readRef(input.comparison.report,baseDir,sources);
    comparisonInput=req.value;comparisonVerification=await verifyFundedComparison(req.value,report.value);
    need(comparisonVerification.verified===true,"FUNDED_COMPARISON_REEXECUTION_FAILED");
    comparison=report.value;components.comparison={verified:true,verification:comparisonVerification,status:comparison.status,artifact_hash:comparison.artifact_hash,period:comparison.period??null};
    try{market=bindMarketSources(comparisonInput,path.dirname(req.filename),sources);}
    catch(error){components.comparison.market_binding_error=String(error.message);}
  }catch(error){components.comparison={verified:false,reason:String(error.message)};}}
  const policies=comparison?.reports?.map(r=>r.result?.candidate).sort();
  check("three_policy_comparison_reexecuted",!!comparison&&comparisonVerification.real_coordinator_and_predictors_reexecuted===true&&
    comparison.status==="REGISTERED_MODELED_MEASUREMENT"&&comparison.data_origin==="HISTORICAL"&&comparisonInput.purpose==="PREREGISTERED_FIXED_MODEL_MEASUREMENT"&&
    hash(policies)===hash(["C0","RIDGE","SVR"])&&comparison.parity?.complete_policy_coverage===true&&comparison.parity?.predictor_reexecution_verified===true&&comparison.parity?.model_source_bindings_verified===true,
    components.comparison,"OBSERVED_THREE_POLICY_COMPARISON_NOT_AVAILABLE");
  check("comparison_market_receipts_bound",market?.verified===true,market||{reason:components.comparison?.market_binding_error??null},components.comparison?.market_binding_error||"COMPARISON_MARKET_RECEIPT_BINDING_MISSING");
  if(input.ledger){try{
    const {value:bundle}=readRef(input.ledger.bundle,baseDir,sources),module=require("../runtime30/net_accounting.js");
    need(typeof module.verifyNetLedgerHistoryBundle==="function","LEDGER_HISTORY_VERIFIER_UNAVAILABLE");
    ledger=module.verifyNetLedgerHistoryBundle(bundle.pages,bundle.expected_integrity);
    need(ledger.verified===true,"LEDGER_HISTORY_REEXECUTION_FAILED");
    components.ledger={verified:true,account_id:ledger.accountId,from:ledger.from,through:ledger.through,observations:ledger.observations.length,
      activities:ledger.activities.length,external_costs:ledger.externalCosts.length,archive_head:ledger.archiveHead,integrity:bundle.expected_integrity,
      execution_nature:ledger.state.evidence?.executionNature??null,source_authenticity_verified:false};
  }catch(error){ledger=null;components.ledger={verified:false,reason:String(error.message)};}}
  check("ledger_history_reconstructed",!!ledger,components.ledger,"RECONCILED_ACCOUNT_HISTORY_MISSING_OR_INVALID");
  const start=instant(comparison?.period?.start_at),end=instant(comparison?.period?.end_at);
  const ls=ledger?.state,closedThrough=instant(ls?.closedEconomic?.through),
    obs=(ledger?.observations||[]).filter(r=>finite(closedThrough)&&r.at<=closedThrough);
  const recordedInsolvency=!!ls&&(ls.insolvency?.account===true||ls.insolvency?.economic===true)&&obs.some(r=>r.equity<=0||r.economicEquity<=0);
  const returnKnown=(row,index,key,capital)=>!index||finite(row[key])||recordedInsolvency&&row[key]===null&&
    (row[capital]<=0||obs[index-1][capital]<=0);
  const ledgerComplete=!!ledger&&["PAPER","REAL","LIVE"].includes(ls.evidence?.executionNature)&&ls.reconciled===true&&
    !["UNVERIFIED","BLOCKED","ERROR","STALE"].includes(ls.status)&&!ls.economicRestatementRequired&&obs.length>=2&&
    obs.every((r,i)=>finite(r.equity)&&finite(r.economicEquity)&&finite(r.cumulativeExternalCostUsd)&&returnKnown(r,i,"accountReturn","equity")&&returnKnown(r,i,"economicReturn","economicEquity"))&&
    ls.costCoverage?.from<=ledger.from&&ls.costCoverage?.through>=closedThrough&&(ls.closedEconomic?.completeReturns===true||recordedInsolvency)&&
    ls.closedEconomic?.comparablePeriodGrid===true&&
    ls.closedEconomic?.observationCount===obs.length;
  check("observed_complete_net_account_curve",ledgerComplete,ls?{status:ls.status,execution_nature:ls.evidence?.executionNature,reconciled:ls.reconciled,
    current_economic_complete:ls.economicComplete,current_return_complete:ls.returnComplete,cost_coverage:ls.costCoverage,closed_economic:ls.closedEconomic,
    scope:"CLOSED_ECONOMIC_PREFIX_ONLY",current_last_observation_at:ledger.through,tail_uncovered_at:ls.closedEconomic?.latestUncoveredAt??null}:null,
    "OBSERVED_ACCOUNT_CURVE_OR_COST_COVERAGE_INCOMPLETE");
  check("applicable_broker_accruals_verified",brokerAccrualsCover(ledger,start,end),
    {documented_amount_usd:ledger?.closedBrokerAccruals?.amountUsd??null,from:ledger?.closedBrokerAccruals?.from??null,through:ledger?.closedBrokerAccruals?.through??null,
      verified_period_from:ledger?.closedBrokerAccruals?.comparedFrom??null,verified_period_through:ledger?.closedBrokerAccruals?.comparedThrough??null,
      current_account_amount_usd:ls?.accounting?.unreportedBrokerAccrualsUsd??null,current_account_claim:ls?.accounting?.unreportedBrokerAccrualsVerified??null,
      recomputed_by_ledger_verifier:ledger?.closedBrokerAccruals?.verified??null,current_scope_verified:ledger?.brokerAccrualsVerified??null},"APPLICABLE_BROKER_ACCRUALS_NOT_VERIFIED");
  const modelChecks=[];
  for(const name of ["RIDGE","SVR"]){
    const model=comparisonInput?.models?.[name],text=comparisonInput?.model_json?.[name],available=instant(model?.available_at);
    let parsedText=null;
    try{if(typeof text==="string")parsedText=parseStrictJSON(text);}catch{/* Malformed source stays unbound. */}
    const passed=!!data&&!!comparison&&model?.origin==="OBSERVED"&&model.data_hash===data.panel_hash&&
      hash(model.feature_names)===hash(data.panel.feature_names)&&model.horizon_hours===data.panel.horizon_hours&&
      available>=instant(data.available_at)&&available<start&&data.panel.rows.every(r=>instant(r.label_known_at)<available)&&
      typeof text==="string"&&hash(parsedText)===hash(model)&&sha(Buffer.from(text))===comparison.model_hashes?.[name]&&
      comparison.model_content_hashes?.[name]===hash(model);
    modelChecks.push({model:name,passed,model_data_hash:model?.data_hash??null,panel_hash:data?.panel_hash??null,available_at:model?.available_at??null,comparison_start_at:finite(start)?start:null});
  }
  check("models_bound_to_causal_panel_before_decisions",modelChecks.every(r=>r.passed),modelChecks,"MODEL_PANEL_HASH_OR_CHRONOLOGY_BINDING_MISSING");
  const compatible=!!ledger&&!!market&&finite(start)&&finite(end)&&end>start&&ledger.accountId===market.account_id&&ledger.from<=start&&closedThrough>=end;
  check("account_and_measurement_periods_bound",compatible,{account_id:ledger?.accountId??null,market_account_id:market?.account_id??null,ledger_from:ledger?.from??null,
    ledger_economic_prefix_through:finite(closedThrough)?closedThrough:null,ledger_last_observation_at:ledger?.through??null,
    comparison_from:finite(start)?start:null,comparison_through:finite(end)?end:null},"ACCOUNT_OR_PERIOD_BINDING_MISSING");
  const observedExternal=compatible?ledger.externalCosts.filter(c=>c.already_in_account===false&&c.at>start&&c.at<=end).reduce((n,c)=>n+c.amount_usd,0):null;
  check("external_cost_total_bound",compatible&&near(observedExternal,comparisonInput.common_request.execution_model.external_cost_usd),
    {ledger_period_external_cost_usd:observedExternal,modeled_external_cost_usd:comparisonInput?.common_request?.execution_model?.external_cost_usd??null,cost_timing:"COMPARISON_LUMP_SUM_IS_STILL_AN_EXPLICIT_MODEL"},"COMPARISON_EXTERNAL_COST_NOT_BOUND_TO_ACCOUNT_PERIOD");
  const report={schema:SCHEMA,input_hash:hash(input),source_hashes:sources,implementation_hashes:implementationHashes(),
    score:checks.every(c=>c.passed)?4:3,criterion:"INTEGRATED_OBSERVED_MEASUREMENT_NOT_PROFIT_OR_AUTONOMOUS_PROMOTION",checks,
    blockers:[...new Set(failures)],components,
    implemented:{causal_panel_builder:true,funded_three_policy_producer:true,ledger_history_verifier:typeof require("../runtime30/net_accounting.js").verifyNetLedgerHistoryBundle==="function",source_reexecution_and_bindings:true},
    observed:{causal_data:checks.find(c=>c.id==="observed_admissible_panel").passed,account_and_costs:ledgerComplete,account_and_costs_scope:"CLOSED_ECONOMIC_PREFIX_ONLY",
      current_account_economic_complete:ls?.economicComplete??null,three_policy_comparison:checks.find(c=>c.id==="three_policy_comparison_reexecuted").passed,market_receipts:market?.verified===true},
    financial_profitability_demonstrated:false,full_autonomous_economic_cycle_verified:false,training_provenance_independently_verified:false,
    source_authenticity_independently_verified:false,...authority,
    limitations:["Score 4 concerns integrated measurement only and can coexist with losses.","Quotes and local receipts do not authenticate a provider independently or establish executable depth.","Comparison fills, liquidity, timing and costs retain their explicitly modeled scope.","Models are checked against panel hashes and chronology; training is not rerun and independent training provenance is not certified.","Ledger amounts include reported and declared costs; unknown broker accruals and unspecified taxes remain outside proven completeness."]};
  report.artifact_hash=hash(report);return report;
}
async function verifyLevel4Readiness(input,report,baseDir=process.cwd()){
  const reproduced=await assessLevel4(input,baseDir),verified=report?.artifact_hash===hash({...report,artifact_hash:undefined})&&hash(report)===hash(reproduced);
  return {schema:"HARPOON_LEVEL4_READINESS_VERIFICATION_1",verified,score:reproduced.score,expected_artifact_hash:reproduced.artifact_hash,observed_artifact_hash:report?.artifact_hash??null,...authority};
}
async function main(argv){
  const args={};for(let i=0;i<argv.length;i+=2){need(["--input","--output","--verify"].includes(argv[i])&&argv[i+1],"USAGE --input request.json --output report.json [--verify report.json]");args[argv[i]]=argv[i+1];}
  need(args["--input"]&&args["--output"],"INPUT_OUTPUT_REQUIRED");
  const filename=path.resolve(args["--input"]),input=parseStrictJSON(fs.readFileSync(filename,"utf8"));
  const result=args["--verify"]?await verifyLevel4Readiness(input,parseStrictJSON(fs.readFileSync(args["--verify"],"utf8")),path.dirname(filename)):await assessLevel4(input,path.dirname(filename));
  fs.mkdirSync(path.dirname(path.resolve(args["--output"])),{recursive:true});fs.writeFileSync(args["--output"],JSON.stringify(result,null,2)+"\n");
  process.stdout.write(JSON.stringify({output:path.resolve(args["--output"]),score:result.score,verified:result.verified??null,blockers:result.blockers??null,...authority})+"\n");
  if(result.verified===false)process.exitCode=2;
}
module.exports={SCHEMA,REQUEST_SCHEMA,parseStrictJSON,assessLevel4,verifyLevel4Readiness,bindMarketSources,brokerAccrualsCover};
if(require.main===module)main(process.argv.slice(2)).catch(e=>{process.stderr.write(String(e)+"\n");process.exitCode=1;});
