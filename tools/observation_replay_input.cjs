"use strict";
/** Convert authenticated-by-hash journal exports into observation-only replay.
 * A local integrity hash does not authenticate the market data provider.
 * No orders, fills, labels, queue depth or position adoption are manufactured.
 */
const fs=require("node:fs"),path=require("node:path"),crypto=require("node:crypto");
const {REQUEST_SCHEMA,hash,validateRequest}=require("./coordinator_replay.cjs");
const {validateConfig}=require("../runtime30/types.js");
const sha=bytes=>crypto.createHash("sha256").update(bytes).digest("hex");
const clone=x=>JSON.parse(JSON.stringify(x));
function need(ok,reason){if(!ok)throw Error(reason);}
// Import schema only: accepting declared source mode never enables that mode
// in the runtime. The reconstructed request always uses the existing PAPER
// validator and the isolated replay's in-memory broker.
const SOURCE_MODES=new Set(["paper","live","real"]);
const CONFIG_FIELDS=new Set(["mode","quant","execution_authority","expected_account_id","stockFeed","optionFeed",
  "capitalLimit","riskFraction","openRiskFraction","totalExposure","assetExposure","factorExposure","dailyLoss",
  "maxDrawdown","quoteAgeMs","orderTtlMs","slippageBps","cryptoFeeBps","optionsFeePerContract","maxSpreadBps",
  "maxOptionSpreadBps","maxPositions","universe","optionUnderlyings","enabledPlugins","exit","researchMaxRuns",
  "nativeProtection","protectionRefreshMs","streaming"]);
const QUANT_CONFIG_FIELDS=new Set(["horizon_hours","scenarios","max_positions","gross_fraction","asset_fraction",
  "factor_fraction","cvar_alpha","cvar_fraction","stress_fraction","daily_loss_fraction","drawdown_fraction",
  "uncertainty_z","risk_penalty","max_quote_age_seconds","slippage_bps","max_model_age_days","solver_seconds",
  "min_edge_usd","min_robust_return_bps","seed"]);
