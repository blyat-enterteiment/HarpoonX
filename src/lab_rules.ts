namespace HLab {
 export type Family='canonical_exit'|'opening_range'|'trend_pullback'|'vwap_reclaim'|'option_context';
 export interface Recipe {name:string;hypothesis:string;family:Family;min_rvol:number;momentum_bps:number;tp1_r:number;tp2_r:number;trail_atr:number;lock_fraction:number;tp1_fraction:number;tp2_fraction:number;hold_hours:number;reentry:boolean;stagnation_minutes:number;progress_r:number;selection_filter:string;trailing_mode:string;exit_layout:string;}
 export const bounds:Record<string,[number,number]>=HContract.bounds;
 export const families:Family[]=HContract.families as Family[];
 export function validate(value:unknown):Recipe {
  if(!value||typeof value!=='object'||Array.isArray(value))throw Error('Receta inválida');
  const r={...HContract.defaults,...value as Record<string,unknown>},keys=['name','hypothesis','family','hold_hours','reentry',...Object.keys(HContract.enums),...Object.keys(bounds)];
  if(Object.keys(r).length!==keys.length||Object.keys(r).some(k=>!keys.includes(k)))throw Error('La receta contiene campos no permitidos');
  if(typeof r.name!=='string'||!r.name.trim()||r.name.length>80||typeof r.hypothesis!=='string'||r.hypothesis.length>1200)throw Error('Nombre o hipótesis inválidos');
  if(!families.includes(r.family as Family)||![1.5,24,48,72].includes(r.hold_hours as number)||typeof r.reentry!=='boolean')throw Error('Familia, plazo o reentrada inválidos');
  for(const [key,[low,high]] of Object.entries(bounds))if(typeof r[key]!=='number'||!Number.isFinite(r[key])||(r[key] as number)<low||(r[key] as number)>high)throw Error('Fuera de límites: '+key);
  if((r.tp2_r as number)<=(r.tp1_r as number)||(r.tp1_fraction as number)+(r.tp2_fraction as number)>HContract.partial_max)throw Error('Objetivos o fracciones incompatibles');
  for(const [key,values] of Object.entries(HContract.enums))if(!values.includes(r[key] as string))throw Error('Fuera de contrato: '+key);
  return structuredClone(r) as unknown as Recipe;
 }
 export function taskGuard(r:Recipe,reference:Recipe,task:string):void {if(!['operations','profitability','sandbox'].includes(task))throw Error('Tarea desconocida');const fields=task==='operations'?Object.keys(reference):task==='profitability'?['family','min_rvol','momentum_bps','reentry','selection_filter']:[];if(fields.some(k=>(r as unknown as Record<string,unknown>)[k] !== (reference as unknown as Record<string,unknown>)[k]))throw Error('La propuesta excede el alcance de esta interacción');}
 export function profile(r:Recipe){return {...r,selective:false,prediction_floor:0};}
 export function eligible(f:Record<string,number>,r:Recipe,breakout:number,chase:number):boolean {return HPEntry.eligible(f,r,breakout,chase);}
 export function diff(a:Record<string,unknown>,b:Recipe):Array<{field:string;before:unknown;after:unknown}>{return Object.entries(b).filter(([k,v])=>!['name','hypothesis'].includes(k)&&a[k]!==v).map(([field,after])=>({field,before:a[field]??null,after}));}
 export function stable(x:unknown):string {if(x===null||typeof x!=='object')return JSON.stringify(x);if(Array.isArray(x))return '['+x.map(stable).join(',')+']';const o=x as Record<string,unknown>;return '{'+Object.keys(o).sort().map(k=>JSON.stringify(k)+':'+stable(o[k])).join(',')+'}';}
 export function localCandidate(base:Recipe,iteration:number):Recipe {return HPEntry.localCandidate(base,iteration);}
}
