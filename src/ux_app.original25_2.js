'use strict';
// Presentation and local plugin import only. All trading actions delegate to existing controls.
let uxReady=false,uxImportBusy=false,uxFolder=null,uxSource=null,uxAutoFolder=true,uxImportRows=[];
const uxRenderKeys={};
const uxBookName={equity:'Acciones',etf:'ETF',crypto:'Cripto'};
function uxEl(tag,content,cls){const e=document.createElement(tag);if(content!=null)e.textContent=String(content);if(cls)e.className=cls;return e;}
function uxChip(status){return uxEl('span',status.label,'ux-chip '+status.code.toLowerCase());}
function uxButton(label,fn,cls='secondary'){const b=uxEl('button',label,cls);b.type='button';b.onclick=fn;return b;}
function uxGo(name,target){navigate(name);if(target){const el=$(target);if(el){el.scrollIntoView({block:'center',behavior:'auto'});el.focus({preventScroll:true});}}}
function uxForward(id,view){if(view)uxGo(view);const b=$(id);if(!b.disabled)b.click();else notify('Acción no disponible todavía. Revisa el estado y el motivo indicado.',true);setTimeout(uxRender,50);}
function uxNavigate(name){
 const nav=$('uxNavigation');if(!nav)return;
 document.querySelectorAll('nav [data-view]').forEach(b=>{if(b.dataset.view===name){b.setAttribute('aria-current','page');const group=b.closest('details');if(group)group.open=true;}else b.removeAttribute('aria-current');});
 nav.classList.remove('ux-open');$('uxMobileMenu').setAttribute('aria-expanded','false');
 // Original status and step controls now live inside the execution view.
 $('mainContent').focus({preventScroll:true});
 if(uxReady)uxRender();
}
function uxEngineInput(e,isCrypto=false){return {connected:Boolean(e.connected),armed:Boolean(e.armed),reconciled:Boolean(e.reconciled),halt:String(e.halt||''),lastTick:e.pulse23?e.pulse23.completed_at:e.lastTick||0,staleMs:isCrypto?60000:Math.max(60000,(e.cfg.poll_seconds||15)*3000),now:Date.now(),marketOpen:isCrypto||Boolean(e.clock?.is_open),pending:Boolean(e.paperStartPending),visible:document.visibilityState==='visible',cryptoBook:isCrypto};}
function uxBookStatus(book,m){
 const c=book==='crypto',e=c?cryptoDesk:engine,base=HUX.entries(uxEngineInput(e,c));
 if(!m)return HUX.state('OFF','No hay estrategia asignada a este motor.');
 if(base.code!=='ON')return base;
 if((c?e.mode:e.cfg.mode)==='live'&&m.binding==='fixed')return HUX.state('ERROR','Este plugin sólo admite PAPER.');
 if(!c&&book==='equity'&&!e.cfg.equities.length&&!e.dynamic.length)return HUX.state('WAIT','No hay acciones en el universo.');
 if(!c&&book==='etf'&&!e.cfg.etf_pairs.length)return HUX.state('WAIT','No hay pares ETF configurados.');
 if(m.family==='astra_second_wave'){
  if(e.cfg.feed!=='sip'||!e.cfg.x.stream)return HUX.state('WAIT','ASTRA requiere SIP y streaming habilitado.');
  if(!e.stream?.ready)return HUX.state('WAIT','ASTRA espera conexión de flujo confirmada.');
  const rows=e.matrix.filter(r=>r.book===book);
  if(!rows.length||!rows.some(r=>r.astra))return HUX.state('WAIT','ASTRA está reuniendo histórico y flujo observados.');
 }
 if(c&&m.family==='shock_recovery'&&e.tape?.state!=='CAPTURANDO')return HUX.state('WAIT','Recuperación espera su captura de flujo y profundidad.');
 const rows=c?[]:e.matrix.filter(r=>r.book===book),ready=rows.filter(r=>r.state==='LISTA').length;
 return HUX.state('ON',c?'Motor habilitado. Las condiciones de señal, liquidez y costes deciden cada entrada.':ready?ready+' señales elegibles; el core vuelve a comprobar riesgo antes de enviar.':'Buscando señales. '+(rows[0]?.reason||'Consulta la matriz para ver cada condición.'));
}
function uxSlots(){return [
 {id:'equity',title:'Acciones',book:'equity',manifest:engine.pluginFor('equity'),view:'overview'},
 {id:'etf',title:'ETF',book:'etf',manifest:engine.pluginFor('etf'),view:'overview'},
 {id:'trend',title:'Cripto · tendencia',book:'crypto',manifest:cryptoDesk.plugins.find(m=>m.family==='trend_xix'),view:'cryptoDesk'},
 {id:'recovery',title:'Cripto · recuperación',book:'crypto',manifest:cryptoDesk.plugins.find(m=>m.family==='shock_recovery'),view:'cryptoDesk'}
 ].map(s=>({...s,status:uxBookStatus(s.book,s.manifest)}));}
