'use strict';
/** Single, bounded research scheduler. Position management never awaits this queue. */
class Loop23 {
 constructor(store,adapters,onchange=()=>{}){this.store=store;this.adapters=adapters;this.onchange=onchange;this.state=null;this.busy=false;this.next=0;this.epoch=0;this.timer=null;this.loading=null;}
 async load(){if(this.state)return;if(this.loading)return this.loading;this.loading=(async()=>{const saved=await this.store.get('framework23-loop');this.state=saved||{schema:'HARPOON-XXIII-LOOP-1',policy:{...HF23.defaults},revision:0,iterations:0,records:[],cost_usd:0,candidates:[],seen:[],status:'LiftOff · sin investigaciones automáticas',last_at:0};this.state.policy=HF23.policy(this.state.policy);this.epoch=this.state.revision;})();try{await this.loading;}finally{this.loading=null;}}
 async stateLock(fn){if(typeof navigator!=='undefined'&&navigator.locks)return navigator.locks.request('harpoon-xxiii-state',{mode:'exclusive'},fn);return fn();}
 mergeDisk(disk){if(!disk)return;if(disk.revision>this.state.revision){this.state.policy=disk.policy;this.state.revision=disk.revision;this.epoch=disk.revision;}this.state.iterations=Math.max(this.state.iterations,disk.iterations);this.state.cost_usd=Math.max(this.state.cost_usd||0,disk.cost_usd||0);this.state.seen=[...new Set([...(disk.seen||[]),...this.state.seen])];this.state.records=[...new Map([...(disk.records||[]),...this.state.records].map(r=>[r.id,r])).values()].sort((a,b)=>a.at.localeCompare(b.at)).slice(-120);const candidates=new Map((disk.candidates||[]).map(r=>[r.id,r]));for(const r of this.state.candidates){const old=candidates.get(r.id);if(!old||(r.evaluations||0)>=(old.evaluations||0))candidates.set(r.id,r);}this.state.candidates=[...candidates.values()];}
 async refreshPolicy(){await this.load();const disk=await this.store.get('framework23-loop');this.mergeDisk(disk);return this.state.policy;}
 async save(){await this.stateLock(async()=>{this.mergeDisk(await this.store.get('framework23-loop'));await this.store.put('framework23-loop',structuredClone(this.state));});this.onchange();}
 permits(kind){return Boolean(this.state?.policy[kind==='hot'?'hot_on':'cold_on']);}
 async configure(policy){await this.load();policy=HF23.policy(policy);await this.stateLock(async()=>{this.mergeDisk(await this.store.get('framework23-loop'));if(policy.max_iterations<this.state.iterations)throw Error('El límite no puede borrar iteraciones consumidas.');this.state.policy=policy;this.state.revision++;this.epoch=this.state.revision;this.next=0;this.state.status=policy.cold_on||policy.hot_on?'Política guardada; esperando ventana y evidencia':'LiftOff · salidas vigentes independientes';await this.store.put('framework23-loop',structuredClone(this.state));});this.onchange();await this.adapters.configure?.(policy);}
 async record(item){const r={id:crypto.randomUUID(),at:new Date().toISOString(),...item};await this.store.put('framework23-event-'+r.id,r);if(r.kind==='STUDY'&&Number.isFinite(r.cost_usd))this.state.cost_usd=(this.state.cost_usd||0)+r.cost_usd;this.state.records.push(r);this.state.records=this.state.records.slice(-120);await this.save();return r;}
 async register(manifest,params,scope='exits'){
  await this.load();if(this.busy)throw Error('Espera al cierre del estudio antes de registrar otra hipótesis.');
  const changed=HF23.patch(manifest.book,manifest.family,manifest.params,params,scope),baseline=await HF23.digest(manifest),fingerprint=await HF23.digest({book:manifest.book,family:manifest.family,params:changed});
  if(HF23.stable(changed)===HF23.stable(manifest.params))throw Error('No hay cambio de parámetros.');if(this.state.candidates.some(c=>c.fingerprint===fingerprint))throw Error('Esta configuración ya fue registrada; no se repite el estudio.');
  if(this.state.candidates.length>=200)throw Error('Límite de 200 hipótesis; exporta el registro antes de ampliar el protocolo.');
  const parts=manifest.version.split('.').map(Number);parts[2]++;
  const m={...manifest,id:(manifest.id.slice(0,45)+'-r'+fingerprint.slice(0,12)),version:parts.join('.'),name:(manifest.name.slice(0,65)+' · ensayo '+fingerprint.slice(0,6)),params:changed};
  const validated=await this.adapters.validatePlugin(m),changes=Object.keys(params).filter(k=>HF23.stable(params[k])!==HF23.stable(manifest.params[k])).map(k=>({field:k,before:manifest.params[k],after:params[k]}));
  const c={id:crypto.randomUUID(),registered_at:new Date().toISOString(),baseline_hash:baseline,baseline:structuredClone(manifest),fingerprint,manifest:validated,changes,scope,status:'REGISTRADA',reason:'Hipótesis congelada; todavía no demuestra mejora.',evaluations:0,orders_enabled:false};
  this.state.candidates.push(c);await this.store.put('framework23-candidate-'+c.id,c);await this.record({kind:'PARAMETER_PROPOSAL',book:m.book,candidate_id:c.id,changes,reason:c.reason,cost_usd:0});return c;
 }
 async once(manual=false){await this.load();if(this.busy)return false;if(!manual&&!this.permits('cold'))return false;if(this.state.iterations>=this.state.policy.max_iterations){this.state.status='Límite de iteraciones alcanzado';await this.save();return false;}
  const execute=async()=>{if(this.busy)return false;this.busy=true;const revision=this.epoch,started=performance.now();
   try{const task=await this.adapters.next(this.state);if(!task){this.state.status='ESPERANDO EVIDENCIA · sin consultas GPT';await this.save();return false;}
    if(this.state.seen.includes(task.key)){this.state.status='SIN CAMBIOS · estudio ya registrado';await this.save();return false;}
    // Reserve study BEFORE launching a worker/API. Failed attempts remain counted.
    if(task.counts_iteration!==false)this.state.iterations++;this.state.seen.push(task.key);this.state.status='EVALUANDO · '+task.label;await this.save();
    const result=await task.run();await this.refreshPolicy();const cancelled=revision!==this.epoch;
    await this.record({kind:'STUDY',book:task.book,task_key:task.key,label:task.label,compute_ms:performance.now()-started,cost_usd:result.cost_usd??0,revision,late:cancelled,result,reason:cancelled?'Política modificada durante el estudio: resultado conservado, aplicación bloqueada.':result.reason||'Evaluación registrada',changes_orders:false});
    this.state.status=cancelled?'Resultado tardío archivado; no aplicado':result.status||'ESTUDIO TERMINADO';
    return true;
   }catch(error){this.state.status='ESTUDIO BLOQUEADO · '+error.message;await this.record({kind:'ERROR',reason:error.message,compute_ms:performance.now()-started,cost_usd:null,changes_orders:false});return false;}
   finally{this.busy=false;this.next=Date.now()+this.state.policy.interval_seconds*1000;this.state.last_at=Date.now();await this.save();}
  };
  // One research owner in this browser origin; native account locks still own execution.
  if(typeof navigator!=='undefined'&&navigator.locks)return navigator.locks.request('harpoon-xxiii-research',{mode:'exclusive',ifAvailable:true},async lock=>{if(!lock){this.state.status='Otra pestaña posee la investigación';this.onchange();return false;}const disk=await this.store.get('framework23-loop');if(disk){this.state=disk;this.epoch=disk.revision;}if(!manual&&!this.permits('cold'))return false;return execute();});
  return execute();
 }
 async pulse(){try{await this.load();if(Date.now()>=this.next&&this.permits('cold'))await this.once();}finally{this.timer=setTimeout(()=>this.pulse(),5000);}}
 export(){return {version:'23.0.0',...structuredClone(this.state),credentials_included:false,profitability_verified:false};}
}

