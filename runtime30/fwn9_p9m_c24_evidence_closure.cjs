"use strict";
/** FWN9 M11-C24: READ ONLY evidence inventory and test disposition.
 * This never executes a strategy, calls a broker, opens M10, or changes service.
 * "PASS" means only specified SOURCE CONTRACT assertions are fulfilled.
 */
const fs=require("node:fs");
const path=require("node:path");
const crypto=require("node:crypto");
const A=require("node:assert/strict");
const ROOT=path.resolve(__dirname,"..");
const need=(ok,tag)=>A.ok(ok,"C24_"+tag);
function readJson(name,root=ROOT){
 const p=path.join(root,name);
 const d=JSON.parse(fs.readFileSync(p,"utf8"));
 need(d&&typeof d==="object"&&!Array.isArray(d),"DOCUMENT_OBJECT_"+name);
 return d;
}
function sourceIntegrity(root=ROOT){
 const registered=readJson("research/modulation9/registration.json",root);
 const names=[
  "quant/harpoon_quant/modulation9.py",
  "runtime30/profit8_replay.js",
  "runtime30/ultimate_reservations.js",
  "research/modulation9/protocol.json"
 ];
 for(const name of names){
  const sha=crypto.createHash("sha256").update(fs.readFileSync(path.join(root,name))).digest("hex");
  need(sha===registered.sources_sha256[name],"FROZEN_SOURCE_HASH_"+name);
 }
 return {status:"PASS",scope:"ORIGINAL_M9_SOURCE_SHA256_ONLY",sourceCount:names.length};
}
function sourceDeployment(root=ROOT){
 const yaml=fs.readFileSync(path.join(root,"render.yaml"),"utf8");
 need(yaml.includes("name: harpoon-xxx-paper")&&
  yaml.includes('autoDeployTrigger: "off"')&&
  yaml.includes("name: harpoon-xxx-journal")&&
  yaml.includes('key: HARPOON_START_PAPER')&&
  yaml.includes('value: "1"'),"DECLARED_DEPLOYMENT_CONFIG_CHANGED");
 return {status:"PASS",scope:"SOURCE_BLUEPRINT_EXISTS_NOT_RUNNING_SERVICE",
  blueprintService:"harpoon-xxx-paper",
  automaticDeployDeclared:false,persistentDiskDeclared:true,
  originalPaperStartFlagDeclared:true,
  deployObserved:null,liveServiceState:null,liveBrokerOrdersObserved:null};
}
function observedSnapshot(original){
 need(original&&typeof original==="object","EXTERNAL_SNAPSHOT_OBJECT");
 need(original.workspaceAuthorized===true&&original.workspaceRecognized===true,
  "EXPLICIT_AUTHORIZED_WORKSPACE_REQUIRED");
 need(original.listServicesText==="null"&&
  original.listServicesWithPreviewsText==="null"&&
  original.postgresText==="No Postgres instances found"&&
  original.keyValueText==="No Key Value instances found",
  "EXTERNAL_SNAPSHOT_NOT_MATCHING_CURRENT_READ_ONLY_FINDINGS");
 need(original.accessMode==="READ_ONLY"&&
  original.secretsRead===false&&original.mutations===0,
  "EXTERNAL_READ_ONLY_CONTRACT");
 return {status:"PASS",scope:"CONNECTOR_DISCOVERY_RESPONSES_OBSERVED_NOT_DISK_OR_LOG_ACCESS",
  workspaceAuthorized:true,serviceInventoryResolved:false,
  workspaceHasZeroServicesProven:false,
  workspaceHasZeroHistoricalDisksProven:false,
  serviceRuntimeStateVerified:false,
  accountExecutionReceiptsRecovered:false,
  note:"Render services returned literal null (not a verified empty list); no ID for service logs or attached disk."};
}
function marketEvidence(root=ROOT){
 const d=readJson("evidence/modulation11/fwn9_phase9m_c23_market_coverage.json",root);
 const old=readJson("research/modulation11/fwn9_phase9m_c23_protocol.json",root);
 need(d.schema==="HARPOON_FWN9_M11_C23_ALPACA_OBSERVED_MARKET_BARS_WINDOW_COVERAGE_1"&&
  d.gates.stock_bar_coverage_complete===true&&
  d.gates.crypto_bar_coverage_complete===true&&
  d.gates.posthoc_market_data_count_as_fresh_OOS===false&&
  d.gates.realizable_net_alpha_certified===false&&
  d.gates.optimal_hour_certified===false,"C23_REALIZED_ECONOMICS_MUST_REMAIN_BLOCKED");
 for(const sym of ["SPY","QQQ"]){
  const v=d.stocks.symbols[sym];
  need(v.complete_sessions===30&&v.observed_unique_regular_bars===2340&&
   v.duplicate_regular_bars===0,"EQUITY_SOURCE_TIME_GRID_"+sym);
 }
 for(const sym of ["BTC/USD","ETH/USD"]){
  const v=d.crypto.symbols[sym];
  need(v.complete_utc_days===42&&v.observed_unique_inside_window===1008&&
   v.bars_excluded_at_or_after_end===1&&v.duplicate_hour_bars===0,
   "CRYPTO_HALF_OPEN_TIME_GRID_"+sym);
 }
 need(d.raw_provider_bytes_saved===false&&
  d.broker_fill_receipts_found===0&&
  d.capital_account_activity_records_found===0&&
  old.frozen.M10_final_sealed===3200&&old.frozen.N9S==="NO_GO",
  "MARKET_SOURCE_IS_NOT_ACCOUNT_FILLS");
 return {status:"PASS",scope:"SAVED_CONNECTED_SUMMARY_SCHEMA_NOT_RAW_PROVIDER_BYTE_REPRODUCTION",
  SPY_5min_complete:2340,QQQ_5min_complete:2340,
  BTC_hourly_complete:1008,ETH_hourly_complete:1008,
  equityFullSessions:30,cryptoFullDays:42,
  actualAccountFillsFound:0,
  rawMarketProviderBytesIndependentlyRechecked:false,
  netExecutionProfitVerified:false,optimalHourVerified:false};
}
function sourceResearchGate(root=ROOT){
 const c22=readJson("evidence/modulation11/fwn9_phase9m_c22_evidence.json",root);
 const c21=readJson("evidence/modulation11/fwn9_phase9m_c21_evidence.json",root);
 const c20=readJson("research/modulation11/fwn9_phase9m_c20_protocol.json",root);
 const c23=readJson("evidence/modulation11/fwn9_phase9m_c23_evidence.json",root);
 need(c22.budget.M10_final_opened===0&&
  c22.budget.M10_final_still_sealed===3200&&
  c22.budget.new_signals===0&&
  c22.budget.new_economic_accounts===0&&
  c21.budget.new_final_M10_accounts_opened===0&&
  c21.constructive_non_equivalence.original_OHLC_and_discrete_first_cross_universally_equivalent===false,
  "C21_C22_ORIGINAL_HOLDOUT_OR_PRICE_EQUIVALENCE_DRIFT");
 need(c20.budget.new_economic_accounts===0&&
  c20.budget.remaining_final_M10_accounts===3200&&
  c23.limits.M10_final_accounts_sealed===3200&&
  c23.limits.real_NET_OOS_proof===false&&
  c23.limits.best_asset_hour_by_net_realized_PnL===null&&
  c23.limits.outperformance_vs_cash_certified===false,
  "C20_C23_ECONOMIC_INFERENCE_MUST_FAIL_CLOSED");
 const expected=["H22_OPENING_CONFIRMATION",
  "H22_CRYPTO_UTC_LIQUIDITY","H22_OPTION_ASYMMETRY_RESEARCH_ONLY"];
 const p22=readJson("research/modulation11/fwn9_phase9m_c22_protocol.json",root);
 need(expected.every(name=>p22.prespecified_hypothesis_bundles.some(x=>x.id===name))&&
  p22.prespecified_hypothesis_bundles.length===3,"C22_ORIGINAL_HYPOTHESES_RENAMED");
 return {status:"PASS",scope:"FROZEN_RESEARCH_EVIDENCE_ONLY",
  originalModelBarFillEqualBrokerReceipt:false,
  C21ExactOHLCFirstCrossRefuted:true,
  sixPrespecifiedVariantsStillUnexecuted:true,
  nativeWEAKPopulationExposureUpperIndependentlyProved:false,
  nativeWEAKPopulationExecutionCreditUpperIndependentlyProved:false,
  originalOutperformanceCertifiable:false};
}
function closure(input,root=ROOT){
 const source=sourceIntegrity(root),
  deployment=sourceDeployment(root),
  render=observedSnapshot(input),
  market=marketEvidence(root),
  research=sourceResearchGate(root);
 const items=[
  ["M9_SOURCE_SHA256","PASS","source hashes validated"],
  ["GITHUB_BLUEPRINT_INSPECTION","PASS","static startup/deploy/disk settings identified"],
  ["AUTHORIZED_RENDER_INVENTORY","PASS","read-only workspace recognized, null service and empty DB/KV responses"],
  ["REAL_RENDER_RUNNING_STATE","BLOCKED","no service ID returned; service health and disk unreadable"],
  ["RENDER_LOGS_AND_ATTACHED_DISK","BLOCKED","no service identifier; no history receipts copied"],
  ["ALPACA_PRICE_BAR_SESSION_COMPLETENESS","PASS","saved 30 equity RTH sessions / 42 UTC crypto days summary"],
  ["RAW_PROVIDER_BYTE_INDEPENDENT_REVALIDATION","BLOCKED","raw connected provider bars not retained or authenticated in GitHub"],
  ["REAL_BROKER_ORDER_FILL_FEES_ACTIVITIES","BLOCKED","connected Alpaca exposes market data, not private account activities"],
  ["ORIGINAL_LIVE_ACCOUNT_CASH_NAV","BLOCKED","Render services and database inaccessible; Alpaca account endpoint missing"],
  ["PER_VARIANT_EXECUTED_NET_RETURNS","BLOCKED","six C22 candidate variants not actually executed"],
  ["FAMILYWISE_FORWARD_OOS_EDGE_VS_CASH","BLOCKED","no net per-candidate realized returns or independent held-out execution opportunities"],
  ["ORIGINAL_EXECUTABLE_BASELINE_COMPARISON","BLOCKED","broker-executable receipt baseline unavailable"],
  ["MODEL_OHLC_EQUALS_FIRST_CROSS","FAIL","refuted by C21 paired eight-step constructive counterexample"],
  ["WEAK_EA_EU_UNIVERSAL_NATIVE_BOUND","BLOCKED","population inputs B/U and full prebar state distribution not certified"],
  ["FUNDED_NET_COMPOUND_ECONOMIC_PROFIT","BLOCKED","arithmetic fixture proven, account profit not observed"],
  ["M10_FINAL_HOLDOUT_SEAL","PASS","no new research account/final created by this branch; live state unverified"],
  ["NO_EXECUTION_AUTHORITY","PASS","this read-only closure does not trade, deploy, merge or start optimizer"],
 ];
 const tally={PASS:0,FAIL:0,BLOCKED:0};
 for(const [,status] of items)tally[status]++;
 const result={schema:"HARPOON_FWN9_M11_C24_READONLY_EVIDENCE_CLOSURE_1",
  source,deployment,render,market,research,
  checks:items.map(([id,status,reason])=>({id,status,reason})),
  statusCounts:tally,allOfflineEngineeringChecksPassed:true,
  allEconomicCertificationChecksPassed:false,
  sixVariantsRealNetProfitsIndependentlyVerified:false,
  optimalAssetTimeByRealizedGrowth:null,
  canAuthorizePaperOrders:false,canAuthorizeLiveOrders:false,
  canStartRecursiveOptimization:false,canOpenM10Final:false,
  latestObservedRuntimeOrdersKnown:false,
  noMutationsPerformedByThisC24Audit:true,
  externalServiceStatus:"UNVERIFIED",
  final:N9S_LOCKED_NO_GO,
  M10_final_sealed:3200};
 need(tally.FAIL>=1&&tally.BLOCKED>=1&&result.M10_final_sealed===3200,
  "MUST_FAIL_CLOSED_ON_REAL_EXECUTION_AND_MISSING_ACCOUNT");
 return result;
}
const N9S_LOCKED_NO_GO="N9S_NO_GO_ECONOMICS_UNPROVEN";
module.exports={readJson,sourceIntegrity,sourceDeployment,observedSnapshot,
 marketEvidence,sourceResearchGate,closure};
if(require.main===module){
 const snapshot=JSON.parse(fs.readFileSync(0,"utf8"));
 process.stdout.write("C24_CLOSURE="+JSON.stringify(closure(snapshot))+"\n");
}
