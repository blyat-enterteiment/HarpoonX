'use strict';
class VaultStore {
 constructor(){this.db=null;}
 async open(){this.db=await new Promise((resolve,reject)=>{const r=indexedDB.open('harpoon-vi',1);r.onupgradeneeded=()=>r.result.createObjectStore('records');r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);});return this;}
 async get(k){return new Promise((resolve,reject)=>{const tx=this.db.transaction('records','readonly'),r=tx.objectStore('records').get(k);r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);});}
 async put(k,v){return new Promise((resolve,reject)=>{const tx=this.db.transaction('records','readwrite');tx.objectStore('records').put(v,k);tx.oncomplete=()=>resolve();tx.onabort=tx.onerror=()=>reject(tx.error||Error('No se pudo persistir el estado'));});}
 async remove(k){return new Promise((resolve,reject)=>{const tx=this.db.transaction('records','readwrite');tx.objectStore('records').delete(k);tx.oncomplete=()=>resolve();tx.onabort=tx.onerror=()=>reject(tx.error);});}
 async saveKeys(mode,keys){let key=await this.get('vault-key');if(!key){key=await crypto.subtle.generateKey({name:'AES-GCM',length:256},false,['encrypt','decrypt']);await this.put('vault-key',key);}const iv=crypto.getRandomValues(new Uint8Array(12)),data=new TextEncoder().encode(JSON.stringify(keys)),cipher=await crypto.subtle.encrypt({name:'AES-GCM',iv,additionalData:new TextEncoder().encode(mode)},key,data);await this.put('keys-'+mode,{iv,cipher});}
 async loadKeys(mode){const v=await this.get('keys-'+mode),key=await this.get('vault-key');if(!v||!key)return null;const data=await crypto.subtle.decrypt({name:'AES-GCM',iv:v.iv,additionalData:new TextEncoder().encode(mode)},key,v.cipher);return JSON.parse(new TextDecoder().decode(data));}
}
class AlpacaError extends Error {
 constructor(status,message,details={}){super(message);this.name='AlpacaError';this.status=status;Object.assign(this,details);}
}
class DirectAlpaca {
 constructor(mode,keys){this.mode=mode;this.keys=keys;this.host=mode==='live'?'https://api.alpaca.markets':'https://paper-api.alpaca.markets';this.requests=[];this.marketRequests=[];this.rateState={};this.transportQueues={};this.diagnostics={};this.onstatus=null;this.retryDelay=600;this.timeoutMs=15000;}
 endpoint(path){
  const clean=path.split('?')[0];
  const names={'/v2/account':'Cuenta','/v2/clock':'Reloj del mercado','/v2/positions':'Posiciones','/v2/orders':'Órdenes','/v2/calendar':'Calendario','/v2/stocks/bars':'Barras de mercado','/v2/stocks/quotes/latest':'Cotizaciones','/v1beta1/screener/stocks/movers':'Universo dinámico','/v2/account/activities':'Actividades','/v2/account/portfolio/history':'Patrimonio histórico','/v1/corporate-actions':'Acciones corporativas'};
  return {clean,label:names[clean]||(clean.startsWith('/v2/orders')?'Conciliación de órdenes':clean.startsWith('/v2/assets/')?'Instrumentos':'Consulta Alpaca')};
 }
 record(details){this.diagnostics[details.label]={...details,at:new Date().toISOString()};this.onstatus?.();}
 priority(path,method,body,market){if(method==='DELETE'||method==='PATCH'||body?.side==='sell')return 0;if(!market&&/^\/v2\/(account$|positions|clock|orders)/.test(path.split('?')[0]))return method==='GET'?1:2;if(market&&path.includes('quotes'))return 1;return 3;}
 async request(path,method='GET',body,market=false){
  const host=market?'data':'trading',priority=this.priority(path,method,body,market);this.transportQueues??={};const q=this.transportQueues[host]??={pending:[],running:0,low:0};
  return new Promise((resolve,reject)=>{q.pending.push({priority,run:()=>this.transport(path,method,body,market,priority),resolve,reject});q.pending.sort((a,b)=>a.priority-b.priority);this.drain(host);});
 }
 drain(host){const q=this.transportQueues[host];while(q.running<3){const index=q.pending.findIndex(t=>t.priority<=1||q.low<1);if(index<0)return;const task=q.pending.splice(index,1)[0],low=task.priority>1;q.running++;if(low)q.low++;task.run().then(task.resolve,task.reject).finally(()=>{q.running--;if(low)q.low--;this.drain(host);});}}
 async transport(path,method='GET',body,market=false,priority=3){
  if(!path.startsWith('/')||path.startsWith('//'))throw Error('Ruta no permitida');
  const {clean,label}=this.endpoint(path),readOnly=method==='GET',host=market?'https://data.alpaca.markets':this.host,details={method,path:clean,label,host,readOnly};
  for(let attempt=1;attempt<=(readOnly?2:1);attempt++){
   const quotaKey=market?'marketRequests':'requests',bucket=market?'data':'trading',cap=market?110:180,now=Date.now();this[quotaKey]=this[quotaKey].filter(t=>t>now-60000);const rate=this.rateState[bucket]||{};
   const ceiling=priority<=1?cap:cap-(market?20:30);
   if(this[quotaKey].length>=ceiling||(rate.blockedUntil||0)>now){const e=new AlpacaError(429,label+' · cuota reservada o límite observado; reintento en siguiente ciclo',{...details,retryable:true,kind:'rate_limit',not_sent:true});this.record({...details,state:'error',status:429,message:e.message,attempt});throw e;}
   this[quotaKey].push(now);
   const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),clean==='/v2/stocks/bars'?this.timeoutMs*2:this.timeoutMs),headers={'APCA-API-KEY-ID':this.keys.key,'APCA-API-SECRET-KEY':this.keys.secret};
   if(body!==undefined)headers['Content-Type']='application/json';
   this.record({...details,state:'pending',status:null,attempt,message:attempt===1?'Consultando…':'Reintentando consulta…'});
   let failure=null;
   try{
    const r=await fetch(host+path,{method,headers,body:body===undefined?undefined:JSON.stringify(body),signal:controller.signal,mode:'cors',credentials:'omit',redirect:'error',cache:'no-store'}),raw=await r.text();
    const remaining=r.headers?.get?.('X-RateLimit-Remaining'),reset=r.headers?.get?.('X-RateLimit-Reset'),retry=r.headers?.get?.('Retry-After');const meta={remaining:remaining!==null&&remaining!==undefined?Number(remaining):null,reset:reset?Number(reset)*1000:null};
    if(r.status===429||meta.remaining===0){const retryMs=retry?(Number.isFinite(Number(retry))?Number(retry)*1000:Date.parse(retry)-Date.now()):0;meta.blockedUntil=Math.max(Date.now()+1000,meta.reset||0,Date.now()+(retryMs>0?retryMs:60000));}this.rateState[bucket]=meta;
    if(!r.ok)throw new AlpacaError(r.status,label+' · HTTP '+r.status+(r.status===401?' · revisa las claves y el entorno seleccionado':r.status===403?' · revisa los permisos de cuenta o del feed':r.status===429?' · límite de solicitudes':''),{...details,retryable:[408,429].includes(r.status)||r.status>=500,kind:'http'});
    let data;try{data=raw?JSON.parse(raw):null;}catch{throw new AlpacaError(r.status,label+' · respuesta JSON no válida',{...details,retryable:false,kind:'invalid_response'});}
    this.record({...details,state:'ok',status:r.status,attempt,message:'Confirmado'});return data;
   }catch(error){
    const timed=controller.signal.aborted;
    failure=error instanceof AlpacaError?error:new AlpacaError(0,label+(timed?' · tiempo de espera agotado':' · conexión interrumpida o bloqueada por el navegador')+(readOnly?'. Falló una consulta de lectura.':'. Respuesta de una operación no confirmada; se conciliará antes de volver a actuar.'),{...details,retryable:true,kind:timed?'timeout':'network'});
    this.record({...details,state:'error',status:failure.status,attempt,message:failure.message,kind:failure.kind});
   }finally{clearTimeout(timer);}
   if(!readOnly||!failure.retryable||attempt===2)throw failure;
   await new Promise(resolve=>setTimeout(resolve,this.retryDelay===0?0:this.retryDelay+Math.floor(Math.random()*150)));
  }
 }
 async bars(symbols,timeframe,start,end,feed){const all={},tokens=new Set();let token='';for(let page=0;page<50;page++){const q=new URLSearchParams({symbols:symbols.join(','),timeframe,start,end,feed,adjustment:'split',limit:'10000',sort:'asc'});if(token)q.set('page_token',token);const r=await this.request('/v2/stocks/bars?'+q,'GET',undefined,true);for(const [s,rows] of Object.entries(r.bars||{}))all[s]=(all[s]||[]).concat(rows);if(!r.next_page_token)return all;token=r.next_page_token;if(tokens.has(token))throw Error('Paginación de barras repetida');tokens.add(token);}throw Error('Historial de barras truncado: reduce el universo');}
 async activities(after,until){const rows=[],tokens=new Set();let token='';for(let i=0;i<200;i++){const q=new URLSearchParams({after,until,direction:'asc',page_size:'100'});if(token)q.set('page_token',token);const a=await this.request('/v2/account/activities?'+q);if(!Array.isArray(a))throw Error('Actividades no válidas');rows.push(...a);if(a.length<100)return rows;token=a.at(-1).id;if(tokens.has(token))throw Error('Paginación de actividades repetida');tokens.add(token);}throw Error('Auditoría incompleta: más de 20,000 actividades; reduce el periodo');}
}
