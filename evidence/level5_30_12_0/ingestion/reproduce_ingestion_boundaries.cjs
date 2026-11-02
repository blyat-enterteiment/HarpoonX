"use strict";
// SYNTHETIC ENGINEERING AUDIT ONLY. No broker, strategy, training or orders.
const fs=require("node:fs"),path=require("node:path"),crypto=require("node:crypto"),cp=require("node:child_process"),assert=require("node:assert/strict");
const root=path.resolve(process.argv[2]||"/workspace/scratch/4ecb05fdc50d/level4_work/HARPOON_XXXUltimate_30_11_0");
const out=path.resolve(process.argv[3]||__dirname),fixtureDir=path.join(out,"synthetic_transport_fixtures");
fs.mkdirSync(fixtureDir,{recursive:true});
const {QuantObservationJournal}=require(path.join(root,"runtime30/quant_observations.js"));
const hash=b=>crypto.createHash("sha256").update(b).digest("hex");
class MemoryStore{constructor(){this.rows=new Map();}async get(k){return structuredClone(this.rows.get(k)||null);}async put(k,v){this.rows.set(k,structuredClone(v));return true;}}
function pair(at,universe=[]){
  const input={now:at,config:{expected_account_id:"SYNTHETIC_INGESTION_AUDIT",mode:"paper",universe,audit_fixture:"SYNTHETIC_ENGINEERING_ONLY"},signals:[],market:{calendar:[]}};
  return [input,{schema:"HARPOON_RUNTIME_OBSERVATION_1",status:"WAIT_FEATURE_DATA",asof:new Date(at).toISOString(),observations:[],rejected:{},selected:[],execution_allowed:false,liveApproved:false}];
}
function save(name,value){const p=path.join(fixtureDir,name),bytes=Buffer.from(JSON.stringify(value));fs.writeFileSync(p,bytes);return {path:path.relative(out,p),sha256:hash(bytes)};}
const py=String.raw`
import json,sys
from pathlib import Path
from harpoon_quant.causal_panel import _exports
case=json.loads(sys.stdin.read())
try:
    frames=_exports(case["refs"],Path(case["root"]),[])
    result={"accepted":True,"frames":len(frames),"error":None}
except (ValueError,KeyError,TypeError) as e:
    result={"accepted":False,"frames":None,"error":str(e)}
print(json.dumps(result))
`;
function check(refs){return new Promise((resolve,reject)=>{const p=cp.spawn("python3",["-c",py],{cwd:root,env:{...process.env,PYTHONPATH:path.join(root,"quant"),OPENBLAS_NUM_THREADS:"1",OMP_NUM_THREADS:"1",MKL_NUM_THREADS:"1"},stdio:["pipe","pipe","pipe"]});let stdout="",stderr="";const timer=setTimeout(()=>{p.kill("SIGKILL");reject(Error("PYTHON_AUDIT_TIMEOUT"));},30000);p.stdout.on("data",d=>stdout+=d);p.stderr.on("data",d=>stderr+=d);p.on("error",e=>{clearTimeout(timer);reject(e);});p.on("close",code=>{clearTimeout(timer);if(code!==0)reject(Error(stderr||"PYTHON_AUDIT_FAILED"));else{try{resolve(JSON.parse(stdout));}catch(e){reject(e);}}});p.stdin.end(JSON.stringify({refs,root:out}));});}
(async()=>{
  const j=new QuantObservationJournal(new MemoryStore(),"AUDIT","SYNTHETIC_INGESTION_AUDIT",{});await j.load();
  const start=Date.parse("2026-10-01T14:00:00Z");
  await j.capture(...pair(start));await j.capture(...pair(start+1000));
  const first=save("page_before_capture.json",await j.exportFrames(0,1));
  await j.capture(...pair(start+2000));
  const next=save("page_after_capture.json",await j.exportFrames(1,2));
  const stable=save("stable_complete.json",await j.exportFrames());
  const race=await check([first,next]);assert.equal(race.accepted,false);assert.equal(race.error,"EXPORT_PAGINATION_OR_BINDING");
  const control=await check([stable]);assert.equal(control.accepted,true);assert.equal(control.frames,3);
  await j.capture(...pair(start+3000,[{symbol:"AUDIT",book:"equity"}]));
  const changed=save("configuration_changed_complete.json",await j.exportFrames());
  const changedResult=await check([changed]);assert.equal(changedResult.accepted,false);assert.equal(changedResult.error,"SOURCE_CONFIG_CHANGED_SPLIT_DATASET");
  const sources=["xxx/quant_observations.ts","runtime30/quant_observations.js","xxx/server.ts","xxx/coordinator.ts","xxx/scheduler.ts","runtime/quant_bridge.cjs","runtime/discovery.cjs","xxx/net_accounting.ts","xxx/sessions.ts","quant/harpoon_quant/causal_panel.py","quant/harpoon_quant/scalar_svr.py","tools/observation_replay_input.cjs","tools/funded_comparison.cjs","tools/level4_readiness.cjs","config/examples/xxx.json"];
  const result={schema:"HARPOON_INGESTION_BOUNDARY_AUDIT_1",nature:"SYNTHETIC_ENGINEERING_ONLY",observed_financial_evidence:false,source_root:root,checks:[{name:"stable_complete_export_control",...control},{name:"capture_between_pages_rejected",...race},{name:"configuration_epoch_change_rejected",...changedResult}],source_hashes:Object.fromEntries(sources.map(s=>[s,hash(fs.readFileSync(path.join(root,s)))])),fixtures:{first,next,stable,changed},execution_allowed:false,financial_acceptance_allowed:false};
  fs.writeFileSync(path.join(out,"reproduction_results.json"),JSON.stringify(result,null,2)+"\n");
  console.log(JSON.stringify({checks:result.checks,output:path.join(out,"reproduction_results.json")}));
})().catch(e=>{console.error(e);process.exitCode=1;});
