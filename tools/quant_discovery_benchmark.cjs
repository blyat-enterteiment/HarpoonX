'use strict';
// Local synthetic discovery workload. No market/broker requests or latency claims.
const {performance}=require('node:perf_hooks');
const os=require('node:os'),fs=require('node:fs'),path=require('node:path');
const bridge=require('../runtime/quant_bridge.cjs');
const {fixture,model}=require('./quant_discovery_fixtures.cjs');
(async()=>{
 const iterations=100,candidates=30,measurements=[],models={},gainers=[];
 for(let i=0;i<candidates;i++){const symbol='MOCK'+String(i).padStart(2,'0');models[symbol]=model();gainers.push({symbol});}
 let requests=0,historicalBars=0,historyLoads=0,quoteRefreshes=0;
 for(let n=0;n<iterations;n++){
  const f=fixture({models,gainers});
  try{
   // 24 synthetic complete previous sessions plus four recent bars.
   const full=f.rows.daily.flatMap(d=>Array.from({length:78},(_,j)=>({...d,t:new Date(Date.parse(d.t)+j*300000).toISOString(),v:1000}))).concat(f.rows.bars.slice(-4));
   f.options.historyOverride=async(names,timeframe)=>Object.fromEntries(names.map(symbol=>[symbol,timeframe==='5Min'?full:f.rows.daily]));
   const start=performance.now(),result=await bridge.discover(f.engine);measurements.push(performance.now()-start);
   if(result.added.length!==candidates || result.health!=='READY')throw Error('Benchmark fixture not ready: '+JSON.stringify(result));
   requests=f.calls.length;historicalBars=full.length*candidates;historyLoads=f.historyCalls.length;quoteRefreshes=f.quoteBooks.length;
  }finally{f.cleanup();}
 }
 const sorted=[...measurements].sort((a,b)=>a-b),q=p=>sorted[Math.min(sorted.length-1,Math.ceil(p*sorted.length)-1)];
 const report={nature:'SYNTHETIC_LOCAL_ENGINEERING_BENCHMARK',iterations,candidates,regular_bars_processed:historicalBars,
  api_mock_requests:requests,historical_load_calls:historyLoads,quote_refresh_calls:quoteRefreshes,real_network_requests:0,orders:0,node:process.version,platform:process.platform,cpu:os.cpus()[0]?.model,
  elapsed_ms:{p50:q(.5),p95:q(.95),p99:q(.99),min:sorted[0],max:sorted.at(-1)},samples_ms:measurements,
  limitations:['Excludes broker, network, persistent-store and market-data latency.','Percentiles describe this small local fixture workload; no production service-level claim.']};
 if(process.env.HARPOON_DISCOVERY_BENCHMARK_OUTPUT)fs.writeFileSync(path.resolve(process.env.HARPOON_DISCOVERY_BENCHMARK_OUTPUT),JSON.stringify(report,null,2)+'\n');
 console.log(JSON.stringify(report,null,2));
})().catch(error=>{console.error(error);process.exitCode=1;});
