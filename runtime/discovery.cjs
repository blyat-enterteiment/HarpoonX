'use strict';
// Bounded watchlist discovery. Admission prepares data; it never authorizes orders.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const {MAX_UNIVERSE_SIZE} = require('../runtime30/types.js');
const runs = new WeakMap();
const NY = new Intl.DateTimeFormat('en-CA', {timeZone:'America/New_York', year:'numeric', month:'2-digit', day:'2-digit'});
const day = value => NY.format(new Date(value));
const canonical = value => Array.isArray(value)?value.map(canonical):value && typeof value==='object'?
 Object.fromEntries(Object.keys(value).sort().map(key=>[key,canonical(value[key])])):value;
// Store implementations may reorder object keys (for example PostgreSQL JSONB).
const hash = value => crypto.createHash('sha256').update(JSON.stringify(canonical(value))).digest('hex');
const validSymbol = value => typeof value === 'string' && /^[A-Z][A-Z0-9.-]{0,9}$/.test(value);
const text = value => typeof value === 'string' && value.trim().length > 0;
const positive = value => typeof value === 'number' && Number.isFinite(value) && value > 0;
const liveOrder = value => !['filled','canceled','expired','rejected','replaced'].includes(String(value?.status || '').toLowerCase());

function protectedSymbols(engine) {
 const protectedSet = new Set((engine.cfg.universe || []).filter(i => i.discovery_managed !== true).map(i => i.symbol));
 const retain = (symbol, underlying) => {if(symbol)protectedSet.add(symbol);if(underlying)protectedSet.add(underlying);const known=engine.market?.assets?.[symbol];if(known?.underlying)protectedSet.add(known.underlying);};
 for (const symbol of engine.cfg.optionUnderlyings || []) protectedSet.add(symbol);
 for (const p of engine.positions || []) retain(p.symbol,p.underlying);
 for (const c of engine.active?.() || []) { retain(c.symbol,c.underlying || c.instrument?.underlying); }
 for (const i of engine.pending?.() || []) retain(i.symbol || i.payload?.symbol,i.underlying || i.payload?.underlying);
 for (const o of engine.openOrders || []) if(liveOrder(o)) {
  retain(o.symbol,o.underlying); for(const leg of o.legs || []) if(liveOrder(leg)) retain(leg.symbol,leg.underlying);
 }
 return protectedSet;
}

function metadata(model, symbol) {
 if(!model || model.accepted !== true || !['equity','etf'].includes(model.book)) return {reason:'NO_CALIBRATED_CLASSIFIED_SECURITY'};
 if(!text(model.metadata_reference) || !text(model.factor)) return {reason:'VERIFIED_CLASSIFICATION_AND_FACTOR_REQUIRED'};
 if(model.metadata_available_at!==undefined && model.metadata_available_at!==null &&
    (!Number.isFinite(Date.parse(model.metadata_available_at)) || Date.parse(model.metadata_available_at)>Date.now()))return {reason:'INVALID_OR_FUTURE_METADATA_TIME'};
 // A declared common stock uses an unleveraged share. ETF leverage must be supplied.
 const leverage = model.leverage ?? (model.book === 'equity' ? 1 : null);
 if(!positive(leverage) || leverage > 3) return {reason:'VERIFIED_LEVERAGE_REQUIRED'};
 const precision = {multiplier:model.multiplier ?? 1, step:model.step ?? 1, minQty:model.minQty ?? 1, tick:model.tick ?? .01};
 if(Object.values(precision).some(v => !positive(v)) || precision.multiplier !== 1) return {reason:'INVALID_SECURITY_PRECISION'};
 return {item:{symbol, book:model.book, factor:model.factor.trim(), leverage, ...precision, tradable:true,
  discovery_managed:true, metadata_reference:model.metadata_reference, metadata_available_at:model.metadata_available_at ?? null}};
}

