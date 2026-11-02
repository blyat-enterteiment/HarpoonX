"use strict";
const test=require("node:test"),assert=require("node:assert/strict");
for(const scenario of ['NOMINAL','STRESS'])test('research fork preserves complete sealed controls '+scenario,()=>{
 const fs=require('node:fs'),read=p=>JSON.parse(fs.readFileSync(p,'utf8'));
 const protocol=read('research/residual_30_18/protocol.json'),data=read(protocol.dataset);
 const artifact=read('evidence/residual_30_18_0/run_completed/signals.json');
 const {run}=require('./research9_replay.cjs');
 for(const policy of ['RESIDUAL_LONG','STOCK_THRESHOLD_OFF','CASH']){
  const actual=run(protocol,data,policy==='CASH'?[]:artifact.signals[scenario][policy],policy,scenario);
  const expected=read('evidence/residual_30_18_0/run_completed/'+scenario+'_'+policy+'.json');
  for(const field of ['funded','curve','accounting','summary'])assert.deepEqual(actual[field],expected[field]);
 }
});
