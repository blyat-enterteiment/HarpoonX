/** XII: pure deterministic primitives. No network, orders or model-generated code. */
namespace HXII {
 export const VERSION='12.0.0';
 export const POLICY='XII-EVENT-1';
 export const REQUIRED=384; // 63 training + 3 embargo + 252 OOS + 3 embargo + 63 prospective
 export const FEATURES=['rvol','momentum_bps','spread_bps','volume_acceleration','atr_pct','vwap_distance','sector_relative_bps','session_minutes'] as const;
 export type Feature=Record<string,unknown>;
 export interface TrainingRow {at:number;end:number;day:string;feature:Feature;target:number}
 export interface Selector {version:string;through:number;cutoff:number;n:number;days:number;calibration_n:number;means:number[];scales:number[];weights:number[];bias:number;margin:number;features:string[];basis:string}
 const avg=(a:number[])=>a.length?a.reduce((x,y)=>x+y,0)/a.length:0;
 const variance=(a:number[])=>{const m=avg(a);return a.length>1?a.reduce((v,x)=>v+(x-m)**2,0)/(a.length-1):0;};
 export function vector(f:Feature):number[]|null {const x=FEATURES.map(k=>f[k]);return x.every(v=>typeof v==='number'&&Number.isFinite(v))?x as number[]:null;}
 function linear(a:number[][],b:number[]):number[] {const m=a.map((r,i)=>[...r,b[i]]),n=b.length;for(let j=0;j<n;j++){let best=j;for(let k=j+1;k<n;k++)if(Math.abs(m[k][j])>Math.abs(m[best][j]))best=k;[m[j],m[best]]=[m[best],m[j]];const d=m[j][j];if(Math.abs(d)<1e-12)throw Error('Singular ridge system');for(let k=j;k<=n;k++)m[j][k]/=d;for(let i=0;i<n;i++)if(i!==j){const w=m[i][j];for(let k=j;k<=n;k++)m[i][k]-=w*m[j][k];}}return m.map(r=>r[n]);}
 export function fitSelector(input:TrainingRow[],cutoff:number):Selector|null {
  const rows=input.filter(r=>r.at<cutoff&&r.end<cutoff&&r.end>=r.at&&Number.isFinite(r.target)&&Math.abs(r.target)<=20&&vector(r.feature)).sort((a,b)=>a.at-b.at),days=[...new Set(rows.map(r=>r.day))].sort();
  if(rows.length<240||days.length<40)return null;
  const split=days[Math.floor(days.length*.75)],train=rows.filter(r=>r.day<split),cal=rows.filter(r=>r.day>=split);
  if(train.length<160||cal.length<40)return null;
  const xs=train.map(r=>vector(r.feature) as number[]),means=FEATURES.map((_,j)=>avg(xs.map(x=>x[j]))),scales=means.map((_,j)=>Math.max(1e-6,Math.sqrt(variance(xs.map(x=>x[j])))));
  const norm=(x:number[])=>[1,...x.map((v,j)=>Math.max(-5,Math.min(5,(v-means[j])/scales[j])))],{a,b}=HTensor.ridgeSystem(HTensor.design(xs,means,scales),train.map(r=>r.target),10);
  const weights=linear(a,b),daily=new Map<string,number[]>();for(const r of cal){const z=norm(vector(r.feature) as number[]),error=r.target-z.reduce((v,x,j)=>v+x*weights[j],0);daily.set(r.day,[...(daily.get(r.day)||[]),error]);}
  const residuals=[...daily.values()].map(avg),bias=avg(residuals),margin=1.96*Math.sqrt(variance(residuals)/Math.max(1,residuals.length));
  return {version:VERSION,cutoff,through:Math.max(...rows.map(r=>r.end)),n:rows.length,days:days.length,calibration_n:cal.length,means,scales,weights,bias,margin,features:[...FEATURES],basis:'Ridge lambda=10; chronological calibration by day. Conservative score, not a guaranteed confidence bound.'};
 }
 export function selection(f:Feature,m:Selector|null|undefined,at:number){
  const x=vector(f),bad={eligible:false,estimate:null,lower:null,reason:'MODELO / CARACTERÍSTICAS INSUFICIENTES'};
  if(!x||!m||m.version!==VERSION||m.features.join()!==FEATURES.join()||m.through>=at||m.weights.length!==9||m.means.length!==8||m.scales.length!==8||![...m.weights,...m.means,...m.scales,m.bias,m.margin].every(Number.isFinite)||m.scales.some(v=>v<=0))return bad;
  const z=x.map((v,j)=>(v-m.means[j])/m.scales[j]);if(z.some(v=>Math.abs(v)>4))return {...bad,reason:'DERIVA DE CARACTERÍSTICAS'};
  const estimate=m.weights[0]+z.reduce((v,x,j)=>v+x*m.weights[j+1],0)+m.bias,lower=estimate-m.margin*Math.sqrt(1+z.reduce((a,b)=>a+b*b,0)/Math.max(1,m.n));
  return {eligible:lower>0,estimate,lower,reason:lower>0?'EXPECTATIVA CONSERVADORA POSITIVA':'EXPECTATIVA INSUFICIENTE'};
 }
 export function cluster(f:Feature):string {
  const s=String(f.symbol||''),factor=String(f.factor||'unclassified');
  if(['AAPL','MSFT','NVDA','AMD','TSLA','AMZN','META','GOOG','GOOGL'].includes(s)||['technology','semiconductors','nasdaq'].includes(factor))return 'growth';
  if(['sp500','dow','smallcap'].includes(factor))return 'broad_market';
  return factor==='unclassified'?'unknown':factor;
 }
 export interface Exposure {symbol:string;factor:string;leverage:number;nominal:number;risk:number}
 export function clusterRoom(f:Feature,active:Exposure[],budget:number,exposureCap=.6,riskCap=.01){const key=cluster(f),members=active.filter(p=>cluster(p as unknown as Feature)===key);return {cluster:key,nominal:Math.max(0,budget*exposureCap-members.reduce((v,p)=>v+p.nominal*p.leverage,0)),risk:Math.max(0,budget*riskCap-members.reduce((v,p)=>v+p.risk,0)),members:members.map(p=>p.symbol)};}
 export interface VolState {at:number;bid:number;rate:number;count:number}
 export function updateVol(prior:VolState|null|undefined,bid:number,at:number,entryAtr:number){
  if(!(bid>0&&entryAtr>0&&Number.isFinite(at)))return {state:prior||null,atr:entryAtr};
  let s:VolState={at,bid,rate:prior?.rate||0,count:prior?.count||0};
  if(prior&&at>prior.at&&at-prior.at<=60000){const dt=at-prior.at,decay=Math.exp(-dt/300000);s.rate=decay*prior.rate+(1-decay)*(bid-prior.bid)**2/dt;s.count=prior.count+1;}
  if(prior&&at<=prior.at)s=prior;
  const estimate=s.count>=12?1.596*Math.sqrt(s.rate*300000):entryAtr;
  return {state:s,atr:Math.max(entryAtr*.5,Math.min(entryAtr*2,estimate))};
 }
 export function bucket(f:Feature){const t=Number(f.session_minutes),d=Number(f.dollar_volume),rel=Number(f.relative_bps),mom=Number(f.momentum_bps);return {book:String(f.book||'unknown'),session:Number.isFinite(t)?t<90?'apertura':t<270?'media':'cierre':'sin dato',liquidity:Number.isFinite(d)?d<1e7?'1–10M':d<1e8?'10–100M':'>100M':'sin dato',regime:Number.isFinite(rel)&&Number.isFinite(mom)?mom>0&&rel>0?'impulso y fuerza relativa':mom>0?'impulso sin fuerza relativa':'sin impulso':'sin dato'};}
 export interface AttributionRow {id:string;symbol:string;feature:Feature;net:number|null;gross:number|null;risk:number;filled:boolean;decision:string;mfe:number|null;mae:number|null;hours:number|null;first_target_minutes:number|null;giveback:number|null;source:'broker'|'shadow'}
 export function attribution(rows:AttributionRow[]){
  const groups=new Map<string,{source:string;dimension:string;bucket:string;rows:AttributionRow[]}>();
  for(const r of rows)for(const [dimension,b]of Object.entries({...bucket(r.feature),decision:r.decision})){const key=r.source+':'+dimension+':'+b;const g=groups.get(key)||{source:r.source,dimension,bucket:b,rows:[]};g.rows.push(r);groups.set(key,g);}
  const summarize=(rs:AttributionRow[])=>{const valid=rs.filter(r=>r.filled&&r.net!==null),rsR=valid.filter(r=>r.risk>0).map(r=>(r.net as number)/r.risk),mean=(key:'mfe'|'mae'|'hours'|'first_target_minutes'|'giveback')=>{const v=valid.map(r=>r[key]).filter((x):x is number=>x!==null&&Number.isFinite(x));return v.length?avg(v):null;};return {signals:rs.length,filled:valid.length,net:valid.length?valid.reduce((v,r)=>v+(r.net as number),0):null,expectancy_r:rsR.length?avg(rsR):null,mfe:mean('mfe'),mae:mean('mae'),hours:mean('hours'),minutes_tp1:mean('first_target_minutes'),giveback_r:mean('giveback')};};
  return {broker:summarize(rows.filter(r=>r.source==='broker')),shadow:summarize(rows.filter(r=>r.source==='shadow')),groups:[...groups.values()].map(g=>({...g,rows:undefined,...summarize(g.rows)})),recent:rows.slice(-80).reverse(),basis:'Fills: ejecuciones confirmadas menos provisión conservadora. Sombras: contrafactuales muestreados por unidad, no dinero perdido. MFE retrospectivo no equivale a beneficio ejecutable.'};
 }
 export function variants<T extends Record<string,unknown>>(base:T):T[]{return HPCatalog.xiiVariants(base); }
 export function stage(closed:number,completeDays:number,net:number,drawdown:number,costsComplete:boolean){if(!costsComplete||net<=0||drawdown>.04)return .25;if(closed>=60&&completeDays>=60)return 1;if(closed>=30&&completeDays>=30)return .5;return .25;}
}
