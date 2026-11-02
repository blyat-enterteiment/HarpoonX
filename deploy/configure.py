import os,json,re,secrets,getpass,subprocess,urllib.request,pathlib
from typing import Any
ROOT=pathlib.Path(__file__).resolve().parents[1]
class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,req,fp,code,msg,headers,newurl):return None
def account(key,secret):
 opener=urllib.request.build_opener(NoRedirect())
 def get(p):
  req=urllib.request.Request('https://paper-api.alpaca.markets'+p,headers={'APCA-API-KEY-ID':key,'APCA-API-SECRET-KEY':secret})
  with opener.open(req,timeout=20) as r:return json.load(r)
 a=get('/v2/account')
 if a.get('status')!='ACTIVE' or a.get('trading_blocked') or a.get('account_blocked'):raise ValueError('Cuenta bloqueada')
 if get('/v2/positions') or get('/v2/orders?status=open&limit=1'):raise ValueError('Primera instalación requiere cuenta dedicada plana')
 return a['id']
def private(n,v,uid=1000):
 p=ROOT/'secrets'/n;p.write_text(v);p.chmod(0o600);os.chown(p,uid,uid)
def compose(books,gpt,domain):
 services: dict[str,dict[str,Any]]={'https':{'image':'caddy:2.10','restart':'unless-stopped','ports':['80:80','443:443'],'env_file':['secrets/proxy.env'],'volumes':['./deploy/Caddyfile:/etc/caddy/Caddyfile:ro','./deploy/dashboard.html:/srv/index.html:ro','caddy_data:/data','caddy_config:/config']},'backups':{'image':'python:3.12-slim','restart':'unless-stopped','volumes':['./data:/data:ro','./backups:/backups','./deploy/backup.py:/app/backup.py:ro','./deploy/backup-loop.sh:/app/loop.sh:ro'],'command':['sh','/app/loop.sh']}}
 for b in books:
  env={'HARPOON_BOOK':b,'HARPOON_START_PAPER':'1','HARPOON_CONTROL_TOKEN_FILE':'/run/secrets/control','APCA_API_KEY_ID_FILE':'/run/secrets/key','APCA_API_SECRET_KEY_FILE':'/run/secrets/secret','HARPOON_RESEARCH_URL':'https://'+domain+'/gpt' if gpt else ''}
  vols=[f'./data/{b}:/data',f'./config/{b}.json:/config/config.json:ro','./secrets/control:/run/secrets/control:ro',f'./secrets/{b}.key:/run/secrets/key:ro',f'./secrets/{b}.secret:/run/secrets/secret:ro']
  if gpt:env['HARPOON_SERVICE_TOKEN_FILE']='/run/secrets/gpt-token';vols+=['./secrets/gpt-token:/run/secrets/gpt-token:ro']
  services[b]={'build':{'context':'.','dockerfile':'deploy/Dockerfile'},'restart':'unless-stopped','init':True,'stop_grace_period':'40s','read_only':True,'tmpfs':['/tmp:rw,noexec,nosuid,size=256m'],'cap_drop':['ALL'],'security_opt':['no-new-privileges:true'],'environment':env,'volumes':vols,'mem_limit':'2g','cpus':2,'healthcheck':{'test':['CMD','node','-e',"fetch('http://localhost:8080/healthz',{signal:AbortSignal.timeout(3000)}).then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"],'interval':'30s','timeout':'5s','start_period':'60s','retries':3}}
 if gpt:services['gpt']={'build':{'context':'./service'},'restart':'unless-stopped','env_file':['secrets/gpt.env'],'volumes':['./data/gpt:/data'],'mem_limit':'512m'}
 for s in services.values():s['logging']={'driver':'json-file','options':{'max-size':'10m','max-file':'3'}}
 return {'name':'harpoon-cloud','services':services,'volumes':{'caddy_data':{},'caddy_config':{}}}
