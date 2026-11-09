"use strict";
/**
 * FWN9 C23: observability and execution-evidence audit, NOT alpha research.
 * Pure deterministic re-analysis of externally supplied historical bars,
 * no orders, market RNG, strategy candidates, economic account executions.
 */
const A=require("node:assert/strict");
const NY=new Intl.DateTimeFormat("en-US",{
  timeZone:"America/New_York",year:"numeric",month:"2-digit",day:"2-digit",
  hour:"2-digit",minute:"2-digit",hourCycle:"h23"
});
const MIN=60000,HOUR=3600000,DAY=86400000;
const STOCKS=["SPY","QQQ"],CRYPTOS=["BTC/USD","ETH/USD"];
function need(ok,code){A.ok(ok,"C23_"+code);}
function validTime(s){
 need(typeof s==="string"&&/T\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)$/.test(s),
  "TIMESTAMP_REQUIRES_UTC_OFFSET");
 const x=Date.parse(s);need(Number.isSafeInteger(x),"FINITE_TIMESTAMP");return x;
}
function local(t){
 const p=Object.fromEntries(NY.formatToParts(new Date(t)).map(x=>[x.type,x.value]));
 return {date:p.year+"-"+p.month+"-"+p.day,minute:Number(p.hour)*60+Number(p.minute)};
}
function clockOf(s,date){
 need(typeof s==="string"&&s.startsWith(date+"T")&&
  /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d$/.test(s),"EXCHANGE_CALENDAR_NY_LOCAL");
 return Number(s.slice(11,13))*60+Number(s.slice(14,16));
}
function stats(){return {n:0,absBodyBps:0,volume:0,dollarTurnover:0,trades:0};}
function count(z,b){
 for(const k of ["open","high","low","close","volume","trade_count"])
  need(typeof b[k]==="number"&&Number.isFinite(b[k]),"BAR_"+k);
 need(b.open>0&&b.close>0&&b.low>0&&b.high>=Math.max(b.open,b.close)&&
  b.low<=Math.min(b.open,b.close)&&b.volume>=0&&b.trade_count>=0,
  "BAR_PRICE_VOLUME_DOMAIN");
 z.n++;z.absBodyBps+=Math.abs(Math.log(b.close/b.open))*10000;
 z.volume+=b.volume;z.dollarTurnover+=b.close*b.volume;z.trades+=b.trade_count;
}
function metric(z,expected){
 return {n:z.n,expected,complete:z.n===expected,
  meanAbsBodyBps:z.n?z.absBodyBps/z.n:null,
  meanReportedVolumePerBar:z.n?z.volume/z.n:null,
  meanPriceTimesVenueVolumeUsdPerBar:z.n?z.dollarTurnover/z.n:null,
  meanReportedTradesPerBar:z.n?z.trades/z.n:null};
}
function stockBucket(minuteSinceOpen,minutesInSession){
 if(minuteSinceOpen<30)return "RTH_OPEN_30";
 if(minuteSinceOpen<120)return "RTH_MORNING_30_120";
 if(minuteSinceOpen>=Math.max(120,minutesInSession-90))return "RTH_LAST_90";
 return "RTH_MID";
}
function stockCoverage(bars,calendar,start,end){
 need(Array.isArray(bars)&&Array.isArray(calendar)&&calendar.length>0,"STOCK_INPUT");
 const session=new Map(),expected={RTH_OPEN_30:0,RTH_MORNING_30_120:0,RTH_MID:0,RTH_LAST_90:0};
 let prior="";
 for(const s of calendar){
  need(typeof s.date==="string"&&/^\d{4}-\d\d-\d\d$/.test(s.date)&&
   s.date>prior&&!session.has(s.date),"CALENDAR_UNIQUE_SORTED");
  const open=clockOf(s.open,s.date),close=clockOf(s.close,s.date);
  need(open===570&&close>open&&close<=960&&(close-open)%5===0,"RTH_EXCHANGE_WINDOW");
  session.set(s.date,{open,close,minutes:close-open});prior=s.date;
  for(let m=0;m<close-open;m+=5)expected[stockBucket(m,close-open)]++;
 }
 const group=Object.fromEntries(Object.keys(expected).map(k=>[k,stats()]));
 const days=new Map(),seen=new Set();
 let outsideWindow=0,nonRegular=0,duplicates=0;
 for(const b of bars){
  const t=validTime(b.timestamp);
  if(t<start||t>=end){outsideWindow++;continue;}
  const d=local(t),s=session.get(d.date);
  if(!s||d.minute<s.open||d.minute>=s.close){nonRegular++;continue;}
  const m=d.minute-s.open;
  need(m%5===0,"RTH_BAR_ALIGNMENT");
  const key=d.date+":"+m;
  if(seen.has(key)){duplicates++;continue;}
  seen.add(key);(days.get(d.date)??(days.set(d.date,new Set()),days.get(d.date))).add(m);
  count(group[stockBucket(m,s.minutes)],b);
 }
 let completeSessions=0;
 for(const [date,s] of session){
  const size=days.get(date)?.size??0;
  if(size===s.minutes/5)completeSessions++;
 }
 return {
  providerRecords:bars.length,regularUniqueBars:seen.size,
  expectedRegularBars:Object.values(expected).reduce((x,y)=>x+y,0),
  completeSessions,expectedSessions:session.size,
  excludedOutsidePeriod:outsideWindow,excludedNonRegular:nonRegular,
  duplicateRegularBars:duplicates,
  coverageComplete:duplicates===0&&completeSessions===session.size&&
   seen.size===Object.values(expected).reduce((x,y)=>x+y,0),
  windows:Object.fromEntries(Object.entries(group).map(([k,z])=>[k,metric(z,expected[k])]))
 };
}
function cryptoCoverage(bars,start,end){
 need(Array.isArray(bars)&&Number.isSafeInteger(start)&&Number.isSafeInteger(end)&&
  start<end&&start%DAY===0&&end%DAY===0&&(end-start)%DAY===0,"CRYPTO_WINDOW_UTC_DAYS");
 const group=Object.fromEntries(["UTC_00_08","UTC_08_16","UTC_16_24"].map(k=>[k,stats()]));
 const seen=new Set(),days=new Map();
 let excludedBeforeStart=0,excludedAtOrAfterEnd=0,duplicates=0;
 for(const b of bars){
  const t=validTime(b.timestamp);
  if(t<start){excludedBeforeStart++;continue;}
  if(t>=end){excludedAtOrAfterEnd++;continue;}
  need(t%HOUR===0,"CRYPTO_UTC_HOUR_ALIGNMENT");
  if(seen.has(t)){duplicates++;continue;}seen.add(t);
  const date=new Date(t).toISOString().slice(0,10),hour=new Date(t).getUTCHours();
  (days.get(date)??(days.set(date,new Set()),days.get(date))).add(hour);
  count(group[hour<8?"UTC_00_08":hour<16?"UTC_08_16":"UTC_16_24"],b);
 }
 const expectedDays=(end-start)/DAY,expectedHours=expectedDays*24;
 const full=Array.from(days.values()).filter(z=>z.size===24).length;
 return {
  providerRecords:bars.length,uniqueInside:seen.size,expectedHours,
  completeDays:full,expectedDays,excludedBeforeStart,excludedAtOrAfterEnd,
  duplicatedHours:duplicates,
  coverageComplete:duplicates===0&&seen.size===expectedHours&&full===expectedDays,
  windows:Object.fromEntries(Object.entries(group).map(([k,z])=>[k,metric(z,expectedDays*8)]))
 };
}
function auditMarketBars({start,end,calendar,stockBars,cryptoBars,
  stockFeed,cryptoFeed}={}){
 const startMs=validTime(start),endMs=validTime(end);
 need(startMs<endMs&&stockFeed==="iex"&&cryptoFeed==="us","EXACT_DECLARED_FEEDS");
 need(stockBars&&cryptoBars&&typeof stockBars==="object"&&typeof cryptoBars==="object",
  "ASSET_GROUPS");
 const stocks={},crypto={};
 for(const a of STOCKS)stocks[a]=stockCoverage(stockBars[a],calendar,startMs,endMs);
 for(const a of CRYPTOS)crypto[a]=cryptoCoverage(cryptoBars[a],startMs,endMs);
 return {
  schema:"FWN9_C23_OBSERVED_MARKET_COVERAGE_ONLY_1",
  marketWindow:{start,end,feedEquity:"iex",feedCrypto:"us"},
  stocks,crypto,
  allBarClocksCovered:Object.values(stocks).every(x=>x.coverageComplete)&&
   Object.values(crypto).every(x=>x.coverageComplete),
  rawProviderPayloadRetained:false,
  IEXIsConsolidatedNBBO:false,
  historicalOptionsContractQuotesAvailable:false,
  actualBrokerOrderFillReceiptsAvailable:false,
  netOutOfSampleProfitabilityCertified:false,
  optimalHourCertified:false,
  thisDoesNotOpenFutureHoldout:true,N9S:"NO_GO",
  budget:{newSignals:0,newSeeds:0,newEconomicAccounts:0,openedM10Final:0}
 };
}
function executionGate({marketAudit,brokerOrderFillReceipts,
  reconciledOneBookAccountHistory,independentOriginalBaselineReceipts,
  counterfactualOpportunityCoverage,optionsContractQuotes}={}){
 need(marketAudit?.schema==="FWN9_C23_OBSERVED_MARKET_COVERAGE_ONLY_1",
  "COVERAGE_AUDIT_FIRST");
 const blockers=[];
 if(!marketAudit.allBarClocksCovered)blockers.push("MISSING_OR_DUPLICATE_SOURCE_BARS");
 if(!marketAudit.IEXIsConsolidatedNBBO)blockers.push("SIP_NBBO_EXECUTION_REFERENCE_NOT_VERIFIED");
 if(!Array.isArray(brokerOrderFillReceipts)||brokerOrderFillReceipts.length===0)
  blockers.push("NO_AUTHENTICATED_BROKER_ORDER_FILLS_AND_REJECTS");
 if(!reconciledOneBookAccountHistory)
  blockers.push("MISSING_SINGLE_FINANCED_NAV_CASH_FEES_AND_EXTERNAL_FLOWS");
 if(!independentOriginalBaselineReceipts)
  blockers.push("NO_COMPARABLE_EXECUTED_ORIGINAL_POLICY_BASELINE");
 if(!counterfactualOpportunityCoverage)
  blockers.push("UNOBSERVED_NONFILLED_AND_REJECTED_OPPORTUNITY_COSTS");
 if(!optionsContractQuotes)
  blockers.push("NO_HISTORICAL_MATCHED_OPTION_QUOTE_UNDERLYING_CHAIN");
 // Input metadata alone cannot be an independent broker attestation, even if
 // values and claimed SHA256 appear well-formed. Only structural readiness.
 blockers.push("BROKER_AUTHENTICITY_AND_MARKET_ATTAINABILITY_NOT_INDEPENDENTLY_AUDITED");
 blockers.push("EXACT_ORIGINAL_OHLC_FIRST_CROSS_EQUIVALENCE_REFUTED_C21");
 return {schema:"FWN9_C23_REALIZED_EDGE_EVIDENCE_GATE_1",
  structuralBlockers:blockers,
  alphaNetOOSCertified:false,optimalTimeByRealizedReturnCertified:false,
  oneBookCompoundedReturnVersusCashCertified:false,
  originalBaselineOutperformanceCertified:false,
  orderAuthority:false,statisticalOptimizationAllowed:false,
  N9S:"NO_GO",M10FinalSealed:3200
 };
}
module.exports={validTime,local,stockBucket,stockCoverage,cryptoCoverage,
  auditMarketBars,executionGate};
