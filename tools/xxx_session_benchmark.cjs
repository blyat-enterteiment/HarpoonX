"use strict";
// Partial local benchmark; excludes quotes, plugins, allocator, network and fills.
const path = require("node:path"), os = require("node:os");
const {performance} = require("node:perf_hooks");
const APP = path.resolve(__dirname,"..");
const BUILD = process.env.HARPOON_SESSION_RUNTIME || path.join(APP,"runtime30");
const {regularClosedBars,sessionContext,streakDiagnostics} = require(path.join(BUILD,"sessions.js"));
const now = Date.parse("2026-10-15T20:00:05Z"), dates=[];
for(let d=0;dates.length<50;d++) {
  const at = new Date(now-d*86400000);
  if(![0,6].includes(at.getUTCDay())) dates.push(at.toISOString().slice(0,10));
}
dates.reverse();
const calendar=dates.map(date=>({date,open:Date.parse(date+"T13:30:00Z"),close:Date.parse(date+"T20:00:00Z")}));
const raw=calendar.flatMap(s=>Array.from({length:78},(_,i)=>({t:new Date(s.open+i*300000).toISOString(),o:100,h:101,l:99,c:100+i*.001,v:1000,vw:100})));
const context=sessionContext(now,calendar), samples=[];
const symbols=40, measured=100, warmup=3;
for(let k=-warmup;k<measured;k++) {
  const start=performance.now();
  for(let symbol=0;symbol<symbols;symbol++) {
    const history=regularClosedBars(raw,now,calendar,false);
    const current=regularClosedBars(history,now,calendar,true);
    const d=streakDiagnostics(current,history,context,calendar);
    if(current.length!==78 || d.length!==77) throw Error("INVALID_BENCHMARK_FIXTURE");
  }
  const elapsed=performance.now()-start;
  if(k>=0) samples.push(elapsed);
}
const sorted=[...samples].sort((a,b)=>a-b), q=p=>sorted[Math.ceil(p*sorted.length)-1];
console.log(JSON.stringify({
  nature:"SYNTHETIC_ENGINEERING_BENCHMARK",node:process.version,platform:process.platform,
  arch:process.arch,cpu:os.cpus()[0]?.model,logical_time:new Date(now).toISOString(),
  symbols_per_batch:symbols,bars_per_symbol:raw.length,regular_sessions:50,
  warmup_batches:warmup,measured_batches:measured,
  batch_ms:{p50:q(.5),p95:q(.95),p99:q(.99),min:sorted[0],max:sorted.at(-1)},
  process_rss_bytes:process.memoryUsage().rss,
  scope:"Regular-history filtering, current-session selection and streak diagnostics only; not end-to-end market latency.",
  environment_limit:"Shared execution host; concurrent work may affect tails. Empirical sample quantiles, not a production latency guarantee.",
  samples_ms:samples
},null,2));
