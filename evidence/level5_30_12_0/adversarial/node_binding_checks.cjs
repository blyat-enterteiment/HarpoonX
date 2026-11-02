'use strict';
// Read-only adversarial software checks. No market evidence or economic trials.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const app=path.resolve(process.argv[2]||'/workspace/scratch/4ecb05fdc50d/level5_work/HARPOON_XXXUltimate_30_12_0');
const output=path.join(__dirname,'node_binding_checks.json');
const m=require(path.join(app,'tools/level5_readiness.cjs'));
const {syntheticComparison}=require(path.join(app,'tools/fixtures/funded_comparison_fixture.cjs'));
const base=syntheticComparison(),clone=x=>JSON.parse(JSON.stringify(x));
const stress=clone(base);stress.common_request.id+='-stress';stress.common_request.execution_model.fees_bps_per_side+=1;
const tests=[];
function check(id,fn,expected){
  let output,error=null;try{output=fn()}catch(e){error=e.message}
  tests.push({id,expected,output:output??null,error,passed:expected==='ACCEPT'?error===null:error===expected});
}
check('UNCHANGED_POLICY_WITH_INCREASED_FEE',()=>m.stressBinding(base,stress),'ACCEPT');
const alteredModel=clone(stress);alteredModel.models.RIDGE.models.AAPL.beta[0]+=.1;
check('L5-A2-MODEL_CHANGED',()=>m.stressBinding(base,alteredModel),'STRESS_CHANGED_MODEL_SIGNALS_MARKET_RISK_OR_CAPITAL');
const alteredRisk=clone(stress);alteredRisk.common_request.config.exit.maxHoldHours-=1;
check('L5-A2-RISK_CHANGED',()=>m.stressBinding(base,alteredRisk),'STRESS_CHANGED_MODEL_SIGNALS_MARKET_RISK_OR_CAPITAL');
const alteredPrice=clone(stress);alteredPrice.common_request.events.find(e=>e.type==='market').quotes[0].bid+=.01;
check('L5-A2-MARKET_CHANGED',()=>m.stressBinding(base,alteredPrice),'STRESS_CHANGED_MODEL_SIGNALS_MARKET_RISK_OR_CAPITAL');
const alteredFees=clone(stress);alteredFees.common_request.execution_model.slippage_bps-=1;
check('L5-A2-COST_REDUCTION',()=>m.stressBinding(base,alteredFees),'STRESS_MUST_NOT_REDUCE_COST:slippage_bps');
(async()=>{
  let error=null;try{await m.deriveLevel5({schema:m.REQUEST_SCHEMA,curves:{SVR:[1,2,3]}})}catch(e){error=e.message}
  tests.push({id:'L5-A1-CALLER_CURVES_REJECTED',error,passed:error==='CALLER_CURVES_NOT_ACCEPTED'});
  const result={scope:'Synthetic software checks; no replay, no market/account observations and no financial experiment',source_sha256:crypto.createHash('sha256').update(fs.readFileSync(path.join(app,'tools/level5_readiness.cjs'))).digest('hex'),tests,passed:tests.filter(t=>t.passed).length,total:tests.length,production_edits:0,new_economic_experiments:0};
  fs.writeFileSync(output,JSON.stringify(result,null,2)+'\n');
  process.stdout.write(JSON.stringify(result)+'\n');
  if(result.passed!==result.total)process.exitCode=1;
})().catch(e=>{process.stderr.write(String(e)+'\n');process.exitCode=1});
