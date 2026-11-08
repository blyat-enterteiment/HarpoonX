"use strict";
/*
 * FWN9 P9M-C4 — finite conditional price-attainability certificate.
 * All first-seven-substep permutations are enumerated, eighth CLOSE is fixed.
 * The log-linear interpolation is a specified COUNTERFACTUAL path, not the
 * original eight-step stochastic law, an executable broker quote, or alpha.
 * No RNG, no broker, no optimizer, no mutation of M9 or native replay.
 */
const A=require("node:assert/strict");
const G=require("./modulation11_execution_equivalence.cjs");
const EPS=1e-9, SCALE=1000000;
const near=(a,b)=>Math.abs(a-b)<=EPS*Math.max(1,Math.abs(a),Math.abs(b));
const tick=(v,t,up)=>(up?Math.ceil(v/t-1e-8):Math.floor(v/t+1e-8))*t;
function ensure(ok,code){A.ok(ok,"P9MC4_"+code);}
function fill(fills,{raw,qty,reason,at,knownAt,step},costs){
  if(!qty)return;
  const px=tick(raw*(1-costs.friction),costs.tick,false);
  fills.push({quantity:qty,rawPrice:raw,fillPrice:px,
    commissionUsd:qty*costs.perSideUsd,reason,at,knownAt,step});
}
/** Strictly monotone log-linear connector between adjacent observed prices. */
function continuousFirstPass(bar,prices,position,costs){
  G.checkGrid(bar,prices);
  ensure(position.quantity>0&&position.quantity%4===0,"FOUR_QUARTER_SHARES");
  const targets=position.targetsR.map(r=>r===null?null:
    tick(position.entry+r*position.distance,costs.tick,true));
  let residual=position.quantity;const done=[false,false],fills=[];
  function stop(raw,at,step){
    fill(fills,{raw,qty:residual,reason:"STOP",at,knownAt:bar.availableAt,step},costs);
    residual=0;
  }
  function target(j,raw,at,step){
    if(done[j]||targets[j]===null)return;
    const qty=Math.min(residual,Math.floor(position.quantity/4));
    fill(fills,{raw,qty,reason:"TP"+(j+1),at,knownAt:bar.availableAt,step},costs);
    residual-=qty;done[j]=true;
  }
  if(bar.o<=position.stop)stop(bar.o,bar.t,-1);
  else for(let j=0;j<2;j++)if(targets[j]!==null&&bar.o>=targets[j])
    target(j,targets[j],bar.t,-1);
  const stepMs=(bar.end-bar.t)/8;
  let prev=bar.o;
  for(let k=0;k<8&&residual>0;k++){
    const next=prices[k],start=bar.t+k*stepMs;
    if(next<prev&&next<=position.stop&&prev>position.stop){
      const frac=Math.log(position.stop/prev)/Math.log(next/prev);
      ensure(frac>=-EPS&&frac<=1+EPS,"INTERPOLATION_FRACTION");
      stop(position.stop,Math.floor(start+Math.max(0,Math.min(1,frac))*stepMs),k);
    }else if(next>prev){
      for(let j=0;j<2;j++){
        const level=targets[j];
        if(level!==null&&!done[j]&&prev<level&&next>=level){
          const frac=Math.log(level/prev)/Math.log(next/prev);
          ensure(frac>=-EPS&&frac<=1+EPS,"INTERPOLATION_FRACTION");
          target(j,level,Math.floor(start+Math.max(0,Math.min(1,frac))*stepMs),k);
        }
      }
    }
    prev=next;
  }
  return {fills,remainingQuantity:residual,
    mechanism:"PIECEWISE_LOG_LINEAR_FIRST_PASSAGE_ASSUMPTION"};
}
function nativePriceSupport(bar,prices,raw){
  G.checkGrid(bar,prices);
  const points=[bar.o,...prices];
  return {raw,
    observedEightStep:points.some(p=>near(p,raw)),
    continuousLogLinear:points.slice(1).some((p,i)=>
      raw>=Math.min(points[i],p)-EPS&&raw<=Math.max(points[i],p)+EPS),
    implicitContinuousInterpolationRequired:
      !points.some(p=>near(p,raw))&&
      points.slice(1).some((p,i)=>raw>=Math.min(points[i],p)-EPS&&
        raw<=Math.max(points[i],p)+EPS)};
}
function integerMicros(usd){
  ensure(Number.isFinite(usd)&&Math.abs(usd)<1000000,"FINITE_MICRO_USD");
  const scaled=usd*SCALE;
  ensure(Math.abs(scaled-Math.round(scaled))<1e-3,"MICRO_PRECISION");
  return BigInt(Math.round(scaled));
}
function independentClose(position,fills,costs){
  let qty=position.quantity,cash=-BigInt(qty)*(
    integerMicros(position.entry)+integerMicros(costs.perSideUsd));
  for(const f of fills){
    ensure(Number.isSafeInteger(f.quantity)&&f.quantity<=qty&&f.quantity>0,
      "NONNEGATIVE_INVENTORY");
    cash+=BigInt(f.quantity)*(integerMicros(f.fillPrice)-
      integerMicros(costs.perSideUsd));
    qty-=f.quantity;
  }
  ensure(qty===0,"ALL_POSITIONS_MUST_CLOSE_IN_THIS_FIXTURE");
  return Number(cash)/SCALE;
}
function uniqueSevenWithClose(prices,callback){
  ensure(prices.length===8&&prices.every(x=>Number.isFinite(x)&&x>0),
    "EIGHT_FINITE_PRICES");
  const original=prices.slice(0,7),last=prices[7],counts=new Map();
  for(const p of original)counts.set(p,(counts.get(p)??0)+1);
  const keys=[...counts.keys()].sort((a,b)=>a-b),path=[];
  let visited=0;
  function walk(){
    if(path.length===7){
      visited++;ensure(visited<=5040,"PERMUTATION_BUDGET");
      callback([...path,last]);return;
    }
    for(const key of keys){
      const n=counts.get(key);
      if(!n)continue;
      counts.set(key,n-1);path.push(key);walk();path.pop();counts.set(key,n);
    }
  }
  walk();return visited;
}
function certificate({bar,prices,position,costs,capitalUsd=20000,calendarFeesUsd=8}){
  ensure(capitalUsd===20000&&calendarFeesUsd===8,"FROZEN_FIXTURE_ACCOUNT");
  ensure(position.quantity===8&&position.targetsR.length===2 &&
    costs.friction===.0003&&costs.perSideUsd===.005&&costs.tick===.01,
    "FROZEN_NOMINAL_FIXTURE");
  G.checkGrid(bar,prices);
  const native=G.nativeBarExits(bar,prices,position,costs);
  ensure(native.remainingQuantity===0,"FULL_NATIVE_CLOSE_REQUIRED");
  const nativePnl=independentClose(position,native.fills,costs);
  const support=native.fills.map(x=>nativePriceSupport(bar,prices,x.rawPrice));
  let lowDisc=Infinity,highDisc=-Infinity,lowInterp=Infinity,highInterp=-Infinity;
  let discLower=null,discUpper=null,interpLower=null,interpUpper=null;
  let nativeBetterThanDiscrete=0,nativeWorseThanDiscrete=0,nativeEqualDiscrete=0,
    continuousPayoffParity=0,continuousReceiptTimingParity=0,
    exactDiscreteFillParity=0,targetFirst=0,stopFirst=0;
  const signature=fillRows=>fillRows.map(x=>[x.reason,x.quantity,Math.round(x.fillPrice*SCALE)]);
  const nativeSig=JSON.stringify(signature(native.fills));
  const n=uniqueSevenWithClose(prices,path=>{
    G.checkGrid(bar,path);
    const discrete=G.substepBarExits(bar,path,position,costs);
    const continuous=continuousFirstPass(bar,path,position,costs);
    ensure(discrete.remainingQuantity===0&&continuous.remainingQuantity===0,
      "FIXTURE_COMPLETE_EXIT_SUPPORT");
    const d=independentClose(position,discrete.fills,costs);
    const c=independentClose(position,continuous.fills,costs);
    ensure(near(G.incrementalCashLedger(position,discrete.fills,costs).markedPnlUsd,d),
      "INDEPENDENT_DISCRETE_LEDGER");
    if(d<lowDisc){lowDisc=d;discLower=path;}
    if(d>highDisc){highDisc=d;discUpper=path;}
    if(c<lowInterp){lowInterp=c;interpLower=path;}
    if(c>highInterp){highInterp=c;interpUpper=path;}
    if(nativePnl>d+1e-7)nativeBetterThanDiscrete++;
    else if(nativePnl<d-1e-7)nativeWorseThanDiscrete++;
    else nativeEqualDiscrete++;
    if(JSON.stringify(signature(discrete.fills))===nativeSig)
      exactDiscreteFillParity++;
    if(JSON.stringify(signature(continuous.fills))===nativeSig){
      continuousPayoffParity++;
      if(continuous.fills.every((f,i)=>f.at===native.fills[i]?.at&&
          f.knownAt===native.fills[i]?.knownAt))
        continuousReceiptTimingParity++;
    }
    if(continuous.fills.some(f=>f.reason==="TP1"))targetFirst++;
    if(continuous.fills[0]?.reason==="STOP")stopFirst++;
  });
  ensure(n===targetFirst+stopFirst,"BARRIER_FIRST_PARTITION");
  const out={schema:"HARPOON_FWN9_P9MC4_FINITE_PRICE_ATTAINABILITY_1",
    sourceNature:"DETERMINISTIC_SYNTHETIC_ENGINEERING_NOT_MARKET_DATA",
    contract:"FIXED_MULTISSET_FIRST_SEVEN;EIGHTH_CLOSE_FIXED;ALL_DISTINCT_PERMUTATIONS",
    counts:{exhaustiveUniqueOrders:n,targetFirst,stopFirst,
      nativeBetterThanDiscrete,nativeWorseThanDiscrete,nativeEqualDiscrete,
      exactDiscreteFillParity,continuousPayoffParity,continuousReceiptTimingParity},
    native:{netTradingUsd:nativePnl,rawFillSupport:support,
      reportedEffectiveAt:native.fills.map(f=>f.at),
      knownAt:native.fills.map(f=>f.knownAt)},
    eightStepFirstCross:{minimumNetUsd:lowDisc,maximumNetUsd:highDisc,
      minimizer:discLower,maximizer:discUpper},
    hypotheticalContinuousInterpolation:{minimumNetUsd:lowInterp,
      maximumNetUsd:highInterp,minimizer:interpLower,maximizer:interpUpper,
      stochasticLawPreserved:false,liquidityEstablished:false},
    nativeWithinFiniteDiscreteEnvelope:
      nativePnl>=lowDisc-EPS&&nativePnl<=highDisc+EPS,
    capitalUsd,calendarFeesUsd,
    invariants:{observedOHLCAndFinalCloseFixed:true,
      nativeStopFirstBarSameForEveryOrdering:true,
      originalEightStepStochasticLawUntouched:true,
      noProbabilitiesInferredFromPermutationCounts:true,
      noAlphaOrEconomicAccounts:true,WEAKPopulationBoundCertified:false,
      nativeExecutionSelfFinancingPopulationCertified:false,N9SAccepted:false},
    caveat:"Exact extrema over this finite conditional permutation catalog only; not the generator's conditional distribution or market fill support"};
  return out;
}
module.exports={certificate,continuousFirstPass,nativePriceSupport,independentClose};
