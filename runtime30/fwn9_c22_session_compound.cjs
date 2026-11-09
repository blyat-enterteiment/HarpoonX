"use strict";
/** FWN9 C22: source-clocked READ ONLY window ranking, funded compounding.
 * Neither a tradable session nor ranking establishes alpha or order authority.
 */
const A=require("node:assert/strict");
const crypto=require("node:crypto");
const {sessionContext}=require("./sessions.js");
const BOOKS=["equity","etf","crypto","options"],MINUTE=60000,EPS=1e-7;
function need(x,id){A.ok(x,"C22_"+id);}
function num(x){return typeof x==="number"&&Number.isFinite(x);}
function close(reason,extra={}){return {eligible:false,reason,executionAllowed:false,...extra};}
function windowFor({book,at,calendar=[],venueOpen,contractSessionVerified}={}){
 need(BOOKS.includes(book),"BOOK");
 need(Number.isSafeInteger(at)&&at>0,"TIMESTAMP");
 if(book==="crypto"){
  const h=new Date(at).getUTCHours();
  const w=h<8?"UTC_00_08":h<16?"UTC_08_16":"UTC_16_24";
  if(venueOpen!==true)return close("VENUE_STATUS_UNKNOWN",{window:w});
  return {eligible:true,window:w,calendarVerified:true,
    optimalProfitabilityProven:false,executionAllowed:false};
 }
 need(Array.isArray(calendar),"CALENDAR");
 const s=sessionContext(at,calendar);
 if(!s.calendar_verified||s.open===null||s.close===null)
  return close("VERIFIED_CALENDAR_REQUIRED",{window:null});
 if(at<s.open||at>=s.close)return close("OUTSIDE_RTH",{window:null});
 if(book==="options"&&contractSessionVerified!==true)
  return close("OPTION_CLASS_SESSION_UNVERIFIED",{window:null});
 const m=(at-s.open)/MINUTE,length=(s.close-s.open)/MINUTE;
 const w=m<30?"RTH_OPEN_30":m<120?"RTH_MORNING_30_120":
   m>=Math.max(120,length-90)?"RTH_LAST_90":"RTH_MID";
 return {eligible:true,window:w,calendarVerified:true,
   sessionDate:s.date,optimalProfitabilityProven:false,executionAllowed:false};
}
function assess(c,{at,calendar=[]}={}){
 need(c&&typeof c.id==="string"&&c.id.length>0&&
  typeof c.symbol==="string"&&c.symbol.length>0,"CANDIDATE_ID");
 const s=windowFor({book:c.book,at,calendar,venueOpen:c.venueOpen,
   contractSessionVerified:c.contractSessionVerified});
 const base={id:c.id,book:c.book,symbol:c.symbol,window:s.window};
 if(!s.eligible)return close(s.reason,base);
 if(s.window!==c.window)return close("WRONG_WINDOW",base);
 if(c.source!=="OBSERVED"||c.costProvenance!=="BROKER_RECEIPTS"||
   c.executableFillEvidence!==true)
  return close("UNVERIFIED_FILL_AND_COST_PROVENANCE",base);
 if(c.researchGate!=="PRESPECIFIED_OOS_FWER_PASS"||
   c.preRegistered!==true||c.frozenBenchmark!==true)
  return close("OOS_FAMILYWISE_GATE_MISSING",base);
 const keys=["grossAlphaLowerBps","roundTripCostUpperBps","impactUpperBps",
   "uncertaintyBufferBps","pairedCashBaselineLowerBps","familywiseUpperP",
   "drawdownFraction","maxDailyLossFraction"];
 for(const k of keys)need(num(c[k]),"FINANCIAL_"+k);
 for(const k of ["roundTripCostUpperBps","impactUpperBps",
   "uncertaintyBufferBps","familywiseUpperP","drawdownFraction",
   "maxDailyLossFraction"])need(c[k]>=0,"NONNEGATIVE_"+k);
 need(Number.isSafeInteger(c.knownAt)&&Number.isSafeInteger(c.independentDays)&&
  Number.isSafeInteger(c.outOfSamplePaths),"EVIDENCE_SAMPLES");
 if(c.knownAt>at||at-c.knownAt>5*MINUTE)return close("STALE_EVIDENCE",base);
 if(c.independentDays<20||c.outOfSamplePaths<30)
  return close("INSUFFICIENT_OOS_DAYS",base);
 if(c.familywiseUpperP>.025)return close("FAMILYWISE_RISK",base);
 if(c.drawdownFraction>.08||c.maxDailyLossFraction>.02)
  return close("RISK_CONSTRAINTS",base);
 const net=c.grossAlphaLowerBps-c.roundTripCostUpperBps-
   c.impactUpperBps-c.uncertaintyBufferBps;
 if(net<=0||c.pairedCashBaselineLowerBps<=0)
  return close("NO_POSITIVE_COST_ADJUSTED_CASH_EDGE",{...base,netLowerBps:net});
 return {eligible:true,reason:"RESEARCH_ONLY",...base,netLowerBps:net,
  logGrowthLower:Math.log1p(net/10000),executionAllowed:false};
}
function rank(rows,context){
 need(Array.isArray(rows),"CANDIDATES");
 const ids=new Set();
 const results=rows.map(x=>{
  need(x&&typeof x.id==="string"&&!ids.has(x.id),"DUPLICATE_ID");
  ids.add(x.id);return assess(x,context);
 });
 const ranked=results.filter(x=>x.eligible)
   .sort((a,b)=>b.netLowerBps-a.netLowerBps||a.id.localeCompare(b.id));
 return {schema:"FWN9_C22_OBSERVED_WINDOW_RESEARCH_RANKING_1",
  assessments:results,rankedIds:ranked.map(x=>x.id),
  bestResearchId:ranked[0]?.id??null,fallback:"CASH",
  newSignals:0,newMarketSeeds:0,newEconomicAccounts:0,
  executionAllowed:false,recursiveSearchEnabled:false,N9S:"NO_GO"};
}

