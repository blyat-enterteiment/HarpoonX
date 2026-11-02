'use strict';
/** Account event hints trigger REST reconciliation. A stream message never authorizes an order. */
class TradeStream {
 constructor(api,onhint,onstatus){this.api=api;this.onhint=onhint;this.onstatus=onstatus;this.closed=false;this.retry=0;}
 start(){if(this.closed||this.ws&&this.ws.readyState<2)return;const ws=new WebSocket(this.api.mode==='paper'?'wss://paper-api.alpaca.markets/stream':'wss://api.alpaca.markets/stream');this.ws=ws;ws.binaryType='arraybuffer';
  ws.onopen=()=>ws.send(JSON.stringify({action:'auth',key:this.api.keys.key,secret:this.api.keys.secret}));
  ws.onmessage=async e=>{try{const text=typeof e.data==='string'?e.data:e.data instanceof ArrayBuffer?new TextDecoder().decode(e.data):await e.data.text();const r=JSON.parse(text);if(r.stream==='authorization'){if(r.data?.status!=='authorized'){this.closed=true;this.onstatus('EVENTOS SIN AUTORIZACIÓN · REST');ws.close();return;}ws.send(JSON.stringify({action:'listen',data:{streams:['trade_updates']}}));this.retry=0;}else if(r.stream==='listening')this.onstatus('TRADE UPDATES ACTIVO');else if(r.stream==='trade_updates')this.onhint(r.data);}catch{this.onstatus('EVENTO NO LEGIBLE · REST');}};
  ws.onerror=()=>this.onstatus('TRADE UPDATES INTERRUMPIDO · REST');ws.onclose=()=>{this.ws=null;if(!this.closed){this.onstatus('TRADE UPDATES RECONECTANDO · REST');this.timer=setTimeout(()=>this.start(),Math.min(60000,1000*2**Math.min(6,this.retry++))+Math.floor(Math.random()*500));}};
 }
 stop(){this.closed=true;clearTimeout(this.timer);this.ws?.close();}
}

