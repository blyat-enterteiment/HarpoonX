'use strict';
const {performance} = require('node:perf_hooks');
const {basicAuth} = require('../deploy/managed.cjs');
const fs = require('node:fs'), path = require('node:path');
const password='SYNTHETIC-BENCHMARK-PASSWORD-'.repeat(2);
const header='Basic '+Buffer.from('trader:'+password).toString('base64');
for(let i=0;i<5000;i++) basicAuth(header,password);
const samples=[];
for(let batch=0;batch<25;batch++) {
 const start=performance.now();
 for(let i=0;i<2000;i++) if(!basicAuth(header,password)) throw Error('Benchmark authentication failed');
 samples.push((performance.now()-start)*1000/2000);
}
samples.sort((a,b)=>a-b);
const report={node:process.version,checks:50000,batches:25,warmup:5000,median_microseconds_per_check:samples[12],p95_batch_microseconds_per_check:samples[23],scope:'Valid synthetic Basic parser plus constant-time value comparison, local CPU only. Not HTTP throughput, inference or trading latency; no optimization improvement is claimed.'};
fs.writeFileSync(path.join(__dirname,'../evidence/auth_benchmark.json'),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify(report));
