"use strict";
/**
 * C30 original-study feasibility preflight, READ ONLY.
 * Probes actual C22/C25/C28/C29 interfaces, never broker/order endpoints.
 * A JSON assertion, SHA, fixture or plan cannot authorize PAPER/LIVE.
 */
const assert=require("node:assert/strict");
const C22=require("./fwn9_c22_session_compound.cjs");
const C25=require("./fwn9_c25_alpaca_readonly_exporter.cjs");
const C28=require("./fwn9_c28_source_obligations.cjs");
const C29=require("./fwn9_c29_frozen_assignments.cjs");
const NATIVE=require("./fwn9_c29_native_producer_reader.cjs");
function need(ok,code){assert.ok(ok,"C30_"+code);}
async function audit({plan=null,nativeJournalExport=null}={}){
 if(plan!==null)C29.validate(plan);
 const arms=plan?.eightArms||[
  ...C28.EXPECTED.map(x=>x.policy),"ORIGINAL_BASELINE","CASH"
 ];
 need(Array.isArray(arms)&&arms.length===8&&new Set(arms).size===8,
  "FROZEN_EIGHT_ARMS");
 need(C28.EXPECTED.length===6&&
  arms.filter(x=>x.startsWith("H22_")).length===6,
  "SIX_ORIGINAL_VARIANTS");
 need(arms.includes("ORIGINAL_BASELINE")&&arms.includes("CASH"),
  "TWO_CONTROLS");
 const optionArms=C28.EXPECTED.filter(x=>x.book.includes("options"))
  .map(x=>x.policy);
 const rank=C22.rank([],{});
 need(rank.schema==="FWN9_C22_OBSERVED_WINDOW_RESEARCH_RANKING_1",
  "ORIGINAL_C22_RANKER");
 const optionSize=C22.size(null,{book:"options",unitPriceUsd:1,
  unitRiskUsd:1,multiplier:100});
 let c25OptionInstrumentSupported=false;
 try{
  await C25.instrumentCatalog(async()=>({class:"option"}),
   {positions:[{symbol:"C30_OPTION_PROBE",asset_class:"option"}]},
   {positions:[]},{rows:[]});
  c25OptionInstrumentSupported=true;
 }catch(err){
  need(String(err).includes("C25_GET_ASSET_CLASS"),
   "UNEXPECTED_C25_CATALOG_FAILURE");
 }
 let nativeObservation=null;
 if(nativeJournalExport!==null)nativeObservation=NATIVE.inspect(nativeJournalExport);
 const blockers=[];
 if(plan===null)blockers.push("NO_FROZEN_PROSPECTIVE_PLAN_SUPPLIED");
 if(rank.executionAllowed!==true)
  blockers.push("FROZEN_C22_RESEARCH_RANKER_PROHIBITS_EXECUTION");
 if(optionArms.length>0&&
    (optionSize.executionAllowed!==true||optionSize.eligible!==true))
  blockers.push("OPTIONS_C22_QUANTITY_EXECUTOR_UNCERTIFIED");
 if(optionArms.length>0&&!c25OptionInstrumentSupported)
  blockers.push("C25_BROKER_EXPORT_CANNOT_ACCOUNT_FOR_OPTIONS");
 if(nativeObservation?.c22SixOriginalVariantPrefilterEvaluationsProved!==true)
  blockers.push("SIX_NATIVE_PREFILTER_EVALUATIONS_NOT_PROVEN");
 // No connected independent registrar or private Trading API verifier.
 // Ignore user-provided success flags that this code cannot authenticate.
 blockers.push("INDEPENDENT_PREOUTCOME_REGISTRATION_NOT_VERIFIED");
 blockers.push("BROKER_PRIVATE_GET_RECEIPTS_NOT_AUTHENTICATED");
 blockers.push("FROZEN_EIGHT_ARM_REAL_FINANCIAL_RETURNS_NOT_OBSERVED");
 return {
  schema:"HARPOON_FWN9_C30_ORIGINAL_STUDY_EXECUTABILITY_PREFLIGHT_1",
  source:"ORIGINAL_C22_C25_C28_C29_MODULE_PROBES",
  frozenPlanValidated:plan!==null,
  frozenPlanDigest:plan?.planDigest??null,
  candidateArms:6,controlArms:2,optionResearchArms:optionArms,
  originalC22RankExecutionAllowed:rank.executionAllowed===true,
  originalC22OptionSizeCertified:
   optionSize.eligible===true&&optionSize.executionAllowed===true,
  originalC25OptionInstrumentAccountingAvailable:c25OptionInstrumentSupported,
  sourceObservationRowsAudited:nativeObservation?.nativeObservationFramesVerified??0,
  originalSixPrefilterExecutionsProved:
   nativeObservation?.c22SixOriginalVariantPrefilterEvaluationsProved===true,
  independentBrokerAndRegistrarAttested:false,
  structuralBlockers:blockers,
  fullEightArmBrokerExperimentExecutable:false,
  mayStartFinancialValidation:false,
  maySendPaperOrLiveOrders:false,
  modifiedLegacySignalOrExecutionCode:false,
  M10FinalAccountsSealed:3200,N9S:"NO_GO"
 };
}
module.exports={audit};
