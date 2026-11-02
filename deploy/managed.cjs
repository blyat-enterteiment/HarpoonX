'use strict';
const fs=require('node:fs'),path=require('node:path'),http=require('node:http'),{spawn}=require('node:child_process'),{timingSafeEqual,randomBytes}=require('node:crypto');
const root=path.resolve(__dirname,'..'),data=process.env.HARPOON_DATA||'/var/data';
const equal=(a,b)=>{const x=Buffer.from(a),y=Buffer.from(b);return x.length===y.length&&timingSafeEqual(x,y);};
function basicAuth(header,password){
 const match=/^Basic ([A-Za-z0-9+/]+={0,2})$/i.exec(header||'');
 if(!match||match[1].length%4!==0)return false;
 const decoded=Buffer.from(match[1],'base64');
 return decoded.toString('base64')===match[1]&&equal(decoded.toString('utf8'),'trader:'+password);
}
function gatewayEnvironment(env,directory,token,port){
 const required=['OPENAI_MODEL','OPENAI_API_KEY','OPENAI_INPUT_USD_PER_MILLION','OPENAI_OUTPUT_USD_PER_MILLION','HARPOON_MONTHLY_CAP','HARPOON_RUN_CAP'];
 for(const key of required)if(!env[key])throw Error('Missing GPT model, key, rates or limits');
 const optional=['PATH','LANG','TZ','NODE_ENV','OPENAI_CACHED_USD_PER_MILLION','OPENAI_CACHE_WRITE_USD_PER_MILLION','HARPOON_HOT_REASONING','HARPOON_COLD_REASONING'];
 return {...Object.fromEntries([...required,...optional.filter(k=>env[k])].map(k=>[k,env[k]])),HARPOON_SERVICE_TOKEN:token,HARPOON_DB:path.join(directory,'research.sqlite'),PORT:String(port),BIND_HOST:'127.0.0.1'};
}
function route(url){const m=/^\/(equity|crypto|gpt)(\/.*)$/.exec(url||'');return m?{book:m[1],path:m[2]}:null;}
function edge({password,token,gptToken,workers,ports,html,origin=null}){
 const handle=async(req,res)=>{
  res.setHeader('Cache-Control','no-store');res.setHeader('X-Content-Type-Options','nosniff');res.setHeader('Referrer-Policy','no-referrer');res.setHeader('X-Frame-Options','DENY');
  if(req.method==='GET'&&req.url==='/healthz'){res.setHeader('Content-Type','application/json');return res.end(JSON.stringify({alive:true,services:[...workers.keys()]}));}
  const target=route(req.url);const gateway=target?.book==='gpt';
  let auth=false;if(gateway)auth=equal(req.headers.authorization||'','Bearer '+gptToken);
  else auth=basicAuth(req.headers.authorization,password);
  if(!auth){res.statusCode=401;if(!gateway)res.setHeader('WWW-Authenticate','Basic realm="HARPOON"');return res.end('Acceso privado');}
  if(!gateway&&(req.headers['sec-fetch-site']==='cross-site'||(req.headers.origin&&req.headers.origin!==origin))){res.statusCode=403;return res.end('{"error":"Origen no permitido"}');}
  if(req.method==='GET'&&req.url==='/'){res.setHeader('Content-Type','text/html; charset=utf-8');return res.end(html);}
  if(!target||!workers.has(target.book)||!target.path.startsWith('/v1/')){res.statusCode=404;return res.end('{"error":"Motor no habilitado"}');}
  if(!['GET','POST'].includes(req.method)){res.statusCode=405;return res.end();}
  if(req.method==='POST'&&!gateway&&req.headers['x-harpoon-action']!=='1'){res.statusCode=403;return res.end();}
  if(req.method==='POST'&&req.headers['content-type']?.split(';')[0].trim()!=='application/json'){res.statusCode=415;return res.end();}
  const bodyLimit=target.book==='crypto'&&target.path==='/v1/warroom'?128000000:30000;let body=Buffer.alloc(0);const chunks=[];let length=0;for await(const chunk of req){length+=chunk.length;chunks.push(chunk);if(length>bodyLimit){res.statusCode=413;return res.end();}}
  body=Buffer.concat(chunks);const upstream=http.request({hostname:'127.0.0.1',port:ports[target.book],path:target.path,method:req.method,headers:{Authorization:'Bearer '+(gateway?gptToken:token),'Content-Type':'application/json','Content-Length':body.length,'X-Harpoon-Action':req.headers['x-harpoon-action']||''},timeout:300000},r=>{res.statusCode=r.statusCode;res.setHeader('Content-Type','application/json');r.pipe(res);});
  upstream.on('timeout',()=>upstream.destroy());upstream.on('error',()=>{if(!res.headersSent){res.statusCode=502;res.end('{"error":"Servicio temporalmente no disponible; no repetir automáticamente acciones"}');}else res.destroy();});
  upstream.end(body);
 };
 return http.createServer((req,res)=>{handle(req,res).catch(()=>{if(!res.headersSent){res.statusCode=400;res.end('Solicitud incompleta');}else res.destroy();});});
}
async function main(){
 process.umask(0o077);fs.mkdirSync(data,{recursive:true});
 const password=process.env.HARPOON_PANEL_PASSWORD||'';if(password.length<32)throw Error('Panel password requires 32 characters');
 const books=(process.env.HARPOON_BOOKS||'crypto').split(',');if(books.some(b=>b!=='crypto'))throw Error('XXV edition supports only the Alpaca crypto book');if(!books.length||new Set(books).size!==books.length||books.some(b=>!['equity','crypto'].includes(b)))throw Error('Invalid books');
 const origin=process.env.RENDER_EXTERNAL_URL||process.env.HARPOON_PUBLIC_ORIGIN;
 if(!origin||new URL(origin).protocol!=='https:'||new URL(origin).origin!==origin)throw Error('HTTPS public origin without path or credentials required');
 const controlPath=path.join(data,'control-token');if(!fs.existsSync(controlPath))fs.writeFileSync(controlPath,randomBytes(32).toString('hex'),{mode:0o600});const token=fs.readFileSync(controlPath,'utf8');
 const gptTokenPath=path.join(data,'gateway-token');if(!fs.existsSync(gptTokenPath))fs.writeFileSync(gptTokenPath,randomBytes(32).toString('hex'),{mode:0o600});const gptToken=fs.readFileSync(gptTokenPath,'utf8');
 const gpt=!!process.env.OPENAI_API_KEY,ports={equity:18081,crypto:18082,gpt:18083},workers=new Map();let stopping=false;
 function launch(name,command,args,env){
  if(stopping)return;const child=spawn(command,args,{cwd:root,env,stdio:'inherit'});workers.set(name,child);
  child.on('error',()=>console.error(JSON.stringify({event:'spawn_failed',service:name})));
  child.on('exit',code=>{workers.delete(name);console.error(JSON.stringify({event:'service_exit',service:name,code}));if(!stopping)setTimeout(()=>launch(name,command,args,env),10000);});
 }
 const plans=[];
 const safeBase=Object.fromEntries(['PATH','LANG','TZ','NODE_ENV'].filter(k=>process.env[k]).map(k=>[k,process.env[k]]));
 if(gpt){
  const d=path.join(data,'gpt');fs.mkdirSync(d,{recursive:true});
  plans.push(['gpt','python3',['service/server.py'],gatewayEnvironment(process.env,d,gptToken,ports.gpt)]);
 }
 const accountIds=new Set();
 for(const book of books){
  const prefix=book.toUpperCase(),key=process.env[prefix+'_APCA_KEY'],secret=process.env[prefix+'_APCA_SECRET'];if(!key||!secret)throw Error('Missing dedicated PAPER account credentials');
  const get=async p=>{const r=await fetch('https://paper-api.alpaca.markets'+p,{headers:{'APCA-API-KEY-ID':key,'APCA-API-SECRET-KEY':secret},redirect:'error',signal:AbortSignal.timeout(15000)});if(!r.ok)throw Error('Broker preflight rejected');return r.json();};
  const account=await get('/v2/account');if(account.status!=='ACTIVE'||account.trading_blocked||account.account_blocked||!account.id)throw Error('Account unavailable');
  if(accountIds.has(account.id))throw Error('Separate accounts required for each book');accountIds.add(account.id);
  const dir=path.join(data,book);fs.mkdirSync(dir,{recursive:true});const configPath=path.join(dir,'config.json'),db=path.join(dir,'runtime.sqlite');
  if(!fs.existsSync(db)){const pos=await get('/v2/positions'),orders=await get('/v2/orders?status=open&limit=1');if(!Array.isArray(pos)||!Array.isArray(orders)||pos.length||orders.length)throw Error('First deployment requires an empty dedicated account');}
  if(fs.existsSync(configPath)){if(JSON.parse(fs.readFileSync(configPath,'utf8')).expected_account_id!==account.id)throw Error('Stored account binding mismatch');}
  else{const raw=process.env[prefix+'_CONFIG_JSON'];const cfg=raw?JSON.parse(raw):JSON.parse(fs.readFileSync(path.join(root,'config/examples',book+'.json'),'utf8'));if((book==='crypto'?cfg.mode:cfg.settings?.mode)!=='paper')throw Error('PAPER only');cfg.execution_authority='dedicated_remote_account';cfg.expected_account_id=account.id;fs.writeFileSync(configPath,JSON.stringify(cfg,null,2),{mode:0o600});}
  plans.push([book,process.execPath,['runtime/watchdog.cjs'],{...safeBase,HARPOON_BOOK:book,HARPOON_CONFIG:configPath,HARPOON_RUNTIME_DB:db,HARPOON_CONTROL_TOKEN:token,HARPOON_START_PAPER:'1',...Object.fromEntries(['HARPOON_TELEGRAM_ENABLED','HARPOON_TELEGRAM_TOKEN','HARPOON_TELEGRAM_CHAT_ID'].filter(k=>process.env[k]).map(k=>[k,process.env[k]])),APCA_API_KEY_ID:key,APCA_API_SECRET_KEY:secret,PORT:String(ports[book]),BIND_HOST:'127.0.0.1',HARPOON_RESEARCH_URL:gpt?origin+'/gpt':'',HARPOON_SERVICE_TOKEN:gptToken}]);
 }
 for(const args of plans)launch(...args);
 const html=fs.readFileSync(path.join(__dirname,'dashboard.html'));
 const server=edge({password,token,gptToken,workers,ports,html,origin});
 server.listen(Number(process.env.PORT||10000),'0.0.0.0');
 const backup=()=>spawn('python3',['deploy/backup.py'],{cwd:root,env:{...safeBase,HARPOON_BACKUP_SOURCE:data,HARPOON_BACKUP_DEST:path.join(data,'backups')},stdio:'inherit'});backup();const backupTimer=setInterval(backup,21600000);
 function stop(){if(stopping)return;stopping=true;clearInterval(backupTimer);for(const c of workers.values())c.kill('SIGTERM');server.close();setTimeout(()=>process.exit(0),35000).unref();}
 process.once('SIGTERM',stop);process.once('SIGINT',stop);
}
if(require.main===module)main().catch(()=>{console.error('{"event":"managed_start_failed","hint":"Check credentials, config, volume and dedicated PAPER account"}');process.exit(1);});
module.exports={route,equal,basicAuth,gatewayEnvironment,edge};
