'use strict';
/* Operational projection only: no new timer sends orders, no model calls. */
const HDesk25={
 snapshot(d,now=Date.now()){
  const pulse=d.pulse23?.completed_at||d.lastTick||0,live=d.connected&&pulse>0&&now-pulse<60000,
   catalogFresh=!!d.catalogAt25&&now-d.catalogAt25<60000,
   quotes=HC19.SYMBOLS.every(s=>d.quotes[s]&&now-d.quotes[s].t<15000),
   active=d.active(),pending=d.state?.intents?.filter(i=>!i.final)||[],
   state=(ok,reason)=>({status:ok?'ON':d.connected?'WAIT':'OFF',reason});
  return {autonomy3:d.autonomy3?.view()||null,options3:d.optionsView3?.()||null,warroom3:d.room3?.view()||null,agents:d.agents25?.view()||null,version:'25.3.0',broker:'ALPACA',mode:d.mode,at:now,pulse,connected:d.connected,
   config:{...d.cfg},execution_symbols:HC19.SYMBOLS.slice(),catalog_at:d.catalogAt25||null,
   roles:[
    {name:'HEAD · Coordinación',...state(live&&d.locked,'Bloqueo exclusivo y conciliación; no genera órdenes por separado.')},
    {name:'SEARCH · Universo',...state(catalogFresh,'Catálogo Alpaca. Los pares ajenos a los plugins quedan sólo visibles.')},
    {name:'RISK · Riesgo',...state(live&&d.reconciled,'Límites de exposición, drawdown y poder de compra del core.')},
    {name:'FLOW · Liquidez',...state(quotes,'Bid/ask y spread. Profundidad adicional cuando Recovery captura el flujo; no identifica ballenas.')},
    {name:'SIGNAL · Estrategias',...state(live&&(Object.keys(d.signals).length>0||!!d.tape),'Tendencia o recuperación según plugin. ON no significa señal de entrada.')},
    {name:'SNIPER · Ejecución',...state(live&&d.armed&&!d.halt,'Único ejecutor original. Intenciones persistentes y conciliación de órdenes ambiguas.')},
    {name:'EXIT · Salidas',...state(live,'Política fijada por campaña; '+active.length+' campañas. Pausar entradas no apaga salidas.')},
    {name:'WATCH · Vigilancia',...state(live,'Pulso y órdenes pendientes: '+pending.length+'. No es un detector de rugs.')}
   ],halt:d.halt||null,agentFault:d.agentFault25||d.profitError25||null,plugins:d.plugins?.map(x=>({id:x.id,family:x.family,version:x.version}))||[],
   catalog:(d.catalog25||[]).map(a=>({symbol:a.symbol,active:a.status==='active',tradable:a.tradable===true,enabled:HC19.SYMBOLS.includes(a.symbol)&&a.class==='crypto'&&a.status==='active'&&a.tradable===true})),
   events:(d.state?.events||[]).slice(0,50),tokens_used_by_this_panel:0};
 }
};
if(typeof module!=='undefined')module.exports=HDesk25;