/** Observe actual successful cycles, not just scheduled attempts. */
function installPulse23(Type,cryptoBook=false){
 const tick=Type.prototype.tick,sync=Type.prototype.sync,market=Type.prototype[cryptoBook?'market':'data'];
 Type.prototype.sync=async function(...args){this.pulse23??=HF23.emptyPulse();try{const value=await sync.apply(this,args);if(this.reconciled)this.pulse23.sync_at=Date.now();return value;}catch(error){this.pulse23.error=error.message;throw error;}};
 if(market)Type.prototype[cryptoBook?'market':'data']=async function(...args){this.pulse23??=HF23.emptyPulse();try{const value=await market.apply(this,args);const times=Object.values(this.quotes||{}).map(q=>q.at??q.t).filter(Number.isFinite);if(times.length)this.pulse23.market_at=Math.max(...times);return value;}catch(error){this.pulse23.error=error.message;throw error;}};
 const handle=Type.prototype.handleError;if(handle)Type.prototype.handleError=function(error){this.pulse23??=HF23.emptyPulse();this.pulse23.error=error.message;return handle.call(this,error);};
 Type.prototype.tick=async function(...args){if(this.busy||!this.connected)return;const p=this.pulse23??=HF23.emptyPulse();p.attempt_at=Date.now();p.error='';p.busy=true;const started=performance.now();try{await tick.apply(this,args);if(!p.error&&this.reconciled&&p.sync_at>=p.attempt_at){p.completed_at=Date.now();p.failures=0;}else p.failures++;}catch(error){p.error=error.message;p.failures++;throw error;}finally{p.busy=false;p.duration_ms=performance.now()-started;}};
}
if(typeof AstraEngine!=='undefined')installPulse23(AstraEngine);if(typeof XXCryptoDesk!=='undefined')installPulse23(XXCryptoDesk,true);

