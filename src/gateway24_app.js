'use strict';
// Transport adapter only: native research validation, orders and LiftOn gates stay intact.
const Gateway24={
 available:false,session:null,busy:false,initialized:false,origin:window.location.origin,
 credentials(){return this.available?{url:this.origin,token:'integrated-session-no-bearer-secret',mode:'integrated'}:null;},
 active(){return this.available&&HGateway24.connected(this.session);},
 async request(path,method='GET',body){
  HGateway24.route(path);if(!HGateway24.eligible(this.origin))throw Error('Abre HARPOON desde el servicio integrado HTTPS.');
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),25000);
  const headers={'Content-Type':'application/json'};if(method!=='GET'&&this.session?.csrf)headers['X-Harpoon-CSRF']=this.session.csrf;
  try{const r=await fetch(this.origin+path,{method,headers,body:body===undefined?undefined:JSON.stringify(body),signal:controller.signal,credentials:'same-origin',redirect:'error',cache:'no-store'});
   const data=await r.json();if(!r.ok){const error=Error(data.error||(r.status===401?'Inicia sesión en el gateway integrado.':'Gateway HTTP '+r.status));error.status=r.status;if(r.status===401){this.session=null;this.render();}throw error;}return data;
  }finally{clearTimeout(timer);}
 },
 attach(){if(!this.available)return;for(const s of [lab,securitiesSupervisor,cryptoSupervisor]){s.credentials=this.credentials();if('healthAt'in s){s.health=null;s.healthAt=0;}}for(const id of ['xxiUrl','labUrl'])$(id).value=this.origin;},
 render(){if(!this.initialized)return;const active=this.active();text('g24State',!this.available?'SIN SERVICIO':active?'SESIÓN ABIERTA':'IDENTIFICARSE');$('g24State').className='ux-chip '+(active?'loaded':this.available?'wait':'off');$('g24Login').hidden=!this.available||active;$('g24Config').hidden=!active;$('g24Standalone').hidden=this.available;if($('g24External'))$('g24External').hidden=this.available;
  text('g24Summary',this.available?'Gateway detectado automáticamente en '+this.origin+'.':'No se detectó un gateway integrado en esta dirección.');
  if(this.available){text('uxGPTCredentialState',active?'GATEWAY INTEGRADO':'SESIÓN CERRADA');$('uxGPTCredentialState').className='ux-chip '+(active?'loaded':'off');}
 },
 populate(data){const c=data.config;for(const [id,key]of Object.entries({g24Model:'model',g24Input:'input_rate',g24Output:'output_rate',g24Cached:'cached_rate',g24Write:'cache_write_rate',g24Monthly:'monthly_cap',g24Run:'run_cap'}))$(id).value=c[key];$('g24Key').required=!data.configured;text('g24Detail',data.configured?'Clave guardada en el gateway. Comprobar valida acceso al modelo; una respuesta de generación aún requiere evidencia y LiftOn.':'Gateway listo. Guarda tu API key; el acceso ya no necesita una URL adicional.');},
 async detect(){if(!HGateway24.eligible(this.origin)){this.render();return;}try{const b=await this.request('/v1/bootstrap');if(b.schema!=='HARPOON-INTEGRATED-24'||!b.same_origin)throw Error('Servicio no compatible');this.available=true;this.attach();try{this.session=await this.request('/v1/session');this.populate(await this.request('/v1/config'));}catch(e){if(e.status!==401)throw e;}}catch(e){text('g24Detail','No se confirmó el gateway: '+e.message);}this.render();},
 async action(fn){if(this.busy)return;this.busy=true;for(const b of $('g24Panel').querySelectorAll('button'))b.disabled=true;try{await fn();}catch(e){text('g24Detail',e.message);notify(e.message,true);}finally{this.busy=false;for(const b of $('g24Panel').querySelectorAll('button'))b.disabled=false;this.render();}},
 async initialize(){if(!h23State.ready||!uxControlReady){setTimeout(()=>this.initialize(),100);return;}
  $('uxGPTCredentialsForm').before($('g24Panel'));const details=document.createElement('details');details.className='g24-external';details.id='g24External';const summary=document.createElement('summary');summary.textContent='Gateway externo · conexión anterior';details.append(summary);$('uxGPTCredentialsForm').before(details);details.append($('uxGPTCredentialsForm'));
  text('uxGPTCredentialDetail','La configuración de GPT está centralizada aquí. COLD y HOT conservan sus controles en Loop recursivo.');
  $('uxCredentialsIntro').querySelector('p').textContent='Alpaca usa API Key ID + Secret. El gateway integrado guarda la API key de OpenAI y comparte presupuesto entre COLD y HOT.';
  const externalSubmit=$('uxGPTCredentialsForm').onsubmit;$('uxGPTCredentialsForm').onsubmit=e=>{if(this.available){e.preventDefault();notify('Estás usando el gateway integrado. La conexión externa anterior se conserva sin modificar.',true);return;}externalSubmit(e);};
  $('g24Login').onsubmit=e=>{e.preventDefault();this.action(async()=>{const token=$('g24Password').value;$('g24Password').value='';this.session=await this.request('/v1/session','POST',{token});this.attach();this.populate(await this.request('/v1/config'));});};
  $('g24Config').onsubmit=e=>{e.preventDefault();this.action(async()=>{if(lab.state?.pending||securitiesSupervisor.state?.pending||cryptoSupervisor.state?.pending)throw Error('Concilia las consultas pendientes antes de cambiar configuración.');const c={api_key:$('g24Key').value.trim(),model:$('g24Model').value.trim(),input_rate:Number($('g24Input').value),output_rate:Number($('g24Output').value),cached_rate:Number($('g24Cached').value),cache_write_rate:Number($('g24Write').value),monthly_cap:Number($('g24Monthly').value),run_cap:Number($('g24Run').value)};$('g24Key').value='';this.populate(await this.request('/v1/config','POST',c));this.attach();});};
  $('g24Check').onclick=()=>this.action(async()=>{const result=await this.request('/v1/provider-check','POST',{});text('g24Detail',result.ok?'Clave y acceso a '+result.model+' confirmados. 0 tokens de generación. No prueba todavía una respuesta de Responses ni rentabilidad.':'No confirmado');});
  $('g24Logout').onclick=()=>this.action(async()=>{await this.request('/v1/logout','POST',{});this.session=null;text('g24Detail','Sesión GPT cerrada. La configuración, los costes y las reservas permanecen; la gestión del bróker continúa.');});
  $('g24Retry').onclick=()=>this.action(()=>this.detect());this.initialized=true;await this.detect();if(!this.available)details.open=true;
 }
};
for(const Class of [LabController,WindowSupervisor]){
 const load=Class.prototype.load,request=Class.prototype.request;
 Class.prototype.load=async function(...args){const result=await load.apply(this,args);if(Gateway24.available)this.credentials=Gateway24.credentials();return result;};
 Class.prototype.request=async function(path,method='GET',body){if(this.credentials?.mode==='integrated'){if(!Gateway24.active())throw Error('Sesión GPT cerrada: entra al gateway desde API keys y conexiones.');return Gateway24.request(path,method,body);}return request.call(this,path,method,body);};
}
Gateway24.initialize();