/** Compounding is across one continuous verified book, not across accounts.
 * All fees included once; withdrawals/deposits require separate flow-aware TWR.
 */
function compound(initial,periods){
 need(num(initial)&&initial>0&&Array.isArray(periods),"COMPOUND_INPUT");
 let equity=initial,lastEnd=-Infinity,lastKnown=-Infinity,total=0,log=0;
 const audit=[];
 for(const [i,p] of periods.entries()){
  need(p&&typeof p==="object","PERIOD");
  need([p.startAt,p.endAt,p.knownAt].every(x=>Number.isSafeInteger(x)&&x>0)&&
   p.startAt>=lastEnd&&p.startAt>=lastKnown&&
   p.endAt>p.startAt&&p.knownAt>=p.endAt,"CAUSAL_RECEIPT_CLOCK");
  need(p.ledgerReconciled===true&&p.costCoverageComplete===true,
   "COSTS_AND_ACCOUNT_RECONCILED");
  for(const k of ["beginningEquityUsd","endingEquityUsd","grossEconomicPnlUsd",
    "tradingFeesUsd","externalCostsUsd","externalFlowUsd"])need(num(p[k]),"ECONOMIC_"+k);
  need(p.tradingFeesUsd>=0&&p.externalCostsUsd>=0&&p.externalFlowUsd===0,
   "NO_UNPRICED_EXTERNAL_CASH_FLOW");
  const pnl=p.grossEconomicPnlUsd-p.tradingFeesUsd-p.externalCostsUsd;
  need(Math.abs(p.beginningEquityUsd-equity)<=EPS&&
   Math.abs(p.endingEquityUsd-equity-pnl)<=EPS,"SELF_FINANCED_EQUITY_IDENTITY");
  need(p.endingEquityUsd>0,"LOG_WEALTH_POSITIVE");
  log+=Math.log(p.endingEquityUsd/equity);total+=pnl;
  audit.push({period:i,beginning:equity,ending:p.endingEquityUsd,netPnl:pnl,
   knownAt:p.knownAt});
  equity=p.endingEquityUsd;lastEnd=p.endAt;lastKnown=p.knownAt;
 }
 need(Math.abs(total-(equity-initial))<=EPS,"TELESCOPING_PNL");
 return {schema:"FWN9_C22_ONE_BOOK_COMPOUNDED_ECONOMICS_1",
  initialEquityUsd:initial,terminalEquityUsd:equity,netEconomicPnlUsd:total,
  compoundReturn:equity/initial-1,logGrowth:log,audit,
  zeroCapitalResets:true,independentAssetAccountsCombined:false,
  liveBrokerFillProven:false,executionAllowed:false,N9S:"NO_GO"};
}
/** Separate observed net equity from settled deployable cash. */
function buyingPower(book,{hardCapitalUsd=20000,riskFraction=.0025,
 grossFraction=.12,reserveFraction=0}={}){
 need(book&&typeof book==="object","BOOK_OBJECT");
 for(const k of ["observedEquityUsd","settledCashUsd","committedCashUsd",
   "unsettledCashUsd","outstandingGrossUsd","outstandingRiskUsd"])
  need(num(book[k])&&book[k]>=0,"BOOK_"+k);
 need(num(hardCapitalUsd)&&hardCapitalUsd>0&&
  num(riskFraction)&&riskFraction>0&&riskFraction<=.0025&&
  num(grossFraction)&&grossFraction>0&&grossFraction<=.12&&
  num(reserveFraction)&&reserveFraction>=0&&reserveFraction<1,
  "FROZEN_CAPS");
 need(book.reconciled===true&&book.receiptsComplete===true&&
  book.riskHalt!==true,"RECONCILED_FINANCING");
 const capital=Math.min(book.observedEquityUsd,hardCapitalUsd);
 const cash=Math.max(0,book.settledCashUsd-book.committedCashUsd-
  book.unsettledCashUsd-reserveFraction*capital);
 return {schema:"FWN9_C22_SETTLED_CAPACITY_1",
  observedEquityUsd:book.observedEquityUsd,
  frozenCapitalBaseUsd:capital,settledAvailableUsd:cash,
  newGrossAdmissionHeadroomUsd:Math.min(cash,
   Math.max(0,grossFraction*capital-book.outstandingGrossUsd)),
  newRiskHeadroomUsd:Math.max(0,riskFraction*capital-book.outstandingRiskUsd),
  continuousGrossCapAssumed:false,unsettledProfitsNotAvailable:true,
  capitalGrowthDoesNotRelaxFrozen20000HardCap:true,
  executionAllowed:false,N9S:"NO_GO"};
}
/** Research quantity only, not a tradable order. */
function size(cap,{book,unitPriceUsd,unitRiskUsd,multiplier=1,step}={}){
 need(BOOKS.includes(book),"SIZE_BOOK");
 for(const [k,v] of Object.entries({unitPriceUsd,unitRiskUsd,multiplier}))
  need(num(v)&&v>0,"SIZE_"+k);
 if(book==="options")return close("OPTIONS_CONTRACT_EXECUTOR_NOT_CERTIFIED");
 need(cap?.schema==="FWN9_C22_SETTLED_CAPACITY_1"&&
  cap.executionAllowed===false&&cap.N9S==="NO_GO"&&
  num(cap.newGrossAdmissionHeadroomUsd)&&cap.newGrossAdmissionHeadroomUsd>=0&&
  num(cap.newRiskHeadroomUsd)&&cap.newRiskHeadroomUsd>=0,
  "SIZE_REQUIRES_VERIFIED_CAPACITY_OBJECT");
 const increment=step??(book==="crypto"?1e-8:1);
 need(num(increment)&&increment>=1e-8&&
  Math.abs(increment*1e8-Math.round(increment*1e8))<1e-6,
  "SIZE_SUPPORTED_PRECISION_INCREMENT");
 const max=Math.min(cap.newGrossAdmissionHeadroomUsd/(unitPriceUsd*multiplier),
  cap.newRiskHeadroomUsd/(unitRiskUsd*multiplier));
 let lots=Math.max(0,Math.floor(max/increment));
 let qty=Number((lots*increment).toFixed(8));
 while(lots>0&&(qty*unitPriceUsd*multiplier>cap.newGrossAdmissionHeadroomUsd+1e-9||
   qty*unitRiskUsd*multiplier>cap.newRiskHeadroomUsd+1e-9)){
  lots-=1;qty=Number((lots*increment).toFixed(8));
 }
 return {schema:"FWN9_C22_RESEARCH_ONLY_FUNDED_QUANTITY_1",book,
  quantity:qty,grossNotionalUsd:qty*unitPriceUsd*multiplier,
  unitStopRiskUsd:qty*unitRiskUsd*multiplier,
  executionAllowed:false,N9S:"NO_GO"};
}
function canonical(obj){
 if(obj===null||typeof obj==="string"||typeof obj==="boolean")return JSON.stringify(obj);
 if(typeof obj==="number"){need(Number.isFinite(obj),"NONFINITE_HASH_INPUT");return JSON.stringify(obj);}
 if(Array.isArray(obj))return "["+obj.map(canonical).join(",")+"]";
 need(obj&&typeof obj==="object"&&Object.getPrototypeOf(obj)===Object.prototype,
  "HASH_PLAIN_OBJECT");
 return "{"+Object.keys(obj).sort().map(k=>JSON.stringify(k)+":"+canonical(obj[k])).join(",")+"}";
}
function fingerprint(obj){need(obj&&typeof obj==="object"&&!Array.isArray(obj),"HASH_OBJECT");
 return crypto.createHash("sha256").update(canonical(obj)).digest("hex");
}
module.exports={windowFor,assess,rank,compound,buyingPower,size,fingerprint};