function historyReason(market, intraday, daily, now) {
 if(!Array.isArray(intraday) || !Array.isArray(daily)) return 'HISTORY_RESPONSE_MISSING_SYMBOL';
 if(!Array.isArray(market.calendar) || !market.calendar.length) return 'HISTORY_CALENDAR_REQUIRED';
 const sessions = market.calendar.filter(s => Number.isFinite(s.open) && Number.isFinite(s.close) && s.open < s.close);
 const closed=[],priorSessions=new Set(),today=day(now);
 for(const b of intraday){
  const t=Date.parse(b.t),end=t+300000;if(end>now)continue;
  const session=sessions.find(s=>s.open<=t && end<=s.close);if(!session)continue;
  closed.push(b);if(session.date<today)priorSessions.add(session.date);
 }
 if(closed.length < 32) return 'HISTORY_32_CLOSED_REGULAR_BARS_REQUIRED';
 if(closed.some(b => ![b.o,b.h,b.l,b.c,b.vw].every(positive) || !Number.isFinite(b.v) || b.v<0)) return 'HISTORY_INVALID_OBSERVED_OHLCV';
 if(priorSessions.size < 10) return 'HISTORY_10_PRIOR_INTRADAY_SESSIONS_REQUIRED';
 const priorDaily = daily.filter(b => Date.parse(b.t)<=now && day(b.t)<today);
 if(new Set(priorDaily.map(b=>day(b.t))).size < 21) return 'HISTORY_21_PRIOR_DAILY_SESSIONS_REQUIRED';
 if(priorDaily.some(b => ![b.o,b.h,b.l,b.c].every(positive) || !Number.isFinite(b.v) || b.v<0)) return 'HISTORY_INVALID_DAILY_OHLCV';
 return null;
}

function freshQuote(engine, symbol, now) {
 const q=engine.market.quotes?.[symbol], age=engine.cfg.quoteAgeMs ?? 15000;
 return q && positive(q.bid) && positive(q.ask) && q.ask>=q.bid &&
  Number.isFinite(q.at) && Number.isFinite(q.received) && q.at<=now+2000 &&
  q.received<=now && now-q.at<=age && now-q.received<=age;
}

function recentBarsReason(market, bars, now) {
 const session=(market.calendar || []).find(s=>s.open<=now && now<s.close);
 if(!session)return 'MARKET_NOT_OPEN';
 const closed=(bars || []).filter(b=>Date.parse(b.t)>=session.open && Date.parse(b.t)+300000<=Math.min(now,session.close));
 if(!closed.length)return 'NO_CLOSED_CURRENT_SESSION_BAR';
 const last=Math.max(...closed.map(b=>Date.parse(b.t)+300000));
 return now-last>660000?'STALE_CURRENT_SESSION_BARS':null;
}

function registry(engine) {
 const payload={schema:'HARPOON_DISCOVERY_REGISTRY_1',at:Date.now(),items:engine.cfg.universe.filter(i=>i.discovery_managed===true).map(i=>({...i}))};
 return {...payload,sha256:hash(payload)};
}

