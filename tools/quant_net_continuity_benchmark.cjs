"use strict";
// Bounded synthetic engineering benchmark. No broker, network, or market replay.
const fs=require("node:fs"),os=require("node:os"),{performance}=require("node:perf_hooks");
const {NetAccountLedger,verifyNetLedgerHistoryBundle}=require("../runtime30/net_accounting.js");
class Store{constructor(){this.rows=new Map();}async get(k){return structuredClone(this.rows.get(k)??null);}async put(k,v){this.rows.set(k,structuredClone(v));return true;}async lease(){return true;}async close(){}}
const api={async request(url,method="GET"){if(method!=="GET")throw Error("WRITES_FORBIDDEN");if(url==="/v2/account")return{id:"SYNTHETIC-BENCH",currency:"USD",cash:"10000",equity:"20000"};if(url==="/v2/positions")return[{symbol:"SPY",qty:"100",market_value:"10000",asset_class:"us_equity"}];if(url.startsWith("/v2/account/activities?"))return[];throw Error("UNEXPECTED_READ");}};
function stats(xs){const ordered=[...xs].sort((a,b)=>a-b),q=p=>ordered[Math.min(ordered.length-1,Math.floor(p*(ordered.length-1)))];return{samples:xs.length,p50_ms:xs.length?q(.5):null,p95_ms:xs.length>=20?q(.95):null,p99_ms:xs.length>=100?q(.99):null,min_ms:ordered[0]??null,max_ms:ordered.at(-1)??null,tail_quantile_limitation:xs.length<100?"INSUFFICIENT_SAMPLES_FOR_REPORTED_P99":null};}
async function main(){
  const store=new Store(),ledger=new NetAccountLedger(store,api,"B","SYNTHETIC-BENCH",{executionNature:"SYNTHETIC_ENGINEERING_ONLY",maxObservations:250,archive:{enabled:true,maxSegments:16,maxStoredBytes:64*1024*1024}});
  const start=Date.UTC(2026,9,15,13,30),before=[],roll=[],after=[],samples=1001;let previous=0;
  for(let i=0;i<samples;i++){
    const now=start+i*60000,t=performance.now();await ledger.refresh({now,instruments:[{symbol:"SPY",book:"etf",multiplier:1,currency:"USD"}],externalCosts:{schema:"HARPOON_COST_RECEIPT_1",account_id:"SYNTHETIC-BENCH",currency:"USD",receipt_id:"SYNTHETIC-CONTINUITY-COST-"+now,coverage_complete:true,from:start,through:now,known_at:now,reference:"SYNTHETIC-BENCH-DECLARATION",categories:["DATA","INFRASTRUCTURE","INFERENCE","OTHER"],entries:[]}});
    const elapsed=performance.now()-t,segments=ledger.view(now).archive.segments;
    (segments>previous?roll:segments?after:before).push(elapsed);previous=segments;
    await new Promise(resolve=>setImmediate(resolve));
  }
  const now=start+(samples-1)*60000,pages=[];let offset=0,t=performance.now();
  do{const page=await ledger.exportHistory(offset,1000);pages.push(page);offset=page.next_offset;}while(offset!==null);
  const exportMs=performance.now()-t;t=performance.now();const checked=verifyNetLedgerHistoryBundle(pages,ledger.view(now).integrity),verifyMs=performance.now()-t;
  t=performance.now();const input=await ledger.performanceInputWithArchive(now),performanceMs=performance.now()-t;
  const view=ledger.view(now),result={schema:"HARPOON_NET_CONTINUITY_BENCHMARK_1",origin:"SYNTHETIC_ENGINEERING_ONLY",external_requests:0,financial_trials:0,
    environment:{node:process.version,platform:process.platform,arch:process.arch,cpu:os.cpus()[0]?.model,host_logical_cpus:os.cpus().length,memory:process.memoryUsage()},
    workload:{observations:samples,positions_per_observation:1,activities:0,declared_expenses:0,explicit_synthetic_cost_coverage:true,active_observation_bound:250,archive_segments:view.archive.segments,archived_observations:view.archive.archivedObservations,active_observations:view.archive.activeObservations,reserved_archive_bytes:view.archive.reservedBytes},
    refresh_before_first_rollover:stats(before),rollover:stats(roll),refresh_after_first_rollover:stats(after),
    full_export:{pages:pages.length,records:pages[0].total_records,elapsed_ms:exportMs},offline_integrity_and_accounting_verification:{observations:checked.observations.length,elapsed_ms:verifyMs,verified:checked.verified},
    performance_materialization:{returns:input?.returns.length??null,elapsed_ms:performanceMs,bytes:input?.materialization_bytes??null},
    limitations:["In-memory Store and synthetic GET responses; no broker latency or production capacity inference.","Archive quota is finite; totals do not imply indefinite autonomy.","Zero costs are an explicit synthetic fixture declaration, not missing actual costs imputed to zero.","No comparison of investment strategies or evidence of profitability."]};
  const output=process.argv[2];if(output)fs.writeFileSync(output,JSON.stringify(result,null,2)+"\n");process.stdout.write(JSON.stringify(result,null,2)+"\n");
}
main().catch(error=>{process.stderr.write(String(error)+"\n");process.exitCode=1;});
