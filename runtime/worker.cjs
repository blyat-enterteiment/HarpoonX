'use strict';
const {parentPort,workerData}=require('node:worker_threads'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const context={console,Intl,Date,Set,Map,Math,JSON,Number,structuredClone,Uint8Array,TextEncoder,TextDecoder};vm.createContext(context);
for(const f of ['defaults','contract','plugins/securities_rules','canonical','plugins/catalog','xiii_core','tensor_core','xii_core','x_core','xi_core','xi_replay','plugins/securities_entries','lab_rules','core','x_research','lab_core','xii_research','xiii_research'])vm.runInContext(fs.readFileSync(path.join(__dirname,'..','src',f+'.js'),'utf8'),context,{filename:f+'.js'});
context.input=workerData.input;
try{const result=workerData.kind==='lab'?vm.runInContext('labCompare(input)',context):vm.runInContext(`(()=>{const a=input,monitor=monitorChampion(a.rows,a.days,a.cfg,a.champion);if(monitor.revert)return {report:{status:'REVERSION POR DETERIORO',monitor},candidate:null,revert:true};return xEvaluate(a.rows,a.days,a.cfg,a.champion,a.usedEnd,a.attempts);})()`,context);parentPort.postMessage({result});}catch(e){parentPort.postMessage({error:e.message});}