function uxSupervisorStatus(s){
 if(window.harpoonLoop23&&!window.harpoonLoop23.permits('hot'))return HUX.state('OFF','HOT LiftOff · no se crean nuevas consultas GPT.');
 if(s.state?.pending||s.busy)return HUX.state('WAIT','Revisión en curso o pendiente de conciliación. '+(s.state?.status||''));
 if(!s.config.enabled||['paused','logs'].includes(s.config.mode))return HUX.state('OFF','Consultas automáticas pausadas. La gestión de posiciones continúa.');
 if(!s.engine.connected)return HUX.state('WAIT','Supervisión configurada; falta conectar este libro.');
 if(!s.credentials)return HUX.state('WAIT','Configura y comprueba el gateway GPT.');
 if(/ESPERA|SIN_SERVICIO|INCIERTO|LÍMITE|PRESUPUESTO|ERROR/i.test(s.state?.status||''))return HUX.state('WAIT',s.state.status);
 if(!s.health||Date.now()-s.healthAt>120000)return HUX.state('WAIT','Sin confirmación reciente del gateway. Revisa Supervisión GPT.');
 return HUX.state('ON',(s.state?.status||'Ventanas habilitadas')+' · ventana '+s.config.interval_seconds+' s.');
}
function uxModules(slots){
 const sec=uxEngineInput(engine),cr=uxEngineInput(cryptoDesk,true),local=window.harpoonLoop23&&!window.harpoonLoop23.permits('cold')?HUX.state('OFF','COLD LiftOff'):engine.researching?HUX.state('ON','Evaluación en curso; conserva la política vigente.'):window.harpoonLoop23?HUX.state('WAIT','Investigación coordinada desde Loop recursivo; herramienta nativa disponible para estudios manuales.'):!engine.cfg.auto_ml||engine.ledger.suspended?HUX.state('OFF','Investigación automática deshabilitada o suspendida.'):engine.hasFixedPlugin()?HUX.state('OFF','Plugin fijo: su promoción automática está deshabilitada.'):!engine.connected?HUX.state('WAIT','Configurado; falta conectar y reunir evidencia.'):HUX.state('WAIT','Programado fuera de sesión; requiere historia suficiente y campañas cerradas.');
 const ls=lab.state,labStatus=window.harpoonLoop23&&!window.harpoonLoop23.permits('cold')?HUX.state('OFF','COLD LiftOff · propuestas y promociones detenidas.'):lab.busy?HUX.state('ON','Laboratorio procesando un estudio.'):!ls?.enabled?HUX.state('OFF','Loop pausado.'):ls.iterations>=ls.max_iterations?HUX.state('WAIT','Límite de iteraciones alcanzado.'):HUX.state('WAIT',ls.status||'Loop habilitado; esperando datos y presupuesto.');
 const crStatus=window.harpoonLoop23&&!window.harpoonLoop23.permits('cold')?HUX.state('OFF','COLD LiftOff'):crResearchBusy?HUX.state('ON','Estudio local en curso.'):!crLoop.enabled?HUX.state('OFF','Investigación automática deshabilitada.'):crLoop.used>=crLoop.budget?HUX.state('WAIT','Presupuesto de estudios agotado.'):HUX.state('WAIT','Espera historia nueva suficiente para un estudio.');
 return [...slots.map(s=>({key:s.id,title:s.title,status:s.status,view:s.view,detail:s.manifest?.name||'Sin asignar',action:'Ver operación'})),
 {key:'exits',title:'Salidas · acciones y ETF',status:HUX.exits(sec,engine.active().length),view:'account',detail:'Take profit, stop y runner',action:'Ver posiciones'},
 {key:'cryptoExits',title:'Salidas · cripto',status:HUX.exits(cr,cryptoDesk.active().length),view:'cryptoDesk',detail:'Gestión de campañas cripto',action:'Ver posiciones'},
 {key:'stream',title:'Datos de mercado',status:!engine.connected?HUX.state('OFF','Sin conexión a Alpaca.'):!engine.cfg.x.stream?HUX.state('OFF','Streaming deshabilitado; el core conserva sus consultas REST.'):engine.stream?.ready?HUX.state('ON',engine.streamState):HUX.state('WAIT',engine.streamState||'Esperando conexión de streaming.'),view:'observability',detail:engine.cfg.feed.toUpperCase()+' · stream / REST',action:'Ver diagnóstico'},
 {key:'gpt',title:'GPT · acciones y ETF',status:uxSupervisorStatus(securitiesSupervisor),view:'supervision',detail:'Revisión por ventanas · presupuesto propio',action:'Ver supervisión',book:'securities'},
 {key:'gptCrypto',title:'GPT · cripto',status:uxSupervisorStatus(cryptoSupervisor),view:'supervision',detail:'Revisión por ventanas · sin enviar órdenes',action:'Ver supervisión',book:'crypto'},
 {key:'ml',title:'Aprendizaje local',status:local,view:'learning',detail:'Validación y promoción bajo reglas vigentes',action:'Ver aprendizaje'},
 {key:'lab',title:'Laboratorio recursivo',status:labStatus,view:'laboratory',detail:'Hipótesis, ensayos y límites',action:'Ver laboratorio'},
 {key:'crLoop',title:'Investigación cripto',status:crStatus,view:'cryptoDesk',detail:crLoop.used+' / '+crLoop.budget+' estudios · 0 tokens',action:'Ver investigación'},...(typeof p22ModuleSnapshot==='function'?p22ModuleSnapshot():[])];
}
function uxAssignGuard(cryptoBook=false){const e=cryptoBook?cryptoDesk:engine;
 if(e.busy)return 'Espera a que termine el ciclo de conciliación.';
 if(e.armed||e.paperStartPending)return cryptoBook?'Pausa las entradas cripto antes de reasignar.':'Pausa las entradas de acciones y ETF antes de reasignar.';
 if(e.active().length||e.positions.length||e.orders.length)return 'Espera a que la cuenta quede sin posiciones ni órdenes pendientes.';
 if((cryptoBook?e.state?.intents:e.ledger.intents)?.some(i=>cryptoBook?!i.final:i.unknown))return 'Resuelve los envíos pendientes o inciertos antes de reasignar.';
 if(!cryptoBook&&e.ledger.openSamples.length)return 'Espera a la maduración de las señales observadas antes de cambiar el experimento.';
 return '';
}
function uxBookCards(slots){
 const signature=JSON.stringify([slots,uxAssignGuard(),uxAssignGuard(true),engine.cfg.mode,cryptoDesk.mode]);if(uxRenderKeys.books===signature)return;uxRenderKeys.books=signature;
 const root=$('uxBooks');root.replaceChildren();
 for(const s of slots){const c=uxEl('article',null,'ux-book-card'),head=uxEl('div',null,'ux-card-top');head.append(uxEl('h4',s.title),uxChip(s.status));c.append(head,uxEl('strong',s.manifest?.name||'Sin estrategia asignada'),uxEl('small',s.manifest?s.manifest.id+' @ '+s.manifest.version:'Elige una estrategia en el catálogo.'),uxEl('p',s.status.reason));const actions=uxEl('div',null,'action-bar');actions.append(uxButton('Cambiar estrategia',()=>{const id=s.id==='equity'?'xxEquity':s.id==='etf'?'xxEtf':s.id==='trend'?'xxTrend':'xxRecovery';uxGo('plugins',id);}));const isCrypto=s.book==='crypto',e=isCrypto?cryptoDesk:engine,stop=e.armed||e.paperStartPending,b=uxButton(stop?'Pausar entradas '+(isCrypto?'cripto':'acciones + ETF'):'Reanudar '+(isCrypto?'cripto':'acciones + ETF'),()=>uxForward(isCrypto?(stop?'crPause':'crResume'):(stop?'pause':'arm'),isCrypto?'cryptoDesk':'overview'),'ghost');b.disabled=!e.connected;actions.append(b);c.append(actions);root.append(c);}
}
function uxCatalogRender(slots){
 const q=$('uxPluginSearch').value.toLocaleLowerCase(),book=$('uxBookFilter').value,filter=$('uxStateFilter').value;
 const rows=xxCatalog.map(m=>{const assigned=slots.find(s=>s.manifest?.id===m.id&&s.manifest.version===m.version);return {m,assigned,status:assigned?.status||HUX.state('OFF','Cargada; no está asignada a ningún motor.')};}).filter(r=>(book==='all'||r.m.book===book)&&(filter==='all'||filter==='assigned'&&r.assigned||filter===r.status.code)&&[r.m.name,r.m.id,r.m.family,r.m.version].join(' ').toLocaleLowerCase().includes(q));
 const sig=JSON.stringify([rows,uxImportBusy]);if(uxRenderKeys.catalog===sig)return;uxRenderKeys.catalog=sig;const root=$('uxCatalog');root.replaceChildren();text('uxFilterCount',rows.length+' de '+xxCatalog.length+' estrategias · '+slots.filter(s=>s.manifest).length+' asignadas');
 if(!rows.length){root.append(uxEl('p','Ninguna estrategia coincide. Prueba otro filtro.','empty'));return;}
 for(const {m,assigned,status} of rows){const card=uxEl('article',null,'ux-plugin-card'),head=uxEl('div',null,'ux-card-top'),badges=uxEl('div',null,'ux-badges');card.dataset.plugin=m.id+'@'+m.version;badges.append(uxEl('span','LOADED','ux-chip loaded'),uxChip(status));head.append(uxEl('span',uxBookName[m.book],'ux-overline'),badges);card.append(head,uxEl('h4',m.name),uxEl('small',m.id+' @ '+m.version),uxEl('p',assigned?'ASIGNADA · '+status.reason:status.reason),uxEl('small',m.binding==='host'?'Reglas canónicas · PAPER / LIVE autorizado':'Parámetros fijos · PAPER'));
 const select=uxButton(assigned?'Ver asignación':'Seleccionar',()=>{const id=m.book==='equity'?'xxEquity':m.book==='etf'?'xxEtf':m.family==='trend_xix'?'xxTrend':'xxRecovery';uxGo('plugins',id);$(id).value=m.id+'@'+m.version;notify('Selección preparada: '+m.name+'. Pulsa Asignar para aplicar el cambio.');});select.disabled=uxImportBusy;card.append(select);root.append(card);}
}
function uxRender(){
 if(!uxReady||!xxReady||!crReady||!xxiReady)return;
 const slots=uxSlots(),modules=uxModules(slots),on=slots.filter(s=>s.status.code==='ON').length,waiting=slots.filter(s=>['WAIT','ERROR'].includes(s.status.code)).length;
 text('uxLoaded',xxCatalog.length);text('uxCatalogCount',xxCatalog.length);text('uxOn',on+' / '+slots.length);text('uxAttention',waiting);text('uxPositions',engine.active().length+cryptoDesk.active().length);
 text('uxAssignmentSummary',slots.filter(s=>s.manifest).map(s=>s.title+': '+s.manifest.name).join(' · '));text('uxStartBadge',xxCatalog.length+' LOADED');
 text('uxFreshness','Actualizado '+new Date().toLocaleTimeString());text('uxHomeSource',$('uxFolderStatus').textContent);
 const sig=JSON.stringify(modules);if(sig!==uxRenderKeys.modules){uxRenderKeys.modules=sig;const root=$('uxModules');root.replaceChildren();for(const m of modules){const card=uxEl('article',null,'ux-module'),head=uxEl('div',null,'ux-card-top');head.append(uxEl('h4',m.title),uxChip(m.status));card.append(head,uxEl('small',m.detail),uxEl('p',m.status.reason),uxButton(m.action,()=>{if(m.book){$('xxiBook').value=m.book;xxiPopulate();renderXXI();}uxGo(m.view);},'ghost'));root.append(card);}}
 uxBookCards(slots);uxCatalogRender(slots);if(typeof p22Render==='function')p22Render();if(typeof uxControlRender==='function')uxControlRender();
 const guard=uxAssignGuard(),cryptoGuard=uxAssignGuard(true);text('uxAssignGuard',guard||'Acciones y ETF: puedes aplicar una asignación.');text('uxCryptoGuard',cryptoGuard||'Cripto: puedes aplicar una asignación.');
 $('xxApplySecurities').disabled=Boolean(guard)||uxImportBusy;$('xxApplyCrypto').disabled=Boolean(cryptoGuard)||uxImportBusy;
 const navStatus={plugins:on+' ON',overview:HUX.entries(uxEngineInput(engine)).label,cryptoDesk:HUX.entries(uxEngineInput(cryptoDesk,true)).label,supervision:modules.find(m=>m.key==='gpt').status.label,learning:modules.find(m=>m.key==='ml').status.label,laboratory:modules.find(m=>m.key==='lab').status.label,account:String(engine.active().length)};
 for(const el of document.querySelectorAll('[data-ux-nav]')){el.textContent=navStatus[el.dataset.uxNav]||'';el.className=el.textContent==='ON'?'on':'';}
 if(!$('home').hidden||!$('plugins').hidden){text('engineBadge',on+' ON · '+waiting+' EN ESPERA');text('modeBadge',engine.cfg.mode.toUpperCase()+' / CRIPTO '+cryptoDesk.mode.toUpperCase());}
}
function uxImportControls(){for(const id of ['uxChooseFolder','uxChooseFiles','uxHomeFolder','uxHomeFiles','astraInstall'])$(id).disabled=uxImportBusy;$('uxRescan').disabled=uxImportBusy||!uxFolder;$('uxAutoFolder').disabled=uxImportBusy;}
async function uxImportFiles(files,source){
 if(uxImportBusy)throw Error('Hay una carga en curso.');if(!xxReady)throw Error('Espera a que termine de cargar el catálogo.');
 uxImportBusy=true;uxImportControls();uxImportRows=[];let added=0,invalid=0,total=0,inspected=0;
 try{
  const candidates=Array.from(files).filter(f=>HUX.rootJson(f.name,f.webkitRelativePath||''));
  if(candidates.length>100)throw Error('Máximo 100 archivos JSON por lectura de carpeta.');
  for(const f of candidates){inspected++;let status='LOADED',detail='';try{
   if(f.size>500000)throw Error('Supera 500 KB por paquete.');total+=f.size;if(total>5000000)throw Error('Supera 5 MB por lectura.');
   const packet=JSON.parse(await f.text());
   if(['HARPOON-XXII-RESEARCH-PLUGIN-1','HARPOON-STRATEGY-RESEARCH-1'].includes(packet?.schema)){
    for(let wait=0;wait<100&&!p22Ready;wait++)await new Promise(resolve=>setTimeout(resolve,50));
    const result=await p22Import(packet);added+=result.added;uxImportRows.push([f.name,result.status,result.detail]);continue;
   }
   if(!packet||!Array.isArray(packet.manifests)){uxImportRows.push([f.name,'OMITIDO','No es un paquete de estrategias HARPOON.']);continue;}
   const incoming=await HXX.unpack(packet),merged=HUX.merge(xxCatalog,incoming,HXX.stable);
   await store.put('plugins-xx-catalog',merged.catalog);xxCatalog=merged.catalog;added+=merged.added;detail=merged.added+' nuevas · '+merged.duplicates+' ya cargadas';
  }catch(error){status='RECHAZADO';detail=error.message;invalid++;}uxImportRows.push([f.name,status,detail]);}
  xxPopulate();xxRenderCatalog();uxSource={name:source,at:Date.now(),files:inspected,added,rejected:invalid};
  try{await store.put('ux-plugin-source',uxSource);}catch{notify('Catálogo procesado; no se pudo guardar el resumen de carpeta.',true);}
  text('uxFolderStatus',source+' · '+inspected+' JSON revisados · '+added+' estrategias nuevas · '+invalid+' rechazados.');
  text('uxImportSummary',uxImportRows.length?'Ver '+uxImportRows.length+' resultados de carga':'No se encontraron paquetes JSON en la raíz');
  cells('uxImportResults',uxImportRows,'No se encontraron JSON en el nivel raíz de la carpeta seleccionada.',3);$('uxImportDetails').open=true;
  notify(added+' estrategias añadidas; '+invalid+' archivos rechazados. La importación no cambia asignaciones ni habilita órdenes.',invalid>0);
 }finally{uxImportBusy=false;uxImportControls();uxRender();}
}
async function uxReadDirectory(handle){const files=[];let scanned=0;for await(const item of handle.values()){if(++scanned>2000)throw Error('Carpeta demasiado grande. Usa una carpeta dedicada para HARPOON y sus paquetes.');if(item.kind==='file'&&/\.json$/i.test(item.name)){files.push(await item.getFile());if(files.length>100)throw Error('Máximo 100 JSON en la raíz.');}}await uxImportFiles(files,handle.name);}
async function uxSelectDirectory(){
 try{
  if(!window.showDirectoryPicker){$('uxDirectoryInput').click();return;}
  const handle=await window.showDirectoryPicker({id:'harpoon-strategies',mode:'read'});uxFolder=handle;
  try{await store.put('ux-plugin-directory',handle);}catch{notify('Carpeta disponible en esta sesión; el navegador no pudo recordar el permiso.',true);}
  await uxReadDirectory(handle);
 }catch(error){if(error.name==='AbortError')return;if(error.name==='SecurityError'||error.name==='NotAllowedError'){uxGo('plugins');text('uxFolderStatus','El navegador solicita selección compatible. Usa el botón Selección alternativa.');$('uxFallbackFolder').hidden=false;notify('Usa Selección alternativa para elegir la carpeta sin permiso persistente.',true);}else notify(error.message,true);}finally{uxImportControls();}
}
async function uxRescan(){try{if(!uxFolder)return;let permission=await uxFolder.queryPermission({mode:'read'});if(permission!=='granted')permission=await uxFolder.requestPermission({mode:'read'});if(permission!=='granted'){text('uxFolderStatus','Carpeta sin permiso de lectura. Los plugins guardados siguen disponibles.');return;}await uxReadDirectory(uxFolder);}catch(error){text('uxFolderStatus','No se pudo leer la carpeta: '+error.message);notify(error.message,true);}}
async function uxRestoreDirectory(){
 uxSource=await store.get('ux-plugin-source');uxAutoFolder=(await store.get('ux-auto-folder'))!==false;$('uxAutoFolder').checked=uxAutoFolder;uxFolder=await store.get('ux-plugin-directory');
 text('uxFolderStatus',uxSource?'Catálogo restaurado. Última carpeta: '+uxSource.name+' · '+new Date(uxSource.at).toLocaleString()+'.':'Catálogo integrado cargado. Puedes añadir paquetes desde tu carpeta raíz.');uxImportControls();
 if(!uxFolder)return;
 if(!uxAutoFolder){text('uxFolderStatus','Carpeta recordada: '+uxFolder.name+'. Lectura automática OFF; catálogo guardado disponible.');return;}
 if(await uxFolder.queryPermission({mode:'read'})==='granted')await uxReadDirectory(uxFolder);
 else text('uxFolderStatus','Catálogo guardado LOADED. Para revisar cambios en '+uxFolder.name+', pulsa Volver a leer carpeta y concede lectura.');
}
function uxFold(node,label,open=false){if(!node)return;const details=uxEl('details',null,'ux-detail panel'),summary=uxEl('summary',label);details.open=open;node.before(details);details.append(summary,node);node.classList.remove('panel');return details;}
function uxLayout(){
 titles.home='Inicio · estado';titles.plugins='Estrategias · LOADED / ON / OFF';titles.overview='Control de ejecución';titles.settings='Conexiones y riesgo';titles.challenge='Comparación externa';
 const overview=$('overview');overview.prepend(document.querySelector('.phase-bar'));overview.prepend(document.querySelector('.operation-status'));
 overview.querySelector('.hero h2').textContent='Control de ejecución';overview.querySelector('.hero p').textContent='Pausa o reanuda entradas, consulta el estado de cuenta y sigue las campañas. Las salidas conservan las reglas congeladas al abrirse.';
 uxFold(overview.querySelector('.local-rules'),'Referencia: reglas canónicas originales (la asignación vigente está en Estrategias)');
 const pluginHero=$('plugins').querySelector('.hero');if(pluginHero)uxFold(pluginHero,'Arquitectura del ejecutor y catálogo');
 uxFold($('astraInstall').closest('article'),'ASTRA 6 · instalar y consultar requisitos',true);
 const astro=$('astraDiagnostics');uxFold(astro,'Diagnóstico técnico de ASTRA');
 const assignments=$('xxApplySecurities').closest('article');assignments.id='uxAssignments';$('uxCatalog').closest('article').after(assignments);
 const group=[...document.querySelectorAll('[data-nav-group]')].find(g=>g.querySelector('[data-view="audit"]'));
 if(group){const details=uxEl('details',null,'ux-nav-details');details.id='uxAnalyzeMenu';const summary=uxEl('summary','ANALIZAR · 10 herramientas');group.before(details);details.append(summary,group);group.querySelector('.nav-label').hidden=true;}
 const cg=uxEl('p',null,'small');cg.id='uxCryptoGuard';$('xxApplyCrypto').after(cg);
 uxFold($('xxCatalog').closest('article'),'Importación individual, exportación y catálogo técnico');
 uxFold($('xxSnapshot').closest('article'),'Recuperación cripto · requisitos y sandbox');
 const fallback=uxButton('Selección alternativa',()=>$('uxDirectoryInput').click(),'ghost');fallback.id='uxFallbackFolder';fallback.hidden=true;$('uxRescan').after(fallback);
 $('xxImportPlugins').multiple=true;
 $('helpDialog').querySelector('h2').textContent='Cómo usar HARPOON';
 const help=$('helpDialog').querySelector('.help-grid');help.replaceChildren();
 for(const [title,body] of [['01 · Carga','Inicio → Cargar carpeta raíz. LOADED significa validado y guardado; no activa órdenes.'],['02 · Asigna','Estrategias → Seleccionar → Aplicar la asignación. Pausa entradas y espera cuenta plana si hay un bloqueo.'],['03 · Conecta','Conexiones y riesgo → claves Alpaca. PAPER puede empezar al conectar; LIVE mantiene su autorización.'],['04 · Comprueba','Inicio muestra ON, OFF, EN ESPERA y BLOQUEADO. ON busca señales; no implica una compra inmediata.']]){const card=uxEl('article');card.append(uxEl('strong',title),uxEl('p',body));help.append(card);}
}
function uxBind(){
 for(const b of document.querySelectorAll('[data-ux-go]'))b.onclick=()=>uxGo(b.dataset.uxGo);
 $('uxChooseFolder').onclick=$('uxHomeFolder').onclick=uxSelectDirectory;
 $('uxChooseFiles').onclick=$('uxHomeFiles').onclick=()=>$('uxFilesInput').click();
 for(const id of ['uxDirectoryInput','uxFilesInput','xxImportPlugins'])$(id).onchange=async e=>{const files=Array.from(e.target.files);if(!files.length)return;try{await uxImportFiles(files,id==='uxDirectoryInput'?(files[0].webkitRelativePath.split('/')[0]||'Carpeta seleccionada'):'Archivos seleccionados');}catch(error){notify(error.message,true);}finally{e.target.value='';}};
 $('uxRescan').onclick=uxRescan;
 $('uxAutoFolder').onchange=async e=>{const previous=uxAutoFolder;try{await store.put('ux-auto-folder',e.target.checked);uxAutoFolder=e.target.checked;}catch(error){e.target.checked=previous;notify(error.message,true);}};
 for(const id of ['uxPluginSearch','uxBookFilter','uxStateFilter'])$(id).addEventListener(id==='uxPluginSearch'?'input':'change',uxRender);
 $('uxNavSearch').oninput=e=>{const q=e.target.value.toLocaleLowerCase();let found=0;for(const group of document.querySelectorAll('[data-nav-group]')){let count=0;for(const b of group.querySelectorAll('[data-view]')){b.hidden=!b.title.toLocaleLowerCase().includes(q);if(!b.hidden)count++;}group.hidden=!count;const details=group.closest('details');if(details){details.hidden=!count;if(q&&count)details.open=true;}found+=count;}$('uxNavEmpty').hidden=found>0;if(q){$('uxNavigation').classList.add('ux-open');$('uxMobileMenu').setAttribute('aria-expanded','true');}};
 $('uxMobileMenu').onclick=()=>{const expanded=$('uxNavigation').classList.toggle('ux-open');$('uxMobileMenu').setAttribute('aria-expanded',String(expanded));};
 $('uxStateExport').onclick=()=>download('HARPOON_Estado_UX.json',{schema:'HARPOON-UX-STATE-1',at:new Date().toISOString(),basis:'Estado local observado; no certifica fills ni rentabilidad.',loaded:xxCatalog.map(m=>({id:m.id,version:m.version,book:m.book})).concat(typeof p22LoadedSnapshot==='function'?p22LoadedSnapshot():[]),modules:uxModules(uxSlots()).map(m=>({title:m.title,status:m.status.code})),mode:{securities:engine.cfg.mode,crypto:cryptoDesk.mode},positions:{securities:engine.active().length,crypto:cryptoDesk.active().length}});
 document.addEventListener('click',()=>setTimeout(uxRender,80));document.addEventListener('visibilitychange',uxRender);
}
uxLayout();uxBind();
(async()=>{for(let n=0;n<200;n++){if(xxReady&&crReady&&xxiReady){uxReady=true;uxGo('home');await uxRestoreDirectory();uxRender();return;}await new Promise(resolve=>setTimeout(resolve,50));}throw Error('No se confirmó el catálogo inicial; revisa los avisos de almacenamiento.');})().catch(e=>notify('Inicio: '+e.message,true));
(function pulse(){if(uxReady)uxRender();setTimeout(pulse,1500);})();
