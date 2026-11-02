"use strict";
// Pure software fixture: invented prices and fixed constant models; no fitting.
const fs=require("node:fs"),path=require("node:path"),crypto=require("node:crypto");
const {syntheticRequest}=require("./coordinator_replay_fixture.cjs");
const {hash}=require("../coordinator_replay.cjs");
const ROOT=path.resolve(__dirname,"../..");
const FEATURES=["momentum_1","momentum_3","momentum_12","rv_12","log_rvol","vwap_z","relative_3","spread_fraction"];
function syntheticModels(){
  const common={origin:"SYNTHETIC_ENGINEERING_ONLY",available_at:"2026-10-14T12:00:00+00:00",last_observation_at:"2026-10-13T12:00:00+00:00",horizon_hours:24,feature_names:FEATURES,target_unit:"return_fraction",
    fixture_purpose:"CONSTANT_INVENTED_MODEL_FOR_INFERENCE_AND_ACCOUNTING_SOFTWARE_TESTS; NO_TRAINING_OR_MARKET_EVIDENCE"};
  const residuals=Object.fromEntries(Array.from({length:25},(_,i)=>["2026-09-"+String(i+1).padStart(2,"0"),((i%3)-1)*.001]));
  const base={accepted:true,mean:Array(8).fill(0),scale:Array(8).fill(1),residuals};
  const RIDGE={...structuredClone(common),schema:"HARPOON_QUANT_CALIBRATION_1",model_kind:"RIDGE",models:{AAPL:{...structuredClone(base),model_kind:"RIDGE",beta:[.03,...Array(8).fill(0)]}}};
  const files=Object.fromEntries(["scalar_svr.py","calibration.py","core.py","support.py"].map(name=>[name,crypto.createHash("sha256").update(fs.readFileSync(path.join(ROOT,"quant/harpoon_quant",name))).digest("hex")]));
  const SVR={...structuredClone(common),schema:"HARPOON_QUANT_CALIBRATION_2",model_kind:"SVR_RBF",research_only:true,implementation_hash:hash(files),
    models:{AAPL:{...structuredClone(base),model_kind:"SVR_RBF",feature_dimension:8,last_observation_at:common.last_observation_at,target_mean:.03,target_scale:1,
      svr:{support_vectors:[],dual_coef:[],gamma:.125,intercept:0}}}};
  SVR.artifact_hash=hash(SVR);
  return {RIDGE,SVR};
}
function syntheticComparison(){
  const common=syntheticRequest();common.id="synthetic-fixed-model-funded-comparison";
  common.config.quant={enabled:false,config:{horizon_hours:24,solver_seconds:1},optimizer:{enabled:false},microstructure:{enabled:false}};
  return {schema:"HARPOON_FUNDED_COMPARISON_REQUEST_1",purpose:"SYNTHETIC_SOFTWARE_TEST",account_scope:"CASH_ONLY_COUNTERFACTUAL_NO_EXTERNAL_FLOWS",predictor_timeout_ms:8000,common_request:common,models:syntheticModels()};
}
module.exports={syntheticComparison,syntheticModels};