def main():
 os.umask(0o077)
 if os.geteuid()!=0:raise ValueError('Ejecuta sudo bash install.sh')
 if (ROOT/'compose.json').exists():print('Se conserva configuración existente.');return
 domain=input('Dominio DNS que apunta al VPS: ').strip().lower()
 if not re.fullmatch(r'[a-z0-9][a-z0-9.-]*\.[a-z]{2,}',domain):raise ValueError('Dominio inválido')
 books={'equity':['equity'],'crypto':['crypto'],'ambos':['equity','crypto']}[input('Motores: equity, crypto o ambos: ').strip()]
 for folder in ['secrets','config','data','backups']:(ROOT/folder).mkdir(exist_ok=True)
 for folder in ['secrets','data','backups']:(ROOT/folder).chmod(0o700)
 control=secrets.token_hex(32);private('control',control)
 password=getpass.getpass('Contraseña NUEVA del panel (16+ caracteres): ')
 if len(password)<16:raise ValueError('Contraseña corta')
 hashed=subprocess.run(['docker','run','--rm','-i','caddy:2.10','caddy','hash-password'],input=password+'\n',text=True,capture_output=True,check=True).stdout.strip()
 if not hashed.startswith('$2'):raise ValueError('Hash inválido')
 private('proxy.env','HARPOON_CONTROL_TOKEN='+control+'\n',0)
 ids=set()
 for b in books:
  cfg=json.loads(pathlib.Path(input('Ruta al JSON exportado para '+b+': ').strip()).expanduser().read_text())
  if cfg.get('execution_authority')!='dedicated_remote_account' or (cfg.get('mode') if b=='crypto' else cfg.get('settings',{}).get('mode'))!='paper':raise ValueError('Requiere configuración PAPER dedicada')
  print('Detén la instancia anterior que opera esta cuenta.')
  key=getpass.getpass('Alpaca PAPER key: ');secret=getpass.getpass('Alpaca PAPER secret: ')
  identifier=account(key,secret)
  if identifier in ids:raise ValueError('Los dos motores requieren cuentas diferentes')
  ids.add(identifier);cfg['expected_account_id']=identifier
  target=ROOT/'config'/f'{b}.json';target.write_text(json.dumps(cfg,indent=2));os.chown(target,1000,1000)
  private(b+'.key',key);private(b+'.secret',secret)
  d=ROOT/'data'/b;d.mkdir(exist_ok=True);os.chown(d,1000,1000)
 gpt=input('Gateway GPT opcional [s/N]: ').lower()=='s'
 if gpt:
  token=secrets.token_hex(32);private('gpt-token',token)
  model=input('ID exacto del modelo disponible: ').strip();key=getpass.getpass('OpenAI key: ')
  if not re.fullmatch(r'[A-Za-z0-9._:-]{1,120}',model) or not re.fullmatch(r'[A-Za-z0-9_-]{20,512}',key):raise ValueError('Modelo/clave inválidos')
  values={'HARPOON_SERVICE_TOKEN':token,'OPENAI_API_KEY':key,'OPENAI_MODEL':model}
  for n in ['OPENAI_INPUT_USD_PER_MILLION','OPENAI_OUTPUT_USD_PER_MILLION','HARPOON_MONTHLY_CAP','HARPOON_RUN_CAP']:
   v=float(input(n+': '))
   if not 0<v<=1000:raise ValueError('Importe inválido')
   values[n]=str(v)
  if float(values['HARPOON_RUN_CAP'])>float(values['HARPOON_MONTHLY_CAP']):raise ValueError('Límites incoherentes')
  private('gpt.env',''.join(k+'='+v+'\n' for k,v in values.items()),0)
  d=ROOT/'data/gpt';d.mkdir(exist_ok=True);os.chown(d,10001,10001)
 caddy=domain+' {\n'
 if gpt:caddy+=' handle_path /gpt/* {\n  reverse_proxy gpt:8080\n }\n'
 caddy+=' handle {\n  basic_auth {\n   trader '+hashed+'\n  }\n'
 for b in books:caddy+='  handle_path /'+b+'/* {\n   reverse_proxy '+b+':8080 {\n    header_up Authorization "Bearer {$HARPOON_CONTROL_TOKEN}"\n   }\n  }\n'
 caddy+='  handle {\n   root * /srv\n   file_server\n  }\n }\n}\n'
 (ROOT/'deploy/Caddyfile').write_text(caddy);(ROOT/'compose.json').write_text(json.dumps(compose(books,gpt,domain),indent=2))
 print('Panel: https://'+domain+' · usuario trader')
if __name__=='__main__':
 try:main()
 except Exception as e:raise SystemExit('Instalación detenida: '+type(e).__name__+'. Comprueba configuración, cuenta y requisitos. No se enviaron órdenes.')