function restore(engine, saved) {
 const blocked=reason=>({status:'BLOCKED',health:'BLOCKED',reason,restored:[],excluded:[]});
 if(!saved || saved.schema!=='HARPOON_DISCOVERY_REGISTRY_1' || !Number.isFinite(saved.at) || saved.at>Date.now()+1000 || !Array.isArray(saved.items) || saved.items.length>MAX_UNIVERSE_SIZE)return blocked('INVALID_DISCOVERY_REGISTRY');
 const {sha256,...payload}=saved;if(sha256!==hash(payload))return blocked('DISCOVERY_REGISTRY_HASH_MISMATCH');
 if(new Set(saved.items.map(i=>i.symbol)).size!==saved.items.length)return blocked('DUPLICATE_DISCOVERY_REGISTRY_SYMBOL');
 for(const i of saved.items)if(i.discovery_managed!==true || !validSymbol(i.symbol) || !['equity','etf'].includes(i.book) || !text(i.factor) || !text(i.metadata_reference) || ![i.leverage,i.multiplier,i.step,i.minQty,i.tick].every(positive) || i.leverage>3 || i.multiplier!==1)return blocked('INVALID_DISCOVERY_REGISTRY_INSTRUMENT');
 if(!Array.isArray(engine.cfg.universe) || engine.cfg.universe.length>MAX_UNIVERSE_SIZE || new Set(engine.cfg.universe.map(i=>i.symbol)).size!==engine.cfg.universe.length)return blocked('INVALID_EXISTING_UNIVERSE');
 for(const item of saved.items){const current=engine.cfg.universe.find(i=>i.symbol===item.symbol);if(current && ['book','factor','leverage','multiplier','step','minQty','tick'].some(k=>current[k]!==item[k]))return blocked('DISCOVERY_REGISTRY_CONFIGURATION_CONFLICT');}
 const protectedSet=protectedSymbols(engine), missing=saved.items.filter(i=>!engine.cfg.universe.some(x=>x.symbol===i.symbol));
 const capacity=Math.min(MAX_UNIVERSE_SIZE,engine.cfg.quant?.discoveryLimit ?? MAX_UNIVERSE_SIZE),slots=Math.max(0,capacity-engine.cfg.universe.length);
 if(missing.filter(i=>protectedSet.has(i.symbol)).length>slots)return blocked('DISCOVERY_RESTORE_CAPACITY_FOR_EXPOSURE');
 missing.sort((a,b)=>Number(protectedSet.has(b.symbol))-Number(protectedSet.has(a.symbol)));
 const restored=[],excluded=[];
 for(const item of missing){
  if(restored.length>=slots){excluded.push({symbol:item.symbol,reason:'RESTORE_CAPACITY'});continue;}
  const restoredItem={...item,tradable:false};engine.cfg.universe.push(restoredItem);
  if(!engine.market.assets[item.symbol])engine.market.assets[item.symbol]=restoredItem;
  restored.push(item.symbol);
 }
 return {status:'RESTORED',health:'WAITING',reason:'VERIFY_CATALOG_AND_FRESH_DATA_AFTER_RESTART',restored,excluded};
}

function eraseWatch(engine, symbol) {
 engine.cfg.universe=engine.cfg.universe.filter(i=>i.symbol!==symbol);
 for(const key of ['assets','bars','daily','quotes','minutes','metadata','microData','snapshots']) if(engine.market[key]) delete engine.market[key][symbol];
 for(const book of ['equity','etf']) if(engine.market.watched?.[book]) engine.market.watched[book]=engine.market.watched[book].filter(s=>s!==symbol);
}

