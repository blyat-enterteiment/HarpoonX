'use strict';
const {parentPort,workerData}=require('node:worker_threads'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const c={console,Date,Math,Number,structuredClone,TextEncoder,Uint8Array};vm.createContext(c);
function inputKind(){return workerData.kind==='vector'?'HVector25.fit(input.labels,HTensor,input.partition||null)':'agentStudy25(HC19.dataset(input.raw),input.config,input.plugin)';}
try{for(const f of ['crypto_core','plugins/crypto_recovery','plugin_registry','agent_research25','tensor_core','vector25'])vm.runInContext(fs.readFileSync(path.join(__dirname,'../src',f+'.js'),'utf8'),c);c.input=workerData;const value=vm.runInContext(inputKind(),c);parentPort.postMessage({value});}catch(e){parentPort.postMessage({error:e.message});}
