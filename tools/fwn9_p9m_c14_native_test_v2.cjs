"use strict";
/* C14: actual-native bar-high support, two funded ledgers, no synthetic market seeds. */
const test=require("node:test"),A=require("node:assert/strict");
const V=require("../runtime30/fwn9_p9m_c14_native_bar_guard.cjs");
const N=require("../runtime30/profit8_replay.js");
const K=require("../runtime30/ultimate_contracts.js");
const BAR=300000,DAY=86400000;
function fixture(){
 const t=Date.UTC(2025,0,3,14,30),end=t+BAR,known=end+1000;
 const bars={
  SYNA:{t,end,availableAt:known,o:100,h:104,l:95,c:99,v:1000},
  SYNB:{t,end,availableAt:known,o:50,h:53,l:48,c:52,v:1000}
 };
 const r=(symbol,kind,quantity,price,at=t,knownAt=known)=>({
  id:symbol+":"+kind+":"+quantity,symbol,kind,quantity,price,at,knownAt,
  feeUsd:quantity*.005
 });
 const native={mode:"NATIVE_OHLC",cash:19000,
  inventory:{SYNA:10,SYNB:0},
  fills:[r("SYNB","ENTRY",4,50.03,t,t),
    r("SYNA","EXIT",3,103,end,known),
    r("SYNA","EXIT",7,98,end,known)],
  noFills:[]};
 const causal={mode:"FIRST_CROSS",cash:18000,
  inventory:{SYNA:0,SYNB:30},
  fills:[r("SYNA","ENTRY",8,100.03,t,t),
    r("SYNB","EXIT",6,53,end,known)],
  noFills:[{symbol:"SYNA",at:end,knownAt:known+60000}]
 };
 return {bars,books:[native,causal],perSideFee:.005,calendarFee:1};
}
test("C14: two independent books, different assets, partials and quantities obey sharp high envelope",()=>{
 const f=fixture(),out=V.auditTwoBooks(f);
 A.equal(out.fillsNotForcedToMatch,true);
 A.notEqual(out.native.endWealthUsd,out.causal.endWealthUsd);
 A(out.native.endWealthUsd<=out.native.grossAtHighUpperUsd);
 A(out.causal.endWealthUsd<=out.causal.grossAtHighUpperUsd);
 A.equal(out.native.postOpenInventory.SYNA,10);
 A.equal(out.native.postOpenInventory.SYNB,4);
 A.equal(out.native.endInventory.SYNA,0);
 A.equal(out.causal.endInventory.SYNA,8);
 A.equal(out.causal.pendingNoFillReceiptCount,1);
 A.equal(out.native.intrabarExecutorEquivalentToEightSteps,false);
});
test("C14: positive OHLC but zero tick selling proceeds do not violate financed envelope",()=>{
 const f=fixture();
 f.books[0].fills[1].price=0;f.books[0].fills[2].price=0;
 const out=V.auditTwoBooks(f);
 A(out.native.endWealthUsd>0);
 A(out.native.endCashUsd>=0);
 A(out.native.endWealthUsd<=out.native.grossAtHighUpperUsd);
});
test("C14: no financing from same-bar target before opening acquisition",()=>{
 const f=fixture();
 f.books[0].cash=100;f.books[0].fills[0].quantity=3;
 f.books[0].fills[0].feeUsd=.015;
 A.throws(()=>V.auditTwoBooks(f),/C14_NO_CASH_BORROWING_ON_ENTRY/);
});
test("C14: cannot price native sell above observed high, nor buy below opening",()=>{
 const f=fixture();
 f.books[0].fills[1].price=105;
 A.throws(()=>V.auditTwoBooks(f),/C14_SELL_NONNEGATIVE_BELOW_OBSERVED_HIGH/);
 const b=fixture();
 b.books[1].fills[0].price=99;
 A.throws(()=>V.auditTwoBooks(b),/C14_BUY_ONLY_AT_OBSERVED_OPEN/);
});
test("C14: receipt chronology and actual fill-fee rules fail closed",()=>{
 const f=fixture();
 f.books[0].fills[2].knownAt=f.books[0].fills[2].at-1;
 A.throws(()=>V.auditTwoBooks(f),/C14_RECEIPT_COST_AND_TIME/);
 const b=fixture();
 b.books[1].fills[1].feeUsd=0;
 A.throws(()=>V.auditTwoBooks(b),/C14_RECEIPT_COST_AND_TIME/);
 const c=fixture();
 c.books[0].fills[0].at=c.bars.SYNA.end;
 c.books[0].fills[0].knownAt=c.bars.SYNA.availableAt;
 A.throws(()=>V.auditTwoBooks(c),/C14_BUY_ONLY_AT_OBSERVED_OPEN/);
});
test("C14: published OHLC and delayed no-fill are separate from physical cash",()=>{
 const f=fixture(),o=V.auditTwoBooks(f);
 A.equal(o.causal.pendingNoFillReceiptCount,1);
 A.equal(o.causal.openedCount,1);
 A.equal(o.causal.closedCount,1);
 A.equal(o.native.paidFeesUsd,.02+.015+.035);
 const bad=fixture();bad.bars.SYNB.availableAt=bad.bars.SYNB.end;
 bad.bars.SYNA.availableAt=bad.bars.SYNA.end;
 A.throws(()=>V.auditTwoBooks(bad),/C14_ORIGINAL_OHLC_BAR_CONTRACT/);
});
function nativeEngineering(){
 const sessions=[0,3,4,5,6,7].map(k=>{
  const open=Date.UTC(2025,0,3,14,30)+k*DAY;
  return {date:new Date(open).toISOString().slice(0,10),open,close:open+78*BAR};
 });
 const series=["SYNA","SYNB"].map(symbol=>({symbol,root:symbol,tick:.01,
  pointValue:1,bars:sessions.flatMap(session=>Array.from({length:78},(_,i)=>({
   t:session.open+i*BAR,end:session.open+(i+1)*BAR,
   availableAt:session.open+(i+1)*BAR+1000,
   o:symbol==="SYNA"?200:100,h:symbol==="SYNA"?200.1:100.1,
   l:symbol==="SYNA"?199.9:99.9,c:symbol==="SYNA"?200:100,v:1000
  })))}));
 const data={schema:"HARPOON-ULTIMATE-DATA-1",kind:"ALPACA_PROXY",
  sessions,series,splitEvents:[],cashDividends:[],
  provenance:{execution:"MODELED_OHLCV",source:"SYNTHETIC_ENGINEERING_ONLY",
   feed:"C14_FIXED_FIXTURE",files:[{name:"C14",sha256:"0".repeat(64)}]}};
 const protocol={...K.defaultProtocol("ALPACA_PROXY"),universe:["SYNA","SYNB"],
   costs:{spreadBps:2,slippageBps:2,perSideUsd:.005}};
 const signals=[["SYNA",60,4],["SYNB",90,1]].map(([symbol,m,distance])=>{
   const at=sessions[0].open+m*60000+1000;
   return {id:symbol+":"+m,symbol,hypothesis:"CLOSED_CHANNEL",
    direction:1,at,index:0,
    plannedEntryAt:N.planSignalEntryAt(at,sessions),
    stopDistance:distance,regime:.4,
    metadata:{roadmapHorizonHours:72,modulation9:{profile:"NATIVE72"}}};
 });
 const limits={...N.PROFIT8_REPLAY_LIMITS};
 const native=N.replayFundedPortfolio(signals,data,protocol,
  [{test:sessions,selected:"ALL:BASELINE"}],sessions,limits,
  {continuous:true,cashDividends:true,
   entryExecution:"IOC_LIMIT_COMMON_CAUSAL_30BPS",
   externalCostPerSessionUsd:0,calendarCostPerDayUsd:1,
   profit8:{mode:"NATIVE_MAX"},researchModulation:true});
 return {native,data,protocol};
}
test("C14: native replay execution prices compatible with observed per-bar HIGH envelope",()=>{
 const {native,data}=nativeEngineering();
 const evidence=V.auditNativeFillPriceSupport({native,data});
 A(native.funded.length>0);
 A(evidence.checkedFills>=2);
 A.equal(evidence.allNativePricesInBarHighEnvelope,true);
 A.equal(evidence.eightSubstepTradeableFillPricesProven,false);
 A.equal(evidence.fullNativePopulationAudited,false);
});
test("C14: tampered actual-native receipt above high or invalid fee is rejected",()=>{
 const {native,data}=nativeEngineering();
 const exit=native.funded[0].inventoryEvents.find(x=>x.kind==="EXIT");
 A(exit);
 exit.filledPrice=1e8;
 A.throws(()=>V.auditNativeFillPriceSupport({native,data}),
  /C14_NATIVE_FILL_OUTSIDE_BAR_HIGH_OR_OPEN/);
 const x=nativeEngineering();
 x.native.funded[0].inventoryEvents[0].knownAt=-1;
 A.throws(()=>V.auditNativeFillPriceSupport(x),
   /C14_NATIVE_FILL_RECEIPT_CAUSAL_AND_COST/);
});
if(process.argv.includes("--emit-c14")){
 const f=fixture(),o=V.auditTwoBooks(f),n=nativeEngineering();
 console.log("FWN9_C14_BAR_EVIDENCE="+JSON.stringify({fixture:f,output:o,
   actualNative:V.auditNativeFillPriceSupport(n)}));
}
if(process.argv.includes("--bench")){
 const f=fixture(),start=process.hrtime.bigint();
 for(let k=0;k<10000;k++)V.auditTwoBooks(f);
 console.log("C14_10000_INDEPENDENT_BAR_BOOKS_MS="+
  (Number(process.hrtime.bigint()-start)/1e6).toFixed(3));
}
