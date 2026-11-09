"use strict";
const test=require("node:test");
const assert=require("node:assert/strict");
const E=require("../runtime30/modulation11_execution_equivalence.cjs");
const B=require("../runtime30/modulation11_formal_execution_bridge.cjs");
const pos={quantity:8,entry:100.03,stop:99.03,distance:1,targetsR:[1.5,null]};
const costs={friction:.0003,perSideUsd:.005,tick:.01};
const up=[100.2,101.8,100.8,100.4,100.1,100.3,100.2,100.0];
const down=[100.2,101.8,100.8,95.5,97,98,99,100.0];
const EPS=1e-7;
test("M11-P4: identical-target-prefix fork refutes standing-order equivalence and reconciles cash",()=>{
  const cert=B.certificate({upPrices:up,downPrices:down,position:pos,costs});
  assert.equal(cert.targetFirstCrossStep,1);
  assert.equal(cert.commonTargetFillQuantity,2);
  assert.equal(cert.exactFirstCrossStandingOrderEquivalenceRefuted,true);
  assert.equal(cert.nativeOffSupportUp,true);
  assert.equal(cert.nativeOffSupportDown,true);
  assert(cert.firstCrossAt<cert.nativeFillAtBarEnd);
  assert(cert.nativeFillAtBarEnd<cert.receiptAvailableAt);
  assert(cert.gapFromExecutionNativeUpUsd<-EPS,"NATIVE_TARGET_REDUCES_MARKED_EQUITY");
  assert(cert.gapFromExecutionNativeDownUsd>EPS,"NATIVE_STOP_FLOOR_ADDS_MARKED_EQUITY");
  assert.equal(cert.universalNativeMarketBoundCertified,false);
  assert.equal(cert.nativeN9SInfeasibilityCertified,false);
  console.log("M11_P4_STRUCTURAL_WITNESS="+JSON.stringify(cert));
});
test("M11-P4: adverse branch with prior target executed in causal first-cross sequence",()=>{
  const bar=B.rawBar(1735920000000,100,down);
  const n=E.nativeBarExits(bar,down,pos,costs);
  const f=E.substepBarExits(bar,down,pos,costs);
  assert.deepEqual(n.fills.map(x=>[x.reason,x.quantity]),[["STOP",8]]);
  assert.deepEqual(f.fills.map(x=>[x.reason,x.quantity]),[["TP1",2],["STOP",6]]);
  assert(n.fills.every(x=>x.at===bar.end));
  assert(f.fills[0].at<bar.end);
  const expected=B.markedEquity({position:pos,fills:n.fills,costs,close:bar.c});
  const expected2=B.markedEquity({position:pos,fills:f.fills,costs,close:bar.c});
  assert(Math.abs((expected.terminalEquityUsd-expected2.terminalEquityUsd)-
    B.certificate({upPrices:up,downPrices:down,position:pos,costs}).gapFromExecutionNativeDownUsd)<EPS);
});
test("M11-P4: stop-only overshoot can credit more than first-step trading price",()=>{
  const p={...pos,targetsR:[null,null]};
  const path=[100.1,100,95.5,98,99.2,99.5,99.8,100];
  const bar=B.rawBar(1735920000000,100,path);
  const n=E.nativeBarExits(bar,path,p,costs),f=E.substepBarExits(bar,path,p,costs);
  assert.equal(n.fills[0].rawPrice,p.stop);
  assert.equal(f.fills[0].rawPrice,95.5);
  assert(B.markedEquity({position:p,fills:n.fills,costs,close:bar.c}).terminalEquityUsd>
    B.markedEquity({position:p,fills:f.fills,costs,close:bar.c}).terminalEquityUsd);
});
test("M11-P4: opening gap preserves raw traded price but not identical event clocks",()=>{
  const p={...pos,targetsR:[null,null]};
  const path=[98.5,98.6,98.7,98.8,98.9,99,99.1,99.2];
  const bar=B.rawBar(1735920000000,98.4,path);
  const n=E.nativeBarExits(bar,path,p,costs),f=E.substepBarExits(bar,path,p,costs);
  assert.equal(n.fills[0].rawPrice,bar.o);
  assert.equal(f.fills[0].rawPrice,bar.o);
  assert(n.fills[0].at>f.fills[0].at);
  assert.equal(n.fills[0].knownAt,f.fills[0].knownAt);
});
test("M11-P4: counterfeit common prefix is rejected, not silently certified",()=>{
  const altered=down.slice();altered[1]=101.9;
  assert.throws(()=>B.certificate({upPrices:up,downPrices:altered,position:pos,costs}),
    /COMMON_FIRST_TARGET_CROSS|SHARED_PREFIX_THROUGH_TARGET/);
});
test("M11-P4: invalid bar-to-step provenance fails closed",()=>{
  const bar=B.rawBar(1735920000000,100,up);
  bar.h+=1;
  assert.throws(()=>E.checkGrid(bar,up),/SUBSTEP_OHLC_IDENTITY/);
});
test("M11-P4: future stop branch is not a strategy signal and has no promotion claim",()=>{
  const cert=B.certificate({upPrices:up,downPrices:down,position:pos,costs});
  assert.equal(cert.scope,"DISCRETE_EIGHT_STEP_PREPOSITIONED_PASSIVE_ORDERS_ONLY");
  assert.equal(cert.nativeN9SInfeasibilityCertified,false);
});
