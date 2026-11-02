'use strict';
// Explicitly synthetic engineering fixtures; the OBSERVED flag exercises a guard.
const fs=require('node:fs'), os=require('node:os'), path=require('node:path');
const instrument=(symbol,book='equity',managed=false)=>({symbol,book,factor:'TEST_FACTOR',leverage:1,multiplier:1,step:1,minQty:1,tick:.01,tradable:true,...(managed?{discovery_managed:true}:{})});
const model=(book='equity',extra={})=>({accepted:true,book,factor:'TEST_FACTOR',leverage:1,metadata_reference:'SYNTHETIC_ENGINEERING_FIXTURE_NOT_INVESTMENT_EVIDENCE',...extra});

function histories(now=Date.now()){
 const bars=[],daily=[],calendar=[];
 const today=new Date(now);today.setUTCHours(0,0,0,0);
 let days=0;
 for(let n=1;days<24;n++){
  const date=new Date(today.getTime()-n*86400000);if([0,6].includes(date.getUTCDay()))continue;
  const opening=date.getTime()+14.5*3600000, closing=opening+6.5*3600000;
  calendar.push({date:date.toISOString().slice(0,10),open:opening,close:closing});
  daily.push({t:new Date(opening).toISOString(),o:100,h:102,l:99,c:101,v:100000,vw:100.5});
  for(let j=0;j<4;j++)bars.push({t:new Date(opening+j*300000).toISOString(),o:100,h:102,l:99,c:101,v:1000,vw:100.5});
  days++;
 }
 for(const rows of [bars,daily])rows.sort((a,b)=>Date.parse(a.t)-Date.parse(b.t));
 const current=Math.floor(now/300000)*300000;
 // Engineering session covering the test clock; not an observed exchange calendar.
 calendar.push({date:new Date(now).toISOString().slice(0,10),open:current-2*3600000,close:current+3600000});
 for(let j=4;j>0;j--)bars.push({t:new Date(current-j*300000).toISOString(),o:100,h:102,l:99,c:101,v:1000,vw:100.5});
 return {bars,daily,calendar};
}

function fixture(options={}){
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'harpoon-discovery-regression-'));
 const file=path.join(dir,'calibration.json');
 fs.writeFileSync(file,JSON.stringify({origin:'OBSERVED',available_at:new Date(Date.now()-86400000).toISOString(),models:options.models||{},...options.calibration}));
 const rows=histories(),calls=[],historyCalls=[],quoteBooks=[];
 const cfg={universe:options.universe||[instrument('STATIC')],optionUnderlyings:[],quoteAgeMs:15000,stockFeed:'sip',quant:{enabled:true,discovery:true,calibrationFile:file,discoveryLimit:40},...options.cfg};
 const engine={cfg,syncAt:Date.now(),reconcileError:'',positions:options.positions||[],openOrders:options.openOrders||[],
  active:()=>options.campaigns||[],pending:()=>options.pending||[],
  api:{request:async(route,method='GET')=>{
   if(method!=='GET')throw Error('MUTATION_FORBIDDEN');calls.push(route);
   if(options.apiOverride){const result=await options.apiOverride(route,engine);if(result!==undefined)return result;}
   if(route.includes('/movers'))return {last_updated:new Date(Date.now()+(options.timeOffset||0)).toISOString(),gainers:options.gainers||[],losers:options.losers||[]};
   if(route.includes('/most-actives'))return {last_updated:new Date(Date.now()+(options.timeOffset||0)).toISOString(),most_actives:options.active||[]};
   if(route.startsWith('/v2/assets/'))return {symbol:decodeURIComponent(route.slice('/v2/assets/'.length)),class:'us_equity',status:'active',tradable:true};
   throw Error('UNEXPECTED_ROUTE '+route);
  }},
  market:{assets:Object.fromEntries(cfg.universe.map(i=>[i.symbol,i])),bars:{},daily:{},quotes:{},watched:{},calendar:rows.calendar,
   fetchBars:async(names,crypto,timeframe,start,end)=>{
    historyCalls.push({names:[...names],timeframe,start,end});
    if(options.historyOverride){const result=await options.historyOverride(names,timeframe,engine);if(result!==undefined)return result;}
    return Object.fromEntries(names.map(s=>[s,timeframe==='5Min'?rows.bars:rows.daily]));
   },
   quotesFor:async book=>{quoteBooks.push(book);if(options.quoteFailure)throw Error('SYNTHETIC_QUOTE_FAILURE');for(const i of engine.cfg.universe.filter(i=>i.book===book))engine.market.quotes[i.symbol]={bid:100,ask:100.01,at:Date.now(),received:Date.now()};},
  },
 };
 for(const i of cfg.universe){engine.market.bars[i.symbol]=rows.bars;engine.market.daily[i.symbol]=rows.daily;engine.market.quotes[i.symbol]={bid:100,ask:100.01,at:Date.now(),received:Date.now()};}
 return {engine,options,calls,historyCalls,quoteBooks,rows,cleanup:()=>fs.rmSync(dir,{recursive:true,force:true})};
}
module.exports={fixture,instrument,model,histories};
