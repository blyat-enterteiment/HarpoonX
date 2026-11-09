"use strict";
/** Read-only original funded native IOC admission / holding validator. */
const A=require("node:assert/strict");
const need=(x,tag)=>A.ok(x,"C20_"+tag),finite=Number.isFinite;
const close=(x,y)=>finite(x)&&finite(y)&&Math.abs(x-y)<=1e-6*Math.max(1,Math.abs(x),Math.abs(y));
function audit({native,data,limits}){
 need(native?.metadata?.executionNature==="HISTORICAL_MODELED_OHLCV;NOT_BROKER_RECEIPTS"&&native?.metadata?.entryExecution==="IOC_LIMIT_COMMON_CAUSAL_30BPS"&&native?.portfolio?.scope==="MODELED_SHARED_CAPITAL_INTEGER_LOTS_CAUSAL_RESERVATIONS"&&native?.reservationBook?.schema==="HARPOON_FUNDED_RESERVATIONS_1"&&Array.isArray(native.funded)&&Array.isArray(native.states)&&Array.isArray(native.modeledNoFills),"ORIGINAL_FUNDED_REPLAY");
 need(limits?.capitalUsd===20000&&limits?.grossFraction===.12&&limits?.assetFraction===.12&&limits?.openRiskFraction===.0025&&data?.schema==="HARPOON-ULTIMATE-DATA-1"&&data?.kind==="ALPACA_PROXY"&&data?.splitEvents?.length===0&&data?.cashDividends?.length===0,"FROZEN_CONTRACT");
 const states=new Map(native.states.map(s=>[s.opportunity.id,s]));
 need(states.size===native.states.length,"UNIQUE_DECISIONS");
 let filled=0,approved=0;const rows=[];
 for(const trade of native.funded){
  const s=states.get(trade.id),plan=s?.iocPlan,commit=s?.profit8CommittedReservation;
  need(s?.status==="MODELED_CAMPAIGN"&&s.positionOpened===true&&["SYNA","SYNB"].includes(trade.symbol)&&trade.direction===1&&Number.isSafeInteger(trade.quantity)&&trade.quantity>0,"MATCHED_FUNDED_ENTRY");
  need(plan?.status==="PLANNED"&&finite(plan.priceCeiling)&&finite(commit?.priceCeiling)&&finite(commit?.notionalUsd)&&close(plan.priceCeiling,commit.priceCeiling)&&close(commit.notionalUsd,trade.quantity*plan.priceCeiling)&&commit.quantity===trade.quantity&&finite(s.equity)&&s.equity>0,"IOC_COMMITMENT_AND_EQUITY");
  const entries=trade.inventoryEvents.filter(e=>e.kind==="ENTRY");
  need(entries.length===1&&entries[0].at===trade.opened&&entries[0].knownAt===trade.opened&&entries[0].quantityDelta===trade.quantity&&finite(entries[0].filledPrice),"SINGLE_CAUSAL_ENTRY_RECEIPT");
  const bar=data.series.find(z=>z.symbol===trade.symbol)?.bars.find(b=>b.t===trade.opened);
  need(bar&&finite(bar.o)&&bar.o>0&&bar.availableAt>=bar.end,"SOURCE_OPENING_BAR");
  const px=entries[0].filledPrice,notional=trade.quantity*px;
  need(px+1e-6>=bar.o&&px<=plan.priceCeiling+1e-6&&notional<=commit.notionalUsd+1e-6&&commit.notionalUsd<=limits.assetFraction*s.equity+1e-6,"SOURCE_FILL_LE_IOC_LE_12PCT_ADMISSION");
  need(trade.closed>=trade.opened&&trade.closed-trade.opened<=72*3600000&&Number.isSafeInteger(trade.holdingClockStartedAt)&&trade.holdingClockStartedAt<=trade.opened&&trade.closed-trade.holdingClockStartedAt<=72*3600000,"SOURCE_HOLD_LE72H");
  filled+=notional;approved+=commit.notionalUsd;
  rows.push({id:trade.id,symbol:trade.symbol,modeledFilledNotionalUsd:notional,approvedIocNotionalUsd:commit.notionalUsd,originalDecisionEquityUsd:s.equity,admissionCapOnly:true});
 }
 for(const nf of native.modeledNoFills)need(nf.positionOpened===false&&!native.funded.some(z=>z.id===nf.signalId),"NOFILL_NOT_FUNDED");
 return {schema:"HARPOON_M11_C20_ORIGINAL_IOC_ADMISSION_A_1",nativeFundedCount:native.funded.length,nativeNoFillCount:native.modeledNoFills.length,modeledFilledNotionalSumUsd:filled,approvedIocNotionalSumUsd:approved,rows,original12PercentAppliesOnlyAtAdmission:true,native72HourReceiptsChecked:true,expectedPopulationAdmissionNotionalUpperUsd:null,expectedPopulationAUpperUsdSubsteps:null,fullNativePolicyClassCertified:false,brokerPriceExecutabilityCertified:false,N9S:"NO_GO",newAccounts:0,openedM10FinalAccounts:0};
}
module.exports={audit};
