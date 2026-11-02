'use strict';
class XIIIEngine extends XIIEngine {
 constructor(store,onchange){super(store,onchange);this.ensureXIII();}
 ensureXIII(){this.ensureXII();this.cfg.xiii??={allocation_enabled:true};this.ledger.xiii??={schema:1,epoch:null,archives:[],allocation:{equity:.5,etf:.5,through:'',history:[],reasons:{}},analysis:null};}
 validateX(c){super.validateX(c);if(c.xiii&&(Object.keys(c.xiii).length!==1||typeof c.xiii.allocation_enabled!=='boolean'))throw Error('Configuración XIII inválida');}
 async init(){await super.init();this.ensureXIII();}
 async afterLoad(){await super.afterLoad();this.ensureXIII();const d=this.ledger.labDeployment;if(d?.active&&d.xiii_schema!==HXIII.POLICY){d.active=false;this.journal('XIII_VALIDACIÓN',{reason:'Las recetas anteriores requieren validación XIII; se conservan salidas de campañas abiertas.'});}this.ledger.settings=structuredClone(this.cfg);await this.save();}
 evidenceFingerprint(){return HLab.stable({experiment:this.ledger.x.experiment,profile:this.profile(),mode:this.cfg.mode,feed:this.cfg.feed,policy:HXIII.POLICY});}
 ensureEpoch(now=Date.now()){
  this.ensureXIII();const x=this.ledger.xiii,fingerprint=this.evidenceFingerprint();
  if(x.epoch?.fingerprint===fingerprint)return x.epoch;
  if(x.epoch){x.archives.push({id:x.epoch.id,started_at:x.epoch.started_at,through:Object.keys(x.epoch.marks).sort().at(-1),analysis:x.analysis});x.archives=x.archives.slice(-12);}
  x.epoch={id:crypto.randomUUID(),fingerprint,started_at:now,capital:this.ledger.budget||this.cfg.starting_budget,marks:{},calendar:[]};x.analysis=null;x.allocation={equity:.5,etf:.5,through:'',history:[],reasons:{equity:'RECOPILANDO',etf:'RECOPILANDO'}};return x.epoch;
 }
 dailyEvidence(now=Date.now()){this.ensureXIII();return xiiiDaily(this.ledger.xiii.epoch,this.cfg.mode.toUpperCase(),this.cfg.xi.external_costs_confirmed,now);}
 markXIII(){
  if(!this.connected||!this.reconciled)return;const now=Date.now(),epoch=this.ensureEpoch(now),day=ny(now).day,session=this.calendar.find(s=>s.date===day);if(!session||now<session.open||now>session.close)return;
  epoch.calendar=[...new Map([...epoch.calendar,...this.calendar].map(s=>[s.date,s])).values()].filter(s=>s.close>=epoch.started_at-86400000);
  const pnl={equity:0,etf:0},closed={equity:0,etf:0};
  for(const c of this.ledger.campaigns){if(!Object.hasOwn(pnl,c.book))return;
   const orders=flattenOrders(this.campaignIntents(c).filter(i=>i.order).map(i=>i.order)),buys=orders.filter(o=>o.side==='buy'),sells=orders.filter(o=>o.side==='sell'),amount=a=>sum(a.map(o=>Number(o.filled_qty||0)*Number(o.filled_avg_price||0))),bq=sum(buys.map(o=>Number(o.filled_qty||0))),sq=sum(sells.map(o=>Number(o.filled_qty||0))),qty=bq-sq;
   if(qty<-.000001||qty>0&&!fresh(this.quotes[c.symbol]))return;
   const value=qty>0?qty*this.quotes[c.symbol].bid:0,paid=amount(buys),sold=amount(sells);
   if(![value,paid,sold].every(Number.isFinite))return;
   pnl[c.book]+=sold-paid+value-(paid+sold+value)*(c.exit_cost_bps??this.cfg.slippage_bps)/10000;if(c.closed&&bq>0)closed[c.book]++;
  }
  epoch.anchor??={...pnl};const net=pnl.equity+pnl.etf-epoch.anchor.equity-epoch.anchor.etf,mark=epoch.marks[day]||{first:now,last:now,gap:0};
  mark.gap=Math.max(mark.gap,now-mark.last);mark.last=now;mark.pnl=pnl;mark.closed=closed;mark.nav=epoch.capital+net;mark.valid=Number.isFinite(mark.nav)&&mark.nav>0;mark.scales={equity:this.ledger.xiii.allocation.equity,etf:this.ledger.xiii.allocation.etf};epoch.marks[day]=mark;
 }
 async refreshXIII(){
  if(!this.connected)throw Error('Conecta para revisar evidencia de esta cuenta');this.ensureEpoch();const e=this.dailyEvidence(),x=this.ledger.xiii;x.analysis=HXIII.analyze(e);await this.updateAllocation();await this.save();this.emit();return x.analysis;
 }
 async updateAllocation(){
  this.ensureXIII();const x=this.ledger.xiii,e=this.dailyEvidence(),latest=e.through,day=ny(Date.now()).day;
  if(x.allocation.review_day===day&&x.allocation.through===latest)return;
  const lastSession=(x.epoch?.calendar||[]).find(s=>s.date===latest),freshEvidence=Boolean(lastSession&&Date.now()-lastSession.close<=7*86400000),economic=this.ledger.xi.economics;
  const usable={...e,costs_confirmed:e.costs_confirmed&&economic.complete===true&&economic.net_economic>0},current=x.allocation;
  const result=HXIII.allocate(usable,current,!this.active().length&&this.reconciled,freshEvidence);
  const changed=result.scales.equity!==current.equity||result.scales.etf!==current.etf;
  Object.assign(current,result.scales,{through:latest,review_day:day,reasons:result.reasons});x.analysis=result.analysis;
  if(changed){const event={at:iso(Date.now()),through:latest,scales:result.scales,reasons:result.reasons,mode:this.cfg.mode};current.history.push(event);current.history=current.history.slice(-250);this.journal('ASIGNACIÓN_XIII',event);}
 }
 decision(row,p,selected){
  this.ensureXIII();const r=super.decision(row,p,selected);if(!r.ask||!this.cfg.xiii.allocation_enabled)return r;
  const multiplier=this.ledger.xiii.allocation[r.book]??.25,stage=this.scale(),effective=Math.min(stage,multiplier),budget=this.ledger.budget,active=this.active(),book=active.filter(c=>c.book===r.book),bookNominal=sum(book.map(c=>c.allocated)),bookRisk=sum(book.map(c=>c.risk_budget)),history=this.ledger.campaigns.filter(c=>c.symbol===r.symbol&&c.day===ny(Date.now()).day),unit=r.risk_unit+2*r.limit*this.cfg.slippage_bps/10000;
  const bookCap=budget*effective*(r.book==='etf'?this.cfg.etf_book_pct:this.cfg.equity_book_pct),campaignRisk=budget*this.cfg.risk_pct*effective-sum(history.map(c=>c.riskSpent||0)),bookRiskRoom=budget*this.cfg.open_risk_pct*effective-bookRisk;
  const quantity=Math.max(0,Math.min(r.quantity,Math.floor((bookCap-bookNominal)/r.limit),Math.floor(campaignRisk/unit),Math.floor(bookRiskRoom/unit))),reasons=[...r.reasons];
  if(quantity<this.cfg.min_plan_qty)reasons.push('ASIGNACIÓN XIII / TAMAÑO');return {...r,quantity,evidence_scale:multiplier,reasons,reason:reasons.join(' · '),state:reasons[0]||'LISTA'};
 }
 async beforeEntries(){await super.beforeEntries();this.markXIII();await this.updateAllocation();}
 async newDay(){await super.newDay();this.ensureXIII();}
 async buildTensor(maxTimes=1024){
  if(!this.connected)throw Error('Conecta para generar la biblioteca de esta cuenta');await this.save();const samples=await this.store.scan('sample-'+this.scope+'-'+this.ledger.x.experiment+'-',30000),all=[...samples,...this.ledger.openSamples],features=[...HXII.FEATURES],cutoff=Date.now(),records=all.filter(s=>s.feature&&Number.isFinite(Date.parse(s.at))&&(!s.feature.bar_end||Date.parse(s.feature.bar_end)<=Date.parse(s.at))).map(s=>({asset:s.feature.symbol,at:Date.parse(s.at),availableAt:Date.parse(s.at),values:features.map(k=>typeof s.feature[k]==='number'&&Number.isFinite(s.feature[k])?s.feature[k]:null)})),cube=HTensor.build(records,features,cutoff,maxTimes),statistics=HTensor.statistics(cube);
  this.tensorLibrary={cube,statistics,experiment:this.ledger.x.experiment,mode:this.cfg.mode.toUpperCase(),created:iso(cutoff)};this.ledger.xiii.tensor={statistics,experiment:this.ledger.x.experiment,created:iso(cutoff),records:records.length,excluded_future:cube.excluded_future};this.journal('TENSOR_XIII',{shape:cube.shape,bytes:statistics.bytes,present:statistics.present,features,cutoff,labels_included:false});await this.save();this.emit();return this.tensorLibrary;
 }
 async exportEvidence(){return {...await super.exportEvidence(),schema:'HARPOON-XIII-1',version:HXIII.VERSION,xiii:this.ledger.xiii,daily_evidence:this.dailyEvidence()};}
}

