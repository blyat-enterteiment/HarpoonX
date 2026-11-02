"use strict";
const fs=require('node:fs'),http=require('node:http'),{timingSafeEqual}=require('node:crypto');
const {DurableStore,loadRuntime,runtimeHealth}=require('./runner.cjs');
const {loadCrypto}=require('./crypto_runner.cjs');
const {CloudControl,readBody}=require('./control.cjs');
function secret(name){const f=process.env[name+'_FILE'];return f?fs.readFileSync(f,'utf8').trim():process.env[name]||'';}
async function main(){
 process.umask(0o077);
 const book=process.env.HARPOON_BOOK;
 if(!['equity','crypto'].includes(book))throw Error('Invalid book');
 const cfg=JSON.parse(fs.readFileSync(process.env.HARPOON_CONFIG||'/config/config.json','utf8'));
 if(cfg.execution_authority!=='dedicated_remote_account'||(book==='crypto'?cfg.mode:cfg.settings?.mode)!=='paper')throw Error('This installation accepts PAPER only');
 const token=secret('HARPOON_CONTROL_TOKEN');if(token.length<32)throw Error('Control secret missing');
 process.env.HARPOON_SERVICE_TOKEN=secret('HARPOON_SERVICE_TOKEN');
 const store=new DurableStore(process.env.HARPOON_RUNTIME_DB||'/data/runtime.sqlite');await store.open();
 const saved=await store.get('cloud-config');
 if(saved&&JSON.stringify(saved)!==JSON.stringify(cfg))throw Error('Configuration differs from persisted journal; reconcile before changing it');
 await store.put('cloud-config',cfg);
 let e,lab,supervisor;
 if(book==='crypto'){e=loadCrypto(store,cfg.strategy);if(cfg.plugins)e.plugins=e.validatePlugins(cfg.plugins);supervisor=e.supervisor;}
 else {({engine:e,lab,supervisor}=loadRuntime(store,cfg));}
 const keys={key:secret('APCA_API_KEY_ID'),secret:secret('APCA_API_SECRET_KEY')};
 if(!keys.key||!keys.secret)throw Error('Missing Alpaca keys');
 // Startup re-arms PAPER only when the operator has not persisted a pause.
 if(!cfg.expected_account_id)throw Error('Expected account required');
 const observed=await fetch('https://paper-api.alpaca.markets/v2/account',{headers:{'APCA-API-KEY-ID':keys.key,'APCA-API-SECRET-KEY':keys.secret},redirect:'error',signal:AbortSignal.timeout(15000)});
 if(!observed.ok||(await observed.json()).id!==cfg.expected_account_id)throw Error('Account binding mismatch');
 const start=process.env.HARPOON_START_PAPER==='1'&&!await store.get('cloud-paused');
 let control=null,agentControl=null,warroomControl=null;
 let stopping=false,maintenance=false,controlBusy=false,boot='connecting';
 const state=()=>({desk25:book==='crypto'?e.desk25?.()||null:null,book,mode:'paper',boot,armed:!!e.armed,halt:e.halt||null,...runtimeHealth(e),positions:e.positions?.length||0,orders:e.orders?.length||0,supervision:supervisor.state||null,research:lab?{status:lab.state?.status,spent:lab.state?.spent,config:{provider:lab.state?.provider,task:lab.state?.task,budget:lab.state?.budget,max_iterations:lab.state?.max_iterations,auto_paper:lab.state?.auto_paper,allow_strategy_entries:lab.state?.allow_strategy_entries}}:null,control:control?.view()||null,plugins:book==='crypto'?e.plugins||[]:['equity','etf'].map(b=>e.pluginFor?.(b)).filter(Boolean),campaigns:e.active?.()||[],economics:e.ledger?.xi?.economics||null});
 const server=http.createServer(async(req,res)=>{
  res.setHeader('Content-Type','application/json');res.setHeader('Cache-Control','no-store');
  const send=(code,x)=>{res.statusCode=code;res.end(JSON.stringify(x));};
  if(req.method==='GET'&&req.url==='/healthz')return send(200,{alive:true,boot});
  const a=Buffer.from(req.headers.authorization||''),b=Buffer.from('Bearer '+token);
  if(a.length!==b.length||!timingSafeEqual(a,b))return send(401,{error:'Unauthorized'});
  if(req.method==='GET'&&req.url==='/v1/state')return send(200,state());
  if(req.method==='POST'&&req.url==='/v1/warroom'){
   if(req.headers['x-harpoon-action']!=='1')return send(403,{error:'Explicit action header required'});
   if(!warroomControl||boot!=='connected')return send(409,{error:'War Room en preparación'});
   try{return send(200,await warroomControl.action(await require('./warroom3.cjs').readBody(req)));}catch(error){return send(409,{error:error.message});}
  }
  if(req.method==='POST'&&req.url==='/v1/agents'){
   if(req.headers['x-harpoon-action']!=='1')return send(403,{error:'Explicit action header required'});
   if(!agentControl||boot!=='connected')return send(409,{error:'Desk en preparación'});
   try{const value=await readBody(req);return send(200,await agentControl.action(value));}catch(error){return send(409,{error:error.message});}
  }
  if(req.method==='POST'&&['/v1/pause','/v1/resume'].includes(req.url)){
   if(req.headers['x-harpoon-action']!=='1')return send(403,{error:'Explicit action header required'});
   if(controlBusy||boot!=='connected')return send(409,{error:'Engine busy or disconnected'});
   controlBusy=true;
   try{
    if(req.url==='/v1/pause'){await store.put('cloud-paused',true);e.cancelPaperStart?.();e.armed=false;await e.pause();}
    else {if(book==='crypto')await e.resume();else await e.startPaper();await store.put('cloud-paused',false);}
    return send(200,state());
   }catch{return send(409,{error:'Native reconciliation gate prevented the action; inspect state'});}
   finally{controlBusy=false;}
  }
  if(req.method==='POST'&&['/v1/gates','/v1/supervision','/v1/research','/v1/review','/v1/study'].includes(req.url)){
   if(req.headers['x-harpoon-action']!=='1')return send(403,{error:'Explicit action header required'});
   if(!control||boot!=='connected')return send(409,{error:'Conexión en preparación'});
   try{const methods={'/v1/gates':'gates','/v1/supervision':'configure','/v1/research':'research','/v1/review':'review','/v1/study':'study'};const value=await readBody(req);return send(200,await control[methods[req.url]](value));}
   catch(e){return send(409,{error:e.message});}
  }
  return send(404,{error:'Not found'});
 });
 server.listen(Number(process.env.PORT||8080),process.env.BIND_HOST||'0.0.0.0');
 // Parent process monitors liveness; pauses, stale prices and absent signals do not cause restarts.
 if(book==='crypto')await e.connect(keys,'paper',start);else await e.connect(keys,{startPaper:start});
 await supervisor.load();
 if(book==='crypto'&&cfg.autonomy&&!await store.get('autonomy3-installed-'+e.scope)){await e.configureAutonomy3(cfg.autonomy);await store.put('autonomy3-installed-'+e.scope,true);}
 if(cfg.supervision&&!await store.get('cloud-supervision-configured')){
  try{await supervisor.request('/v1/review-policy','POST',cfg.supervision);await store.put('xxi-supervision-config',cfg.supervision);await store.put('cloud-supervision-configured',true);await supervisor.load();}
  catch{console.error(JSON.stringify({event:'supervision_unavailable',trading_unaffected:true}));}
 }
 if(lab){await lab.load();if(!await store.get('cloud-lab-configured')){Object.assign(lab.state,{enabled:false,auto_paper:false},cfg.research||{});await lab.save();await store.put('cloud-lab-configured',true);}}
 control=new CloudControl(store,e,supervisor,lab);await control.load();if(book==='crypto'&&e.ensureAgents25)agentControl=require('./agents25.cjs').attach(e);if(book==='crypto'){await e.ensureOptions3();warroomControl=require('./warroom3.cjs').attach(e);}boot='connected';
 const timer=setInterval(async()=>{
  if(stopping||maintenance)return;maintenance=true;
  try{
   if(!await store.lease(e.leaseName)){e.locked=false;e.stop('Lease lost');throw Error('lease');}
   if(warroomControl)warroomControl.pulse().catch(()=>console.error('{"event":"warroom_cycle_error"}'));
   if(agentControl)agentControl.pulse().catch(()=>console.error('{"event":"agent_cycle_error"}'));
   control.tick().catch(()=>console.error('{"event":"control_cycle_error"}'));
   await e.save();console.log(JSON.stringify({event:'pulse',...state()}));
  }catch{e.armed=false;console.error('{"event":"persistence_or_lease_error"}');process.exitCode=1;await close();}
  finally{maintenance=false;}
 },5000);
 async function close(){
  if(stopping)return;stopping=true;e.autonomy3?.stop();clearInterval(timer);e.cancelPaperStart?.();e.armed=false;e.connected=false;
  clearTimeout(e.nextTimer);clearTimeout(e.timer);clearTimeout(e.eventTimer);
  e.stream?.stop();e.tradeStream?.stop();e.tape?.stop();e.wrTape3?.stop();
  // Never snapshot/release during a broker write. Container grace period preserves journal on forced exit.
  const until=Date.now()+25000;while(e.busy&&Date.now()<until)await new Promise(r=>setTimeout(r,100));
  if(e.busy)process.exit(1);
  if(warroomControl)await warroomControl.drain();if(agentControl)await agentControl.drain();await e.save();await store.lease(e.leaseName,true);await store.close();server.close();process.exit(process.exitCode||0);
 }
 process.once('SIGTERM',()=>close().catch(()=>process.exit(1)));
 process.once('SIGINT',()=>close().catch(()=>process.exit(1)));
}
if(require.main===module)main().catch(()=>{console.error('{"event":"startup_failed","hint":"Check config, credentials, account and persistent journal"}');process.exit(1);});
module.exports={secret};
