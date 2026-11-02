'use strict';
/* Bounded, deterministic coordinate search. Research only; no network or order authority. */
(function(root,factory){
 const W=typeof module==='object'&&module.exports?require('./warroom3.js'):root.HWarRoom3,api=factory(W);
 if(typeof module==='object'&&module.exports)module.exports=api;else root.HOptimize3=api;
 api.workerSource=W.workerSource.split('onmessage=e=>')[0]+'const HOptimize3=('+factory.toString()+')(HWarRoom3);onmessage=e=>{try{postMessage({value:HOptimize3.run(e.data)})}catch(x){postMessage({error:x.message})}};';
})(typeof globalThis!=='undefined'?globalThis:this,function(W){
 const KEYS=['entry_days','exit_days','atr_days','atr_multiple'],RECIPES=['C1','C2','C3','C4','C5','C6','C7'];
 const clone=x=>structuredClone(x),demand=(ok,msg)=>{if(!ok)throw Error(msg);};
 function policy(raw={}){
  demand(raw&&typeof raw==='object'&&!Array.isArray(raw),'Política de búsqueda inválida');
  const p={maxTrials:16,batchSize:4,maxComputeMs:60000,patienceBatches:3,finalists:3,...raw};
  demand(Object.keys(p).sort().join(',')==='batchSize,finalists,maxComputeMs,maxTrials,patienceBatches','Parámetros de búsqueda desconocidos');
  for(const [key,lo,hi]of [['maxTrials',8,64],['batchSize',1,4],['maxComputeMs',5000,120000],['patienceBatches',2,8],['finalists',1,3]])demand(Number.isInteger(p[key])&&p[key]>=lo&&p[key]<=hi,'Presupuesto de búsqueda inválido: '+key);
  return p;
 }
 function candidate(base,raw){const c=W.config(raw);for(const key of Object.keys(base))if(!KEYS.includes(key))demand(c[key]===base[key],'La búsqueda no cambia riesgo, capital, costes ni plazo: '+key);return c;}
 function key(plan){return W.stable([plan.recipe,...KEYS.map(k=>plan.strategy[k])]);}
 function create(base,raw={}){return {schema:'HARPOON-OPTIMIZER-3-1',version:'25.3.1',policy:policy(raw),base:W.config(base),status:'READY',reserved:[],rows:[],baseline:null,batches:0,computeMs:0,cacheHits:0,stagnant:0,bestScore:null,stopReason:null,pending:null,pauseRequested:false,ordersEnabled:false,paidModelCalls:0};}
 function propose(state){
  const p=policy(state.policy),used=new Set(state.reserved.map(x=>x.key)),out=[],rows=state.rows.filter(x=>!x.error&&Number.isFinite(x.searchScore)).sort((a,b)=>b.searchScore-a.searchScore||b.run.metrics.netUsd-a.run.metrics.netUsd),anchor=rows[0]?.strategy||state.base,round=Math.floor(Math.max(0,state.reserved.length-RECIPES.length)/p.batchSize),scale=Math.pow(.5,Math.min(round,4));
  let skipped=0;
  for(let n=0;n<500&&out.length<Math.min(p.batchSize,p.maxTrials-state.reserved.length);n++){
   const index=state.reserved.length+out.length;
   let recipe,strategy;
   if(index<RECIPES.length&&n===out.length){recipe=RECIPES[index];strategy={...state.base};}
   else{recipe=rows.length?rows[Math.floor(n/8)%Math.min(3,rows.length)].recipe:RECIPES[(index+n)%RECIPES.length];strategy={...anchor};const k=KEYS[Math.floor(n/2)%KEYS.length],sign=n%2?1:-1,step={entry_days:Math.max(1,Math.round(12*scale)),exit_days:Math.max(1,Math.round(5*scale)),atr_days:Math.max(1,Math.round(6*scale)),atr_multiple:Math.max(.1,.75*scale)}[k],bounds={entry_days:[10,120],exit_days:[2,60],atr_days:[5,60],atr_multiple:[1,6]}[k];strategy[k]=Math.round(Math.min(bounds[1],Math.max(bounds[0],strategy[k]+sign*step))*1000)/1000;}
   if(strategy.exit_days>=strategy.entry_days)continue;
   const plan={recipe,strategy:candidate(state.base,strategy)},fingerprint=key(plan);
   if(used.has(fingerprint)){skipped++;continue;}
   used.add(fingerprint);out.push({...plan,key:fingerprint,id:'T'+String(state.reserved.length+out.length+1).padStart(3,'0')});
  }
  return {plans:out,cacheHits:skipped};
 }
 function validateInput(input){
  const cp=W.protocol(input.protocol),s=input.optimizer;pcheck(s,cp.strategy);const d=W.dataset(input.data,input.asof??Date.now());
  demand(d.daily[W.SYMBOLS[0]].at(-1).availableAt>=cp.holdoutStart,'Datos insuficientes para los ocho meses de búsqueda');
  demand(d.daily[W.SYMBOLS[0]][0].t<=cp.start-cp.policy.trainDays*W.DAY-cp.policy.embargoHours*W.HOUR-121*W.DAY,'Falta calentamiento previo');
  return {cp,s,d};
 }
 function pcheck(s,base){demand(s?.schema==='HARPOON-OPTIMIZER-3-1'&&W.stable(s.base)===W.stable(base),'Búsqueda incompatible con el protocolo');policy(s.policy);demand(s.reserved.length<=s.policy.maxTrials&&s.rows.length<=s.reserved.length,'Contabilidad de ensayos inválida');}
 function score(run,baseline,p){const ci=W.blockBootstrap(run.metrics.returns.map((v,i)=>v-baseline.metrics.returns[i]),p.bootstrapSamples);return {searchScore:ci.lower??-1e9,deltaCiDaily:ci};}
 function run(input){
  const started=performance.now(),{cp,s,d}=validateInput(input),baseline=s.baseline||W.simulate(d,'C0',cp.strategy,cp.policy,cp.start,cp.holdoutStart),elapsed=()=>Math.ceil(performance.now()-started);
  if(input.phase==='batch'){
   demand(Array.isArray(input.batch)&&input.batch.length>0&&input.batch.length<=s.policy.batchSize,'Lote inválido');const rows=[];
   for(const plan of input.batch){
    demand(RECIPES.includes(plan.recipe)&&key(plan)===plan.key&&s.reserved.some(x=>x.id===plan.id&&x.key===plan.key)&&!s.rows.some(x=>x.id===plan.id),'Ensayo sin reserva o ya observado');candidate(cp.strategy,plan.strategy);
    if(elapsed()>=input.remainingMs){rows.push({...plan,error:'PRESUPUESTO_AGOTADO',searchScore:null});continue;}
    try{const result=W.simulate(d,plan.recipe,plan.strategy,cp.policy,cp.start,cp.holdoutStart);rows.push({...plan,run:result,...score(result,baseline,cp.policy)});}catch(e){rows.push({...plan,error:String(e.message).slice(0,250),searchScore:null});}
   }
   return {schema:'HARPOON-OPTIMIZER-BATCH-3-1',baseline,rows,elapsedMs:elapsed(),dataReadThrough:cp.holdoutStart,holdoutOpened:false,externalOrders:0,paidModelCalls:0};
  }
  demand(input.phase==='finalize','Etapa de búsqueda desconocida');
  const valid=s.rows.filter(x=>x.run&&!x.error),trialSharpes=[...(input.priorTrialSharpes||[]),...s.rows.map(x=>x.run?(x.run.metrics.sharpe??0)/Math.sqrt(365):0),...Array(Math.max(0,s.reserved.length-s.rows.length)).fill(0)],assessments=valid.map(row=>({...row,gates:W.gates(row.run,baseline,cp.policy,trialSharpes,d.source)})),eligible=assessments.filter(x=>{x.gates.checks.completeSearch=valid.length===s.reserved.length;x.gates.accepted=Object.values(x.gates.checks).every(Boolean);return x.gates.accepted;}).sort((a,b)=>b.run.metrics.netUsd-a.run.metrics.netUsd||a.id.localeCompare(b.id)).slice(0,s.policy.finalists);
  let winner=null,stress=null;
  for(const row of eligible){if(elapsed()>=input.remainingMs)break;const result=W.simulate(d,row.recipe,row.strategy,cp.policy,cp.start,cp.holdoutStart,{costMultiplier:2});row.gates.checks.stress=result.metrics.netUsd>0;row.gates.accepted=Object.values(row.gates.checks).every(Boolean);if(row.gates.accepted){winner=row;stress=result;break;}}
  for(const row of assessments){row.gates.checks.stress??=false;row.gates.accepted=Object.values(row.gates.checks).every(Boolean);}
  const rows=[{...baseline,gates:null}];if(winner)rows.push({...winner.run,gates:winner.gates,stress:stress.metrics});
  const study={schema:'HARPOON-WARROOM-STUDY-3',version:'25.3.0',source:d.source,stage:'train',ordersEnabled:false,promoted:false,externalOrders:0,paidModelCalls:0,window:{start:cp.start,validationEnd:cp.holdoutStart,end:cp.end},basis:'Bounded adaptive parameter search on first eight months only. Historical fills are estimates.',status:winner?'READY_TO_LOCK':'NO_CANDIDATE',selected:winner?.recipe||null,selectedStrategy:winner?.strategy||null,rows,trialSharpes,states:{C0:baseline.state,...(winner?{[winner.recipe]:winner.run.state}:{})},stressStates:winner?{[winner.recipe]:stress.state}:{},models:winner?{[winner.recipe]:winner.run.model}:{},reason:winner?'Parámetros fijados; falta abrir una sola reserva final de tres meses.':'Ninguna candidata supera todas las puertas; se conserva la estrategia vigente.'};
  return {schema:'HARPOON-OPTIMIZER-FINAL-3-1',study,assessments:assessments.map(x=>({id:x.id,gates:x.gates})),elapsedMs:elapsed(),selectedTrial:winner?.id||null,holdoutOpened:false,externalOrders:0,paidModelCalls:0};
 }
 function summary(s){if(!s)return null;const best=s.rows.filter(r=>r.run&&!r.error).sort((a,b)=>b.searchScore-a.searchScore)[0];return {schema:s.schema,version:s.version,status:s.status,policy:clone(s.policy),trialsReserved:s.reserved.length,trialsCompleted:s.rows.filter(x=>x.run).length,batches:s.batches,computeMs:s.computeMs,cacheHits:s.cacheHits,stopReason:s.stopReason,selectedTrial:s.selectedTrial||null,searchThrough:s.searchThrough,holdoutOpened:false,ordersEnabled:false,paidModelCalls:0,best:best?{id:best.id,recipe:best.recipe,strategy:clone(best.strategy),netUsd:best.run.metrics.netUsd,deltaCiDaily:best.deltaCiDaily}:null,rows:s.rows.map(x=>({id:x.id,recipe:x.recipe,strategy:clone(x.strategy),error:x.error||null,searchScore:x.searchScore,netUsd:x.run?.metrics.netUsd??null,sharpeHac:x.run?.metrics.sharpeHac??null,sortino:x.run?.metrics.sortino??null,drawdown:x.run?.metrics.drawdown??null,trades:x.run?.metrics.trades??null,deltaCiDaily:x.deltaCiDaily,gates:x.gates||null}))};}
 return {KEYS,RECIPES,policy,candidate,key,create,propose,run,summary};
});