async function execute(engine) {
 const config=engine.cfg, cfg=config.quant || {}, now=Date.now();
 const snapshot={started_at:now,completed_at:null,sources:{},candidates:[]};
 const receipt={status:'BLOCKED',health:'BLOCKED',reason:null,at:now,snapshot_id:null,snapshot,
  added:[],removed:[],repaired:[],rejected:{},ready_symbols:[],pending_symbols:[],
  ranking_policy:'SOURCE_COUNT_DESC_THEN_SYMBOL_ASC',
  scope:'SIP screener union; fixed configured names and inventory are protected. Readiness does not certify a signal, fills or profit.'};
 const finish=(reason, status='BLOCKED', health='BLOCKED')=>{
  for(const record of snapshot.candidates) delete record.item;
  snapshot.completed_at=Date.now();receipt.at=snapshot.completed_at;
  receipt.status=status;receipt.health=health;receipt.reason=reason;
  receipt.snapshot_id=hash(snapshot);receipt.capacity && (receipt.capacity.current_total=engine.cfg.universe.length);
  if(Array.isArray(engine.cfg.universe))receipt.registry=registry(engine);
  return receipt;
 };
 const fail=(record,reason,state='EXCLUDED')=>{record.state=state;record.reason=reason;receipt.rejected[record.symbol]=reason;};
 const modelPath=process.env.HARPOON_QUANT_MODEL || cfg.calibrationFile || path.join(process.env.HARPOON_DATA || '/var/data','quant_calibration.json');
 if(!fs.existsSync(modelPath)) return finish('CALIBRATION_FILE_REQUIRED');
 let cal;
 try{
  if(fs.statSync(modelPath).size>32*1024*1024) return finish('CALIBRATION_SIZE_LIMIT');
  cal=JSON.parse(fs.readFileSync(modelPath,'utf8'));
 }catch{return finish('CALIBRATION_INVALID');}
 if(!cal || typeof cal!=='object' || Array.isArray(cal) || !cal.models || typeof cal.models!=='object' || Array.isArray(cal.models)) return finish('CALIBRATION_INVALID');
 snapshot.calibration={schema:cal.schema ?? null,available_at:cal.available_at ?? null,sha256:hash(cal)};
 if(cal.schema==='HARPOON_QUANT_CALIBRATION_2' || cal.model_kind==='SVR_RBF' || cal.estimator==='svr' ||
    Object.values(cal.models).some(m=>m?.model_kind==='SVR_RBF' || m?.kind==='SVR_RBF')) return finish('SVR_RESEARCH_ONLY');
 const available=Date.parse(cal.available_at);
 if(cal.origin!=='OBSERVED' || !Number.isFinite(available) || available>=now || now-available>30*86400000) return finish('OBSERVED_CURRENT_CALIBRATION_REQUIRED');
 const configured=cfg.discoveryLimit ?? MAX_UNIVERSE_SIZE;
 if(!Number.isInteger(MAX_UNIVERSE_SIZE) || !Number.isInteger(configured) || configured<1 || configured>48 || !Array.isArray(config.universe)) return finish('INVALID_DISCOVERY_CAPACITY');
 const capacity=Math.min(MAX_UNIVERSE_SIZE,configured);
 receipt.capacity={configured_limit:configured,effective_total_limit:capacity,current_total:config.universe.length,clamped:configured!==capacity};
 if(config.universe.length>MAX_UNIVERSE_SIZE || new Set(config.universe.map(i=>i.symbol)).size!==config.universe.length) return finish('INVALID_EXISTING_UNIVERSE');
 const queries=[['movers','/v1beta1/screener/stocks/movers?top=50'],['most_actives','/v1beta1/screener/stocks/most-actives?by=volume&top=100']];
 for(const [source,url] of queries){
  try{
   const response=await engine.api.request(url,'GET',undefined,true), received=Date.now();
   snapshot.sources[source]={published_at:response?.last_updated ?? null, received_at:received, rows:response};
   const published=Date.parse(response?.last_updated);
   if(!Number.isFinite(published) || received-published>900000 || published>received+1000) return finish('STALE_OR_FUTURE_SCREENER');
   const lists=source==='movers'?[response.gainers,response.losers]:[response.most_actives];
   if(lists.some(rows=>!Array.isArray(rows) || rows.length>(source==='movers'?50:100))) return finish('INVALID_SCREENER_SCHEMA_OR_BOUND');
  }catch(error){snapshot.sources[source]={...(snapshot.sources[source]||{}),error:String(error)};return finish('SCREENER_REQUEST_FAILED');}
 }
 const candidates=new Map();
 for(const [source,rows] of [['gainers',snapshot.sources.movers.rows.gainers],['losers',snapshot.sources.movers.rows.losers],['most_actives',snapshot.sources.most_actives.rows.most_actives]]) {
  for(const row of rows){
   const symbol=row?.symbol;
   if(!validSymbol(symbol)){snapshot.candidates.push({symbol:symbol??null,sources:[source],rank:null,state:'EXCLUDED',reason:'INVALID_SYMBOL'});continue;}
   if(!candidates.has(symbol)) candidates.set(symbol,{symbol,sources:[],state:'OBSERVED',reason:null,rank:null});
   const candidate=candidates.get(symbol);if(!candidate.sources.includes(source))candidate.sources.push(source);
  }
 }
 for(const record of candidates.values()) record.source_count=new Set(record.sources.map(s=>s==='most_actives'?'most_actives':'movers')).size;
 const sorted=[...candidates.values()].sort((a,b)=>b.source_count-a.source_count || (a.symbol<b.symbol?-1:a.symbol>b.symbol?1:0));
 sorted.forEach((c,index)=>{c.rank=index+1;snapshot.candidates.push(c);});
 const rank=new Map(sorted.map(c=>[c.symbol,c.rank]));
 const protectedAtStart=protectedSymbols(engine), rotating=config.universe.filter(i=>i.discovery_managed===true && !protectedAtStart.has(i.symbol));
 const fixedCount=config.universe.length-rotating.length, eligible=[], repairs=[];
 for(const record of sorted){
  const m=metadata(cal.models[record.symbol],record.symbol);
  if(m.reason){fail(record,m.reason);continue;}
  record.item=m.item;
  const existing=config.universe.find(i=>i.symbol===record.symbol);
  if(existing && protectedAtStart.has(record.symbol)){
   record.state='PROTECTED_EXISTING';record.reason='CONFIGURED_OR_EXPOSED';
   if(historyReason(engine.market,engine.market.bars[record.symbol],engine.market.daily[record.symbol],Date.now())){
    record.repair_existing=true;record.state='PENDING_HISTORY';repairs.push(record);
   }
   continue;
  }
  eligible.push(record);
 }
 const target=eligible.slice(0,Math.max(0,capacity-fixedCount));
 for(const record of eligible.slice(target.length)) fail(record,'EXCLUDED_CAPACITY');
 const staged=[...repairs];let degraded=false;
 for(const record of target){
  const existing=config.universe.find(i=>i.symbol===record.symbol);
  if(existing){
   record.state='WATCHED';record.reason='EXISTING_DYNAMIC';
   if(historyReason(engine.market,engine.market.bars[record.symbol],engine.market.daily[record.symbol],Date.now())){
    record.repair_existing=true;record.state='PENDING_HISTORY';staged.push(record);
   }
   continue;
  }
  record.state='PENDING_METADATA';
  try{
   const asset=await engine.api.request('/v2/assets/'+encodeURIComponent(record.symbol));
   if(asset?.symbol!==record.symbol || asset?.class!=='us_equity' || asset?.status!=='active' || asset?.tradable!==true){fail(record,'ASSET_NOT_TRADABLE_OR_IDENTITY_MISMATCH');continue;}
   record.state='PENDING_HISTORY';staged.push(record);
  }catch(error){record.error=String(error);fail(record,'ASSET_REQUEST_FAILED','PENDING_METADATA');degraded=true;}
 }
 let intraday={},daily={};
 if(staged.length){
  const symbols=staged.map(r=>r.symbol);
  try{
   intraday=await engine.market.fetchBars(symbols,false,'5Min',Date.now()-50*86400000,Date.now());
   daily=await engine.market.fetchBars(symbols,false,'1Day',Date.now()-100*86400000,Date.now());
  }catch(error){
   for(const record of staged){record.error=String(error);fail(record,'HISTORY_REQUEST_FAILED','PENDING_HISTORY');}
   receipt.pending_symbols=staged.map(r=>r.symbol);
   return finish('HISTORY_PREPARATION_INCOMPLETE','OBSERVED_DISCOVERY','DEGRADED');
  }
 }
 if(engine.cfg!==config) return finish('CONFIGURATION_CHANGED_DURING_DISCOVERY');
 const commitAt=Date.now();
 if(Object.values(snapshot.sources).some(source=>commitAt-Date.parse(source.published_at)>900000 || Date.parse(source.published_at)>commitAt+1000))return finish('SCREENER_EXPIRED_DURING_PREPARATION');
 const targetSymbols=new Set(target.map(r=>r.symbol));
 for(const record of staged){
  const reason=historyReason(engine.market,intraday[record.symbol],daily[record.symbol],Date.now());
  if(reason){fail(record,reason,'PENDING_HISTORY');receipt.pending_symbols.push(record.symbol);degraded=true;continue;}
  // No await between the final exposure check and commit: broker callbacks cannot interleave it.
  const protectedNow=protectedSymbols(engine);
  if(config.universe.some(i=>i.symbol===record.symbol)){
   for(const [key,loaded] of [['bars',intraday[record.symbol]],['daily',daily[record.symbol]]]){
    const merged=new Map([...loaded,...(engine.market[key][record.symbol]||[])].map(b=>[b.t,b]));
    engine.market[key][record.symbol]=[...merged.values()].sort((a,b)=>Date.parse(a.t)-Date.parse(b.t));
   }
   record.state='HISTORY_READY';record.reason='EXISTING_HISTORY_REPAIRED';receipt.repaired.push(record.symbol);continue;
  }
  if(record.repair_existing){fail(record,'EXISTING_SYMBOL_REMOVED_DURING_PREPARATION');continue;}
  if(config.universe.length>=capacity){
   const checkedAt=Date.now();
   if(!Number.isFinite(engine.syncAt) || engine.syncAt<=0 || engine.syncAt>checkedAt || checkedAt-engine.syncAt>15000 || engine.reconcileError){
    fail(record,'ROTATION_REQUIRES_RECENT_RECONCILIATION');degraded=true;continue;
   }
   const removable=config.universe.filter(i=>i.discovery_managed===true && !protectedNow.has(i.symbol) && !targetSymbols.has(i.symbol))
    .sort((a,b)=>(rank.get(b.symbol)??Infinity)-(rank.get(a.symbol)??Infinity) || (a.symbol<b.symbol?-1:1));
   if(!removable.length){fail(record,'EXCLUDED_CAPACITY_PROTECTED_OR_CHANGED');continue;}
   eraseWatch(engine,removable[0].symbol);receipt.removed.push(removable[0].symbol);
  }
  if(config.universe.length>=capacity){fail(record,'EXCLUDED_CAPACITY');continue;}
  const item={...record.item,discovered_at:Date.now()};
  config.universe.push(item);engine.market.assets[record.symbol]=item;
  engine.market.bars[record.symbol]=intraday[record.symbol];engine.market.daily[record.symbol]=daily[record.symbol];
  record.state='HISTORY_READY';record.reason='AWAIT_FRESH_QUOTE_AND_SIGNAL';receipt.added.push(record.symbol);
 }
 for(const book of new Set([...receipt.added,...receipt.repaired].map(symbol=>engine.market.assets[symbol]?.book).filter(Boolean))){
  try{await engine.market.quotesFor(book,(engine.active?.()||[]).filter(c=>c.book===book).map(c=>c.symbol));}
  catch(error){receipt.quote_error=String(error);degraded=true;}
 }
 for(const record of sorted){
  delete record.item;
  if(['WATCHED','HISTORY_READY','PROTECTED_EXISTING'].includes(record.state)){
   if(engine.market.assets[record.symbol]?.tradable!==true){record.readiness_reason='CATALOG_VERIFICATION_REQUIRED';continue;}
   const reason=historyReason(engine.market,engine.market.bars[record.symbol],engine.market.daily[record.symbol],Date.now());
   if(reason){record.readiness_reason=reason;continue;}
   const recent=recentBarsReason(engine.market,engine.market.bars[record.symbol],Date.now());
   if(recent){record.readiness_reason=recent;continue;}
   if(freshQuote(engine,record.symbol,Date.now())){record.data_ready=true;receipt.ready_symbols.push(record.symbol);}
   else record.readiness_reason='FRESH_QUOTE_REQUIRED';
  }
 }
 return finish(degraded?'DISCOVERY_PARTIAL_DATA':receipt.ready_symbols.length?'WATCHLIST_DATA_READY':'NO_READY_CANDIDATES',
  'OBSERVED_DISCOVERY',degraded?'DEGRADED':receipt.ready_symbols.length?'READY':'WAITING');
}

function discover(engine) {
 const current=runs.get(engine);if(current)return current;
 const job=execute(engine).finally(()=>runs.delete(engine));runs.set(engine,job);return job;
}
module.exports={discover,restore,registry,protectedSymbols,historyReason,recentBarsReason};
