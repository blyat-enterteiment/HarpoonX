'use strict';
/** Read-only broker context. Failures never pause the execution engine. */
async function xxiBrokerContext(e,cryptoBook=false){
 if(!e.connected||!e.api)throw Error('Conecta Alpaca');if(e.contextBusy)return;e.contextBusy=true;
 try{const at=Date.now(),context={at,mode:cryptoBook?e.mode:e.cfg.mode,feed:cryptoBook?'crypto/us':e.cfg.feed,account_status:e.account.status,errors:[]};
  try{const q=new URLSearchParams({period:'1D',timeframe:'5Min',pnl_reset:'per_day'});if(cryptoBook)q.set('intraday_reporting','continuous');const raw=await e.api.request('/v2/account/portfolio/history?'+q);if(!Array.isArray(raw.timestamp)||!Array.isArray(raw.equity)||raw.timestamp.length!==raw.equity.length)throw Error('Historial de patrimonio inválido');const i=raw.timestamp.length-1;context.portfolio={points:raw.timestamp.length,last_at:i>=0?raw.timestamp[i]*1000:null,last_equity:i>=0?raw.equity[i]:null,base_value:raw.base_value,timeframe:raw.timeframe,basis:'NAV del broker; no PnL realizado. Flujos pueden cambiar la comparación.'};}
  catch(error){context.errors.push({capability:'portfolio_history',status:error.status||0,reason:error.message});}
  if(!cryptoBook){const symbols=[...new Set(e.active().map(c=>c.symbol).concat((e.matrix||[]).slice(0,6).map(r=>r.symbol)))].slice(0,12);if(symbols.length)try{const q=new URLSearchParams({symbols:symbols.join(','),start:new Date(at-7*86400000).toISOString().slice(0,10),end:new Date(at+7*86400000).toISOString().slice(0,10),limit:'100'}),raw=await e.api.request('/v1/corporate-actions?'+q,'GET',undefined,true);if(!raw||typeof raw!=='object'||!raw.corporate_actions)throw Error('Formato de acciones corporativas no confirmado');context.corporate_actions={symbols,complete:!raw.next_page_token,events:raw.corporate_actions,note:'Contexto observado; no se modifica automáticamente cantidad, precio ni política congelada.'};}catch(error){context.errors.push({capability:'corporate_actions',status:error.status||0,reason:error.message});}}
  context.native_protection=cryptoBook?'Stop-limit confirmado por conciliación; TP/trailing dinámico requiere ejecutor':'Bracket/OTO confirmados por conciliación; runner/trailing dinámico requiere ejecutor';
  e.brokerContext=context;await e.store.put('xxi-broker-context-'+e.scope,context);return context;
 }finally{e.contextBusy=false;}
}
// One account update socket for crypto. Events are hints, never fill authorization.
const xxiCryptoConnect=XXCryptoDesk.prototype.connect;
XXCryptoDesk.prototype.connect=async function(...args){await xxiCryptoConnect.apply(this,args);this.tradeStream?.stop();this.tradeStream=new TradeStream(this.api,()=>{if(this.busy)return;clearTimeout(this.eventTimer);this.eventTimer=setTimeout(()=>this.tick(),120);},status=>{this.tradeStreamState=status;this.onchange();});this.tradeStream.start();};
