"use strict";
const assert=require("node:assert/strict");
const test=require("node:test");
const M=require("../runtime30/modulation11_admission_mirror_v2.cjs");
const N=require("../runtime30/profit8_replay.js");
const C=require("../runtime30/ultimate_contracts.js");
const H=3600000;
function fixture(change={}){
 const t=Date.UTC(2025,0,3,15,30),at=[t,t+3*H,t+5*H];
 const signals=at.map((time,i)=>({id:["SYNA:0","SYNB:1","SYNA:2"][i],
   symbol:i===1?"SYNB":"SYNA",direction:1,hypothesis:"CLOSED_CHANNEL",
   at:time,plannedEntryAt:time+60000,stopDistance:2.1,
   metadata:{roadmapHorizonHours:72}}));
 const series=["SYNA","SYNB"].map(symbol=>({symbol,root:symbol,
   tick:0.01,pointValue:1,
   bars:at.map(time=>({t:time-600000,end:time-300000,availableAt:time-299000,
     o:100,h:100.1,l:99.9,c:100,v:1000}))}));
 const data={series,sessions:[]};
 const p={...C.defaultProtocol("ALPACA_PROXY"),universe:["SYNA","SYNB"],
   costs:{spreadBps:2,slippageBps:2,perSideUsd:.005}};
 const exitPlan=(mode,id)=>{
   if(id==="SYNA:0")return mode==="NATIVE_OHLC"?
     {at:t+2*H,price:103}:{at:t+4*H,price:98+(change.futureCausalPxDelta||0)};
   if(id==="SYNB:1")return {at:t+6*H,price:102};
   return {at:t+7*H,price:101};
 };
 const receiptFactory=({mode,signal,quantity,iocPlan})=>{
   assert(quantity>0&&iocPlan.status==="PLANNED");
   const iocAt=signal.plannedEntryAt,x=exitPlan(mode,signal.id);
   assert(iocAt<=x.at);
   return [{id:signal.id,kind:"IOC",at:iocAt,knownAt:iocAt,
     price:change.noFill?iocPlan.priceCeiling+0.10:100.03},
     ...(change.noFill?[]:[{id:signal.id,kind:"EXIT",at:x.at,
       knownAt:x.at+(mode==="FIRST_CROSS"&&change.lateReceipt?2*H:1000),
       price:x.price,quantity:"ALL"}])];
 };
 return {t,at,data,signals,protocol:p,limits:{...N.PROFIT8_REPLAY_LIMITS},
   fixedCosts:[{at:t-12*H,usd:1}],terminalAt:t+8*H,
   receiptFactory};
}
function pair(x){return M.mirror(fixture(x));}
test("P8: independent identities and funded quantities diverge using known receipt clocks",()=>{
 const o=pair({});
 assert.equal(o.native.admits.length,2);
 assert.deepEqual(o.native.admits.map(x=>x.id),["SYNA:0","SYNB:1"]);
 assert.equal(o.causal.admits.length,2);
 assert.deepEqual(o.causal.admits.map(x=>x.id),["SYNA:0","SYNA:2"]);
 assert.equal(o.admissionIdentityDiverges,true);
 assert.equal(o.native.admits[0].quantity,o.causal.admits[0].quantity);
 assert(o.native.admits[0].quantity>0&&o.causal.admits[1].quantity>0);
 const deniedB=o.causal.decisions.find(d=>d.id==="SYNB:1");
 assert.equal(deniedB.status,"REFUSED");
 assert(["INTEGER_RISK_OR_EXPOSURE","SYMBOL_BUSY"].includes(deniedB.reason));
 const deniedA=o.native.decisions.find(d=>d.id==="SYNA:2");
 assert.equal(deniedA.status,"REFUSED");
 assert(o.native.netUsd!==o.causal.netUsd);
 assert(Math.abs(o.native.bookedTradingUsd-o.native.fixedUsd-o.native.netUsd)<1e-7,
   "COSTS_MUST_SUBTRACT");
});
test("P8: future prices cannot change any decision before corresponding receipt",()=>{
 const a=pair({}),b=pair({futureCausalPxDelta:-9});
 const prefix=o=>o.causal.decisions.slice(0,2).map(x=>[x.id,x.status,x.quantity,
   x.priorRiskUsd,x.cashPoolUsd]);
 assert.deepEqual(prefix(a),prefix(b));
 assert.notEqual(a.causal.netUsd,b.causal.netUsd);
});
test("P8: no-fill releases reservation only on received IOC and does not create inventory",()=>{
 const o=pair({noFill:true});
 assert.equal(o.native.admits.length,3);
 assert.equal(o.causal.admits.length,3);
 assert.equal(o.native.filledCampaigns,0);
 assert.equal(o.causal.filledCampaigns,0);
 assert.equal(o.native.netUsd,-1);
 assert.equal(o.causal.netUsd,-1);
 assert(o.native.receipts.every(x=>x.status==="NO_FILL"));
});
test("P8: late received exit cannot finance an earlier subsequent intention",()=>{
 const x=fixture({lateReceipt:true});
 // Extend terminal so delayed last receipt remains in scope.
 const o=M.mirror(x);
 const b=o.causal.decisions.find(x=>x.id==="SYNB:1");
 assert(b);
 assert.equal(b.status,"REFUSED");
});
test("P8: reject a receipt whose knowledge precedes its effective fill",()=>{
 const x=fixture(),f=x.receiptFactory;
 x.receiptFactory=args=>f(args).map((r,i)=>i===0?{...r,knownAt:r.at-1}:r);
 assert.throws(()=>M.mirror(x),/M11_P8_NONCAUSAL_RECEIPT/);
});
test("P8: reject unresolved terminal inventory and unsupported economic assertions",()=>{
 const x=fixture(),f=x.receiptFactory;
 x.receiptFactory=args=>f(args).filter(r=>r.kind!=="EXIT");
 assert.throws(()=>M.mirror(x),/M11_P8_UNRESOLVED_TERMINAL_RESERVATION/);
 const o=pair({});
 assert.equal(o.claims.fullStochasticBridgeProven,false);
 assert.equal(o.claims.nativeInfeasibilityCertified,false);
 assert.equal(o.claims.fullOperationalCoverage,false);
 assert.equal(o.claims.continuousTwelvePercentCap,false);
});
if(process.argv.includes("--emit-accountant")){
 const o=pair({});
 process.stdout.write("M11_P8_ACCOUNTANT="+JSON.stringify({
   fixedCostsUsd:o.native.fixedUsd,
   native:o.native,causal:o.causal,deltaNetUsd:o.deltaNetUsd})+"\n");
}

if(process.argv.includes("--bench")){
 const begin=process.hrtime.bigint();
 for(let i=0;i<1000;i++)pair({});
 console.log("M11_P8_MIRROR_1000_MS="+(Number(process.hrtime.bigint()-begin)/1e6).toFixed(3));
}

test("P8-v2: crossing UTC midnight without calendar fee is rejected",()=>{
 const x=fixture();x.terminalAt=x.t+10*H;
 assert.throws(()=>M.mirror(x),/M11_P8_CALENDAR_COST_REQUIRED_EACH_DATE/);
 x.fixedCosts.push({at:Date.UTC(2025,0,4),usd:1});
 const y=M.mirror(x);
 assert(y.native.netUsd < pair({}).native.netUsd);
});
