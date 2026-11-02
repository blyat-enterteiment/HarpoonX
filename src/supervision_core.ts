/** Pure supervision contracts: no broker, mutation, credentials or model SDK. */
namespace HXXI {
 export const VERSION='21.0.0';
 export type Mode='adaptive'|'periodic'|'logs'|'paused';
 export interface Config {enabled:boolean;mode:Mode;interval_seconds:number;heartbeat_seconds:number;daily_usd:number;monthly_usd:number;max_calls:number;output_tokens:number;}
 export const defaults:Config={enabled:false,mode:'adaptive',interval_seconds:300,heartbeat_seconds:1800,daily_usd:2,monthly_usd:30,max_calls:300,output_tokens:1200};
 export function configure(value:unknown):Config {
  if(!value||typeof value!=='object'||Array.isArray(value))throw Error('Configuración de supervisión inválida');
  const c={...defaults,...value} as Config;
  if(Object.keys(c).some(k=>!(k in defaults))||typeof c.enabled!=='boolean'||!['adaptive','periodic','logs','paused'].includes(c.mode))throw Error('Modo de supervisión inválido');
  for(const [k,lo,hi,integer] of [['interval_seconds',60,3600,true],['heartbeat_seconds',300,86400,true],['daily_usd',0,100,false],['monthly_usd',0,1000,false],['max_calls',1,1440,true],['output_tokens',256,2000,true]] as const){const n=c[k];if(typeof n!=='number'||!Number.isFinite(n)||n<lo||n>hi||(integer&&!Number.isInteger(n)))throw Error('Fuera de rango: '+k);}
  if(c.heartbeat_seconds<c.interval_seconds)throw Error('El heartbeat debe ser mayor o igual a la ventana');
  return c;
 }
 export function stable(v:unknown):string {if(v===undefined)return 'null';if(v===null||typeof v!=='object')return JSON.stringify(v);if(Array.isArray(v))return '['+v.map(stable).join(',')+']';return '{'+Object.entries(v).sort(([a],[b])=>a.localeCompare(b)).map(([k,x])=>JSON.stringify(k)+':'+stable(x)).join(',')+'}';}
 export async function digest(v:unknown):Promise<string>{const b=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(stable(v)));return Array.from(new Uint8Array(b),n=>n.toString(16).padStart(2,'0')).join('');}
 export function finite(v:unknown):number|null {return typeof v==='number'&&Number.isFinite(v)?v:null;}
 export interface Window {start:number;end:number;key:string;}
 export function windowAt(now:number,seconds:number,session:{open:number;close:number}|null,cryptoBook:boolean):Window|null {
  if(!Number.isFinite(now)||!Number.isInteger(seconds)||seconds<60||seconds>3600)throw Error('Reloj o intervalo inválido');
  let anchor=cryptoBook?Math.floor(now/86400000)*86400000:session?.open;
  if(cryptoBook&&now-(anchor as number)<seconds*1000)anchor=(anchor as number)-86400000;
  const close=cryptoBook?(anchor as number)+86400000:session?.close;
  if(anchor==null||close==null||now<anchor)return null;
  const boundary=Math.min(close,anchor+Math.floor((now-anchor)/(seconds*1000))*seconds*1000);
  const end=now>=close?close:boundary;
  if(end<=anchor)return null;
  const start=anchor+Math.max(0,Math.ceil((end-anchor)/(seconds*1000))-1)*seconds*1000;
  return {start,end,key:String(start)+'-'+end};
 }
 export interface Finding {severity:'low'|'medium'|'high';title:string;evidence_ids:string[];recommendation:'observe'|'investigate'|'propose_exit_trial';rationale:string;}
 export interface Review {snapshot_id:string;config_hash:string;plugin_hash:string;verdict:'no_issue_detected'|'investigate'|'insufficient_evidence';findings:Finding[];next_review_reason:string;}
 export function validateReview(value:unknown,context:{snapshot_id:string;config_hash:string;plugin_hash:string;evidence:{id:string}[]}):Review {
  if(!value||typeof value!=='object')throw Error('Revisión vacía');const r=value as Review;
  const keys=['snapshot_id','config_hash','plugin_hash','verdict','findings','next_review_reason'];
  if(Object.keys(r).length!==keys.length||keys.some(k=>!(k in r)))throw Error('Contrato de revisión inválido');
  for(const k of ['snapshot_id','config_hash','plugin_hash'] as const)if(r[k]!==context[k])throw Error('Identidad de revisión incompatible');
  if(!['no_issue_detected','investigate','insufficient_evidence'].includes(r.verdict)||typeof r.next_review_reason!=='string'||r.next_review_reason.length>600||!Array.isArray(r.findings)||r.findings.length>6)throw Error('Revisión fuera de contrato');
  const ids=new Set(context.evidence.map(e=>e.id));
  for(const f of r.findings){if(!f||Object.keys(f).sort().join(',')!=='evidence_ids,rationale,recommendation,severity,title'||!['low','medium','high'].includes(f.severity)||!['observe','investigate','propose_exit_trial'].includes(f.recommendation)||typeof f.title!=='string'||f.title.length>160||typeof f.rationale!=='string'||f.rationale.length>800||!Array.isArray(f.evidence_ids)||f.evidence_ids.length<1||f.evidence_ids.length>8||f.evidence_ids.some(id=>!ids.has(id)))throw Error('Hallazgo sin evidencia o permiso válido');}
  return r;
 }
 export function compound(c:{prior:number;realized:number;settled:number;peak:number;reserve:number;reserve_pct:number;growth_cap:number;capital_limit:number;equity:number}):{budget:number;reserve:number} {
  if(Object.values(c).some(v=>!Number.isFinite(v))||c.reserve_pct<0||c.reserve_pct>1)throw Error('Contabilidad insuficiente');
  const add=Math.max(0,c.realized-c.peak)*c.reserve_pct,reserve=c.reserve+add;
  return {budget:Math.max(0,Math.min(c.capital_limit,c.prior*c.growth_cap,c.prior+c.realized-c.settled-add,c.equity-reserve)),reserve};
 }
 export function takeProfit(rows:{closed:boolean;gross?:number;net?:number;mfe_r?:number;captured_r?:number}[]){
  const closed=rows.filter(r=>r.closed),net=closed.map(r=>finite(r.net)),paired=closed.filter(r=>finite(r.mfe_r)!==null&&finite(r.captured_r)!==null&&(r.mfe_r as number)>0);
  return {closed:closed.length,net:net.every(v=>v!==null)?net.reduce<number>((a,b)=>a+(b as number),0):null,net_complete:net.every(v=>v!==null),capture_proxy:paired.length?paired.reduce((s,r)=>s+(r.captured_r as number)/(r.mfe_r as number),0)/paired.length:null,paired:paired.length};
 }
}
