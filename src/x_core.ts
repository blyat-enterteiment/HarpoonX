/** HARPOON X: deterministic, strictly typed research and execution primitives. */
namespace HX {
  export interface Session { date: string; open: number; close: number }
  export interface Quote { bid: number; ask: number; at: number; received: number }
  export interface Profile {astra?:{partialFraction:number}; name: string; min_rvol: number; momentum_bps: number; tp1_r: number; tp2_r: number; trail_atr: number; lock_fraction: number; prediction_floor: number; tp1_fraction?: number; tp2_fraction?: number; reentry?: boolean; selective?: boolean; stagnation_minutes?:number; progress_r?:number; trailing_mode?:string; exit_layout?:string }
  export interface Feature { symbol: string; book: string; factor: string; leverage: number; ask: number; bid: number; base: number; atr: number; perf5: number; rvol: number; momentum_bps: number; spread_bps: number; vwap_distance: number; atr_pct: number; asof: string; bar_end?: string; dollar_volume?: number; relative_bps?: number; volume_acceleration?: number; reset_base?: number; consolidation_atr?: number; sector_proxy?: string; candidate_number?: number; reentry_trigger?: number }
  export interface Levels { limit: number; stop: number; risk_unit: number; tp1: number; tp2: number; trigger: number }
  export interface ExitHistory { created: number; closed_at?: string; peak: number; closed: boolean; entry: number }
  export interface Outcome { first_target_minutes?:number|null; return: number; filled: boolean; entry_at: number | null; exit_at: number; marks: Record<string, number>; mfe_r: number; mae_r: number; reason: string; held_hours: number; risk_weight: number }
  export interface Lot { firstWeight?: number; secondWeight?: number; weight: number; left: number; entry: number; stop: number; tp1: number; tp2: number; first: boolean; second: boolean }
  export interface Shadow { vol?:HXII.VolState|null; dynamicAtr?:number; firstTargetAt?:number; plannedQty?: number; at: number; deadline: number; last: number; lastBid: number; anchor: number; risk: number; atr: number; profile: Profile; costs: number; paid: number; proceeds: number; opened: number; riskSpent: number; riskBudget: number; peak: number; stop: number; entry: number; levels: number; first: boolean; peakAt: number; lots: Lot[]; pending: { at: number; weight: number; levels: Levels } | null; marks: Record<string, number>; done: boolean; valid: boolean; reason: string; entryAt: number | null; mfe: number; mae: number; exitAt: number; tradingStagnation: number }
  export const VERSION = '12.0.0';
  export const finite = (x: number): boolean => Number.isFinite(x);
  export function nyTime(day: string, clock: string): number {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(day) || !/^\d{2}:\d{2}(?::\d{2})?$/.test(clock)) throw Error('Calendario inválido');
    const desired = Date.parse(day + 'T' + clock.slice(0, 5) + ':00Z');
    const fmt = new Intl.DateTimeFormat('en-CA', {timeZone:'America/New_York', year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'});
    let value = desired;
    for (let i=0;i<3;i++) { const parts = Object.fromEntries(fmt.formatToParts(new Date(value)).map(p=>[p.type,p.value])); const shown = Date.parse(`${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}:00Z`); value += desired-shown; }
    if (!finite(value)) throw Error('Fecha de mercado inválida');
    return value;
  }
  export function sessions(raw: {date:string;open:string;close:string}[]): Session[] {
    return raw.map(s=>({date:s.date,open:nyTime(s.date,s.open),close:nyTime(s.date,s.close)})).sort((a,b)=>a.open-b.open);
  }
  export function deadline(at: number, hours: number, calendar: Session[], bufferMinutes=10): number {
    if (![1.5,24,48,72].includes(hours) || bufferMinutes<1) throw Error('Plazo no permitido');
    const cap=at+hours*3600000;
    if (!calendar.length || calendar[calendar.length-1].close<cap) throw Error('Calendario insuficiente para la salida');
    let latest=NaN;
    for (const s of calendar) {
      const last=s.close-bufferMinutes*60000;
      if (s.open>cap) break;
      if (cap-30000<s.open) continue;
      if (last>=at && s.open<=cap) latest=Math.max(finite(latest)?latest:at,Math.min(cap-30000,last));
    }
    if (!finite(latest)||latest<=at) throw Error('Sin ventana de salida válida');
    return latest;
  }
  export function tradingMillis(a: number, b: number, calendar: Session[]): number {
    return calendar.reduce((v,s)=>v+Math.max(0,Math.min(b,s.close)-Math.max(a,s.open)),0);
  }
  export function parts(q: number, profile: Profile): number[] {return HPPolicy.parts(q,profile);}
  export function reentry(f: Feature, history: ExitHistory[], now: number, enabled: boolean): string | null {return HPPolicy.reentry(f,history,now,enabled);}
  export function quality(f: Feature, p: Profile, minDollarVolume: number, maxCostFraction: number, lv: Levels, costsBps: number): {score:number; reasons:string[]; cost_r:number} {return HPPolicy.quality(f,p,minDollarVolume,maxCostFraction,lv,costsBps);}
  export function newShadow(f: Feature, lv: Levels, p: Profile, until: number, costsBps: number, plannedQty?: number): Shadow {return HPPolicy.newShadow(f,lv,p,until,costsBps,plannedQty);}
  export function marked(s: Shadow, bid: number): number {
    return (s.proceeds+s.lots.reduce((v,l)=>v+l.left*bid*(1-s.costs),0)-s.paid)/s.anchor;
  }
  export function finishShadow(s: Shadow, q: Quote, reason: string): void {
    for (const l of s.lots) {s.proceeds+=l.left*q.bid*(1-s.costs);l.left=0;}
    s.pending=null;s.done=true;s.reason=reason;s.exitAt=q.received;
  }
  export function stepShadow(s: Shadow, q: Quote, day: string, calendar: Session[], makeLevels:(ask:number,bid:number)=>Levels): void {return HPPolicy.stepShadow(s,q,day,calendar,makeLevels);}
  export function outcome(s: Shadow): Outcome {
    return {first_target_minutes:s.firstTargetAt&&s.entryAt?(s.firstTargetAt-s.entryAt)/60000:null,risk_weight:s.riskSpent/s.riskBudget,return:marked(s,s.lastBid),filled:s.opened>0,entry_at:s.entryAt,exit_at:s.exitAt,marks:{...s.marks},mfe_r:s.mfe,mae_r:s.mae,reason:s.reason,held_hours:s.entryAt===null?0:(s.exitAt-s.entryAt)/3600000};
  }
  export function normalCDF(x: number): number {const z=Math.abs(x),t=1/(1+.2316419*z),d=.3989422804014327*Math.exp(-z*z/2),p=1-d*t*(.319381530+t*(-.356563782+t*(1.781477937+t*(-1.821255978+t*1.330274429))));return x>=0?p:1-p;}
  export function normalQuantile(p: number): number {if(!(p>0&&p<1))throw Error('Probabilidad inválida');let lo=-9,hi=9;for(let i=0;i<80;i++){const mid=(lo+hi)/2;if(normalCDF(mid)<p)lo=mid;else hi=mid;}return (lo+hi)/2;}
  export function dsr(returns: number[], trialSharpes: number[], trials: number): {probability:number|null;effective_n:number;trials:number;threshold:number|null} {
    const n=returns.length,m=returns.reduce((a,b)=>a+b,0)/n,v=returns.reduce((a,b)=>a+(b-m)**2,0)/n;
    if(n<30||v<=1e-20||trialSharpes.length<3)return {probability:null,effective_n:n,trials,threshold:null};
    const sd=Math.sqrt(v),sr=m/sd,skew=returns.reduce((a,b)=>a+((b-m)/sd)**3,0)/n,kurt=returns.reduce((a,b)=>a+((b-m)/sd)**4,0)/n;
    let vif=1;for(let lag=1;lag<=5;lag++)vif+=2*(1-lag/6)*returns.slice(lag).reduce((a,b,i)=>a+(b-m)*(returns[i]-m),0)/(n*v);
    const effective=Math.min(n,n/Math.max(1,vif)),tmean=trialSharpes.reduce((a,b)=>a+b,0)/trialSharpes.length,tvar=trialSharpes.reduce((a,b)=>a+(b-tmean)**2,0)/Math.max(1,trialSharpes.length-1),k=Math.max(3,trials);
    const threshold=Math.sqrt(tvar)*((1-.5772156649)*normalQuantile(1-1/k)+.5772156649*normalQuantile(1-1/(k*Math.E)));
    const den=Math.sqrt(Math.max(1e-12,1-skew*sr+(kurt-1)*sr*sr/4));
    return {probability:normalCDF((sr-threshold)*Math.sqrt(effective-1)/den),effective_n:effective,trials:k,threshold};
  }
}
