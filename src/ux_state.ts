/** Read-only presentation model. It has no broker, credentials or order authority. */
namespace HUX {
 export type Code = 'ON' | 'OFF' | 'WAIT' | 'ERROR';
 export interface Status {code:Code; label:string; reason:string}
 export interface EngineState {connected:boolean; armed:boolean; reconciled:boolean; halt:string; lastTick:number; staleMs:number; now:number; marketOpen:boolean; pending:boolean; visible:boolean; cryptoBook:boolean}
 export function state(code:Code,reason:string):Status{return {code,label:code==='WAIT'?'EN ESPERA':code==='ERROR'?'BLOQUEADO':code,reason};}
 export function entries(e:EngineState):Status {
  if(!e.connected)return state('OFF','Conecta la cuenta de este libro.');
  if(e.halt)return state('ERROR',e.halt);
  if(!e.reconciled)return state('WAIT','La cuenta aún no está conciliada.');
  if(!e.armed&&!e.pending)return state('OFF','Entradas pausadas. Las salidas tienen su propio estado.');
  if(e.cryptoBook&&!e.visible)return state('WAIT','Vuelve a esta pestaña para habilitar entradas cripto.');
  if(!e.cryptoBook&&!e.marketOpen)return state('WAIT','Mercado cerrado; espera la sesión regular.');
  if(!e.lastTick||e.now-e.lastTick>e.staleMs)return state('WAIT','Sin ciclo reciente confirmado. Revisa conexión y datos.');
  if(!e.armed)return state('WAIT','Inicio solicitado; esperando datos válidos.');
  return state('ON','Motor habilitado y ciclo reciente. Espera una señal elegible antes de enviar órdenes.');
 }
 export function exits(e:EngineState,count:number):Status {
  if(!count)return state('OFF','No hay campañas abiertas que gestionar.');
  if(!e.connected||!e.reconciled||!e.lastTick||e.now-e.lastTick>e.staleMs)return state('ERROR','Hay posiciones y no se confirma gestión dinámica reciente. Revisa cuenta y órdenes.');
  if(e.halt)return state('WAIT','Hay campañas abiertas y una alerta del motor. Comprueba las salidas en Cuenta y órdenes.');
  return state('ON',count+' campañas en seguimiento. Pausar entradas no desactiva sus salidas.');
 }
 export interface Manifest {id:string;version:string;book:string;family:string;name:string;binding:string}
 export function merge<T extends Manifest>(current:T[],incoming:T[],stable:(m:T)=>string):{catalog:T[];added:number;duplicates:number}{
  const catalog=current.slice();let added=0,duplicates=0;
  for(const m of incoming){const old=catalog.find(x=>x.id===m.id&&x.version===m.version);if(old){if(stable(old)!==stable(m))throw Error('Versión inmutable: '+m.id+'@'+m.version);duplicates++;}else{catalog.push(m);added++;}}
  if(catalog.length>150)throw Error('Máximo 150 plugins cargados.');
  return {catalog,added,duplicates};
 }
 export function rootJson(name:string,path=''):boolean{return /\.json$/i.test(name)&&(!path||path.split('/').filter(Boolean).length===2);}
}
