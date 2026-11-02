'use strict';
const {parentPort,workerData}=require('node:worker_threads'),W=require('../src/warroom3.js');
try{parentPort.postMessage({value:workerData.operation==='selector'?require('./selector30.cjs').evaluate(workerData.selectorInput):workerData.operation==='optimize'?require('../src/optimizer3.js').run(workerData):W.study(workerData)});}catch(e){parentPort.postMessage({error:e.message});}
