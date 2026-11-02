"use strict";
// Test-only synthetic inputs. This never reserves a research journal or fits a model.
const fs=require("node:fs"),path=require("node:path"),crypto=require("node:crypto");
const {syntheticComparison}=require("./funded_comparison_fixture.cjs");
const {runFundedComparison}=require("../funded_comparison.cjs");
const {deriveLevel5}=require("../level5_readiness.cjs");
function write(root,name,value){const raw=JSON.stringify(value,null,2)+"\n";fs.writeFileSync(path.join(root,name),raw);return {path:name,sha256:crypto.createHash("sha256").update(raw).digest("hex")};}
async function makeLevel5Fixture(root){
  fs.mkdirSync(root,{recursive:true});const base=syntheticComparison();
  base.common_request.execution_model.operating_cash_reserve={amount_usd:2,known_at:base.common_request.start_at-1,method:"FIXED_INITIAL_CASH_RESERVE"};
  const stress=structuredClone(base);
  stress.common_request.id+="-stress";stress.common_request.execution_model.slippage_bps+=1;
  const br=await runFundedComparison(base),sr=await runFundedComparison(stress);
  const comparison={request:write(root,"base_request.json",base),report:write(root,"base_report.json",br)};
  const level4={schema:"HARPOON_LEVEL4_READINESS_REQUEST_1",data:null,comparison,ledger:null};
  const request={schema:"HARPOON_LEVEL5_DERIVATION_REQUEST_1",level4:{request:write(root,"level4_request.json",level4)},
    stress:[{id:"COST_STRESS",request:write(root,"stress_request.json",stress),report:write(root,"stress_report.json",sr)}]};
  const requestRef=write(root,"level5_request.json",request),derived=await deriveLevel5(request,root);
  write(root,"derived.json",derived);return {base,stress,baseReport:br,stressReport:sr,request,requestRef,derived};
}
if(require.main===module)makeLevel5Fixture(path.resolve(process.argv[2])).then(()=>process.stdout.write("SYNTHETIC_ENGINEERING_FIXTURE_READY\n")).catch(e=>{process.stderr.write(String(e)+"\n");process.exitCode=2;});
module.exports={makeLevel5Fixture,write};
