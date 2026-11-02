'use strict';
// Direct venue trades, quotes and reset/delta order books. No synthetic taker flow.
// A disconnect resets the warm-up: missing flow is never filled from candle closes.
class CryptoTape {
 constructor(api){this.api=api;this.state='SIN CONEXIÓN';this.socket=null;this.closed=false;this.rows={};this.retry=null;this.reset();}
 reset(){this.started=Date.now();for(const s of HC19.SYMBOLS)this.rows[s]={bars:[],current:null,quote:null,book:new Map(),bookAt:0,bookReady:false,ids:new Set(),lastTrade:0};}
 start(){if(this.socket||this.closed)return;this.reset();this.state='CONECTANDO FLUJO';const ws=this.socket=new WebSocket('wss://stream.data.alpaca.markets/v1beta3/crypto/us');ws.onopen=()=>ws.send(JSON.stringify({action:'auth',key:this.api.keys.key,secret:this.api.keys.secret}));ws.onmessage=e=>{try{const messages=JSON.parse(e.data);for(const m of messages){if(m.T==='success'&&m.msg==='authenticated'){ws.send(JSON.stringify({action:'subscribe',trades:HC19.SYMBOLS,quotes:HC19.SYMBOLS,orderbooks:HC19.SYMBOLS}));this.state='CAPTURANDO';}else if(m.T==='error'){this.state='FEED RECHAZADO';ws.close();}else this.ingest(m,Date.now());}}catch{this.state='MENSAJE INVÁLIDO';ws.close();}};ws.onerror=()=>{this.state='FALLO DE FLUJO';ws.close();};ws.onclose=()=>{if(this.socket!==ws)return;this.socket=null;this.reset();this.state='DESCONECTADO · HISTORIA INVALIDADA';if(!this.closed)this.retry=setTimeout(()=>this.start(),30000);};}
 stop(){this.closed=true;clearTimeout(this.retry);const ws=this.socket;this.socket=null;ws?.close();this.reset();this.state='DETENIDO';}
 ingest(m,received){const r=this.rows[m.S],t=Date.parse(m.t);if(!r)return;if(!Number.isFinite(t)||t>received+1000||received-t>5000){if(m.T==='t'){r.bars=[];r.current=null;this.started=received;}return;}
  if(m.T==='q'){const bid=Number(m.bp),ask=Number(m.ap);if(!(bid>0&&ask>=bid))return;if(!r.quote||t>=r.quote.atMs)r.quote={atMs:t,bid,ask};}
  if(m.T==='o'){if(m.r===true){r.book.clear();r.bookReady=true;}if(!r.bookReady||t<r.bookAt)return;for(const a of m.a||[]){const p=Number(a.p),s=Number(a.s);if(!(p>0&&s>=0))continue;if(s===0)r.book.delete(p);else r.book.set(p,s);}r.bookAt=t;}
  if(m.T!=='t')return;const p=Number(m.p),size=Number(m.s);if(!(p>0&&size>0)||!Number.isFinite(p)||!Number.isFinite(size)||m.i==null){r.bars=[];r.current=null;this.started=received;return;}const id=String(m.i);if(r.ids.has(id))return;r.ids.add(id);if(r.ids.size>100000)r.ids.delete(r.ids.values().next().value);
  const frame=900000,start=Math.floor(t/frame)*frame;if(t<r.lastTrade){r.bars=[];r.current=null;this.started=received;return;}r.lastTrade=t;
  if(r.current&&start>r.current.startMs){const old=r.current;if(old.complete&&start===old.startMs+frame){r.bars.push({...old,availableMs:received,tradeVwap:old.notional/old.volume});r.bars=r.bars.slice(-110);}else r.bars=[];r.current=null;}
  if(!r.current)r.current={startMs:start,availableMs:0,open:p,high:p,low:p,close:p,volume:0,notional:0,tradeVwap:p,buyVolume:0,sellVolume:0,complete:start>=this.started};
  const b=r.current;b.high=Math.max(b.high,p);b.low=Math.min(b.low,p);b.close=p;b.volume+=size;b.notional+=p*size;if(m.tks==='B')b.buyVolume+=size;if(m.tks==='S')b.sellVolume+=size;
 }
 snapshot(symbol,now){const r=this.rows[symbol];if(!r?.quote)return null;const depth=r.bookReady?{atMs:r.bookAt,askUsdWithin25bps:[...r.book].filter(([p])=>p>=r.quote.ask&&p<=r.quote.ask*1.0025).reduce((n,[p,s])=>n+p*s,0)}:undefined;return {asofMs:now,symbol,venue:'alpaca-us',source:'RECORDED',daily:[],intraday:r.bars,quote:r.quote,depth};}
}
