"use strict";
/** Fixed engineering clock rows; NO provider account, trading trial, RNG or seed. */
const test=require("node:test"),A=require("node:assert/strict");
const D=require("../runtime30/fwn9_p9m_c23_market_data_audit.cjs");
const HOUR=3600000,MIN=60000;
const bar=(t)=>({timestamp:new Date(t).toISOString(),open:100,high:101,
 low:99,close:100.25,volume:1000,trade_count:12});
function stockRows(date,openHourUTC){
 const start=Date.parse(date+"T00:00:00Z")+openHourUTC*HOUR+30*MIN;
 return Array.from({length:78},(_,i)=>bar(start+i*5*MIN));
}
function cryptoRows(start,end,extraEnd=true){
 const a=[];
 for(let t=start;t<end;t+=HOUR)a.push(bar(t));
 if(extraEnd)a.push(bar(end));
 return a;
}
const start="2026-01-15T00:00:00Z",end="2026-01-16T00:00:00Z";
function fixture(){
 const rows=stockRows("2026-01-15",14),c=cryptoRows(Date.parse(start),Date.parse(end));
 return {start,end,calendar:[{date:"2026-01-15",open:"2026-01-15T09:30:00",close:"2026-01-15T16:00:00"}],
  stockFeed:"iex",cryptoFeed:"us",stockBars:{SPY:structuredClone(rows),QQQ:structuredClone(rows)},
  cryptoBars:{"BTC/USD":structuredClone(c),"ETH/USD":structuredClone(c)}
 };
}
test("C23 exact offset-time normalization fixes false missing UTC first day",()=>{
 A(Date.parse("2026-11-09T00:00:00.000Z")===Date.parse("2026-11-09T00:00:00Z"));
 A("2026-11-09T00:00:00.000Z"<"2026-11-09T00:00:00Z");
 const s=Date.parse(start),e=Date.parse(end),r=cryptoRows(s,e);
 const x=D.cryptoCoverage(r,s,e);
 A.equal(x.completeDays,1);A.equal(x.uniqueInside,24);
 A.equal(x.excludedAtOrAfterEnd,1);
 A.equal(x.coverageComplete,true);
});
test("C23 full original one-day equity NY calendar and crypto UTC 24-hour coverage",()=>{
 const r=D.auditMarketBars(fixture());
 A.equal(r.stocks.SPY.completeSessions,1);
 A.equal(r.stocks.QQQ.regularUniqueBars,78);
 A.equal(r.crypto["BTC/USD"].completeDays,1);
 A.equal(r.crypto["ETH/USD"].uniqueInside,24);
 A.equal(r.allBarClocksCovered,true);
 A.equal(r.actualBrokerOrderFillReceiptsAvailable,false);
 A.equal(r.netOutOfSampleProfitabilityCertified,false);
 A.equal(r.N9S,"NO_GO");
});
test("C23 exact original NY slot boundaries 6,18,36,18",()=>{
 const r=D.auditMarketBars(fixture()).stocks.SPY.windows;
 A.deepEqual(Object.fromEntries(Object.entries(r).map(([k,v])=>[k,v.n])),
  {RTH_OPEN_30:6,RTH_MORNING_30_120:18,RTH_MID:36,RTH_LAST_90:18});
});
test("C23 early close has 42 regular bars without imaginary afternoon session",()=>{
 const day="2026-11-27",open=Date.parse(day+"T14:30:00Z");
 const b=Array.from({length:42},(_,i)=>bar(open+i*5*MIN));
 const x=D.stockCoverage(b,[{date:day,open:day+"T09:30:00",close:day+"T13:00:00"}],
  Date.parse(day+"T00:00:00Z"),Date.parse("2026-11-28T00:00:00Z"));
 A.equal(x.coverageComplete,true);A.equal(x.expectedRegularBars,42);
 A.equal(x.windows.RTH_LAST_90.n,18);
 A.equal(x.windows.RTH_MID.n,0);
});
test("C23 summer daylight saving RTH opening is 13:30 UTC",()=>{
 const day="2026-07-15",bars=stockRows(day,13);
 const x=D.stockCoverage(bars,[{date:day,open:day+"T09:30:00",
  close:day+"T16:00:00"}],Date.parse(day+"T00:00:00Z"),
  Date.parse("2026-07-16T00:00:00Z"));
 A.equal(x.completeSessions,1);
 A.equal(x.coverageComplete,true);
});
test("C23 missing 5 minute bar not accepted as complete session",()=>{
 const f=fixture();f.stockBars.SPY.splice(12,1);
 const r=D.auditMarketBars(f);
 A.equal(r.allBarClocksCovered,false);
 A.equal(r.stocks.SPY.regularUniqueBars,77);
 A.equal(r.stocks.SPY.completeSessions,0);
});
test("C23 duplicated 5 minute bar separately counted and not passed",()=>{
 const f=fixture();f.stockBars.QQQ.push(f.stockBars.QQQ[0]);
 const r=D.auditMarketBars(f);
 A.equal(r.allBarClocksCovered,false);
 A.equal(r.stocks.QQQ.duplicateRegularBars,1);
});
test("C23 bad date timezone and naive UTC conversion reject",()=>{
 const f=fixture();f.cryptoBars["BTC/USD"][0].timestamp="2026-01-15T00:00:00";
 A.throws(()=>D.auditMarketBars(f),/C23_TIMESTAMP_REQUIRES_UTC_OFFSET/);
});
test("C23 negative quote prices or corrupt low high rejected",()=>{
 const f=fixture();f.stockBars.SPY[0].low=102;
 A.throws(()=>D.auditMarketBars(f),/C23_BAR_PRICE_VOLUME_DOMAIN/);
});
test("C23 malformed early close and non-sorted exchange calendars rejected",()=>{
 const day="2026-11-27";
 const b=[];
 A.throws(()=>D.stockCoverage(b,[{date:day,open:day+"T09:30:00",close:day+"T18:00:00"}],0,1),
  /C23_RTH_EXCHANGE_WINDOW/);
 A.throws(()=>D.stockCoverage(b,[
  {date:day,open:day+"T09:30:00",close:day+"T13:00:00"},
  {date:day,open:day+"T09:30:00",close:day+"T13:00:00"}
 ],0,1),/C23_CALENDAR_UNIQUE_SORTED/);
});
test("C23 after-calendar final bar at exclusive cutoff not included",()=>{
 const f=fixture();
 const r=D.auditMarketBars(f);
 A.equal(r.crypto["BTC/USD"].excludedAtOrAfterEnd,1);
 A.equal(r.crypto["BTC/USD"].expectedHours,24);
});
test("C23 no broker trade receipts implies all six hypotheses remain uncertified",()=>{
 const proof=D.executionGate({marketAudit:D.auditMarketBars(fixture())});
 A.equal(proof.alphaNetOOSCertified,false);
 A.equal(proof.optimalTimeByRealizedReturnCertified,false);
 A.equal(proof.originalBaselineOutperformanceCertified,false);
 A.equal(proof.N9S,"NO_GO");
 A.equal(proof.M10FinalSealed,3200);
 A(proof.structuralBlockers.includes("NO_AUTHENTICATED_BROKER_ORDER_FILLS_AND_REJECTS"));
 A(proof.structuralBlockers.includes("EXACT_ORIGINAL_OHLC_FIRST_CROSS_EQUIVALENCE_REFUTED_C21"));
});
test("C23 fake self-claimed fill snapshots and booleans never self-certify",()=>{
 const base=D.auditMarketBars(fixture());
 const gate=D.executionGate({marketAudit:base,brokerOrderFillReceipts:[{source:"ALPACA",signature:"fake"}],
  reconciledOneBookAccountHistory:{claimed:true},
  independentOriginalBaselineReceipts:{claimed:true},
  counterfactualOpportunityCoverage:{claimed:true},
  optionsContractQuotes:{claimed:true}});
 A.equal(gate.alphaNetOOSCertified,false);
 A(gate.structuralBlockers.includes("BROKER_AUTHENTICITY_AND_MARKET_ATTAINABILITY_NOT_INDEPENDENTLY_AUDITED"));
});
test("C23 rejects unsupported market feeds rather than silently comparing IEX to SIP",()=>{
 const f=fixture();f.stockFeed="sip";
 A.throws(()=>D.auditMarketBars(f),/C23_EXACT_DECLARED_FEEDS/);
});
test("C23 no market signals, account trials or sealed M10 calls",()=>{
 const r=D.auditMarketBars(fixture());
 A.deepEqual(r.budget,{newSignals:0,newSeeds:0,newEconomicAccounts:0,openedM10Final:0});
 A.equal(r.thisDoesNotOpenFutureHoldout,true);
});