function numericQuantConfig(raw){
  if(raw===undefined)return undefined;
  need(raw&&typeof raw==="object"&&!Array.isArray(raw),"SOURCE_QUANT_CONFIG_OBJECT_REQUIRED");
  for(const [key,value]of Object.entries(raw)){
    need(QUANT_CONFIG_FIELDS.has(key),"SOURCE_QUANT_CONFIG_FIELD_UNSUPPORTED:"+key);
    need(typeof value==="number"&&Number.isFinite(value)&&value>=0,"SOURCE_QUANT_CONFIG_NUMERIC_REQUIRED:"+key);
  }
  // The same numeric envelope as harpoon_quant.core.Config, without copying
  // any executable/path-bearing quant settings into an offline request.
  const within=(key,low,high,integer=false)=>raw[key]===undefined||
    raw[key]>=low&&raw[key]<=high&&(!integer||Number.isSafeInteger(raw[key]));
  need((raw.horizon_hours===undefined||raw.horizon_hours>0&&raw.horizon_hours<=72)&&
    (raw.cvar_alpha===undefined||raw.cvar_alpha>0&&raw.cvar_alpha<1),"SOURCE_QUANT_HORIZON_OR_TAIL");
  need(within("scenarios",32,4096,true)&&within("max_positions",1,48,true)&&
    within("seed",0,Number.MAX_SAFE_INTEGER,true),"SOURCE_QUANT_INTEGER_COMPUTE_BUDGET");
  need(within("min_robust_return_bps",0,100),"SOURCE_QUANT_QUALITY_BPS_ENVELOPE");
  need(["cvar_fraction","stress_fraction","gross_fraction","asset_fraction","factor_fraction","solver_seconds"]
    .every(key=>raw[key]===undefined||raw[key]>0),"SOURCE_QUANT_ZERO_BOUND");
  return clone(raw);
}
function epoch(value){return typeof value==="number"?value:Date.parse(value);}
function clockText(value){
  if(typeof value==="string"&&/^\d{2}:\d{2}$/.test(value))return value;
  const at=epoch(value);need(Number.isFinite(at),"SOURCE_CALENDAR_TIME_INVALID");
  return new Intl.DateTimeFormat("en-GB",{timeZone:"America/New_York",hour:"2-digit",minute:"2-digit",hourCycle:"h23"}).format(new Date(at));
}
function fromObservationExport(bundle,assumptions){
  need(bundle?.schema==="HARPOON_OBSERVATION_EXPORT_1"&&Array.isArray(bundle.frames)&&bundle.frames.length>0&&bundle.frames.length<=100,"OBSERVATION_EXPORT_REQUIRED");
  need(bundle.execution_allowed===false&&bundle.liveApproved===false,"EXPORT_AUTHORITY_MUST_BE_FALSE");
  need(assumptions&&typeof assumptions.initial_cash_usd==="number"&&assumptions.initial_cash_usd>0&&assumptions.execution_model,"EXPLICIT_COUNTERFACTUAL_CASH_AND_COSTS_REQUIRED");
  const first=bundle.frames[0],sourceConfig=first.runtime_input?.config;
  need(sourceConfig&&typeof sourceConfig==="object"&&!Array.isArray(sourceConfig)&&
    typeof sourceConfig.expected_account_id==="string"&&sourceConfig.expected_account_id.trim(),"SOURCE_ACCOUNT_CONFIGURATION_REQUIRED");
  need(SOURCE_MODES.has(sourceConfig.mode),"SOURCE_CONFIGURATION_MODE_UNSUPPORTED");
  need(Object.keys(sourceConfig).every(key=>CONFIG_FIELDS.has(key)),"SOURCE_CONFIGURATION_FIELD_UNSUPPORTED");
  need(sourceConfig.quant===undefined||sourceConfig.quant&&typeof sourceConfig.quant==="object"&&
    !Array.isArray(sourceConfig.quant)&&typeof sourceConfig.quant.enabled==="boolean","SOURCE_QUANT_CONFIGURATION_REQUIRED");
  const cfg=clone(sourceConfig),configHash=hash(sourceConfig),quantConfig=numericQuantConfig(sourceConfig.quant?.config);
  need(bundle.account_id===cfg.expected_account_id,"EXPORT_ACCOUNT_BINDING");
  const fullUniverse=clone(cfg.universe||[]),excluded=fullUniverse.filter(a=>!["equity","etf","crypto"].includes(a.book)||a.multiplier!==1).map(a=>({symbol:a.symbol,reason:"OUTSIDE_REPLAY_CONTRACT"}));
  cfg.universe=fullUniverse.filter(a=>["equity","etf","crypto"].includes(a.book)&&a.multiplier===1);
  need(cfg.universe.length>0,"NO_SUPPORTED_SOURCE_SYMBOLS");
  cfg.enabledPlugins=(cfg.enabledPlugins||[]).filter(id=>!id.startsWith("options-"));cfg.optionUnderlyings=[];
  const overrides={mode:"paper",account_id:"OFFLINE-OBSERVATIONS-"+hash(bundle.account_id).slice(0,16),streaming:false,
    quant_enabled:false,quant_config_scope:"VALIDATED_NUMERIC_CONFIG_ONLY",native_protection:"stop"};
  cfg.mode="paper";cfg.expected_account_id=overrides.account_id;cfg.streaming=false;
  cfg.quant=quantConfig===undefined?{enabled:false}:{enabled:false,config:quantConfig};cfg.nativeProtection="stop";
  validateConfig(cfg);
  const events=[],provenance=[],rejections=[],calendar=new Map(),lastQuotes=new Map();let last=-Infinity;
  for(const [index,frame]of bundle.frames.entries()){
    need(frame.schema==="HARPOON_PROSPECTIVE_FRAME_1"&&frame.account_id===bundle.account_id&&frame.external_authenticity_verified===false&&frame.financial_acceptance_allowed===false,"SOURCE_FRAME_CONTRACT");
    const {source_frame_sha256,...payload}=frame;
    need(/^[a-f0-9]{64}$/.test(source_frame_sha256||"")&&sha(JSON.stringify(payload))===source_frame_sha256,"SOURCE_FRAME_HASH_MISMATCH");
    const input=frame.runtime_input,now=input.now;
    need(Number.isSafeInteger(now)&&now>last,"SOURCE_FRAME_CLOCK_NONCAUSAL");last=now;
    need(input.config?.expected_account_id===bundle.account_id&&hash(input.config)===configHash,"SOURCE_CONFIG_CHANGED_SPLIT_REPLAY");
    for(const row of input.market.calendar||[]){const item={date:row.date,open:clockText(row.open),close:clockText(row.close)},old=calendar.get(item.date);need(!old||hash(old)===hash(item),"SOURCE_CALENDAR_CHANGED");calendar.set(item.date,item);}
    const event={id:"frame-"+index+"-market",at:now,type:"market",quotes:[]};
    const rejected=(symbol,reason,extra={})=>rejections.push({frame:index,symbol,reason,...extra});
    for(const [symbol,q]of Object.entries(input.market.quotes||{})){
      const at=epoch(q.at),received=epoch(q.received);
      if(!Number.isSafeInteger(at)||!Number.isSafeInteger(received)||at>received||received>now){rejected(symbol,"QUOTE_CLOCK_OR_RECEIPT_UNVERIFIED");continue;}
      if(now-at>cfg.quoteAgeMs){rejected(symbol,"STALE_QUOTE_IN_SOURCE_FRAME");continue;}
      if(lastQuotes.has(symbol)&&at<=lastQuotes.get(symbol)){rejected(symbol,"REPEATED_OR_REGRESSING_QUOTE_NO_NEW_LIQUIDITY");continue;}
      need(typeof q.bid==="number"&&q.bid>0&&typeof q.ask==="number"&&q.ask>=q.bid,"SOURCE_QUOTE_PRICE_INVALID");
      event.quotes.push({symbol,market_at:at,received_at:received,bid:q.bid,ask:q.ask,executable_qty:0});lastQuotes.set(symbol,at);
    }
    const missing=[];
    for(const [key,span]of [["bars",300000],["minutes",60000],["daily",86400000]]){
      if(!input.market[key]){missing.push(key);continue;}
      event[key]={};
      for(const [symbol,rows]of Object.entries(input.market[key])){
        need(Array.isArray(rows),"SOURCE_HISTORY_ARRAY_REQUIRED");const accepted=[];
        for(const row of rows){const at=Date.parse(row.t),known=row.known_at!==undefined?epoch(row.known_at):row.received!==undefined?epoch(row.received):now;
          if(!Number.isFinite(at)||at+span>now){rejected(symbol,"BAR_NOT_CLOSED_IN_FRAME",{resolution:key,t:row.t});continue;}
          if(!Number.isSafeInteger(known)||known>now||known<at+span){rejected(symbol,"BAR_AVAILABILITY_NONCAUSAL",{resolution:key,t:row.t});continue;}
          accepted.push({...clone(row),known_at:known});
        }
        event[key][symbol]=accepted;
      }
    }
    events.push(event,{id:"frame-"+index+"-session",at:now,type:"sessions"});
    const selected=input.observation_coverage?.selected_symbols;
    need(Array.isArray(selected),"SOURCE_CAPTURE_COVERAGE_REQUIRED");
    const books=[...new Set(selected.map(s=>cfg.universe.find(a=>a.symbol===s)?.book).filter(Boolean))];
    for(const book of books)events.push({id:"frame-"+index+"-evaluate-"+book,at:now,type:"evaluate",book});
    provenance.push({frame:index,at:now,source_frame_sha256,source_data_origin:frame.data_origin,coverage:clone(input.observation_coverage),missing_histories:missing,available_quote_symbols:event.quotes.map(q=>q.symbol),order_evaluation:false});
  }
  const dataOrigin=bundle.frames.some(frame=>String(frame.data_origin).includes("SYNTHETIC"))?"SYNTHETIC":"HISTORICAL";
  const request={schema:REQUEST_SCHEMA,id:"prospective-observation-replay-"+hash(provenance).slice(0,16),mode:"OFFLINE",execution_origin:"MODELED",data_origin:dataOrigin,start_at:bundle.frames[0].runtime_input.now,initial_cash_usd:assumptions.initial_cash_usd,config:cfg,calendar:[...calendar.values()].sort((a,b)=>a.date.localeCompare(b.date)),execution_model:clone(assumptions.execution_model),events,
    execution_allowed:false,liveApproved:false,financial_acceptance_allowed:false,
    source_evidence:{schema:"HARPOON_OBSERVATION_ADAPTER_1",origin:"PROSPECTIVE_RUNTIME_SAMPLES_UNVERIFIED",observation_only:true,source_export_hash:hash(bundle),local_frame_integrity_verified:true,external_authenticity_verified:false,source_account_positions_adopted:false,zero_executable_quantity_reason:"EXECUTABLE_DEPTH_ABSENT_AND_NO_EXECUTION_CLAIM",all_samples_have_zero_executable_qty:true,source_config_hash:configHash,source_account_id:bundle.account_id,source_config_mode:sourceConfig.mode,source_execution_nature_verified:false,source_export_complete:bundle.complete_export===true,coverage_not_upgraded:true,configuration_overrides_for_offline_evaluation:overrides,excluded_symbols:excluded,frames:provenance,rejections,financial_acceptance_allowed:false,limitations:["SOURCE_MODE_IS_METADATA_NOT_REAL_EXECUTION_AUTHENTICATION","OFFLINE_PROJECTION_DOES_NOT_ADD_LIVE_RUNTIME_CAPABILITY_OR_REMOVE_SVR_SHADOW","NO_ORDERS_CREATED_BY_ADAPTER_EVENTS","NO_FUNDED_WEALTH_PATH_OR_PREDICTOR_EQUIVALENCE","MISSING_HISTORY_REMAINS_MISSING","UNKNOWN_BAR_AVAILABILITY_IS_FIRST_EXPORTED_SNAPSHOT_ONLY","SAMPLED_FRAMES_DO_NOT_ESTABLISH_INTRABAR_ORDER_OR_90_MINUTE_PATH_CONTINUITY"]}};
  validateRequest(request);return request;
}
async function main(argv){const args={};for(let i=0;i<argv.length;i+=2){need(["--input","--output","--assumptions"].includes(argv[i])&&argv[i+1],"USAGE --input export.json --assumptions explicit_assumptions.json --output replay.json");args[argv[i]]=argv[i+1];}need(args["--input"]&&args["--output"]&&args["--assumptions"],"INPUT_ASSUMPTIONS_OUTPUT_REQUIRED");const result=fromObservationExport(JSON.parse(fs.readFileSync(args["--input"],"utf8")),JSON.parse(fs.readFileSync(args["--assumptions"],"utf8")));fs.mkdirSync(path.dirname(path.resolve(args["--output"])),{recursive:true});fs.writeFileSync(args["--output"],JSON.stringify(result,null,2)+"\n");process.stdout.write(JSON.stringify({output:path.resolve(args["--output"]),frames:result.source_evidence.frames.length,order_events:0,financial_acceptance_allowed:false})+"\n");}
module.exports={fromObservationExport};
if(require.main===module)main(process.argv.slice(2)).catch(error=>{process.stderr.write(String(error)+"\n");process.exitCode=1;});