const xiiiPriorProposal=LabController.prototype.proposal;
LabController.prototype.proposal=async function(data,reference){
 if(!this.engine.cfg.xiii||this.state.provider!=='local'||this.state.task==='operations')return xiiiPriorProposal.call(this,data,reference);
 const used=new Set(this.state.trials.filter(t=>t.recipe).map(t=>HXI.recipeKey(t.recipe)));
 for(const value of HXIII.variants(reference)){const recipe=HLab.validate(value);HLab.taskGuard(recipe,reference,this.state.task||'profitability');if(HXI.recipeKey(recipe)!==HXI.recipeKey(reference)&&!used.has(HXI.recipeKey(recipe)))return {recipe,findings:[],cost_usd:0,source:'LOCAL · XIII',prompt_version:'harpoon-prompts-5',task:this.state.task||'profitability'};}
 return xiiiPriorProposal.call(this,data,reference);
};
const xiiiPriorContext=LabController.prototype.context;
LabController.prototype.context=function(data,reference){const context=xiiiPriorContext.call(this,data,reference),a=this.engine.ledger.xiii?.analysis;context.xiii=a?{source:a.source,sessions:a.sessions,books:a.books,correlation:a.correlation,joint_loss_fraction:a.joint_loss_fraction}:null;return context;};
