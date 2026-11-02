'use strict';
// Bounded software benchmark. Receipts/history below are manufactured solely
// for engineering load; no broker, historical financial dataset or new trial.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const os=require('node:os');
const {performance}=require('node:perf_hooks');
const {NetAccountLedger,netLedgerDigest}=require('../runtime30/net_accounting.js');
const T0=Date.UTC(2026,9,15,13,30),MIN=60000;
class MemoryStore{
  constructor(){this.data=new Map();}
  async get(k){return structuredClone(this.data.get(k)??null);}
  async put(k,v){this.data.set(k,structuredClone(v));return true;}
  async lease(){return true;}
  async close(){}
}
function costs(through){return {schema:'HARPOON_COST_RECEIPT_1',account_id:'benchmark-account',currency:'USD',
  receipt_id:'SYNTHETIC-ENGINEERING-COST-'+through,coverage_complete:true,
  from:T0,through,known_at:through,reference:'SYNTHETIC_ENGINEERING_ZERO_COST_COVERAGE',
  categories:['DATA','INFRASTRUCTURE','INFERENCE','OTHER'],entries:[]};}
function stats(values){const v=[...values].sort((a,b)=>a-b);return {n:v.length,p50_ms:v[Math.floor((v.length-1)*.5)],
  p95_ms:v.length>=20?v[Math.floor((v.length-1)*.95)]:null,
  p99_ms:v.length>=100?v[Math.floor((v.length-1)*.99)]:null,max_ms:v.at(-1),
  small_sample_high_quantiles_not_reported:v.length<100};}
async function main(){
  const store=new MemoryStore(),cfg={executionNature:'SYNTHETIC_ENGINEERING_ONLY',maxObservations:12000};
  let rows=[],requests=0;
  const api={async request(path,method){assert.equal(method,'GET');requests++;
    if(path==='/v2/account')return {id:'benchmark-account',currency:'USD',cash:'20000',equity:'20000'};
    if(path==='/v2/positions')return [];
    if(path.startsWith('/v2/account/activities?')){const q=new URL(path,'https://fixture.invalid').searchParams;
      const token=q.get('page_token'),start=token?rows.findIndex(r=>r.id===token)+1:0;
      return structuredClone(rows.slice(start,start+Number(q.get('page_size'))));}
    throw Error('UNEXPECTED_REQUEST');}};
  let ledger=new NetAccountLedger(store,api,'benchmark-ledger','benchmark-account',cfg);
  await ledger.refresh({now:T0,externalCosts:costs(T0)});
  rows=Array.from({length:2000},(_,i)=>({id:'fee-'+String(i).padStart(6,'0'),activity_type:'FEE',
    date:'2026-10-15',created_at:new Date(T0+30000).toISOString(),net_amount:'0'}));
  await ledger.refresh({now:T0+MIN,externalCosts:costs(T0+MIN)});
  const state=await store.get('benchmark-ledger'),template=state.observations[1];
  for(let i=2;i<10000;i++){
    const o=structuredClone(template);o.at=T0+i*MIN;o.activitiesThrough=o.at;o.activityIds=[];
    o.sourceReceipt.receiptTime=o.at;o.sourceHash=netLedgerDigest(o.sourceReceipt);o.economicKnownAt=o.at;
    state.observations.push(o);
  }
  let now=state.observations.at(-1).at;
  state.lastSuccess=now;state.lastAttempt=now;state.costCoverage.through=now;state.costCoverage.known_at=now;
  state.coverage.untilCreatedAt=now;state.evidence.observationsHash=netLedgerDigest(state.observations);
  state.evidence.benchmarkManufacturedHistory=true;state.evidence.knownAt=now;state.evidence.observedAt=now;
  delete state.integrity;state.integrity=netLedgerDigest(state);await store.put('benchmark-ledger',state);
  ledger=new NetAccountLedger(store,api,'benchmark-ledger','benchmark-account',cfg);await ledger.load();
  const summary=[],full=[],refresh=[];
  for(let i=0;i<2000;i++){const start=performance.now();const v=ledger.view(now);summary.push(performance.now()-start);assert.equal(v.observations,undefined);}
  for(let i=0;i<5;i++){const start=performance.now();ledger.exportState(now);full.push(performance.now()-start);}
  const beforeRefreshRequests=requests;
  for(let i=0;i<3;i++){now+=MIN;const start=performance.now();await ledger.refresh({now,externalCosts:costs(now)});refresh.push(performance.now()-start);}
  const output={schema:'HARPOON_LEDGER_ENGINEERING_BENCHMARK_1',nature:'SYNTHETIC_ENGINEERING_ONLY',
    environment:{node:process.version,platform:process.platform,architecture:process.arch,cpu:os.cpus()[0]?.model??null},
    load:{observations:10000,activities:rows.length,read_requests_per_refresh:(requests-beforeRefreshRequests)/3,
      persisted_bytes:Buffer.byteLength(JSON.stringify(await store.get('benchmark-ledger')))},
    summary:stats(summary),export_full:stats(full),refresh_with_memory_store:stats(refresh),
    rss_bytes:process.memoryUsage().rss,peak_rss_bytes:process.resourceUsage().maxRSS*1024,
    source_authenticity_verified:false,financial_advantage_demonstrated:false,
    limitations:['No network or actual broker latency is measured.','Full history for the benchmark is manufactured and is not a financial experiment.',
      'Memory Store timings do not measure production disk/network throughput.','Repeated samples share one process and are not independent hardware trials.'],
    summary_avoids_full_row_copy:true,retention_policy:'Bounded journal stops certification at configured limits; no capital reset or silent truncation.'};
  if(process.argv[2])fs.writeFileSync(process.argv[2],JSON.stringify(output,null,2)+'\n');
  process.stdout.write(JSON.stringify(output,null,2)+'\n');
}
main().catch(error=>{process.stderr.write(String(error.stack||error)+'\n');process.exitCode=1;});
