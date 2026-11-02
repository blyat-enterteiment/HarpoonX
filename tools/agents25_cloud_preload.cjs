'use strict';
// Read-only broker fixtures. Any broker mutation fails this isolated test.
const DAY=86400000;
global.WebSocket=class {constructor(){this.readyState=0}send(){}close(){this.readyState=3}};
global.fetch=async url=>{const u=new URL(url);let data;
 if(u.pathname==='/v2/account')data={id:'agents-fixture-account',status:'ACTIVE',equity:'20000',cash:'20000',non_marginable_buying_power:'20000'};
 else if(u.pathname==='/v2/clock')data={timestamp:new Date().toISOString()};
 else if(u.pathname==='/v2/positions'||u.pathname==='/v2/orders'||u.pathname==='/v2/account/activities')data=[];
 else if(u.pathname==='/v2/assets')data=['BTC/USD','ETH/USD'].map(symbol=>({symbol,class:'crypto',status:'active',tradable:true,min_order_size:'0.0001',min_trade_increment:'0.0001',price_increment:'0.01'}));
 else if(u.pathname.endsWith('/latest/quotes'))data={quotes:Object.fromEntries(['BTC/USD','ETH/USD'].map(s=>[s,{bp:100,ap:100.01,t:new Date().toISOString()}]))};
 else if(u.pathname.endsWith('/bars')){const end=Math.floor(Date.now()/DAY)*DAY,rows=Array.from({length:1100},(_,i)=>{const t=end-(1100-i)*DAY,c=100*(1+.1*Math.sin(i/23));return {t:new Date(t).toISOString(),o:c,h:c*1.01,l:c*.99,c,v:10000}});data={bars:{'BTC/USD':rows,'ETH/USD':rows}};}
 else throw Error('External network prohibited in agents cloud test '+u.pathname);
 return new Response(JSON.stringify(data),{status:200,headers:{'Content-Type':'application/json'}});
};
