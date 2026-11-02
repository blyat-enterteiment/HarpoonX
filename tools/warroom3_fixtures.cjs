'use strict';
const W=require('../src/warroom3.js');
function protocol(){return {schema:'HARPOON-WARROOM-CAMPAIGN-3',id:'fixture-warroom-3',start:'2025-11-01',end:'2026-10-01',strategy:W.defaults()};}
function data(){const start=Date.parse('2024-04-01'),end=Date.parse('2026-10-01'),daily=[];for(let t=start,i=0;t<end;t+=W.DAY,i++){const c=100*Math.exp(i*.0004+.11*Math.sin(i/21)),o=c*.998;daily.push({t,o,h:c*1.008,l:o*.992,c,v:10000});}const h4=[];for(let t=start,i=0;t<end;t+=4*W.HOUR,i++){const c=100*Math.exp(i*.00007+.1*Math.sin(i/126));h4.push({t,o:c,h:c*1.005,l:c*.995,c,v:2000});}return {schema:'HARPOON-WARROOM-DATA-3',source:'SYNTHETIC_TEST',venue:'alpaca-us',bars:{'BTC/USD':daily,'ETH/USD':structuredClone(daily)},h4:{'BTC/USD':h4},quotes:[],trades:[],gaps:[],instruments:{'BTC/USD':{min_trade_increment:1e-6},'ETH/USD':{min_trade_increment:1e-6}}};}
class Store{constructor(){this.data=new Map();}async get(k){return structuredClone(this.data.get(k));}async put(k,v){this.data.set(k,structuredClone(v));}}
module.exports={protocol,data,Store};
