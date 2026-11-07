"use strict";
const test=require("node:test");
const assert=require("node:assert/strict");
const E=require("../runtime30/modulation11_execution_equivalence.cjs");
const B=require("../runtime30/modulation11_formal_execution_bridge.cjs");
const W=require("../runtime30/modulation11_payoff_envelope.cjs");
const pos={quantity:8,entry:100.03,stop:99.03,distance:1,targetsR:[1.5,null]};
const costs={friction:.0003,perSideUsd:.005,tick:.01};
const up=[100.2,101.8,100.8,100.4,100.1,100.3,100.2,100];
const down=[100.2,101.8,100.8,95.5,97,98,99,100];
function calc(path,position=pos,c=costs,open=100){
  const bar=B.rawBar(1735920000000,open,path);
  return W.certificate({bar,prices:path,position,costs:c});
}
test("M11-P5: identical previous inventory, phase4 fork with signed but bounded differences",()=>{
  const a=calc(up),b=calc(down);
  assert(Math.abs(a.realizedNativeMinusObservedUsd+0.54)<1e-7);
  assert(Math.abs(b.realizedNativeMinusObservedUsd-15.66)<1e-7);
  for(const w of [a,b]){
    assert(w.lowerGapUsd<=w.realizedNativeMinusObservedUsd);
    assert(w.realizedNativeMinusObservedUsd<=w.upperGapUsd);
    assert(w.globalAbsoluteGapBoundUsd>=Math.abs(w.realizedNativeMinusObservedUsd));
    assert.equal(w.measuredNativeExpectedCredit,false);
    assert.equal(w.globalN9SInfeasibilityCertified,false);
    assert.equal(w.contract,"RETROSPECTIVE_BAR_END_MARK_FOR_IDENTICAL_PREBAR_LONG_INVENTORY");
  }
  console.log("M11_P5_ENVELOPE_WITNESS="+JSON.stringify({up:a,down:b}));
});
test("M11-P5: observed stop overshoot cannot exceed volume-conditioned envelope",()=>{
  const p={...pos,targetsR:[null,null]};
  const x=calc([100.1,100,95.5,98,99.2,99.5,99.8,100],p);
  assert(x.realizedNativeMinusObservedUsd>0);
  assert.equal(x.soldQuantityNative,8);
  assert.equal(x.soldQuantityObserved,8);
  assert(x.upperGapUsd>=x.realizedNativeMinusObservedUsd);
});
test("M11-P5: opening gap agrees in fill price, not execution clock",()=>{
  const p={...pos,targetsR:[null,null]};
  const x=calc([98.5,98.6,98.7,98.8,98.9,99,99.1,99.2],p,costs,98.4);
  assert(Math.abs(x.realizedNativeMinusObservedUsd)<1e-7);
  assert(x.native.fills[0].at>x.observed.fills[0].at);
});
test("M11-P5: no crossing means exactly zero gap with zero sold volume",()=>{
  const x=calc([100.1,100.2,100.3,100.4,100.5,100.4,100.3,100.2]);
  assert.equal(x.soldQuantityNative,0);
  assert.equal(x.soldQuantityObserved,0);
  assert.equal(x.lowerGapUsd,0);
  assert.equal(x.upperGapUsd,0);
  assert.equal(x.realizedNativeMinusObservedUsd,0);
});
test("M11-P5: extra target and rounding still inside correct tick-and-fee bound",()=>{
  const p={...pos,targetsR:[1.5,3]};
  const x=calc([100.5,101.82,103.5,100.5,100.3,100.2,100.1,100.2],p);
  assert.equal(x.soldQuantityNative,4);
  assert.equal(x.soldQuantityObserved,4);
  assert(x.pathwiseBoundVerified);
  assert(x.lowerGapUsd<=x.realizedNativeMinusObservedUsd+1e-7);
});
test("M11-P5: deterministic exhaustive grid over 729 synthetic engineering fixtures",()=>{
  const lattice=[95.5,100,103.5];
  let cases=0, bothSigns=new Set();
  for(let mask=0;mask<729;mask++){
    let m=mask;const path=[];
    for(let i=0;i<6;i++){path.push(lattice[m%3]);m=Math.floor(m/3);}
    path.push(99.9,100);
    const x=calc(path);
    if(x.realizedNativeMinusObservedUsd>1e-7)bothSigns.add("positive");
    if(x.realizedNativeMinusObservedUsd< -1e-7)bothSigns.add("negative");
    assert(x.pathwiseBoundVerified);
    assert(x.realizedNativeMinusObservedUsd>=x.lowerGapUsd-1e-7);
    assert(x.realizedNativeMinusObservedUsd<=x.upperGapUsd+1e-7);
    cases++;
  }
  assert.equal(cases,729);
  assert(bothSigns.has("positive")&&bothSigns.has("negative"));
  console.log("M11_P5_ENGINEERING_LATTICE_CASES="+cases);
});
test("M11-P5: input and provenance corruption are rejected",()=>{
  const bar=B.rawBar(1735920000000,100,up);
  bar.h=100;
  assert.throws(()=>W.certificate({bar,prices:up,position:pos,costs}),
    /SUBSTEP_OHLC_IDENTITY/);
});
test("M11-P5: guard capital and never claim population stochastic bound",()=>{
  const bar=B.rawBar(1735920000000,100,down);
  assert.throws(()=>W.certificate({bar,prices:down,position:pos,costs,initialUsd:30000}),
    /UNCHANGED_CAPITAL_ONLY/);
  const x=calc(down);
  assert.equal(x.globalN9SInfeasibilityCertified,false);
  assert.equal(x.measuredNativeExpectedCredit,false);
});