/** Attributable observed portfolio; deposits outside owned campaigns cannot masquerade as profit. */
function quantSummary23(e){
 if(!e.connected||typeof e.dailyEvidence!=='function')return {available:false,reason:'Conecta y reúne sesiones completas de una política.'};
 const evidence=e.dailyEvidence(),rows=evidence.rows||[];if(rows.length<2)return {available:false,reason:'Faltan al menos dos sesiones completas y consecutivas con NAV observado. Los ratios requieren 30.',observations:rows.length};
 const market=rows.map(r=>e.ledger.sessions[r.day]?.market_return),benchmark=market.every(Number.isFinite)?market:undefined;
 const campaignRows=e.ledger.campaigns.filter(c=>c.closed&&c.closed_at&&Number.isFinite(c.netConservative)&&ny(c.closed_at).day>=rows[0].day&&ny(c.closed_at).day<=rows.at(-1).day);
 const series={source:e.cfg.mode.toUpperCase(),label:'Cartera atribuible · acciones + ETF',dates:rows.map(r=>r.day),returns:rows.map(r=>r.equity+r.etf),benchmark,annualization:252,capital:rows[0].capital,risk_hash:HF23.stable({risk:e.cfg.risk_pct,policy:evidence.policy_id}),cost_basis:'Fills confirmados y NAV a bid con provisión de ejecución; facturas externas sin asignar a este período',external_costs_usd:0,costs_confirmed:false,rf_annual:0,mar_annual:0,trades:campaignRows.map(c=>({net:c.netConservative,hours:(Date.parse(c.closed_at)-c.created)/3600000})),policy_hash:evidence.policy_id,basis:evidence.basis,boundary:'continuous'};
 const s=HM23.summarize(series);return {available:true,source:s.source,from:s.from,through:s.through,observations:s.n,metrics:Object.fromEntries(Object.entries(s.metrics).map(([k,v])=>[k,v.value])),basis:series.cost_basis,alpha_ci95:s.alpha_ci95,warnings:s.warnings};
}
