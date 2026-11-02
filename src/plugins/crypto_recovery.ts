namespace HPRecovery {
export const API = 'harpoon.strategy/1' as const;
export const MINUTE = 60_000, DAY = 86_400_000, BPS = 10_000;
export type SymbolName = 'BTC/USD' | 'ETH/USD';
export type Family = 'trend_xix' | 'shock_recovery';
export type Source = 'SYNTHETIC' | 'RECORDED';
export interface Bar {
  startMs: number; availableMs: number; open: number; high: number; low: number; close: number;
  volume: number; tradeVwap: number; buyVolume: number; sellVolume: number;
}
export interface Quote { atMs: number; bid: number; ask: number }
export interface Depth { atMs: number; askUsdWithin25bps: number }
export interface Snapshot {
  asofMs: number; symbol: SymbolName; venue: 'alpaca-us'; source: Source;
  daily: readonly Bar[]; intraday: readonly Bar[]; quote: Quote; depth?: Depth;
}
export interface Manifest {
  api: typeof API; id: string; version: '1.0.0'; family: Family;
  symbols: readonly SymbolName[]; params: Readonly<Record<string, number>>;
}
export interface Costs { feePerSideBps: number; slippagePerSideBps: number }
export interface Proposal {
  pluginId: string; revision: string; family: Family; symbol: SymbolName; source: Source;
  signalMs: number; expiresMs: number; entryCeiling: number; stop: number; target: number | null;
  holdMs: number | null; costBps: number; diagnostics: Readonly<Record<string, number>>;
}
export interface Evaluation { proposal: Proposal | null; reason: string; diagnostics: Readonly<Record<string, number>> }
export interface ExitPolicy { stop: number; target: number | null; deadlineMs: number | null }
export function demand(ok: boolean, why: string): asserts ok { if (!ok) throw new Error(why); }
export function finite(n: number): boolean { return typeof n === 'number' && Number.isFinite(n); }
export function mean(a: readonly number[]): number { demand(a.length > 0, 'Empty sample'); return a.reduce((s,x)=>s+x,0)/a.length; }
export function stdev(a: readonly number[]): number { demand(a.length > 1, 'Sample too small'); const m=mean(a); return Math.sqrt(a.reduce((s,x)=>s+(x-m)**2,0)/(a.length-1)); }
export function median(a: readonly number[]): number { demand(a.length>0,'Empty sample'); const b=[...a].sort((x,y)=>x-y),n=b.length; return n%2 ? b[(n-1)/2] : (b[n/2-1]+b[n/2])/2; }
export function quoteValid(q: Quote, now: number, ttl: number): boolean { return [q.atMs,q.bid,q.ask,now].every(finite) && q.bid>0 && q.ask>=q.bid && now>=q.atMs && now-q.atMs<=ttl; }
export function spreadBps(q: Quote): number { return (q.ask-q.bid)/((q.ask+q.bid)/2)*BPS; }
export function costBps(q: Quote, c: Costs): number {
  demand([c.feePerSideBps,c.slippagePerSideBps].every(x=>finite(x)&&x>=0&&x<=100),'Invalid costs');
  return 2*c.feePerSideBps+2*c.slippagePerSideBps+spreadBps(q);
}
export function closedBars(raw: readonly Bar[], frame: number, asof: number): Bar[] {
  demand(Array.isArray(raw)&&raw.length<=20_000&&finite(asof),'Invalid history');
  const out: Bar[]=[];
  for(const b of raw){
    demand([b.startMs,b.availableMs].every(finite),'Invalid timestamp');
    // Future observations are excluded before any numeric feature is read.
    if(b.availableMs>asof||b.startMs+frame>asof)continue;
    demand(Number.isInteger(b.startMs)&&b.startMs%frame===0&&b.availableMs>=b.startMs+frame,'Unclosed or misaligned bar');
    demand([b.open,b.high,b.low,b.close,b.volume,b.tradeVwap,b.buyVolume,b.sellVolume].every(finite),'Nonfinite bar');
    demand(Math.min(b.open,b.high,b.low,b.close,b.tradeVwap)>0&&b.volume>=0&&b.buyVolume>=0&&b.sellVolume>=0,'Invalid prices or volume');
    demand(b.high>=Math.max(b.open,b.close,b.low)&&b.low<=Math.min(b.open,b.close,b.high),'Invalid OHLC');
    demand(b.tradeVwap>=b.low&&b.tradeVwap<=b.high,'VWAP outside traded range');
    demand(b.buyVolume+b.sellVolume<=b.volume+Math.max(1e-10,b.volume*1e-10),'Signed volume exceeds total');
    if(out.length)demand(b.startMs-out[out.length-1].startMs===frame,'Gap, duplicate, or unsorted history');
    out.push({...b});
  }
  return out;
}
export function canonical(m: Manifest): string {
  return JSON.stringify({api:m.api,id:m.id,version:m.version,family:m.family,symbols:[...m.symbols].sort(),params:Object.fromEntries(Object.entries(m.params).sort(([a],[b])=>a.localeCompare(b)))});
}

const RECOVERY = {shockZ:2.5, minShockBps:100, volumeRatio:2, sellShare:0.65, recoveryBuyShare:0.5, maxSpreadBps:15, roomCostMultiple:2, minRewardRisk:1.25, holdHours:6};
export function defaultManifest(family:'trend_xix'|'shock_recovery', id=family):Manifest {
  return {api:API,id,version:'1.0.0',family,symbols:['BTC/USD','ETH/USD'],params:family==='trend_xix'?{entryDays:20,exitDays:10,atrDays:20,atrMultiple:3,holdHours:0}:{...RECOVERY}};
}
export function validateManifest(raw:unknown):Manifest {
  demand(raw!==null&&typeof raw==='object'&&!Array.isArray(raw),'Manifest must be an object');
  const x=raw as Record<string,unknown>;
  demand(Object.keys(x).sort().join(',')==='api,family,id,params,symbols,version','Unknown or missing manifest field');
  demand(x.api===API&&x.version==='1.0.0'&&typeof x.id==='string'&&/^[a-z][a-z0-9_]{2,48}$/.test(x.id),'Invalid plugin identity/API');
  demand(x.family==='trend_xix'||x.family==='shock_recovery','Unknown family; code review required');
  demand(Array.isArray(x.symbols)&&x.symbols.length>0&&x.symbols.length<=2&&new Set(x.symbols).size===x.symbols.length&&x.symbols.every(s=>s==='BTC/USD'||s==='ETH/USD'),'Invalid symbols');
  demand(x.params!==null&&typeof x.params==='object'&&!Array.isArray(x.params),'Invalid parameters');
  const params=x.params as Record<string,number>;
  const ranges:Record<string,readonly[number,number]>=x.family==='trend_xix'?{entryDays:[10,120],exitDays:[2,60],atrDays:[5,60],atrMultiple:[1,6],holdHours:[0,72]}:{shockZ:[2,4],minShockBps:[100,500],volumeRatio:[1.5,4],sellShare:[0.6,0.85],recoveryBuyShare:[0.5,0.7],maxSpreadBps:[2,30],roomCostMultiple:[2,4],minRewardRisk:[1,3],holdHours:[1,24]};
  demand(Object.keys(params).sort().join(',')===Object.keys(ranges).sort().join(','),'Unknown/missing parameter');
  for(const [k,[lo,hi]] of Object.entries(ranges)) demand(finite(params[k])&&params[k]>=lo&&params[k]<=hi,`Parameter outside bounds: ${k}`);
  if(x.family==='trend_xix')demand(params.exitDays<params.entryDays&&['entryDays','exitDays','atrDays','holdHours'].every(k=>Number.isInteger(params[k])),'Invalid trend windows');
  else demand(Number.isInteger(params.holdHours),'Recovery holdHours must be an integer');
  return {api:API,id:x.id,version:'1.0.0',family:x.family,symbols:[...x.symbols],params:{...params}} as Manifest;
}
export function legacySignal(s:Snapshot,m:Manifest):HC19.Signal {
  const b=closedBars(s.daily,DAY,s.asofMs).map(x=>({t:x.startMs,o:x.open,h:x.high,l:x.low,c:x.close,v:x.volume}));
  const p=m.params,c={...HC19.defaults,entry_days:p.entryDays,exit_days:p.exitDays,atr_days:p.atrDays,atr_multiple:p.atrMultiple,hold_hours:p.holdHours};
  HC19.validate(c);HC19.normalize(b,s.asofMs);return HC19.signal(b,c);
}
function reject(reason:string,diagnostics:Record<string,number>={}):Evaluation{return {proposal:null,reason,diagnostics};}
function atr(b:readonly Bar[],n=14):number {const last=b.slice(-n-1),r:number[]=[];for(let i=1;i<last.length;i++)r.push(Math.max(last[i].high-last[i].low,Math.abs(last[i].high-last[i-1].close),Math.abs(last[i].low-last[i-1].close)));return mean(r);}
export function evaluate(m:Manifest,s:Snapshot,costs:Costs):Evaluation {
  validateManifest(m);
  if(s.venue!=='alpaca-us'||!m.symbols.includes(s.symbol)||!['SYNTHETIC','RECORDED'].includes(s.source))return reject('UNSUPPORTED_DATA');
  const ttl=m.family==='shock_recovery'?2000:15000;
  if(!quoteValid(s.quote,s.asofMs,ttl))return reject('STALE_QUOTE');
  const costsBps=costBps(s.quote,costs),p=m.params;
  let proposal:Proposal;
  if(m.family==='trend_xix'){
    const sig=legacySignal(s,m);
    if(s.asofMs-sig.available_at>60*MINUTE)return reject('DAILY_WINDOW_CLOSED');
    if(!sig.enter)return reject('NO_BREAKOUT');
    if(spreadBps(s.quote)>30)return reject('WIDE_SPREAD');
    const entry=s.quote.ask*(1+costs.slippagePerSideBps/BPS),stop=entry-p.atrMultiple*sig.atr;
    if(stop<=0)return reject('INVALID_STOP');
    proposal={pluginId:m.id,revision:canonical(m),family:m.family,symbol:s.symbol,source:s.source,signalMs:sig.available_at,expiresMs:Math.min(sig.available_at+60*MINUTE,s.asofMs+15000),entryCeiling:entry,stop,target:null,holdMs:p.holdHours===0?null:p.holdHours*60*MINUTE,costBps:costsBps,diagnostics:{atr:sig.atr,upper:sig.upper,lower:sig.lower}};
  }else{
    const all=closedBars(s.intraday,15*MINUTE,s.asofMs);
    if(all.length<99)return reject('INSUFFICIENT_HISTORY');
    const last=all[all.length-1],signalMs=last.startMs+15*MINUTE;
    if(s.asofMs-signalMs>MINUTE)return reject('SIGNAL_EXPIRED');
    const pre=all.slice(-99,-3),shock=all.slice(-3,-1),confirm=last;
    const returns=pre.slice(1).map((b,i)=>Math.log(b.close/pre[i].close)),sigma=stdev(returns);
    if(sigma<1e-8)return reject('DEGENERATE_VOLATILITY');
    const shockReturn=Math.log(shock[1].close/pre[pre.length-1].close),z=-(shockReturn-2*mean(returns))/(sigma*Math.sqrt(2));
    const baseVolume=median(pre.map(b=>b.volume)),shockVolume=shock[0].volume+shock[1].volume;
    if(baseVolume<=0||shockVolume<=0||confirm.volume<=0)return reject('NO_TRADED_VOLUME');
    const signedShock=shock.reduce((n,b)=>n+b.buyVolume+b.sellVolume,0),signedConfirm=confirm.buyVolume+confirm.sellVolume;
    if(signedShock/shockVolume<0.95||signedConfirm/confirm.volume<0.95)return reject('MISSING_TAKER_FLOW');
    const volumeRatio=shockVolume/(2*baseVolume),sellShare=shock.reduce((n,b)=>n+b.sellVolume,0)/signedShock;
    const buyShare=confirm.buyVolume/signedConfirm,low=Math.min(...shock.map(b=>b.low));
    const d:Record<string,number>={shockZ:z,shockBps:-shockReturn*BPS,volumeRatio,sellShare,buyShare};
    if(z<p.shockZ||-shockReturn*BPS<p.minShockBps||volumeRatio<p.volumeRatio||sellShare<p.sellShare)return reject('NO_SHOCK',d);
    if(confirm.close<=shock[1].close||confirm.low<low||confirm.high===confirm.low||(confirm.close-confirm.low)/(confirm.high-confirm.low)<0.6||buyShare<p.recoveryBuyShare)return reject('NO_RECOVERY',d);
    if(spreadBps(s.quote)>p.maxSpreadBps)return reject('WIDE_SPREAD',d);
    const depth=s.depth;
    if(!depth||![depth.atMs,depth.askUsdWithin25bps].every(finite)||depth.askUsdWithin25bps<=0||depth.atMs>s.asofMs||s.asofMs-depth.atMs>2000)return reject('MISSING_FRESH_DEPTH',d);
    const anchorBars=pre.slice(-24),volume=anchorBars.reduce((n,b)=>n+b.volume,0);
    if(volume<=0)return reject('NO_VWAP',d);
    const target=anchorBars.reduce((n,b)=>n+b.tradeVwap*b.volume,0)/volume;
    const entry=s.quote.ask*(1+costs.slippagePerSideBps/BPS),stop=low-0.25*atr(pre),room=(target/entry-1)*BPS,risk=(1-stop/entry)*BPS;
    d.roomBps=room;d.costBps=costsBps;d.netRewardRisk=(room-costsBps)/(risk+costsBps);
    if(stop<=0||stop>=entry||target<=entry||room<p.roomCostMultiple*costsBps||d.netRewardRisk<p.minRewardRisk)return reject('INSUFFICIENT_NET_ROOM',d);
    proposal={pluginId:m.id,revision:canonical(m),family:m.family,symbol:s.symbol,source:s.source,signalMs,expiresMs:signalMs+MINUTE,entryCeiling:entry,stop,target,holdMs:p.holdHours*60*MINUTE,costBps:costsBps,diagnostics:d};
  }
  return {proposal,reason:'CANDIDATE_NOT_AN_ORDER',diagnostics:proposal.diagnostics};
}
}