test("C23 same frozen OHLC admits both profitable and loss-making hypothetical fills",()=>{
 const w=D.fillNonidentificationWitness();
 A.equal(w.bar.open,100);
 A.equal(w.bar.close,100.1);
 A(w.paths[0].netPnlUsd>0);
 A(w.paths[1].netPnlUsd<0);
 A.equal(w.cannotCertifyOptimalWindowFromPriceBars,true);
 A.equal(w.bothAreHypotheticalNotActualBrokerReceipts,true);
 A.equal(w.newMarketSeeds,0);
});
test("C23 six frozen preregistered variants have no direct realized receipts",()=>{
 const r=D.variantReceiptReadiness();
 A.equal(r.candidateCount,6);
 A.equal(r.acceptedForFamilywiseOOS,0);
 A.equal(r.financialGO,false);
 A.equal(r.variants.every(x=>x.reason==="NO_ACTUAL_EXECUTION_RECEIPT_FOR_THIS_FROZEN_VARIANT"),true);
});
test("C23 forged policy names and fake broker origin booleans never certify performance",()=>{
 const q=D.variantReceiptReadiness({
  executedPolicyIds:["H22_CRYPTO_UTC_LIQUIDITY@UTC_16_24"],
  independentBrokerOriginVerified:true,fullCandidateOpportunityTrace:true
 });
 A.equal(q.independentlyCertifiedVariantCount,0);
 A.equal(q.financialGO,false);
 A.equal(q.variants.filter(x=>x.reportedPolicyReceiptIdPresent).length,1);
 A.equal(q.variants.some(x=>x.reason==="COMPLETE_NET_CASH_RECONCILIATION_AND_CONTROL_UNAVAILABLE"),true);
 A.throws(()=>D.variantReceiptReadiness({executedPolicyIds:[null]}),
  /C23_ORIGINAL_POLICY_ID_LIST/);
});
