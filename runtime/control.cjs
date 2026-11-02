'use strict';
const vm=require('node:vm'),fs=require('node:fs'),path=require('node:path'),{randomUUID}=require('node:crypto');
const contract={};vm.createContext(contract);vm.runInContext(fs.readFileSync(path.join(__dirname,'../src/supervision_core.js'),'utf8'),contract);
const validate=value=>JSON.parse(JSON.stringify(contract.HXXI.configure(value)));
class CloudControl {
 constructor(store,engine,supervisor,lab){this.store=store;this.engine=engine;this.supervisor=supervisor;this.lab=lab;this.busy=false;this.manual=false;this.policy={hot:false,cold:false};this.events=[];this.lastPolicySync=0;
  const request=supervisor.request.bind(supervisor);
  supervisor.request=(url,method='GET',body)=>{if(method!=='GET'&&url!=='/v1/review-policy'&&!this.policy.hot&&!this.manual)throw Error('LiftOff: nuevas solicitudes GPT bloqueadas');return request(url,method,body);};
 }
 async load(){this.policy=await this.store.get('cloud-control-policy')||{hot:false,cold:false};this.events=await this.store.get('cloud-control-events')||[];if(this.lab){this.lab.state.enabled=this.policy.cold;await this.lab.save();}}
 async event(action,result){const row={id:randomUUID(),at:Date.now(),action,result};this.events.push(row);this.events=this.events.slice(-200);await this.store.put('cloud-control-events',this.events);}
 view(){return {policy:{...this.policy,cold:this.engine.agents25?.state.policy.researchOn??this.policy.cold},busy:this.busy,supervision_config:this.supervisor.config||null,events:this.events.slice(-30),reviews:this.supervisor.state?.reviews?.slice(-20)||[],windows:this.supervisor.state?.windows?.slice(-20)||[],trials:this.lab?.state?.trials?.slice(-20)||[],cold_supported:!!this.lab||typeof this.engine.studyWarRoom3==='function'};}
 async exclusive(action,fn){if(this.busy||this.supervisor.busy||this.lab?.busy)throw Error('Hay un ciclo en curso; espera antes de modificar su configuración');this.busy=true;try{const value=await fn();await this.event(action,'COMPLETADO');return value;}catch(e){await this.event(action,'RECHAZADO: '+e.message);throw e;}finally{this.busy=false;}}
 async gates(next){
  if(!next||Object.keys(next).some(k=>!['hot','cold'].includes(k))||typeof next.hot!=='boolean'||typeof next.cold!=='boolean')throw Error('Se requieren hot y cold booleanos');
  if(next.cold&&!this.lab&&typeof this.engine.studyWarRoom3!=='function')throw Error('Investigación cripto disponible en el sandbox original; no en este adaptador');
  // LiftOff takes precedence even during in-flight research. Do not clear budgets or pending IDs.
  if(!next.hot&&!next.cold){if(this.engine.ensureAgents25)await (await this.engine.ensureAgents25()).configure({researchOn:false});this.policy={hot:false,cold:false};await this.store.put('cloud-control-policy',this.policy);if(this.lab){this.lab.state.enabled=false;await this.lab.save();}await this.event('LiftOff','Nuevos ciclos y promociones detenidos; consultas enviadas pueden tener coste');return this.view();}
  return this.exclusive('LiftOn',async()=>{if(next.hot&&!this.supervisor.credentials)throw Error('Gateway GPT no configurado');if(next.hot){await this.syncPolicy(true);if(!this.supervisor.config.enabled)throw Error('Guarda una política GPT habilitada antes de LiftOn');}if(this.engine.ensureAgents25)await (await this.engine.ensureAgents25()).configure({researchOn:next.cold});this.policy={...next};await this.store.put('cloud-control-policy',this.policy);if(this.lab){this.lab.state.enabled=next.cold;await this.lab.save();}return this.view();});
 }
 async syncPolicy(force=false){if(!force&&Date.now()-this.lastPolicySync<60000)return;const h=await this.supervisor.request('/v1/health');if(!h.supervision?.policy)throw Error('Gateway sin política de supervisión');const c=validate(h.supervision.policy);await this.store.put('xxi-supervision-config',c);await this.supervisor.load();this.supervisor.health=h;this.supervisor.healthAt=Date.now();this.lastPolicySync=Date.now();}
 async configure(value){return this.exclusive('Configurar GPT',async()=>{const c=validate(value);await this.supervisor.request('/v1/review-policy','POST',c);await this.store.put('xxi-supervision-config',c);await this.supervisor.load();this.lastPolicySync=0;return this.view();});}
 async research(value){return this.exclusive('Configurar laboratorio',async()=>{
  if(!this.lab)throw Error('Laboratorio remoto no disponible para cripto');
  const allowed=['budget','max_iterations','provider','task','auto_paper','allow_strategy_entries'];
  if(!value||Object.keys(value).some(k=>!allowed.includes(k)))throw Error('Parámetro de laboratorio desconocido');
  const next={...Object.fromEntries(allowed.map(k=>[k,this.lab.state[k]])),...value};
  if(!['local','openai'].includes(next.provider)||!['operations','profitability','sandbox'].includes(next.task)||typeof next.auto_paper!=='boolean'||typeof next.allow_strategy_entries!=='boolean')throw Error('Contrato de laboratorio inválido');
  if(next.provider==='openai'&&!this.lab.credentials)throw Error('Gateway GPT no configurado');
  await this.lab.configure(next);return this.view();
 });}
 async review(){return this.exclusive('Revisar una vez',async()=>{if(!this.supervisor.credentials)throw Error('Gateway GPT no configurado');await this.syncPolicy(true);this.manual=true;try{await this.supervisor.pulse(true);}finally{this.manual=false;}return this.view();});}
 async study(){return this.exclusive('Investigar una vez',async()=>{if(this.engine.studyWarRoom3)return this.engine.studyWarRoom3();if(!this.lab)throw Error('No hay laboratorio remoto cripto');await this.lab.cycle(true);return this.view();});}
 async tick(){if(this.busy||this.supervisor.busy||this.lab?.busy)return;this.busy=true;try{
  if(this.policy.hot){await this.syncPolicy();await this.supervisor.pulse();}
  else if(this.supervisor.state?.pending){await this.supervisor.pulse();} // Only GET reconciliation permitted by request wrapper.
 }catch(e){await this.event('Supervisión',e.message);}finally{this.busy=false;}
 // A GPT outage does not prevent the independent local laboratory or broker exits.
 if(this.policy.cold&&this.lab)await this.lab.pulse();
 }
}
async function readBody(req){if(req.headers['content-type']?.split(';')[0]!=='application/json')throw Error('Usa application/json');let raw='';for await(const chunk of req){raw+=chunk;if(Buffer.byteLength(raw)>30000)throw Error('JSON demasiado grande');}const value=JSON.parse(raw);if(!value||Array.isArray(value)||typeof value!=='object')throw Error('Objeto JSON requerido');return value;}
module.exports={CloudControl,validate,readBody};
