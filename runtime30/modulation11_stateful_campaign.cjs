"use strict";
/** M11 phase2. Diagnostic full-campaign finite-state model; NO broker/portfolio route. */
const assert = require("node:assert/strict");
const NATIVE = require("./profit8_replay.js");
const MOD = require("./modulation9_exit.cjs");
const CHECK = require("./modulation11_execution_equivalence.cjs");
const TICK_EPS = 1e-10;
function roundTick(v, tick, up) {
  return (up ? Math.ceil(v / tick - TICK_EPS) : Math.floor(v / tick + TICK_EPS)) * tick;
}
function requireFinite(values) {
  assert(values.every(v => Number.isFinite(v)), "FINITE_COUNTERFACTUAL_INPUT");
}
function statefulCampaign({signal, series, data, protocol, quantity, substeps, mode}) {
  assert(mode === "NATIVE_OHLC" || mode === "FIRST_CROSS", "DIAGNOSTIC_MODE_ONLY");
  assert(signal.direction === 1 && signal.hypothesis === "CLOSED_CHANNEL", "LONG_CLOSED_ONLY");
  assert(Number.isSafeInteger(quantity) && quantity > 0, "INTEGER_CAMPAIGN");
  const profile = MOD.profileFor(signal);
  assert(profile !== null && ["NATIVE72","PROTECT48","RUNNER72"].includes(profile.profile),
    "PROFILE_NOT_YET_MODELED");
  assert(data.splitEvents.length === 0 && data.cashDividends.length === 0, "NO_CORPORATE_EVENTS");
  const index = series.bars.findIndex(b => b.t === signal.plannedEntryAt);
  assert(index >= 0 && NATIVE.planSignalEntryAt(signal.at, data.sessions) === signal.plannedEntryAt,
    "VALID_CAUSAL_ENTRY_GRID");
  const first = series.bars[index];
  const distance = Math.ceil(signal.stopDistance / series.tick) * series.tick;
  const friction = (protocol.costs.spreadBps / 2 + protocol.costs.slippageBps) / 10000;
  const fee = protocol.costs.perSideUsd;
  const entry = roundTick(first.o * (1 + friction), series.tick, true);
  requireFinite([distance, friction, fee, entry]);
  assert(entry > distance && distance > 0, "STOP_ABOVE_ZERO");
  const holding = NATIVE.planCalendarHolding(signal, first.t, data, protocol);
  assert(holding.status !== "REFUSED_BEFORE_ENTRY", "ENTRY_REFUSED");
  const deadline = holding.deadlineAt;
  let remaining = quantity, stop = entry - distance, peak = entry;
  let pendingStop = null, realized = -quantity * fee;
  const state = MOD.createState(profile), tpDone = [false,false], fills = [], transitions = [];
  let lastKnown = first.t, ambiguity = 0;
  const sell = (qty, raw, b, reason, step) => {
    if (qty <= 0) return;
    assert(qty <= remaining, "NO_NEGATIVE_INVENTORY");
    const px = roundTick(raw * (1 - friction), series.tick, false);
    const at = step === null ? b.end : step === -1 ? b.t :
      b.t + Math.floor((step + 1) * (b.end - b.t) / 8);
    const knownAt = step === -1 ? b.t : b.availableAt;
    remaining -= qty;
    realized += (px - entry) * qty - fee * qty;
    lastKnown = Math.max(lastKnown, knownAt);
    fills.push({quantity:qty,rawPrice:raw,price:px,at,knownAt,reason,step});
  };
  for(let i=index;i<series.bars.length && remaining;i++){
    const b=series.bars[i], prior=series.bars[i-1];
    if(i>index && b.t !== prior.end){
      const priorSession = data.sessions.findIndex(s=>s.close===prior.end);
      assert(priorSession>=0 && data.sessions[priorSession+1]?.open===b.t,
        "GAP_IN_OPEN_EXPOSURE_TAPE");
    }
    const path=substeps[String(b.t)] ?? substeps[b.t];
    CHECK.checkGrid(b,path);
    if(pendingStop && b.t >= pendingStop.knownAt) {
      stop=pendingStop.price;
      pendingStop=null;
    }
    if(state) stop=MOD.advance(state,b.t,stop,1);
    if(b.t>=deadline){
      sell(remaining,b.o,b,"TIME",-1);
      break;
    }
    const stalled=state ? MOD.stalledExit(state,b.t,first.t,entry,distance,1) : null;
    if(stalled){
      sell(remaining,b.o,b,b.o<=stop?"STOP":stalled,-1);
      break;
    }
    const before = remaining;
    const stopHit=b.l<=stop;
    const targetPrices=profile.targetsR.map(r=>r===null?null:roundTick(entry+r*distance,series.tick,true));
    const targetHit=targetPrices.some((target,j)=>target!==null && !tpDone[j] && b.h>=target);
    if(stopHit && targetHit) ambiguity++;
    if(mode==="NATIVE_OHLC"){
      if(stopHit) sell(remaining,Math.min(b.o,stop),b,"STOP",null);
      else for(let j=0;j<2 && remaining;j++){
        const target=targetPrices[j];
        if(!tpDone[j] && target!==null && b.h>=target){
          sell(Math.min(Math.floor(quantity*.25),remaining),target,b,"TP"+(j+1),null);
          tpDone[j]=true;
        }
      }
    }else{
      const points=[{price:b.o,step:-1},...path.map((price,step)=>({price,step}))];
      for(const point of points){
        if(remaining===0)break;
        if(point.price<=stop){
          sell(remaining,point.price,b,"STOP",point.step);
          break;
        }
        for(let j=0;j<2 && remaining;j++){
          const target=targetPrices[j];
          if(!tpDone[j] && target!==null && point.price>=target){
            const qty=Math.min(Math.floor(quantity*.25),remaining);
            if(qty>0){sell(qty,point.price,b,"TP"+(j+1),point.step);tpDone[j]=true;}
          }
        }
      }
    }
    const pnl=realized+(b.c-entry)*remaining-remaining*fee;
    if(b.c>peak)peak=b.c;
    const custom=!profile.nativeTrailing;
    const candidate=roundTick(custom
      ? MOD.nextStop(profile,1,stop,entry,peak,distance,friction,fee,series.pointValue,series.tick)
      : NATIVE.nextTrailingStop(1,stop,entry,peak,distance,"BASELINE",signal.regime),
      series.tick,false);
    if(custom)MOD.queueStop(state,candidate,b.availableAt,stop,1);
    else if(candidate>stop) pendingStop={price:candidate,knownAt:b.availableAt};
    if(state)MOD.observe(state,b,1);
    transitions.push({barAt:b.t,remainingBefore:before,remainingAfter:remaining,stop,
      peakClose:peak,targetDone:tpDone.slice(),candidateStop:candidate,knownAt:b.availableAt});
    if(b.t>deadline)throw Error("UNOBSERVED_CALENDAR_DEADLINE");
  }
  assert(remaining===0,"UNRESOLVED_OPEN_EXPOSURE");
  assert(fills.length>0,"NO_EXIT_FILLS");
  const closed=fills.at(-1).at;
  return {schema:"HARPOON_M11_FULL_CAMPAIGN_COUNTERFACTUAL_1",mode,
    quantity,entry,distance,opened:first.t,closed,terminalKnownAt:lastKnown,deadline,
    netUsd:realized,feesUsd:fee*(quantity+fills.reduce((n,f)=>n+f.quantity,0)),
    remaining,ambiguousBars:ambiguity,fills,transitions,semanticLimit:
    "SUBSTEPS_DIAGNOSTIC_NOT_MARKET_LIQUIDITY_OR_FILL_GUARANTEE"};
}
function compareNative({signal,series,data,protocol,quantity,substeps}) {
  const options={cashDividends:true,profit8Trace:true,researchModulation:true};
  const native=NATIVE.replayCampaign(signal,series,data,protocol,"BASELINE",quantity,1,options);
  assert(native!==null,"NATIVE_PATH_REQUIRED");
  const modeled=statefulCampaign({signal,series,data,protocol,quantity,substeps,mode:"NATIVE_OHLC"});
  const discrete=statefulCampaign({signal,series,data,protocol,quantity,substeps,mode:"FIRST_CROSS"});
  const actual=native.inventoryEvents.filter(e=>e.kind==="EXIT");
  assert.equal(actual.length,modeled.fills.length,"NATIVE_FILL_COUNT");
  for(let i=0;i<actual.length;i++){
    assert.equal(-actual[i].quantityDelta,modeled.fills[i].quantity,"NATIVE_EXIT_QUANTITY");
    assert.equal(actual[i].reason,modeled.fills[i].reason,"NATIVE_EXIT_REASON");
    assert(Math.abs(actual[i].filledPrice-modeled.fills[i].price)<1e-7,"NATIVE_FILL_PRICE");
    assert.equal(actual[i].at,modeled.fills[i].at,"NATIVE_EFFECTIVE_TIME");
    assert.equal(actual[i].knownAt,modeled.fills[i].knownAt,"NATIVE_RECEIPT_TIME");
  }
  assert(Math.abs(native.netUsd-modeled.netUsd)<1e-7,"NATIVE_NET_LEDGER");
  assert.equal(native.quantity,modeled.quantity,"NATIVE_ENTRY_QUANTITY");
  assert.equal(native.opened,modeled.opened,"NATIVE_ENTRY_AT");
  assert.equal(native.closed,modeled.closed,"NATIVE_CLOSED_AT");
  return {native,modeled,discrete,deltaNetUsd:modeled.netUsd-discrete.netUsd};
}
module.exports={statefulCampaign,compareNative};
