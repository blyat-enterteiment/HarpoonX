/** Generic, bounded daily-allocation research host. No strategy identifiers or broker authority. */
namespace H22 {
 export type Expr=number|string|Expr[];
 export interface Events {source:string;from:string;to:string;known_at:string;dates:string[]}
 export interface Rule {weekday:number;nth:number;holiday:'previous_session';source:string}
 export interface Plugin {schema:string;id:string;version:string;name:string;symbol:string;book:string;description:string;orders_enabled:false;permissions:string[];source:Record<string,unknown>;source_canonical:string;parameters:Record<string,number>;program:{start:number;burn_in:number;state:Record<string,number>;nodes:{id:string;expr:Expr}[];update:Record<string,string>;outputs:Record<string,string>};calendar_rules:Record<string,Rule>;event_sets:Record<string,Events>;notes:string[];sha256:string}
 export interface Data {schema:string;symbol:string;kind:'historical'|'synthetic';source:string;adjustment:'all';asof:string;calendar:{source:string;from:string;to:string;sessions:{date:string;open:number;close:number}[]};bars:{date:string;open:number;close:number}[];event_sets?:Record<string,Events>}
 export interface Point {date:string;next_session:string;values:Record<string,number>;ready:boolean}
 export interface Costs {capital:number;cost_bps:number;financing_apr:number;fee_apr:number;benchmark_weight:number}
 export const VERSION='22.0.0';
 const key=/^[a-zA-Z][a-zA-Z0-9_-]{0,79}$/;
 const safeKey=(s:string)=>key.test(s)&&!['constructor','prototype','__proto__'].includes(s);
 export function stable(v:unknown):string {if(v===null||typeof v!=='object')return JSON.stringify(v);if(Array.isArray(v))return '['+v.map(stable).join(',')+']';return '{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+stable((v as Record<string,unknown>)[k])).join(',')+'}';}
 export async function digest(s:string):Promise<string>{return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(s))),n=>n.toString(16).padStart(2,'0')).join('');}
 function obj(x:unknown):asserts x is Record<string,unknown>{if(!x||typeof x!=='object'||Array.isArray(x))throw Error('Objeto requerido');}
 function finite(n:unknown,lo=-1e9,hi=1e9):asserts n is number {if(typeof n!=='number'||!Number.isFinite(n)||n<lo||n>hi)throw Error('Número fuera de límites');}
 function date(s:unknown):asserts s is string{if(typeof s!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(s)||!Number.isFinite(Date.parse(s))||new Date(s).toISOString().slice(0,10)!==s)throw Error('Fecha inválida');}
 function keys(x:Record<string,unknown>,allowed:string[]){if(Object.keys(x).some(k=>!allowed.includes(k))||allowed.some(k=>!Object.hasOwn(x,k)))throw Error('Contrato desconocido o incompleto');}
 function events(e:Events){obj(e);date(e.from);date(e.to);date(e.known_at);if(!e.source||e.from>e.to||!Array.isArray(e.dates)||e.dates.length>500||new Set(e.dates).size!==e.dates.length)throw Error('Calendario de eventos inválido');for(const d of e.dates){date(d);if(d<e.from||d>e.to)throw Error('Evento fuera de cobertura');}}
 const arity:Record<string,number>={add:2,sub:2,mul:2,div:2,min:2,max:2,clip:3,gt:2,lt:2,eq:2,and:2,or:2,if:3,neg:1,log:1,sqrt:1,ref:1,param:1,state:1,price:2,calendar:1,previous_month_close:0,scheduled:2,previous_schedule_close:1,event:2};
 export function validate(p:Plugin):Plugin {
  obj(p);keys(p as unknown as Record<string,unknown>,['schema','id','version','name','symbol','book','description','orders_enabled','permissions','source','source_canonical','parameters','program','calendar_rules','event_sets','notes','sha256']);
  if(p.schema!=='HARPOON-XXII-RESEARCH-PLUGIN-1'||!safeKey(p.id)||!/^\d+\.\d+\.\d+$/.test(p.version)||typeof p.name!=='string'||p.name.length>140||!p.name||typeof p.description!=='string'||p.description.length>2000||!['equity','etf'].includes(p.book)||!/^([A-Z][A-Z0-9.-]{0,9})$/.test(p.symbol))throw Error('Plugin diario incompatible');
  if(p.orders_enabled!==false||stable(p.permissions)!==stable(['daily_data','local_research']))throw Error('El host XXII no concede órdenes ni red a plugins de investigación');
  obj(p.parameters);obj(p.program);obj(p.program.state);obj(p.program.update);obj(p.program.outputs);obj(p.calendar_rules);obj(p.event_sets);
  if(Object.keys(p.parameters).length>40||Object.keys(p.program.state).length>20||Object.keys(p.program.outputs).length>20||Object.keys(p.calendar_rules).length>8||Object.keys(p.event_sets).length>8)throw Error('Plugin excede capacidad');
  for(const [k,v] of Object.entries({...p.parameters,...p.program.state})){if(!safeKey(k))throw Error('Nombre reservado');finite(v,-1000,1000);}
  finite(p.program.start,5,252);finite(p.program.burn_in,20,252);if(!Number.isInteger(p.program.start)||!Number.isInteger(p.program.burn_in)||!Array.isArray(p.program.nodes)||p.program.nodes.length>80)throw Error('Programa inválido');
  for(const [k,r] of Object.entries(p.calendar_rules)){if(!safeKey(k)||r.holiday!=='previous_session'||!r.source)throw Error('Regla de calendario inválida');finite(r.weekday,1,5);finite(r.nth,1,4);if(!Number.isInteger(r.weekday)||!Number.isInteger(r.nth))throw Error('Calendario no entero');}
  for(const [k,e] of Object.entries(p.event_sets)){if(!safeKey(k))throw Error('Evento inválido');events(e);}
  const names=new Set<string>();let budget=0;
  function expr(x:Expr,depth=0):void{
   if(++budget>3000||depth>25)throw Error('Expresión excesiva');if(typeof x==='number'){finite(x);return;}
   if(!Array.isArray(x)||typeof x[0]!=='string'||!Object.hasOwn(arity,x[0])||x.length!==arity[x[0]]+1)throw Error('Operador o aridad no admitido');
   const op=x[0],s=x[1];if(['ref','param','state','calendar','price','scheduled','previous_schedule_close','event'].includes(op)){
    if(typeof s!=='string')throw Error('Nombre requerido');
    if(op==='ref'&&!names.has(s)||op==='param'&&!Object.hasOwn(p.parameters,s)||op==='state'&&!Object.hasOwn(p.program.state,s))throw Error('Referencia ausente o adelantada');
    if(op==='calendar'&&!['month_position','remaining','first','first_ready'].includes(s))throw Error('Campo de calendario desconocido');
    if(op==='price'){if(!['open','close'].includes(s))throw Error('Precio desconocido');finite(x[2],0,252);if(!Number.isInteger(x[2]))throw Error('Desfase inválido');}
    if(['scheduled','previous_schedule_close'].includes(op)&&!Object.hasOwn(p.calendar_rules,s))throw Error('Calendario ausente');
    if(op==='event'&&!Object.hasOwn(p.event_sets,s))throw Error('Eventos ausentes');
    if(['scheduled','event'].includes(op)){finite(x[2],0,1);if(!Number.isInteger(x[2]))throw Error('Desfase inválido');}return;
   }for(const a of x.slice(1))expr(a,depth+1);
  }
  for(const n of p.program.nodes){if(!safeKey(n.id)||names.has(n.id))throw Error('Nodo duplicado/reservado');expr(n.expr);names.add(n.id);}
  for(const [k,v] of Object.entries(p.program.update))if(!Object.hasOwn(p.program.state,k)||!names.has(v))throw Error('Actualización de estado inválida');
  if(!Object.hasOwn(p.program.outputs,'weight'))throw Error('Falta salida weight');
  for(const [k,v] of Object.entries(p.program.outputs))if(!safeKey(k)||!names.has(v))throw Error('Salida inválida');
  if(!Array.isArray(p.notes)||p.notes.length>20||p.notes.some(s=>typeof s!=='string'||s.length>2000))throw Error('Notas inválidas');
  if(!/^[a-f0-9]{64}$/.test(p.sha256)||typeof p.source_canonical!=='string'||p.source_canonical.length>100000)throw Error('Integridad ausente');
  return p;
 }
 export async function unpack(raw:unknown):Promise<Plugin>{const p=validate(raw as Plugin),{sha256,...payload}=p;if(await digest(stable(payload))!==sha256)throw Error('SHA-256 del plugin no coincide');
  obj(p.source);const {integrity,...source}=p.source;obj(integrity);if(integrity.algorithm!=='sha256'||integrity.scope!=='all_fields_except_integrity'||await digest(p.source_canonical)!==integrity.canonical_payload_sha256||stable(JSON.parse(p.source_canonical))!==stable(source))throw Error('La procedencia no coincide con su hash');
  if(p.source.schema!=='HARPOON-STRATEGY-RESEARCH-1'||p.source.id!==p.id||p.source.symbol!==p.symbol)throw Error('Adaptador y especificación no corresponden');return structuredClone(p);
 }
 export function validateData(d:Data,p:Plugin):Data{
  if(d.schema!=='HARPOON-DAILY-DATA-1'||d.symbol!==p.symbol||!['historical','synthetic'].includes(d.kind)||!d.source||d.adjustment!=='all'||!Number.isFinite(Date.parse(d.asof))||Date.parse(d.asof)>Date.now()+60000)throw Error('Dataset, fuente, fecha o ajuste incompatible');
  const c=d.calendar;date(c.from);date(c.to);if(!c.source||c.from.slice(8)!=='01'||c.to!==new Date(Date.UTC(Number(c.to.slice(0,4)),Number(c.to.slice(5,7)),0)).toISOString().slice(0,10)||!Array.isArray(c.sessions)||c.sessions.length>6000||c.sessions.length<60||!Array.isArray(d.bars)||d.bars.length<65||d.bars.length>5000)throw Error('Se requieren meses completos y al menos 65 barras');
  let prev='';const byDate=new Map<string,number>();for(const [i,s] of c.sessions.entries()){date(s.date);finite(s.open,1,1e15);finite(s.close,s.open+1,1e15);if(s.date<=prev||s.date<c.from||s.date>c.to||new Date(s.close).toISOString().slice(0,10)!==s.date)throw Error('Sesión inválida/duplicada');byDate.set(s.date,i);prev=s.date;}
  let prevIndex=-1;for(const b of d.bars){date(b.date);finite(b.open,.00001,1e7);finite(b.close,.00001,1e7);const i=byDate.get(b.date);if(i===undefined||prevIndex>=0&&i!==prevIndex+1||c.sessions[i].close>Date.parse(d.asof))throw Error('Barras incompletas, desordenadas o todavía abiertas');prevIndex=i;}
  if(prevIndex>=c.sessions.length-1)throw Error('Falta calendario de la próxima sesión');
  for(const e of Object.values(d.event_sets||{}))events(e);return d;
 }
 export function signals(p:Plugin,d:Data):Point[]{validate(p);validateData(d,p);const bars=d.bars,ss=d.calendar.sessions,indices=new Map(ss.map((s,i)=>[s.date,i])),barIndex=new Map(bars.map((b,i)=>[b.date,i])),state={...p.program.state},out:Point[]=[];
  const schedules:Record<string,string[]>={};for(const [k,r] of Object.entries(p.calendar_rules)){const dates:string[]=[];for(const month of new Set(ss.map(s=>s.date.slice(0,7)))){const base=new Date(month+'-01T00:00:00Z'),delta=(r.weekday-base.getUTCDay()+7)%7+(r.nth-1)*7;base.setUTCDate(1+delta);const nominal=base.toISOString().slice(0,10);const ds=ss.filter(s=>s.date.slice(0,7)===month&&s.date<=nominal);if(ds.length)dates.push(ds[ds.length-1].date);}schedules[k]=dates;}
  for(let i=p.program.start;i<bars.length;i++){
   const day=bars[i].date,ci=indices.get(day)!;const priorMonth=bars.slice(0,i).findLast(b=>b.date.slice(0,7)!==day.slice(0,7));if(!priorMonth)continue;
   const month=ss.filter(s=>s.date.slice(0,7)===day.slice(0,7)),pos=month.findIndex(s=>s.date===day),nodes:Record<string,number>={};
   const evalExpr=(x:Expr):number=>{if(typeof x==='number')return x;const a=x as Expr[],op=a[0] as string,k=a[1] as string;
    const ev=(n:number)=>evalExpr(a[n]);let v:number;
    switch(op){
     case 'ref':v=nodes[k];break;case 'param':v=p.parameters[k];break;case 'state':v=state[k];break;
     case 'price':{const b=bars[i-(a[2] as number)];if(!b)throw Error('Lookback insuficiente');v=b[k as 'open'|'close'];break;}
     case 'calendar':v=k==='month_position'?pos:k==='remaining'?month.length-pos-1:k==='first_ready'?Number(out.length===p.program.burn_in):Number(out.length===0);break;
     case 'previous_month_close':v=priorMonth.close;break;
     case 'scheduled':v=Number(schedules[k].includes(ss[ci+(a[2] as number)]?.date));break;
     case 'previous_schedule_close':{const past=schedules[k].filter(s=>s<day).at(-1),b=past?barIndex.get(past):undefined;if(b===undefined||b>=i)throw Error('Falta precio del evento anterior');v=bars[b].close;break;}
     case 'event':{const e=d.event_sets?.[k]||p.event_sets[k],check=ss[ci+(a[2] as number)]?.date;if(!check||day<e.known_at||day<e.from||check>e.to)throw Error('Calendario '+k+' sin cobertura conocida para '+day);v=Number(e.dates.includes(check));break;}
     case 'if':v=ev(1)?ev(2):ev(3);break;case 'and':v=Number(Boolean(ev(1))&&Boolean(ev(2)));break;case 'or':v=Number(Boolean(ev(1))||Boolean(ev(2)));break;
     case 'add':v=ev(1)+ev(2);break;case 'sub':v=ev(1)-ev(2);break;case 'mul':v=ev(1)*ev(2);break;case 'div':{const q=ev(2);if(q===0)throw Error('División por cero');v=ev(1)/q;break;}
     case 'min':v=Math.min(ev(1),ev(2));break;case 'max':v=Math.max(ev(1),ev(2));break;case 'clip':{const lo=ev(2),hi=ev(3);if(lo>hi)throw Error('Clip invertido');v=Math.max(lo,Math.min(hi,ev(1)));break;}
     case 'gt':v=Number(ev(1)>ev(2));break;case 'lt':v=Number(ev(1)<ev(2));break;case 'eq':v=Number(ev(1)===ev(2));break;
     case 'neg':v=-ev(1);break;case 'log':v=Math.log(ev(1));break;case 'sqrt':v=Math.sqrt(ev(1));break;default:throw Error('Operador no permitido');
    }finite(v);return v;
   };
   for(const n of p.program.nodes)nodes[n.id]=evalExpr(n.expr);
   const values:Record<string,number>={};for(const [k,n] of Object.entries(p.program.outputs))values[k]=nodes[n];finite(values.weight,0,1.5);
   out.push({date:day,next_session:ss[ci+1].date,values,ready:out.length>=p.program.burn_in});for(const [k,n]of Object.entries(p.program.update))state[k]=nodes[n];
  }if(!out.some(s=>s.ready))throw Error('Historial insuficiente después del calentamiento');return out;
 }
 function stats(returns:number[],equity:number[],initial:number){const n=returns.length,m=returns.reduce((a,b)=>a+b,0)/n,sd=Math.sqrt(returns.reduce((s,r)=>s+(r-m)**2,0)/Math.max(1,n-1)),down=Math.sqrt(returns.reduce((s,r)=>s+Math.min(0,r)**2,0)/n);let peak=initial,dd=0;for(const v of equity){peak=Math.max(peak,v);dd=Math.max(dd,1-v/peak);}return {sessions:n,net_return:equity.at(-1)!/initial-1,nav:equity.at(-1),sharpe:sd>1e-12?m/sd*Math.sqrt(252):null,sortino:down>1e-12?m/down*Math.sqrt(252):null,max_drawdown:dd};}
 export function backtest(p:Plugin,d:Data,c:Costs){finite(c.capital,100,1e8);finite(c.cost_bps,0,100);finite(c.financing_apr,0,1);finite(c.fee_apr,0,.2);finite(c.benchmark_weight,0,1.5);const sig=signals(p,d),byDate=new Map(sig.filter(s=>s.ready).map(s=>[s.next_session,s]));
  const run=(benchmark:boolean)=>{let cash=c.capital,shares=0,totalCosts=0,realized=0,basis=0,previous=c.capital;const returns:number[]=[],nav:number[]=[],trades:unknown[]=[],dates:string[]=[];
   for(const [i,b]of d.bars.entries()){const s=byDate.get(b.date);if(!s)continue;const gap=i?Math.max(1,(Date.parse(b.date)-Date.parse(d.bars[i-1].date))/86400000):1;const finance=Math.max(0,-cash)*c.financing_apr*gap/365,fee=previous*c.fee_apr*gap/365;cash-=finance+fee;totalCosts+=finance+fee;
    const pre=cash+shares*b.open;if(pre<=0)throw Error('Capital agotado');const weight=benchmark?c.benchmark_weight:s.values.weight,cost=c.cost_bps/10000;let navAfter=pre;for(let j=0;j<16;j++)navAfter=pre-Math.abs(weight*navAfter-shares*b.open)*cost;
    const targetShares=weight*navAfter/b.open,delta=targetShares-shares,transaction=Math.abs(delta)*b.open*cost;
    if(delta>0){basis+=delta*b.open+transaction;}else if(delta<0&&shares>0){const soldBasis=basis*(-delta/shares);realized+=(-delta)*b.open-transaction-soldBasis;basis-=soldBasis;}
    cash-=delta*b.open+transaction;shares=targetShares;totalCosts+=transaction;
    const value=cash+shares*b.close;if(value<=0||!Number.isFinite(value))throw Error('Capital agotado');returns.push(value/previous-1);nav.push(value);dates.push(b.date);previous=value;
    trades.push({date:b.date,signal_date:s.date,price:b.open,weight,turnover:Math.abs(delta)*b.open,cost:transaction,financing:finance,fee,nav:value});
   }if(returns.length<20)throw Error('Se requieren al menos 20 sesiones de evaluación');return {...stats(returns,nav,c.capital),returns,dates,total_costs:totalCosts,realized_net_sales:realized,net_realized_after_carry:realized-totalCosts+trades.reduce((s:number,t)=>s+(t as {cost:number}).cost,0),unrealized:shares*d.bars.at(-1)!.close-basis,remaining_exposure:shares*d.bars.at(-1)!.close,trades};};
  const strategy=run(false),benchmark=run(true),n=strategy.returns.length,a=strategy.returns,b=benchmark.returns,ma=a.reduce((s,v)=>s+v,0)/n,mb=b.reduce((s,v)=>s+v,0)/n,vb=b.reduce((s,v)=>s+(v-mb)**2,0),cov=a.reduce((s,v,i)=>s+(v-ma)*(b[i]-mb),0),beta=vb>1e-15?cov/vb:null;
  return {schema:'HARPOON-XXII-RESEARCH-REPORT-1',plugin:{id:p.id,version:p.version,sha256:p.sha256},data:{symbol:d.symbol,kind:d.kind,source:d.source,asof:d.asof,calendar:d.calendar.source},costs:c,strategy,benchmark,beta,alpha_annual:beta===null?null:(ma-beta*mb)*252,last_signal:sig.at(-1),status:'EXPLORATORIO · SIN PROMOCIÓN',evidence:'Replay cronológico; no es walk-forward optimizado ni validación fuera de muestra. Benchmark de peso fijo, no riesgo equiparado. Tasa libre de riesgo 0.',orders_enabled:false,paid_tokens:0};
 }
}
