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
