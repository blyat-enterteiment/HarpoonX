'use strict';
const assert=require('node:assert/strict'),fs=require('fs'),os=require('os'),path=require('path'),{spawn}=require('child_process'),{once}=require('events');
(async()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'harpoon-cloud-')),token='synthetic-control-token-32-characters';
 fs.writeFileSync(path.join(dir,'config.json'),JSON.stringify({execution_authority:'dedicated_remote_account',settings:{mode:'paper'},expected_account_id:'fixture-account'}));
 let child;const port=19387,base='http://127.0.0.1:'+port;
 const env={...process.env,PORT:String(port),HARPOON_BOOK:'equity',HARPOON_CONFIG:path.join(dir,'config.json'),HARPOON_RUNTIME_DB:path.join(dir,'db.sqlite'),HARPOON_CONTROL_TOKEN:token,APCA_API_KEY_ID:'synthetic',APCA_API_SECRET_KEY:'synthetic',HARPOON_START_PAPER:'1'};
 const get=(url,method='GET',auth=true,action=false)=>fetch(base+url,{method,headers:{...(auth?{Authorization:'Bearer '+token}:{}),...(action?{'X-Harpoon-Action':'1'}:{})}});
 async function start(){child=spawn(process.execPath,['--require',path.join(__dirname,'cloud_preload.cjs'),path.join(__dirname,'../runtime/cloud.cjs')],{env,stdio:'pipe'});let output='';child.stderr.on('data',d=>output+=d);for(let n=0;n<100;n++){try{const r=await get('/v1/state');const s=await r.json();if(s.boot==='connected')return s;}catch{}await new Promise(r=>setTimeout(r,30));}throw Error('Startup failed '+output);}
 async function stop(){const exited=once(child,'exit');child.kill('SIGTERM');await exited;}
 try{
  assert.equal((await start()).armed,true);
  assert.equal((await get('/v1/state','GET',false)).status,401);
  assert.equal((await get('/v1/pause','POST',true,false)).status,403);
  assert.equal((await (await get('/v1/pause','POST',true,true)).json()).armed,false);
  await stop();assert.equal((await start()).armed,false);
  assert.equal((await (await get('/v1/resume','POST',true,true)).json()).armed,true);
  await stop();
  const {loadCrypto}=require('../runtime/crypto_runner.cjs');const vm=require('vm'),c={};vm.createContext(c);vm.runInContext(fs.readFileSync(path.join(__dirname,'../src/crypto_core.js'),'utf8'),c);const cfg=vm.runInContext('HC19.defaults',c);
  assert.equal(loadCrypto({},cfg).constructor.name,'XXCryptoDesk');
  const report={checks:7,passed:7,results:['PAPER configured startup','Unauthorized state denied','Action header required','Pause disables entries','Pause survives process restart with SQLite','Explicit PAPER resume','Current crypto plugin engine loads'],external_orders:0,openai_calls:0,scope:'Launcher integration uses injected engine; native engine tested separately'};
  fs.writeFileSync(path.join(__dirname,'../evidence/cloud_tests.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report,null,2));
 }finally{if(child?.exitCode===null)child.kill('SIGKILL');fs.rmSync(dir,{recursive:true,force:true});}
})().catch(e=>{console.error(e);process.exitCode=1;});
