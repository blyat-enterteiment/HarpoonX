/** XI: shared contracts. No network, credentials, model calls or order authority. */
namespace HXI {
 export const VERSION='12.0.0';
 export const POLICY='XI-EXECUTION-1';
 export interface Session {date:string;open:number;close:number}
 export function entryWindow(at:number,session:Session|undefined,closeMinutes:number):boolean {
  return Boolean(session&&Number.isFinite(at)&&at>=session.open&&at<session.close-(closeMinutes+20)*60000);
 }
 export function stable(value:unknown):string {
  if(value===null||typeof value!=='object')return JSON.stringify(value);
  if(Array.isArray(value))return '['+value.map(stable).join(',')+']';
  const obj=value as Record<string,unknown>;
  return '{'+Object.keys(obj).sort().map(k=>JSON.stringify(k)+':'+stable(obj[k])).join(',')+'}';
 }
 export function recipeKey(recipe:Record<string,unknown>):string {
  return stable(Object.fromEntries(Object.entries(recipe).filter(([k])=>!['name','hypothesis',...(recipe.exit_layout==='single_target'?['tp2_r','tp2_fraction']:[])].includes(k))));
 }
 export interface OptionSnapshot {latestQuote?:{bp?:number;ap?:number;bs?:number;as?:number;t?:string};impliedVolatility?:number;greeks?:{delta?:number;gamma?:number};}
 export interface Contract {symbol:string;strike:number;expiry:string;type:'C'|'P';bid:number;ask:number;mid:number;iv:number;delta:number|null;gamma:number|null;at:number;}
 export interface OptionEvidence {underlying:string;feed:string;asof:number;valid:boolean;reason:string;contracts:number;expiry:string|null;expiry_at:number|null;iv_atm:number|null;expected_range:number|null;straddle:number|null;skew25:number|null;term_slope:number|null;iv_rv:number|null;horizon_hours:number;quote_at:number|null;proxy:boolean;}
 export function optionEvidence(underlying:string,snapshots:Record<string,OptionSnapshot>,spot:number,feed:string,now:number,hours:number,rv:number|null=null,complete=true,calendar:Session[]=[]):OptionEvidence {
  const out:OptionEvidence={underlying,feed,asof:now,valid:false,reason:'SIN DATOS VÁLIDOS',contracts:0,expiry:null,expiry_at:null,iv_atm:null,expected_range:null,straddle:null,skew25:null,term_slope:null,iv_rv:null,horizon_hours:hours,quote_at:null,proxy:false};
  if(feed!=='opra'){out.reason='INDICATIVE: sólo exploración, no validación';return out;}
  if(!complete){out.reason='CADENA INCOMPLETA';return out;}
  if(!(Number.isFinite(spot)&&spot>0&&[1.5,24,48,72].includes(hours)))return out;
  const expiryCache=new Map<string,number>();
  const expiryTime=(day:string):number=>{const cached=expiryCache.get(day);if(cached!==undefined)return cached;const known=calendar.find(s=>s.date===day);if(known)return known.close;const desired=Date.parse(day+'T16:00:00Z'),fmt=new Intl.DateTimeFormat('en-CA',{timeZone:'America/New_York',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'});let t=desired;for(let i=0;i<3;i++){const p=Object.fromEntries(fmt.formatToParts(new Date(t)).map(p=>[p.type,p.value]));t+=desired-Date.parse(p.year+'-'+p.month+'-'+p.day+'T'+p.hour+':'+p.minute+':00Z');}expiryCache.set(day,t);return t;};
  const contracts:Contract[]=[];
  for(const [symbol,s]of Object.entries(snapshots)){
   const m=/^([A-Z][A-Z0-9.]*)(\d{2})(\d{2})(\d{2})([CP])(\d{8})$/.exec(symbol),q=s.latestQuote;
   if(!m||m[1]!==underlying||!q)continue;
   const expiry='20'+m[2]+'-'+m[3]+'-'+m[4],at=Date.parse(q.t||''),iv=s.impliedVolatility;
   if(!Number.isFinite(at)||now-at>60000||at>now+2000||!(typeof q.bp==='number'&&typeof q.ap==='number'&&q.bp>0&&q.ap>=q.bp&&(q.ap-q.bp)/((q.ap+q.bp)/2)<=.3)||!(typeof iv==='number'&&Number.isFinite(iv)&&iv>0&&iv<5))continue;
   // Exclude 0DTE and contracts that cannot cover the requested horizon.
   const expiryAt=expiryTime(expiry);
   if(expiry<=new Date(now).toISOString().slice(0,10)||expiryAt-now<hours*3600000)continue;
   const delta=s.greeks?.delta,gamma=s.greeks?.gamma;
   contracts.push({symbol,strike:Number(m[6])/1000,expiry,type:m[5] as 'C'|'P',bid:q.bp,ask:q.ap,mid:(q.bp+q.ap)/2,iv,delta:typeof delta==='number'&&Number.isFinite(delta)?delta:null,gamma:typeof gamma==='number'&&Number.isFinite(gamma)?gamma:null,at});
  }
  out.contracts=contracts.length;
  const expiries=[...new Set(contracts.map(c=>c.expiry))].sort(),points:Array<{expiry:string;iv:number;straddle:number;at:number;t:number;skew:number|null}>=[];
  for(const expiry of expiries){
   const cs=contracts.filter(c=>c.expiry===expiry),pairs=cs.filter(c=>c.type==='C').map(c=>({call:c,put:cs.find(p=>p.type==='P'&&p.strike===c.strike)})).filter(p=>p.put&&Math.abs(p.call.strike/spot-1)<=.08).sort((a,b)=>Math.abs(a.call.strike-spot)-Math.abs(b.call.strike-spot));
   const pair=pairs[0];if(!pair?.put)continue;
   const near=(type:'C'|'P',delta:number)=>cs.filter(c=>c.type===type&&c.delta!==null&&Math.abs(c.delta-delta)<=.12).sort((a,b)=>Math.abs((a.delta as number)-delta)-Math.abs((b.delta as number)-delta))[0];
   const call25=near('C',.25),put25=near('P',-.25);
   points.push({expiry,iv:(pair.call.iv+pair.put.iv)/2,straddle:pair.call.mid+pair.put.mid,at:Math.min(pair.call.at,pair.put.at),t:(expiryTime(expiry)-now)/(365*86400000),skew:call25&&put25?put25.iv-call25.iv:null});
  }
  const p=points[0];if(!p){out.reason='FALTA PAR ATM O COTIZACIÓN RECIENTE';return out;}
  out.valid=true;out.reason='OPRA · contexto de volatilidad, sin señal direccional';out.expiry=p.expiry;out.expiry_at=expiryTime(p.expiry);out.iv_atm=p.iv;out.expected_range=spot*p.iv*Math.sqrt(hours/(365*24));out.straddle=p.straddle;out.skew25=p.skew;out.quote_at=p.at;
  if(points[1])out.term_slope=(points[1].iv**2*points[1].t-p.iv**2*p.t)/(points[1].t-p.t);
  if(rv!==null&&Number.isFinite(rv)&&rv>0)out.iv_rv=p.iv/rv;
  return out;
 }
 export function realizedVol(closes:number[]):number|null {
  if(closes.length<21||closes.some(v=>!Number.isFinite(v)||v<=0))return null;
  const r=closes.slice(1).map((v,i)=>Math.log(v/closes[i])),mean=r.reduce((a,b)=>a+b,0)/r.length;
  return Math.sqrt(r.reduce((v,x)=>v+(x-mean)**2,0)/(r.length-1)*252);
 }
 export interface Study {sealed_through:string;attempts:number;pending:{id:string;owner:string;through:string;at:string}|null;history:Array<{id:string;owner:string;through:string;status:string}>;}
 export function study(seed?:Partial<Study>):Study{return {sealed_through:seed?.sealed_through||'',attempts:seed?.attempts||0,pending:seed?.pending||null,history:seed?.history||[]};}
 export function reserveStudy(s:Study,id:string,owner:string,start:string,end:string,at:string):Study {
  if(s.pending)throw Error('Otra evaluación posee el holdout. Recupera su resultado antes de continuar.');
  if(start<=s.sealed_through||end<start)throw Error('Holdout ya consumido; espera observaciones nuevas.');
  return {...s,sealed_through:end,attempts:s.attempts+1,pending:{id,owner,through:end,at}};
 }
 export function finishStudy(s:Study,id:string,status:string):Study {
  if(s.pending?.id!==id)throw Error('Reserva de holdout incompatible');
  return {...s,pending:null,history:[...s.history,{id,owner:s.pending.owner,through:s.pending.through,status}].slice(-1000)};
 }
 export interface EconomicInput {gross:number;reportedFees:number|null;otherTrading:number;research:number;data:number;infra:number;unknownAdjustments:number;fillsReconciled:boolean;}
 export function economics(x:EconomicInput){
  const finite=[x.gross,x.otherTrading,x.research,x.data,x.infra].every(Number.isFinite);
  const complete=finite&&x.reportedFees!==null&&Number.isFinite(x.reportedFees)&&x.unknownAdjustments===0&&x.fillsReconciled;
  const net=complete?x.gross-(x.reportedFees as number)+x.otherTrading:null;
  return {complete,gross:x.gross,net_trading:net,net_economic:net===null?null:net-x.research-x.data-x.infra,external_costs:x.research+x.data+x.infra,reason:complete?'Fills y ajustes conciliados; revisa contra estado de cuenta':'Neto no certificado: faltan conciliación, costes o clasificación de ajustes'};
 }
}
