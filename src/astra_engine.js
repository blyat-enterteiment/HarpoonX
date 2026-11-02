'use strict';
/** ASTRA adapter: strategy code never submits orders or changes account limits. */
class AstraEngine extends XXEngine {
 constructor(store,onchange){super(store,onchange);this.astraTape=new HAstra.Tape();this.astraBars={};this.astraRefresh=0;this.astraDiagnostics={};this.astraCache={};}
 ensureAstra(){this.ledger.astra6??={schema:1,cases:[],seen:{},closed:0,valid:0,last_error:'',last_capture:0};return this.ledger.astra6;}
 validateX(cfg){super.validateX(cfg);for(const book of ['equity','etf'])if(cfg.xx_books?.[book]){const m=HXX.validate(cfg.xx_books[book]);if(m.book!==book)throw Error('ASTRA: libro incompatible');}}
 onMarketQuote(symbol,q){this.astraTape?.quote(symbol,q);}
 onMarketData(r){if(r.T==='t')this.astraTape?.trade(r,Date.now());}
 onMarketStatus(status){if(status!=='STREAM ACTIVO')this.astraTape?.reset();}
 astraSymbols(){return this.symbols().filter(s=>{const c=this.active().find(c=>c.symbol===s&&c.profile.astra);return c||this.cfg.equities.includes(s)||this.dynamic.includes(s)||localClass(s,this.cfg).book==='etf';}).filter(s=>this.active().some(c=>c.symbol===s&&c.profile.astra)||this.pluginFor(localClass(s,this.cfg).book).family===HAstra.FAMILY);}
 optionTargets(){return this.astraSymbols().filter(s=>this.astraParams(s)?.optionsRequired).slice(0,12);}
 astraParams(symbol){return this.active().find(c=>c.symbol===symbol&&c.profile.astra)?.profile.astra||this.profileFor({book:localClass(symbol,this.cfg).book}).astra;}
 async preparePluginData(symbols,now){
  const state=this.ensureAstra(),targets=this.astraSymbols();this.astraTargets=targets;if(!targets.length)return;
  if(this.cfg.feed!=='sip'||!this.cfg.x.stream){state.last_error='ASTRA necesita SIP y stream activo para validar flujo';return;}
  // Warm historical bars asynchronously; broker protection is never held waiting for the download.
  if(this.astraLoading||now-this.astraRefresh<60000)return;
  this.astraRefresh=now;this.astraLoading=true;
  const scope=this.scope,selected=[...new Set([...this.active().filter(c=>c.profile.astra).map(c=>c.symbol),...targets])].slice(0,12),all=[...new Set([...selected,'SPY',...selected.map(s=>this.sectorProxy(localClass(s,this.cfg).factor)).filter(Boolean)])];
  for(const s of targets.filter(s=>!selected.includes(s)))this.astraDiagnostics[s]='Límite de captura: 12 activos; prioridad a posiciones';
  this.astraTask=(async()=>{try{if(this.astraCalendarDay!==ny(now).day){const rawCalendar=await this.api.request('/v2/calendar?'+new URLSearchParams({start:iso(now-35*86400000).slice(0,10),end:iso(now).slice(0,10)}));this.astraCalendar=HX.sessions(rawCalendar);if(!this.astraCalendar.length)throw Error('ASTRA: calendario histórico ausente');this.astraCalendarDay=ny(now).day;}for(const s of all){if(scope!==this.scope||!this.connected)break;const previous=this.astraBars[s]||[],start=previous.length?now-1200000:now-35*86400000,raw=await this.api.bars([s],'1Min',iso(start),iso(now),this.cfg.feed),received=Date.now(),map=new Map(previous.map(b=>[b.t,b]));for(const b of raw[s]||[]){const t=Date.parse(b.t),n=ny(t);const session=this.astraCalendar.find(s=>s.date===n.day);if(!session||t<session.open||t+60000>session.close||t+60000>received-3000)continue;map.set(t,{t,available:received,day:n.day,minute:n.minute,o:Number(b.o),h:Number(b.h),l:Number(b.l),c:Number(b.c),v:Number(b.v)});}this.astraBars[s]=[...map.values()].filter(b=>b.t>now-35*86400000).sort((a,b)=>a.t-b.t);}
    state.last_capture=Date.now();state.last_error='';
   }catch(error){state.last_error=error.message;this.journal('ASTRA_DATOS_ERROR',{reason:error.message,execution_continues:true});}finally{this.astraLoading=false;}})();
 }
 astraSnapshot(symbol,now=Date.now()){
  const factor=localClass(symbol,this.cfg).factor,proxy=this.sectorProxy(factor),q=this.quotes[symbol],session=this.calendar.find(s=>s.date===ny(now).day);
  if(!q||!session)return null;
  return {symbol,at:now,source:'ALPACA_OBSERVED',feed:this.cfg.feed,sessionOpen:session.open,bars:this.astraBars[symbol]||[],market:this.astraBars.SPY||[],sector:proxy?this.astraBars[proxy]||[]:[],sectorSymbol:proxy,quote:q,flows:this.astraTape.flow(symbol),slippageBps:this.cfg.slippage_bps,options:this.optionEvidence[symbol]||null};
 }
 enrichFeature(row,now){const f=super.enrichFeature(row,now),p=this.astraParams(row.symbol);if(!p)return f;const snapshot=this.astraSnapshot(row.symbol,Date.now());if(!snapshot)return f;const a=HAstra.evaluate(snapshot,p);if(!this.cfg.x.stream)a.reasons.push('ASTRA: stream desactivado');if(this.astraDiagnostics[row.symbol]?.startsWith('Límite'))a.reasons.push(this.astraDiagnostics[row.symbol]);a.ready=a.reasons.length===0;this.astraDiagnostics[row.symbol]=a.reasons.join(' · ')||'SEGUNDA OLA CONFIRMADA';this.astraCache[row.symbol]=a;return {...f,astra:a};}
 decision(row,p,selected){const result=super.decision(row,p,selected);if(!p.astra||!result.ask)return result;const reasons=[...result.reasons];if(!row.astra||!row.astra.ready)if(!reasons.some(x=>x.includes('ASTRA')))reasons.push('ASTRA: condiciones incompletas');return {...result,reasons,state:reasons[0]||'LISTA',reason:reasons.join(' · ')};}
 async manage(){for(const c of this.active().filter(c=>c.profile.astra)){const snapshot=this.astraSnapshot(c.symbol);if(snapshot)c.astraLatest=HAstra.evaluate(snapshot,c.profile.astra);}await super.manage();}
 async submit(payload,c){if(c.profile?.astra&&payload.side==='buy'){
   if(this.cfg.mode!=='paper')throw Error('ASTRA: LIVE no validado');
   const q=this.quotes[c.symbol],a=c.feature.astra;if(!HAstra.validQuote(q,Date.now())||HAstra.entryReasons({...q,astra:a},Date.now(),c.profile.astra).length){c.closing='ASTRA: señal vencida durante envío';throw Error(c.closing);}
  }return super.submit(payload,c);}
 async observeX(rows,selected){await super.observeX(rows,selected);const state=this.ensureAstra(),now=Date.now();
  for(const study of state.cases.filter(c=>!c.done)){const q=this.quotes[study.symbol];if(!HAstra.validQuote(q,now))continue;this.stepAstraStudy(study,q,now);}
  for(const row of this.matrix){if(!row.astra?.ready||row.quantity<this.cfg.min_plan_qty||row.state!=='LISTA'||state.seen[row.astra.impulseId]||state.cases.some(c=>!c.done&&c.symbol===row.symbol)||state.cases.filter(c=>!c.done).length>=12)continue;
   const p=this.profileFor(row);if(!p.astra)continue;const baseline={...this.cfg.profile};delete baseline.astra;
   const study={id:crypto.randomUUID(),symbol:row.symbol,at:now,last:now,deadline:row.deadline,signal:structuredClone(row.astra),plugin:this.campaignPlugin(row,p),qty:row.quantity,levels:{limit:row.limit,stop:row.stop,risk_unit:row.risk_unit,tp1:row.tp1,tp2:row.tp2},source:'OBSERVED_QUOTES_SIMULATED_FILLS',valid:true,done:false,variants:[]};
   for(const [name,profile,parts]of [['ASTRA parcial',p,HX.parts(row.quantity,p)],['ASTRA sin parcial',{...p,astra:{...p.astra,partialFraction:0}},[0,0,row.quantity]],['Salidas canónicas, mismas entradas',baseline,HX.parts(row.quantity,baseline)],['Objetivo fijo 2R',{...p,astra:{...p.astra,partialFraction:0}},[row.quantity,0,0]]])study.variants.push({name,profile:structuredClone(profile),parts,left:row.quantity,filled:false,done:false,proceeds:0,entry:row.limit,peak:row.limit,peakAt:now,virtual_stop:row.stop,risk_unit:row.risk_unit,atr:row.astra.metrics.atr,exit_cost_bps:this.cfg.slippage_bps,tp1_filled:false,tp2_filled:false,stagnationMs:0,closing:'',fillAt:null,net:null});
   state.seen[row.astra.impulseId]=now;state.cases.push(study);this.journal('ASTRA_COMPARACIÓN_ABIERTA',{id:study.id,symbol:row.symbol,signal:row.astra,simulated_fills:true,orders_sent:0});
  }
  for(const [k,v]of Object.entries(state.seen))if(now-v>4*86400000)delete state.seen[k];
  for(const study of state.cases.filter(c=>c.done&&!c.archived)){study.archived=true;state.closed++;if(study.valid)state.valid++;this.buffers.push(['astra-study-'+this.scope+'-'+study.id,structuredClone(study)]);}
  state.cases=state.cases.filter(c=>!c.done).concat(state.cases.filter(c=>c.done).slice(-100));
 }
 stepAstraStudy(study,q,now){
  if(now<=study.last)return;const gap=HX.tradingMillis(study.last,now,this.calendar);if(gap>60000)study.valid=false;study.last=now;const snapshot=this.astraSnapshot(study.symbol,now),signal=snapshot?HAstra.evaluate(snapshot,study.plugin.resolved.astra):null;
  for(const v of study.variants){if(v.done)continue;if(!v.filled){if(now-study.at>30000||now>=study.deadline){v.done=true;v.net=0;v.reason='SIN FILL';continue;}if(q.ask>study.levels.limit)continue;v.filled=true;v.fillAt=now;v.paid=study.qty*study.levels.limit*(1+v.exit_cost_bps/10000);continue;}
   v.stagnationMs+=gap;if(q.bid>v.peak){v.peakAt=now;v.stagnationMs=0;}
   if(q.bid<=v.virtual_stop)v.closing='PROTECCIÓN';
   if(now>=study.deadline)v.closing='PLAZO';
   const fixed=v.name==='Objetivo fijo 2R',cost=1-v.exit_cost_bps/10000;
   if(!v.closing){for(const first of [true,false]){if(!v.parts[first?0:1])continue;const target=Math.ceil((v.entry+(first?(fixed?2:v.profile.tp1_r):v.profile.tp2_r)*v.risk_unit)/cost*100)/100,key=first?'tp1_filled':'tp2_filled';if(!v[key]&&q.bid>=target+.01){const n=Math.min(v.left,v.parts[first?0:1]);v.proceeds+=n*target*cost;v.left-=n;v[key]=true;}}
    if(!fixed){v.astraLatest=signal;HPSecurities.markExit(v,q.bid,now,v.exit_cost_bps);}
   }
   if(v.closing||v.left===0){v.proceeds+=v.left*q.bid*cost;v.left=0;v.done=true;v.net=v.proceeds-v.paid;v.reason=v.closing||'OBJETIVOS';v.exitAt=now;}
  }
  study.done=study.variants.every(v=>v.done);if(study.done)study.closedAt=now;
 }
 async mature(){await super.mature();const state=this.ensureAstra();for(const study of state.cases.filter(c=>!c.done&&Date.now()>c.deadline+60000)){study.done=true;study.valid=false;study.closedAt=Date.now();for(const v of study.variants.filter(v=>!v.done)){v.done=true;v.net=null;v.reason='OBSERVACIÓN INCOMPLETA';}}}
 async changeSettings(cfg){if(this.ensureAstra().cases.some(c=>!c.done)&&HLab.stable(cfg)!==HLab.stable(this.cfg))throw Error('ASTRA: espera a que maduren las comparaciones de salidas');await super.changeSettings(cfg);this.astraRefresh=0;this.astraDiagnostics={};}
 async exportAstra(){await this.save();const archived=await this.store.scan('astra-study-'+this.scope+'-',50000),cases=[...new Map([...archived,...this.ensureAstra().cases].map(c=>[c.id,c])).values()];return {schema:'HARPOON-ASTRA6-EVIDENCE-1',created:iso(Date.now()),plugin_version:HAstra.VERSION,mode:this.cfg.mode,source:'OBSERVED_QUOTES_SIMULATED_FILLS',cases,diagnostics:this.astraDiagnostics,profitability_verified:false,limits:'Mismas entradas y riesgo por cohorte. Simulación conservadora sin posición de cola ni impacto; no constituye validación independiente o walk-forward. Sin promoción automática.'};}
 async exportEvidence(){return {...await super.exportEvidence(),astra6:await this.exportAstra()};}
}
