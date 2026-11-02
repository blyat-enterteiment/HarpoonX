'use strict';
/* The only bridge from agents to the original Alpaca executor. */
function installAgentDesk25(Type){
 const priorSync=Type.prototype.sync,priorManage=Type.prototype.manage,priorEntries=Type.prototype.entries,
  priorSend=Type.prototype.send,priorResume=Type.prototype.resume;
 Type.prototype.ensureAgents25=async function(){if(!this.scope)throw Error('Conecta una cuenta antes de iniciar agentes');if(!this.agents25){this.agents25=new HAgents25.Desk(this.store);await this.agents25.load(this.scope);}return this.agents25;};
 Type.prototype.agentSnapshot25=function(){const now=Date.now(),campaigns=(this.state?.campaigns||[]).map(c=>{const ins=this.intents(c),filled=ins.some(i=>Number(i.order?.filled_qty)>0);return {id:c.id,leadId:c.agentLead25||null,closed:c.closed===true,filled,unknown:ins.some(i=>i.unknown)};}),positions=this.active().map(c=>{const ins=this.intents(c),q=this.quotes[c.symbol],protection=ins.find(i=>!i.final&&i.payload.side==='sell'&&i.payload.type==='stop_limit'&&i.order?.id);return {id:c.id,symbol:c.symbol,qty:Number(this.position(c.symbol)?.qty||0),stop:c.stop,target:c.target||null,deadline:c.deadline||(c.config.hold_hours?c.opened+c.config.hold_hours*3600000:null),protected:!!protection,stale:!q||!HAgents25.fresh(q.t,now,15000),pendingExit:c.closing||null};});return {at:now,mode:this.mode,equity:Number(this.account.equity),campaigns,positions,closedTrades:(this.state?.campaigns||[]).filter(c=>c.closed&&Number.isFinite(c.net_estimate)&&this.intents(c).some(i=>Number(i.order?.filled_qty)>0)).map(c=>({id:c.id,symbol:c.symbol,net:c.net_estimate})),closedNet:(this.state?.campaigns||[]).filter(c=>c.closed&&this.intents(c).some(i=>Number(i.order?.filled_qty)>0)).reduce((n,c)=>n+Number(c.net_estimate||0),0),watch:{locked:!!this.locked,reconciled:!!this.reconciled,unknown:(this.state?.intents||[]).filter(i=>i.unknown).length,pulse:this.pulse23?.sync_at||this.lastTick,now},sources:[{name:'Alpaca catalog',at:this.catalogAt25||null},{name:'Alpaca quotes',at:Math.min(...Object.values(this.quotes).map(q=>q.t))||null}],flows:this.agentFlows25||null};};
 Type.prototype.sync=async function(...args){const value=await priorSync.apply(this,args);const desk=await this.ensureAgents25();await desk.observe(this.agentSnapshot25());if(desk.state.risk.halted){this.armed=false;this.halt='AGENTS · '+desk.state.risk.reason;}return value;};
 Type.prototype.manage=async function(...args){
  // Agents can request monitoring but cannot delay or replace native exits.
  const value=await priorManage.apply(this,args);
  if(this.agents25){this.agents25.schedule(this.agentSnapshot25()).catch(e=>{this.agents25.state.lastError=String(e.message).slice(0,240);});}
  return value;
 };
 Type.prototype.candidate25=function(candidate){const now=Date.now(),s=candidate.symbol,q=candidate.quote||this.quotes[s],cfg=candidate.config||this.cfg,
   asset=this.catalog25.find(a=>a.symbol===s),eq=Number(this.account.equity),net=(this.state.campaigns||[]).filter(c=>c.closed).reduce((n,c)=>n+Number(c.net_estimate||0),0),
   budget=Math.max(0,Math.min(eq,this.cfg.capital_limit,this.agents25.state.policy.compoundRealizedOnly?this.state.anchor+net:eq)),
   cash=Math.min(Number(this.account.cash),Number(this.account.non_marginable_buying_power??this.account.cash)),priceStep=Number(asset?.price_increment),qtyStep=Number(asset?.min_trade_increment),
   limit=q&&priceStep>0?Math.ceil(q.ask*(1+this.cfg.slippage_bps/10000)/priceStep)*priceStep:0,
   stop=candidate.proposal?.stop??limit-cfg.atr_multiple*candidate.sig?.atr,used=this.active().reduce((n,c)=>n+Number(this.position(c.symbol)?.market_value||0),0),
   qty=limit>0&&qtyStep>0&&stop>0?Math.min(HC19.quantity(budget,cash,used,limit,(limit-stop)/cfg.atr_multiple,cfg,qtyStep),candidate.depthCap?HC19.floorQty(candidate.depthCap/limit,qtyStep):Infinity):0,
   plugin=candidate.plugin?.manifest||this.plugins.find(p=>p.id===candidate.plugin?.id)||this.plugins.find(p=>p.family==='trend_xix'),
   validPlugin=!!plugin&&this.plugins.some(p=>p.id===plugin.id&&p.version===plugin.version),recovery=plugin?.family==='shock_recovery',snapshot=recovery?this.tape?.snapshot(s,now):null;
  return {key:s+':'+(candidate.seenKey||plugin?.id||'native')+':'+candidate.sig?.available_at,symbol:s,pluginId:plugin?.id||'native',mode:this.mode,
   identity:{symbol:s,plugin:plugin||null,signalAt:candidate.sig?.available_at,policy:this.cfg,ttl:candidate.ttl,capitalLimit:this.cfg.capital_limit},
   quote:q||{ask:0,bid:0},plan:{symbol:s,side:'buy',type:'limit',time_in_force:'ioc',qty:Number.isFinite(qty)?qty:0,limit,stop,holdHours:cfg.hold_hours,target:candidate.proposal?.target??null,maxFeeBps:this.cfg.fee_bps,slippageBps:this.cfg.slippage_bps,budget},
   search:{catalogFresh:HAgents25.fresh(this.catalogAt25,now,60000),asset,allowed:HC19.SYMBOLS.includes(s),pluginAllowed:validPlugin,symbol:s},
   risk:{connected:!!this.connected,locked:!!this.locked,reconciled:!!this.reconciled,halted:this.agents25.state.risk.halted,accountValid:this.account.status==='ACTIVE'&&!this.account.trading_blocked&&!this.account.account_blocked&&!this.account.trade_suspended_by_user,ambiguous:this.state.intents.some(i=>i.unknown),active:this.active().some(c=>c.symbol===s),policyValid:Number.isFinite(cfg.risk_fraction)&&cfg.risk_fraction>0&&cfg.risk_fraction<=this.cfg.risk_fraction&&cfg.total_cap<=this.cfg.total_cap&&cfg.asset_cap<=this.cfg.asset_cap,budget,cash,stopDistance:limit-stop,riskFraction:cfg.risk_fraction,assetCap:cfg.asset_cap},
   flow:{quote:q,now,maxSpread:this.cfg.max_spread_bps,depthRequired:recovery,depth:snapshot?.depth},
   signal:{enter:candidate.sig?.enter===true,signalAt:candidate.sig?.available_at,now,ttl:candidate.ttl||3600000,validPlugin,recoveryAllowed:!recovery||this.mode==='paper',pluginId:plugin?.id||'native'}};
 };
 Type.prototype.refreshAgentFlows25=async function(){if(!this.agents25||this.agentFlowBusy25||Date.now()-(this.lastAgentFlows25||0)<300000)return;this.agentFlowBusy25=true;this.lastAgentFlows25=Date.now();try{const r=this.agents25.state.risk,rows=await this.api.activities(new Date(r.startAt||Date.now()).toISOString(),new Date().toISOString());let net=0,complete=true;for(const row of rows){if(['CSD','CSW','ACATC','JNLC'].includes(row.activity_type)){const value=Number(row.net_amount);if(!Number.isFinite(value))complete=false;else net+=value;}else if(['ACATS','FOPT','JNL','JNLS','TRANS'].includes(row.activity_type))complete=false;}this.agentFlows25={day:r.day,after:r.startAt,through:Date.now(),netUsd:net,complete,basis:'Actividades publicadas por Alpaca; posibles cargos o movimientos tardíos. No certifica contabilidad.'};}catch(e){this.agentFlows25={day:this.agents25.state.risk.day,complete:false,reason:'Actividades no conciliadas'};}finally{this.agentFlowBusy25=false;}};
 Type.prototype.scanAgents25=async function(){if(!this.connected||this.busy||!this.reconciled||!this.locked||this.agentScanBusy25)return;const desk=await this.ensureAgents25();if(!desk.state.policy.enabled||Date.now()-(this.lastAgentScan25||0)<desk.state.policy.intervalSeconds*1000)return;this.lastAgentScan25=Date.now();this.agentScanBusy25=true;this.busy=true;try{if(!HAgents25.fresh(this.catalogAt25,Date.now(),60000))await this.refreshAssets25();for(const candidate of this.entryCandidates())await desk.process(this.candidate25(candidate));}catch(e){desk.state.lastError='Búsqueda: '+e.message;await desk.persist();}finally{this.agentScanBusy25=false;this.busy=false;}};
 Type.prototype.entries=async function(...args){if(!this.armed||!this.reconciled||!this.locked)return;const desk=await this.ensureAgents25();if(!desk.state.policy.enabled||desk.state.risk.halted)return;
  if(!HAgents25.fresh(this.catalogAt25,Date.now(),60000))try{await this.refreshAssets25();}catch(e){desk.state.lastError='Catálogo no disponible: '+e.message;await desk.persist();return;}
  const native=this.entryCandidates,hadOwn=Object.hasOwn(this,'entryCandidates'),allowed=[];
  for(const candidate of native.call(this)){const lead=await desk.process(this.candidate25(candidate));if(lead?.stage==='APPROVED')allowed.push({...candidate,agentLead25:lead.id});}
  if(!allowed.length)return;
  // Freeze a per-cycle list. Core still rechecks quote, size, account and campaign inventory.
  this.entryCandidates=()=>allowed;this.permits25=new Map(allowed.map(c=>[c.symbol,c.agentLead25]));
  try{return await priorEntries.apply(this,args);}finally{if(hadOwn)this.entryCandidates=native;else delete this.entryCandidates;this.permits25=null;}
 };
 Type.prototype.send=async function(payload,c){if(payload.side!=='buy')return priorSend.call(this,payload,c);
  const desk=await this.ensureAgents25(),id=this.permits25?.get(payload.symbol);if(!id)throw Error('Compra sin embudo agéntico');
  const lead=desk.state.leads.find(l=>l.id===id);if(!lead)throw Error('Oportunidad no disponible');
  // Preserve the core's smaller sizing; cap any larger size to the approved plan.
  const qty=Math.min(Number(payload.qty),lead.plan.qty);payload={...payload,qty:String(HC19.floorQty(qty,Number(this.assets[payload.symbol].min_trade_increment)))};
  c.stop=Math.max(c.stop,lead.plan.stop);if(c.stop>=Number(payload.limit_price))throw Error('Stop aprobado ya invalidado');c.agentLead25=id;await desk.consume(id,payload,c.id);await this.save();
  try{const intent=await priorSend.call(this,payload,c);await desk.outcome(id,Number(intent.order?.filled_qty)>0?'EXECUTED':this.terminal(intent.order)?'ATTEMPTED':'SUBMITTING',intent.order);return intent;}
  catch(e){await desk.outcome(id,'UNKNOWN',null);throw e;}
 };
 Type.prototype.resume=async function(...args){const desk=await this.ensureAgents25();if(desk.state.risk.halted)throw Error('Restablece el corte del desk antes de reanudar. '+desk.state.risk.reason);return priorResume.apply(this,args);};
}
if(typeof XXCryptoDesk!=='undefined')installAgentDesk25(XXCryptoDesk);
