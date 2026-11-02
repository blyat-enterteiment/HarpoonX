"use strict";
// Synthetic accounting/regression fixtures; no financial trial or external I/O.
const test=require("node:test"),assert=require("node:assert/strict");
const {validateRequest,executeReplay,SimulatedReplayBroker}=require("./coordinator_replay.cjs");
const {runFundedComparison}=require("./funded_comparison.cjs");
const {syntheticComparison}=require("./fixtures/funded_comparison_fixture.cjs");
function reserved(amount=1000){
  const input=syntheticComparison();
  input.common_request.execution_model.operating_cash_reserve={method:"FIXED_INITIAL_CASH_RESERVE",
    amount_usd:amount,known_at:input.common_request.start_at-1};
  return input;
}
test("the actual coordinator retains reserved cash and exposes only remaining buying power",async()=>{
  const input=reserved(),result=await executeReplay(input.common_request);
  assert(result.fills.length>0,"Exercise actual trading with a funded reserve");
  for(const s of result.snapshots){
    assert.equal(s.account.operating_cash_reserve_usd,1000);
    assert.equal(Number(s.account.buying_power),Number(s.account.cash)-1000);
    assert.equal(Number(s.account.non_marginable_buying_power),Number(s.account.cash)-1000);
    assert(Number(s.account.cash)>=1000);
    assert(Math.abs(Number(s.account.equity)-Number(s.account.cash)-s.positions.reduce((n,p)=>n+Number(p.market_value),0))<1e-7);
  }
});
test("a nearly fully reserved account produces no purchases instead of recycling operating money",async()=>{
  const input=reserved(19999),result=await executeReplay(input.common_request);
  assert.equal(result.fills.length,0);assert.equal(result.metrics.account_equity_final_usd,20000);
  assert.equal(result.metrics.economic_pnl_net_usd,-1);
  assert.equal(Number(result.final_state.account.buying_power),1);
});
test("late, unfunded, negative and insufficient reserves are rejected before replay",()=>{
  for(const change of [r=>r.amount_usd=-1,r=>r.amount_usd=20001,r=>r.amount_usd=.5,
    (r,c)=>r.known_at=c.start_at,r=>r.method="FREE_CAPITAL",r=>r.amount_usd=null]){
    const input=reserved(),common=input.common_request;change(common.execution_model.operating_cash_reserve,common);
    assert.throws(()=>validateRequest(common),/OPERATING_RESERVE/);
  }
});
test("partial fills and their fees cannot consume the locked operating reserve",()=>{
  const input=reserved(100),common=input.common_request;
  common.initial_cash_usd=1000;common.execution_model.fees_bps_per_side=0;common.execution_model.fee_per_fill_usd=1;
  const clock={now:common.start_at+2},broker=new SimulatedReplayBroker(common,clock);
  broker.engine={state:{intents:[]}};
  broker.quotes.set("AAPL",{bid:100,ask:100,at:clock.now});
  const order={side:"buy",symbol:"AAPL",qty:"10",filled_qty:"0",filled_avg_price:null,created_ms:common.start_at,
    client_order_id:"synthetic-reserve-partial"};
  const quote={market_at:clock.now,received_at:clock.now};
  broker.fill(order,8,100,"synthetic-first-fill",quote);
  assert.equal(broker.cash,199);assert.equal(Number(broker.account().buying_power),99);
  const cash=broker.cash,count=broker.fills.length;
  assert.throws(()=>broker.fill(order,1,100,"synthetic-late-fill",quote),/CAPITAL_OR_INVENTORY/);
  assert.equal(broker.cash,cash);assert.equal(broker.fills.length,count);
});
test("reserving capital is neither a fee nor an additional contribution in all three funded paths",async()=>{
  const input=reserved(),report=await runFundedComparison(input);
  assert.equal(report.status,"ENGINEERING_ONLY");assert.equal(report.financial_acceptance_allowed,false);
  assert.equal(report.parity.complete_policy_coverage,true);
  for(const role of ["C0","RIDGE","SVR"]){
    const curve=report.curves[role],last=curve.curve.at(-1);
    assert.equal(last.account_equity_usd-last.economic_equity_usd,1);
    assert.equal(curve.metrics.account_pnl_net_usd-curve.metrics.economic_pnl_net_usd,1);
    assert(curve.curve.every(r=>r.external_flow_usd===0));
    for(const s of report.reports.find(r=>r.result.candidate===role).result.snapshots)
      assert.equal(Number(s.account.buying_power),Number(s.account.cash)-1000);
  }
});
