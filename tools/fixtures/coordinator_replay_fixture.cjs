"use strict";
// Synthetic event construction only. Quotes, volume and fees are MODELED.
const {REQUEST_SCHEMA}=require("../coordinator_replay.cjs");
function syntheticRequest(){
  const start=Date.parse("2026-10-15T15:30:10Z"),open=Date.parse("2026-10-15T13:30:00Z");
  const past=["2026-09-29","2026-09-30","2026-10-01","2026-10-02","2026-10-05","2026-10-06","2026-10-07","2026-10-08","2026-10-09","2026-10-12","2026-10-13","2026-10-14","2026-10-15"];
  const dates=[...past,"2026-10-16","2026-10-19","2026-10-20","2026-10-21","2026-10-22","2026-10-23"];
  const config=structuredClone(require("../../config/examples/xxx.json"));
  config.expected_account_id="OFFLINE-SYNTHETIC-REPLAY";config.streaming=false;config.quant={enabled:false};config.nativeProtection="stop";
  config.universe=config.universe.filter(a=>a.symbol==="AAPL");config.enabledPlugins=["equity-canonical-host"];config.optionUnderlyings=[];
  const bars={},daily={};
  for(const symbol of ["AAPL","SPY","XLK"]){
    bars[symbol]=[];
    for(const date of past){const session=Date.parse(date+"T13:30:00Z");
      for(let j=0;j<24;j++){const c=symbol==="XLK"?100+j*.2:symbol==="SPY"?100:100+j*.08,t=session+j*300000;
        bars[symbol].push({t:new Date(t).toISOString(),o:c,h:c+.15,l:c-.15,c,v:session===open?3000:1000,vw:c,known_at:t+303000});}
    }
    daily[symbol]=Array.from({length:30},(_,j)=>{const t=open-(30-j)*86400000;return {t:new Date(t).toISOString(),o:95,h:96,l:94,c:95,v:10000,vw:95,known_at:t+86400000};});
  }
  return {schema:REQUEST_SCHEMA,id:"synthetic-real-coordinator-lifecycle",mode:"OFFLINE",execution_origin:"MODELED",data_origin:"SYNTHETIC",start_at:start,initial_cash_usd:20000,config,calendar:dates.map(date=>({date,open:"09:30",close:"16:00"})),execution_model:{origin:"MODELED",causal_fills:"STRICTLY_LATER_QUOTE",mark_method:"BID",cancel_mode:"EXPLICIT_CONFIRMATION",fees_bps_per_side:1,fee_per_fill_usd:.01,slippage_bps:0,external_cost_usd:1,ack_latency_ms:0,liquidity_assumption:"Explicit executable quantity per future quote is a synthetic scenario, not observed depth or queue priority."},events:[
    {id:"history",at:start,type:"market",bars,daily,quotes:["AAPL","SPY","XLK"].map(symbol=>({symbol,market_at:start,bid:101.1,ask:101.11,executable_qty:0}))},
    {id:"plugin-evaluation",at:start,type:"evaluate",book:"equity"},
    {id:"entry",at:start+1,type:"entries",book:"equity"},
    {id:"future-fill-quote",at:start+1000,type:"market",quotes:[{symbol:"AAPL",market_at:start+1000,bid:101.1,ask:101.11,executable_qty:1000}]},
    {id:"entry-reconciliation",at:start+1000,type:"reconcile"},
    {id:"protect",at:start+1000,type:"manage"},
    {id:"protection-reconciliation",at:start+1001,type:"reconcile"},
  ]};
}
module.exports={syntheticRequest};
