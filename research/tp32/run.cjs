"use strict";
// Historical BAR MODEL, never a broker adapter. Synthetic fills are explicitly modelling assumptions.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const root=path.resolve(__dirname,'../..'), out=path.join(root,'evidence/tp32');
const read=f=>JSON.parse(fs.readFileSync(path.join(root,f),'utf8'));
const data=read('evidence/tp32/prepared.json'), protocol=read('research/tp32/protocol.json');
const {profile,IDS}=require('../../runtime/exit_profiles32.cjs');
const policy=require('../../runtime30/policy.js'), types=require('../../runtime30/types.js');
const L=require('../../runtime/legacy30.cjs').create();
const cfg=read('config/examples/xxx.json');cfg.expected_account_id='RESEARCH-NO-ACCOUNT';cfg.universe.forEach(i=>i.tradable=true);
const bySymbol=Object.fromEntries(cfg.universe.map(i=>[i.symbol,i]));
const iso=t=>new Date(t).toISOString(),day=t=>L.ny(t).day,avg=a=>a.reduce((s,x)=>s+x,0)/Math.max(1,a.length);
const norm=a=>a.map(b=>({t:iso(b[0]),o:b[1],h:b[2],l:b[3],c:b[4],v:b[5],vw:b[6]}));
const hash=f=>crypto.createHash('sha256').update(fs.readFileSync(path.join(root,f))).digest('hex');
if(hash(protocol.parametersSource)!==protocol.parametersSha256)throw Error('Registered profile source changed');
const baseProfile={...L.settings.profile,family:'canonical_exit',hold_hours:48,selection_filter:'none'};
const entryCfg={...L.settings,slippage_bps:cfg.slippageBps,profile:baseProfile};
function basePolicy(f,lv){return policy.freezeExit({tp1R:baseProfile.tp1_r,tp2R:baseProfile.tp2_r,tp1Fraction:baseProfile.tp1_fraction,tp2Fraction:baseProfile.tp2_fraction,lockFraction:baseProfile.lock_fraction,trailR:baseProfile.trail_atr*f.atr/lv.risk_unit,maxHoldHours:48,trailingMode:'entry_atr',stagnationMinutes:20,progressR:1,reentry:false},cfg)}
function parity(){let checked=0;for(const p of read('evidence/tp32/feature-parity.json')){
  const f=p.feature,q={bid:f.bid,ask:f.ask,at:p.now,received:p.now};
  const actual=L.feature(f.symbol,norm(p.bars),norm(p.daily),q,p.now,{...L.settings,equity_factors:Object.fromEntries(cfg.universe.map(i=>[i.symbol,i.factor]))});
  for(const k of ['base','atr','perf5','perf20','rvol','momentum_bps','rsi','atr_pct','vwap_distance','spread_bps'])if(Math.abs(actual[k]-f[k])>1e-7*Math.max(1,Math.abs(actual[k])))throw Error('Feature mismatch '+k+' '+actual[k]+' '+f[k]);checked++;
}if(checked<20)throw Error('Too few native feature parity samples');return checked;}
const parityCount=parity(),cohorts=[],seen=new Set(),gateReasons={};
for(const p of read('evidence/tp32/candidates.json')){
 const f=p.feature,key=f.symbol+'|'+day(f.at);if(seen.has(key))continue;
 const chosen=L.localSelected(p.selectionRows,baseProfile);
 if(f.book==='etf'&&!f.pair&&f.perf5>0&&f.rvol>=2&&f.momentum_bps>=20)chosen.add(f.symbol);
 const lv=L.localLevels(f,entryCfg),d=L.HPSecurities.entryDecision(f,baseProfile,entryCfg,lv,chosen),quality=L.HX.quality(f,baseProfile,1e6,.5,lv,cfg.slippageBps);
 const reasons=[...d.reasons,...quality.reasons];if(reasons.length){for(const r of reasons)gateReasons[r]=(gateReasons[r]||0)+1;continue;}
 seen.add(key);cohorts.push({symbol:f.symbol,book:bySymbol[f.symbol].book,at:f.at,entry:lv.limit,stop:lv.stop,exit:basePolicy(f,lv),atr:f.atr,regime:{momentum_bps:f.momentum_bps,rvol:f.rvol},plugin:f.book+'-canonical-host'});
}
for(const s of ['BTC/USD','ETH/USD']){
 const daily=norm(data.daily[s]),cc=L.HC19.defaults;
 for(let j=21;j<daily.length;j++){
  const now=Date.parse(daily[j].t)+86400000;if(iso(now).slice(0,10)<protocol.historyFrom||iso(now).slice(0,10)>protocol.historyThrough)continue;
  const bars=L.HC19.normalize(daily.slice(0,j+1),now),sig=L.HC19.signal(bars,cc);if(!sig.enter)continue;
  const raw=data.series[s].find(b=>b[0]>=now);if(!raw)continue;
  const ask=raw[1]*(1+protocol.costs.modeledFullSpreadCryptoBps/20000);if(ask>sig.close*1.02)continue;
  const entry=ask*(1+cfg.slippageBps/10000),stop=entry-cc.atr_multiple*sig.atr;if(stop<=0)continue;
  cohorts.push({symbol:s,book:'crypto',at:now,entry,stop,exit:policy.freezeExit({},cfg),atr:sig.atr,regime:{momentum_bps:(sig.close/bars.at(-4).c-1)*10000,rvol:bars.at(-1).v/avg(bars.slice(-21,-1).map(b=>b.v))},plugin:'crypto-canonical-host'});
 }
}
cohorts.sort((a,b)=>a.at-b.at||a.symbol.localeCompare(b.symbol));
const times=Object.fromEntries(Object.entries(data.series).map(([s,a])=>[s,a.map(b=>b[0])]));
function lower(a,t){let l=0,h=a.length;while(l<h){const m=(l+h)>>>1;if(a[m]<t)l=m+1;else h=m;}return l;}
function spread(s){return s.includes('/')?10:['SPXL','SPXS'].includes(s)?5:2;}
function replay(signal,id,stress=1,delay=0,partial=1,qtyOverride){
 const s=signal.symbol,a=data.series[s],ix=times[s],asset=bySymbol[s],book=asset.book;
 // Next bar open after the closed signal bar. The 3-second feed-arrival offset is not resolved by OHLCV.
 let j=lower(ix,signal.at-(book==='crypto'?0:3000))+delay;
 if(!a[j]||a[j][0]>(signal.at+300000*(delay+1)))return {excluded:'ENTRY_DATA_GAP'};
 const raw=a[j],at=raw[0]+3000,ask=raw[1]*(1+spread(s)*stress/20000),fill=ask*(1+cfg.slippageBps*stress/10000);
 if(fill>signal.entry+asset.tick*1e-6)return {excluded:'UNFILLED_ENTRY_LIMIT'};
 const unitRisk=signal.entry-signal.stop+signal.entry*(2*cfg.slippageBps+(book==='crypto'?2*cfg.cryptoFeeBps:0))*stress/10000;
 let qty=qtyOverride??types.floorStep(Math.min(cfg.capitalLimit*cfg.assetExposure/signal.entry,cfg.capitalLimit*cfg.riskFraction/unitRisk),asset.step);
 qty=types.floorStep(qty*partial,asset.step);if(qty<asset.minQty)return {excluded:'SIZE_BELOW_MINIMUM'};
 const selected=profile(signal.exit,id,signal.regime),c={id:s+'|'+at,symbol:s,book,plugin:signal.plugin,created:at,instrument:asset,policy:selected.policy,risk:signal.entry-signal.stop,peak:fill,stop:signal.stop,closed:false,intents:['entry'],entryCeiling:signal.entry,entryAtr:signal.atr};
 try{c.deadline=policy.deadlineFor(book,at,c.policy.maxHoldHours,data.calendar)}catch{return {excluded:'CALENDAR_END'}}
 if(data.splits.some(r=>r.symbol===s&&r.ex_date>day(at)&&r.ex_date<=day(c.deadline)))return {excluded:'SPLIT_CROSSING_PATH'};
 if(!a.at(-1)||a.at(-1)[0]+300000<c.deadline)return {excluded:'RIGHT_CENSORED'};
 const localCfg={...cfg,slippageBps:cfg.slippageBps*stress,cryptoFeeBps:cfg.cryptoFeeBps*stress};
 const fee=book==='crypto'?cfg.cryptoFeeBps*stress/10000:0;
 const intents=[{id:'entry',campaign:c.id,symbol:s,kind:'entry',status:'filled',payload:{qty:String(qty)},at,order:{filled_qty:String(qty),filled_avg_price:String(fill)}}];
 let remaining=qty,fees=qty*fill*fee,proceeds=0,peakPnl=-fees,mae=0,ambiguous=0,closedAt=at,reason='';const exits=[],marks=[];
 function sell(n,px,t,kind){n=types.floorStep(Math.min(n,remaining),asset.step);if(n<asset.minQty)return;remaining=types.floorStep(Math.max(0,remaining-n),asset.step);fees+=n*px*fee;proceeds+=n*px;closedAt=t;reason=kind;intents.push({id:'exit'+intents.length,campaign:c.id,symbol:s,kind,status:'filled',at:t,payload:{qty:String(n)},order:{filled_qty:String(n),filled_avg_price:String(px)}});exits.push({at:t,qty:n,price:px,kind});}
 for(let k=j;k<a.length&&remaining>=asset.minQty;k++){
  const b=a[k],end=b[0]+300000;if(b[0]>c.deadline+300000)return {excluded:'EXIT_DATA_GAP'};
  if(k>j&&b[0]-a[k-1][0]>300000&&book==='crypto')return {excluded:'CRYPTO_DATA_GAP'};
  if(k>j&&day(b[0])===day(a[k-1][0])&&b[0]-a[k-1][0]>300000)return {excluded:'INTRADAY_DATA_GAP'};
  const half=spread(s)*stress/20000,bidLow=b[3]*(1-half),bidOpen=b[1]*(1-half),bidClose=b[4]*(1-half);
  // A resting stop gets pessimistic precedence whenever a target and stop could both have traded.
  const target=fill+(2*cfg.slippageBps+(book==='crypto'?2*cfg.cryptoFeeBps:0))*stress*fill/10000+c.policy.tp1R*c.risk;
  if(bidLow<=c.stop){if(b[2]*(1-half)>=target)ambiguous++;sell(remaining,Math.min(c.stop,bidOpen)*(1-cfg.slippageBps*stress/10000),end,'stop');}
  else{
   const q={bid:bidClose,ask:b[4]*(1+half),at:end,received:end};
   if(book==='crypto'){
    const available=norm(data.daily[s].filter(d=>d[0]+86400000<=end));
    try{if(L.HC19.signal(L.HC19.normalize(available,end),L.HC19.defaults).exit)c.strategyClose='CLOSED_DAILY_CHANNEL_EXIT'}catch{}
   }
   policy.observeExit(c,q,end,data.calendar,L);
   const d=policy.exitDecision(c,intents,q,remaining,end,localCfg);
   if(d){const next=a[k+1];if(!next)return {excluded:'EXIT_DATA_GAP'};const t=next[0];if(t>c.deadline+3600000&&d.kind!=='time')return {excluded:'EXIT_DATA_GAP'};
    const nextBid=next[1]*(1-half),limit=bidClose*(1-cfg.slippageBps*stress/10000);
    if(!['tp1','tp2'].includes(d.kind)||nextBid>=limit){const px=['tp1','tp2'].includes(d.kind)?Math.max(limit,nextBid*(1-cfg.slippageBps*stress/10000)):nextBid*(1-cfg.slippageBps*stress/10000);sell(d.qty,px,t,d.kind);}
   }
  }
  const pnl=proceeds+remaining*bidClose-qty*fill-fees;peakPnl=Math.max(peakPnl,pnl);mae=Math.min(mae,pnl);marks.push({at:end,pnl,qty:remaining,price:bidClose});
 }
 if(remaining>=asset.minQty)return {excluded:'UNFINISHED_PATH'};
 const net=proceeds-qty*fill-fees;if(marks.length)marks.at(-1).pnl=net;
 return {symbol:s,book,id,regime:selected.regime,opened:at,closedAt,signalAt:signal.at,entry:fill,qty,riskUsd:qty*unitRisk,net,gross:proceeds-qty*fill,fees,peakPnl,mae,giveback:Math.max(0,peakPnl-net),captureRatio:peakPnl>0?net/peakPnl:null,ambiguous,reason,exits,marks};
}
const variants={};for(const id of IDS){variants[id]={base:[],stress:[],delayed:[],partial:[],excluded:{}};for(const s of cohorts){
 const base=replay(s,id);if(base.excluded){variants[id].excluded[base.excluded]=(variants[id].excluded[base.excluded]||0)+1;continue;}variants[id].base.push(base);
 for(const [key,args] of [['stress',[2,0,1]],['delayed',[1,1,1]],['partial',[1,0,.5]]]){const r=replay(s,id,...args);if(!r.excluded)variants[id][key].push(r);}
}console.log(id,variants[id].base.length,variants[id].excluded);}
// Admission at chronological entry time uses only previously observed fills/marks, shared core sizing.
function funded(id,stress=1){const kind=stress===1?'base':'stress',shared=IDS.map(i=>new Set(variants[i][kind].map(t=>t.symbol+'|'+t.signalAt))),accepted=[],occupied=[],scfg={...cfg,slippageBps:cfg.slippageBps*stress,cryptoFeeBps:cfg.cryptoFeeBps*stress};let skipped=0;
 for(const s of cohorts){
  if(!shared.every(keys=>keys.has(s.symbol+'|'+s.at))){skipped++;continue;}
  if(occupied.some(t=>t.symbol===s.symbol&&t.closedAt>s.at)){skipped++;continue;}
  let cash=cfg.capitalLimit,equity=cfg.capitalLimit;const positions=[],campaigns=[],intents=[];
  for(const t of accepted){
   const sells=t.exits.filter(e=>e.at<=s.at),sold=sells.reduce((n,e)=>n+e.qty,0),remaining=Math.max(0,t.qty-sold),fee=t.book==='crypto'?scfg.cryptoFeeBps/10000:0;
   const received=sells.reduce((n,e)=>n+e.qty*e.price,0);cash-=t.qty*t.entry*(1+fee);cash+=received*(1-fee);equity+=received-t.qty*t.entry-t.qty*t.entry*fee-received*fee;
   if(remaining>1e-8){const observed=t.marks.filter(m=>m.at<=s.at).at(-1),px=observed?.price||t.entry;equity+=remaining*px;positions.push({symbol:t.symbol,qty:String(remaining),market_value:String(remaining*px)});const original=cohorts.find(x=>x.symbol===t.symbol&&x.at===t.signalAt);const c={id:t.symbol+'|'+t.opened,symbol:t.symbol,book:t.book,closed:false,instrument:bySymbol[t.symbol],risk:original.entry-original.stop};campaigns.push(c);intents.push({campaign:c.id,kind:'entry',status:'filled',order:{filled_qty:String(t.qty),filled_avg_price:String(t.entry)}});for(const e of sells)intents.push({campaign:c.id,kind:e.kind,status:'filled',order:{filled_qty:String(e.qty),filled_avg_price:String(e.price)}});}
  }
  if(equity<cfg.capitalLimit*(1-cfg.maxDrawdown)){skipped++;continue;}
  const account={equity:String(equity),cash:String(cash),buying_power:String(cash),non_marginable_buying_power:String(cash),options_buying_power:String(cash)};
  const n=policy.availableSize(s,bySymbol[s.symbol],scfg,account,positions,campaigns,intents);if(!n){skipped++;continue;}
  const r=replay(s,id,stress,0,1,n);if(r.excluded){skipped++;continue;}accepted.push(r);occupied.push(r);
 }return {trades:accepted,skipped};}
const portfolios={};for(const id of IDS){portfolios[id]={base:funded(id),stress:funded(id,2)};console.log('funded',id,portfolios[id].base.trades.length);}
const result={schema:'HARPOON-WF-RAW-32-1',generatedAt:iso(Date.now()),source:'OBSERVED_OHLCV_MODELED_EXECUTION',protocol,protocolSha256:hash('research/tp32/protocol.json'),nativeFeatureParitySamples:parityCount,cohortCount:cohorts.length,gateReasons,coverage:data.coverage,limitations:[...data.limitations,'Three-second bar-arrival and 15-second signal/20-second order TTL cannot be reconstructed; bar fills are comparative research only.','Funded portfolio models single long entry, shared capital/exposure constraints and no borrowing; broker queue/impact and settlement not reproduced.','Intrabar adverse stop precedence; trailing updates at bar close, not a one-second production replay.','Crypto channel exit shared with native signal; no proprietary tape/ASTRA/options-context reconstruction.'],variants,portfolios};
fs.writeFileSync(path.join(out,'raw-results.json'),JSON.stringify(result)+'\n');
console.log(JSON.stringify({cohorts:cohorts.length,nativeFeatureParitySamples:parityCount,files:'evidence/tp32/raw-results.json'}));
