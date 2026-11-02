'use strict';
// Financial bookkeeping fixtures only. These tests never submit broker orders
// and do not establish an investable advantage or authenticate broker receipts.
const test = require('node:test');
const assert = require('node:assert/strict');
const {NetAccountLedger, netLedgerDigest} = require('../runtime30/net_accounting.js');
const T0 = Date.UTC(2026, 9, 15, 13, 30), MIN = 60000;
const ASSETS = [
  {symbol:'AAPL',book:'equity',multiplier:1,currency:'USD'},
  {symbol:'SPY',book:'etf',multiplier:1,currency:'USD'},
  {symbol:'AAPL261120C00200000',book:'options',multiplier:100,currency:'USD'},
];
class Store {
  data = new Map();
  fail = false;
  writes = 0;
  async get(key) { return structuredClone(this.data.get(key) ?? null); }
  async put(key, value) {
    if (this.fail) throw Error('SYNTHETIC_DISK_FULL');
    this.writes++; this.data.set(key,structuredClone(value)); return true;
  }
  async lease() { return true; }
  async close() {}
}
class FinancialBroker {
  account = {id:'ledger-account',currency:'USD',equity:'20000',cash:'20000'};
  positions = [];
  activities = [];
  calls = [];
  pageOverride = null;
  hook = null;
  constructor() { this.sequence = 0; }
  mark(symbol, price) {
    const position = this.positions.find(p=>p.symbol===symbol);
    assert(position, 'mark requires an actual fixture position');
    position.market_value = String(Number(position.qty)*price*(position.multiplier??1));
    this.revalue();
  }
  revalue() { this.account.equity = String(Number(this.account.cash)+this.positions.reduce((s,p)=>s+Number(p.market_value),0)); }
  fill({symbol='AAPL',qty=1,price=100,side='buy',at=T0+MIN/2,order_id='order',multiplier=1,type='fill',...rest}={}) {
    const signed = side==='buy'?qty:-qty;
    this.account.cash = String(Number(this.account.cash)-signed*price*multiplier);
    let pos = this.positions.find(p=>p.symbol===symbol);
    if (!pos) {pos={symbol,qty:'0',market_value:'0',asset_class:multiplier===100?'us_option':'us_equity',multiplier};this.positions.push(pos);}
    pos.qty = String(Number(pos.qty)+signed);
    pos.market_value = String(Number(pos.qty)*price*multiplier);
    this.positions = this.positions.filter(p=>Number(p.qty)!==0);
    const row = {id:'activity-'+(++this.sequence),activity_type:'FILL',transaction_time:new Date(at).toISOString(),
      qty:String(qty),price:String(price),symbol,side,order_id,type,...rest};
    this.activities.push(row);this.revalue();return row;
  }
  cash(type,amount,at=T0+MIN/2,extra={}) {
    const row={id:'activity-'+(++this.sequence),activity_type:type,net_amount:String(amount),date:new Date(at).toISOString().slice(0,10),...extra};
    this.activities.push(row);this.account.cash=String(Number(this.account.cash)+amount);this.revalue();return row;
  }
  async request(path,method='GET') {
    assert.equal(method,'GET','the ledger must never send an external write');
    this.calls.push(path);if(this.hook) await this.hook(path,this);
    if(path==='/v2/account')return structuredClone(this.account);
    if(path==='/v2/positions')return structuredClone(this.positions);
    if(path.startsWith('/v2/account/activities?')){
      const q=new URL(path,'https://fixture.invalid').searchParams;
      if(this.pageOverride)return structuredClone(await this.pageOverride(q));
      const token=q.get('page_token'),index=token?this.activities.findIndex(x=>x.id===token)+1:0;
      return structuredClone(this.activities.slice(index,index+Number(q.get('page_size'))));
    }
    throw Error('UNEXPECTED_READ '+path);
  }
}
function report(through,entries=[],from=T0) {
  return {schema:'HARPOON_COST_RECEIPT_1',account_id:'ledger-account',currency:'USD',
    receipt_id:'fixture-cost-receipt-'+through,coverage_complete:true,
    from,through,known_at:through,reference:'fixture-cost-coverage-'+through,
    categories:['DATA','INFRASTRUCTURE','INFERENCE','OTHER'],entries};
}
function cost(id,amount,at,extra={}) {
  return {id,amount_usd:amount,at,known_at:at,category:'INFRASTRUCTURE',reference:'fixture-invoice-'+id,already_in_account:false,...extra};
}
function input(now,extras={}) {return {now,instruments:ASSETS,externalCosts:report(now),...extras};}
async function harness(options={},initialize=true) {
  const store=new Store(),api=new FinancialBroker();
  const ledger=new NetAccountLedger(store,api,'fixture-net-ledger','ledger-account',{executionNature:'SYNTHETIC_ENGINEERING_ONLY',...options});
  if(initialize)await ledger.refresh(input(T0));
  return {store,api,ledger};
}
function near(actual,expected,epsilon=1e-10){assert(Number.isFinite(actual));assert(Math.abs(actual-expected)<=epsilon,`${actual} != ${expected}`);}
function preflow(activity,equityBefore,equityAfter,at,knownAt=at) {
  const evidence={activityId:activity.id,at,equityBefore,equityAfter};
  return {...evidence,known_at:knownAt,reference:'fixture-preflow-'+activity.id,evidence,evidenceHash:netLedgerDigest(evidence)};
}
async function rejected(ledger,now,pattern,extras={}) {
  const count=ledger.exportState(now).observations.length;
  await assert.rejects(ledger.refresh(input(now,extras)),pattern);
  assert.equal(ledger.view(now).reconciled,false);
  assert.equal(ledger.exportState(now).observations.length,count,'invalid evidence must not advance the accepted curve');
}

// 30.15: invalid expense evidence does not invalidate an independently reconciled
// broker NAV. It rejects the economic extension and preserves prior costs.
async function rejectedCost(ledger,now,pattern,extras={}) {
  const before=ledger.exportState(now),costs=structuredClone(before.externalCosts);
  await ledger.refresh(input(now,extras));
  const after=ledger.exportState(now);
  assert.equal(after.reconciled,true);
  assert.equal(after.observations.length,before.observations.length+1);
  assert.equal(after.economicComplete,false);
  assert.equal(after.accounting.economicNetPnlUsd,null);
  assert.equal(after.accounting.externalCostsUsd,null);
  assert.equal(after.observations.at(-1).economicReturn,null);
  assert.equal(after.costSource.status,'REJECTED_BY_LEDGER');
  assert.match(after.costSource.reason,pattern);
  assert.deepEqual(after.externalCosts,costs);
  assert.deepEqual(after.observations.slice(0,-1),before.observations);
}

test('incremental integrity hashing preserves canonical JSON bytes, including Unicode and number values',()=>{
  const {createHash}=require('node:crypto');
  const value={z:[null,'ñ / \"',true,0,-0,1e-7],a:{c:2,b:1}};
  const canonical='{"a":{"b":1,"c":2},"z":[null,"ñ / \\\"",true,0,0,1e-7]}';
  assert.equal(netLedgerDigest(value),createHash('sha256').update(canonical).digest('hex'));
  assert.equal(netLedgerDigest(value),netLedgerDigest({a:{b:1,c:2},z:value.z}));
  assert.throws(()=>netLedgerDigest({x:NaN}),/NONFINITE_EVIDENCE/);
});

test('baseline is a current observation, with atomic complete evidence and no external writes',async()=>{
  const {store,api,ledger}=await harness();const v=ledger.exportState(T0);
  assert.equal(v.status,'OBSERVED_ECONOMIC_NET');assert.equal(v.reconciled,true);
  assert.equal(v.accounting.accountNetPnlUsd,0);assert.equal(v.accounting.economicNetPnlUsd,0);
  assert.equal(v.observations.length,1);assert.equal(v.authorizesOrders,false);
  assert.equal(v.sourceAuthenticityVerified,false);assert.equal(v.marketDataFreshnessVerified,false);
  assert.equal(v.baseline.marketTimestamp,null);assert.equal(store.writes,1);
  assert.equal(api.calls.length,5);assert.equal(v.coverage.baselineScope,'FIRST_RECONCILED_OBSERVATION_NOT_HISTORICAL_ACCOUNT_INCEPTION');
  assert.equal(netLedgerDigest(v.baseline.sourceReceipt),v.baseline.sourceHash);
});

test('missing external cost evidence remains null while account NAV and PnL are reconciled',async()=>{
  const {ledger}=await harness({},false);
  await ledger.refresh({now:T0,instruments:ASSETS});const v=ledger.view(T0);
  assert.equal(v.status,'OBSERVED_ACCOUNT_NET');assert.equal(v.reconciled,true);
  assert.equal(v.accounting.externalCostsUsd,null);assert.equal(v.accounting.economicNetPnlUsd,null);
  assert.equal(v.economicComplete,false);assert.equal(ledger.performanceInput(T0),null);
});

test('partial fills are counted by delta qty; later cancellation contributes no invented fill',async()=>{
  const {api,ledger}=await harness();
  api.fill({qty:4,type:'partial_fill',cum_qty:'4',leaves_qty:'6'});
  api.fill({qty:3,price:101,type:'partial_fill',cum_qty:'7',leaves_qty:'3',at:T0+40000});
  // Remaining three shares canceled: no FILL activity and no inventory change.
  await ledger.refresh(input(T0+MIN));const v=ledger.exportState(T0+MIN);
  assert.equal(v.activities.length,2);assert.equal(v.observations.at(-1).positions[0].quantity,7);
  assert.equal(v.reconciliation.expectedCashUsd,19297);
  near(v.accounting.accountNetPnlUsd,4);assert.equal(v.reconciled,true);
});

test('open position losses are included, independently of realized trade profit',async()=>{
  const {api,ledger}=await harness();api.fill({qty:10});api.mark('AAPL',90);
  await ledger.refresh(input(T0+MIN,{externalCosts:report(T0+MIN,[cost('infra',2,T0+30000)])}));
  const v=ledger.exportState(T0+MIN);near(v.accounting.accountNetPnlUsd,-100);near(v.accounting.economicNetPnlUsd,-102);
  near(v.accounting.openPositionMarketValueUsd,900);near(v.accounting.totalReturnEconomic,-102/20000);
  assert.equal(v.observations[1].economicEquity,19898);
});

test('reported fee is already in NAV: one subtraction, and replay is idempotent',async()=>{
  const {api,ledger}=await harness();api.fill({qty:2});api.cash('FEE',-1);
  await ledger.refresh(input(T0+MIN));await ledger.refresh(input(T0+2*MIN));
  const v=ledger.exportState(T0+2*MIN);assert.equal(v.activities.length,2);
  assert.equal(v.accounting.reportedAccountFeesUsd,1);assert.equal(v.accounting.accountNetPnlUsd,-1);
  assert.equal(v.accounting.economicNetPnlUsd,-1);assert.equal(v.observations[2].accountReturn,0);
});

test('operating cost booked in broker cash is linked and never charged a second time',async()=>{
  const {api,ledger}=await harness();const fee=api.cash('FEE',-2);
  const expenses=[cost('already-paid',2,T0+30000,{already_in_account:true,activity_id:fee.id})];
  await ledger.refresh(input(T0+MIN,{externalCosts:report(T0+MIN,expenses)}));
  const v=ledger.view(T0+MIN);assert.equal(v.accounting.accountNetPnlUsd,-2);assert.equal(v.accounting.economicNetPnlUsd,-2);
  assert.equal(v.accounting.externalCostsUsd,0);
});

test('ambiguous embedded trade fee or net-amount commission cannot be silently counted twice',async()=>{
  for(const extra of [{commission:'1'},{net_amount:'-101'}]){
    const {api,ledger}=await harness();api.fill(extra);
    await rejected(ledger,T0+MIN,/AMBIGUOUS_(EMBEDDED_FILL_FEE|FILL_NET_AMOUNT)/);
  }
});

test('deposits and withdrawals neutralize economic PnL; day-only flow times block TWR',async()=>{
  const {api,ledger}=await harness();api.cash('CSD',1000);api.cash('CSW',-250);
  await ledger.refresh(input(T0+MIN));const v=ledger.exportState(T0+MIN);
  assert.equal(v.accounting.finalEquityUsd,20750);assert.equal(v.accounting.externalFlowsUsd,750);
  assert.equal(v.accounting.accountNetPnlUsd,0);assert.equal(v.accounting.economicNetPnlUsd,0);
  assert.equal(v.accounting.totalReturnAccount,null);assert.equal(v.accounting.totalReturnEconomic,null);
  assert.equal(v.observations[1].returnStatus,'FLOW_TIME_PRECISION_INSUFFICIENT');assert.equal(ledger.performanceInput(T0+MIN),null);
});

test('flow value alone is insufficient for TWR even when transaction time is known',async()=>{
  const {api,ledger}=await harness();api.cash('CSD',500,T0+30000,{transaction_time:new Date(T0+30000).toISOString()});
  await ledger.refresh(input(T0+MIN));const v=ledger.view(T0+MIN);
  assert.equal(v.accounting.accountNetPnlUsd,0);assert.equal(v.accounting.totalReturnAccount,null);
});

test('hash-bound pre-flow evidence permits exact subperiod TWR without turning a flow into profit',async()=>{
  const {api,ledger}=await harness();const at=T0+30000;
  const deposit=api.cash('CSD',1000,at,{transaction_time:new Date(at).toISOString()});
  await ledger.refresh(input(T0+MIN,{preFlowMarks:[preflow(deposit,20000,21000,at)]}));
  await ledger.refresh(input(T0+2*MIN));const v=ledger.view(T0+2*MIN);
  assert.equal(v.accounting.totalReturnAccount,0);assert.equal(v.accounting.totalReturnEconomic,0);
  const p=ledger.performanceInput(T0+2*MIN);assert.deepEqual(p.returns,[0,0]);
  assert.equal(p.source_authenticity_verified,false);assert.equal(p.annualization_authorized,false);
});

test('TWR chains price gains before and after capital flows, with external costs at their actual periods',async()=>{
  const {api,ledger}=await harness();api.fill({qty:100,at:T0+10000});api.mark('AAPL',110);
  const at=T0+30000,d=api.cash('CSD',1000,at,{transaction_time:new Date(at).toISOString()});
  api.mark('AAPL',120);api.cash('FEE',-1,T0+50000);
  const cs=[cost('before-flow',2,T0+20000),cost('after-flow',3,T0+40000)];
  await ledger.refresh(input(T0+MIN,{preFlowMarks:[preflow(d,21000,22000,at)],externalCosts:report(T0+MIN,cs)}));
  const v=ledger.view(T0+MIN);assert.equal(v.accounting.accountNetPnlUsd,1999);assert.equal(v.accounting.economicNetPnlUsd,1994);
  near(v.accounting.totalReturnAccount,(21000/20000)*(22999/22000)-1);
  near(v.accounting.totalReturnEconomic,(20998/20000)*(22994/21998)-1);
});

test('pre-flow marks must bind both numeric values and original receipt hash',async()=>{
  const {api,ledger}=await harness();const at=T0+30000;
  const d=api.cash('CSD',500,at,{transaction_time:new Date(at).toISOString()});
  const mark=preflow(d,20000,20500,at);mark.equityBefore=19000;mark.equityAfter=19500;
  await rejected(ledger,T0+MIN,/PREFLOW_SOURCE_VALUE_MISMATCH/,{preFlowMarks:[mark]});
});

test('late-reported settlement fees are consumed by creation coverage, never skipped by date',async()=>{
  const {api,ledger}=await harness();
  const now=T0+MIN;api.cash('FEE',-3,now,{date:'2026-10-14',created_at:new Date(now-1000).toISOString()});
  await ledger.refresh(input(now));const v=ledger.exportState(now);
  assert.equal(v.accounting.accountNetPnlUsd,-3);assert.equal(v.activities[0].timePrecision,'DAY');
  assert.equal(v.activities[0].knownAt,now);assert.equal(v.coverage.afterCreatedAt,Date.UTC(2026,9,15));
});

test('complete pagination uses last activity id, and persisted id history cannot disappear',async()=>{
  const {api,ledger}=await harness({pageSize:2});
  api.fill({qty:1});api.cash('FEE',-1);api.cash('DIV',2);
  await ledger.refresh(input(T0+MIN));const v=ledger.view(T0+MIN);
  assert.equal(v.coverage.pages,2);assert.equal(v.activities_count,3);
  assert(api.calls.some(p=>p.includes('page_token=activity-2')));
  api.activities.splice(1,1);await rejected(ledger,T0+2*MIN,/ACTIVITY_HISTORY_GAP/);
});

test('page overlap, repeated cursor, and truncation at page limit block certification',async()=>{
  {
    const {api,ledger}=await harness({pageSize:1,maxPages:3});api.cash('DIV',1);
    api.pageOverride=()=>[api.activities[0]];
    await rejected(ledger,T0+MIN,/ACTIVITY_PAGE_OVERLAP_OR_LOOP/);
  }
  {
    const {api,ledger}=await harness({pageSize:1,maxPages:1});api.cash('DIV',1);
    await rejected(ledger,T0+MIN,/ACTIVITY_PAGINATION_INCOMPLETE/);
  }
});

test('unknown currency or activity type cannot become a zero-cost activity',async()=>{
  for(const row of [
    {type:'FEE',amount:-1,extra:{currency:'EUR'}},
    {type:'CFEE',amount:-1,extra:{}},
    {type:'JNLC',amount:1,extra:{}},
    {type:'SSP',amount:0,extra:{symbol:'AAPL',qty:'2'}},
  ]){
    const {api,ledger}=await harness();api.cash(row.type,row.amount,T0+30000,row.extra);
    await rejected(ledger,T0+MIN,/(UNSUPPORTED_ACTIVITY|CRYPTO_FEE_CURRENCY_UNKNOWN)/);
  }
});

test('missing account currency, missing NAV, and missing position marks are rejected',async()=>{
  for(const mutate of [a=>delete a.account.currency,a=>delete a.account.equity,a=>{a.fill();delete a.positions[0].market_value;}]){
    const {api,ledger}=await harness();mutate(api);
    await rejected(ledger,T0+MIN,/(CURRENCY_UNVERIFIED|EQUITY_MISSING|POSITION_MARK_MISSING)/);
  }
});

test('cash, inventory, and NAV discrepancies preserve the prior accepted curve',async()=>{
  for(const mutate of [
    a=>{a.account.cash='19990';a.revalue();},
    a=>{a.positions=[{symbol:'AAPL',qty:'1',market_value:'100',asset_class:'us_equity'}];a.account.cash='19900';a.revalue();},
    a=>{a.account.equity='20001';},
  ]){
    const {api,ledger}=await harness();mutate(api);
    await rejected(ledger,T0+MIN,/(CASH_OR_INVENTORY_MISMATCH|NAV_MISMATCH)/);
    assert.equal(ledger.view(T0+MIN).lastSuccess,T0);
  }
});

test('account identity and unmodeled option multipliers are verified',async()=>{
  {
    const {api,ledger}=await harness();api.account.id='other-account';await rejected(ledger,T0+MIN,/ACCOUNT_ID_MISMATCH/);
  }
  {
    const {api,ledger}=await harness();api.fill({symbol:'UNMAPPED_OPTION',multiplier:100});
    await rejected(ledger,T0+MIN,/INSTRUMENT_MULTIPLIER_UNKNOWN/);
  }
  {
    const {api,ledger}=await harness();api.fill({symbol:'AAPL261120C00200000',price:2,multiplier:100});
    await ledger.refresh(input(T0+MIN));assert.equal(ledger.view(T0+MIN).reconciliation.expectedCashUsd,19800);
  }
});

test('future transaction, creation, cost-known-at, and snapshot times cannot certify evidence',async()=>{
  for(const field of ['transaction_time','created_at','known_at']){
    const {api,ledger}=await harness();api.fill({[field]:new Date(T0+2*MIN).toISOString()});
    await rejected(ledger,T0+MIN,/(FUTURE_ACTIVITY|FUTURE_KNOWN_AT)/);
  }
  {
    const {ledger}=await harness();const r=report(T0+MIN);r.known_at=T0+2*MIN;
    await rejectedCost(ledger,T0+MIN,/COST_RECEIPT_FUTURE_OR_REVERSED/,{externalCosts:r});
  }
  {
    const {api,ledger}=await harness();api.account.as_of=new Date(T0+2*MIN).toISOString();
    await rejected(ledger,T0+MIN,/SNAPSHOT_STALE_OR_FUTURE/);
  }
});

test('stale receipt and explicitly stale snapshot disable current metrics',async()=>{
  const {api,ledger}=await harness();assert.equal(ledger.view(T0+4*MIN).status,'STALE');
  assert.equal(ledger.performanceInput(T0+4*MIN),null);
  api.account.as_of=new Date(T0-5*MIN).toISOString();await rejected(ledger,T0+MIN,/SNAPSHOT_STALE_OR_FUTURE/);
});

test('state changes within non-atomic API collection are rejected',async()=>{
  const {api,ledger}=await harness();let accounts=0;
  api.hook=(path,a)=>{if(path==='/v2/account' && ++accounts===2){a.account.cash='20001';a.revalue();}};
  await rejected(ledger,T0+MIN,/SNAPSHOT_CHANGED_DURING_COLLECTION/);
});

test('persistence failure cannot advance in-memory NAV or activate derived performance',async()=>{
  const {api,store,ledger}=await harness();api.cash('FEE',-1);const saved=await store.get('fixture-net-ledger');store.fail=true;
  await assert.rejects(ledger.refresh(input(T0+MIN)),/LEDGER_PERSISTENCE_FAILURE/);
  const v=ledger.view(T0+MIN);assert.equal(v.persisted,false);assert.equal(v.reconciled,false);assert.equal(v.lastSuccess,T0);
  assert.equal(v.accounting.accountNetPnlUsd,0);assert.deepEqual(await store.get('fixture-net-ledger'),saved);
  store.fail=false;await ledger.refresh(input(T0+MIN));assert.equal(ledger.view(T0+MIN).accounting.accountNetPnlUsd,-1);
});

test('restart restores exact capital, activities, costs, and idempotent fill inventory',async()=>{
  const {api,store,ledger}=await harness();api.fill({qty:2});api.cash('FEE',-1);
  const expenses=[cost('compute',2,T0+30000)];await ledger.refresh(input(T0+MIN,{externalCosts:report(T0+MIN,expenses)}));
  const next=new NetAccountLedger(store,api,'fixture-net-ledger','ledger-account',{executionNature:'SYNTHETIC_ENGINEERING_ONLY'});
  await next.load();assert.equal(next.exportState(T0+MIN).integrity,ledger.exportState(T0+MIN).integrity);
  await next.refresh(input(T0+2*MIN,{externalCosts:report(T0+2*MIN,expenses)}));
  const v=next.view(T0+2*MIN);assert.equal(v.activities_count,2);assert.equal(v.observations_count,3);
  assert.equal(v.accounting.economicNetPnlUsd,-3);assert.equal(v.baseline.equity,20000);
});

test('state integrity and policy mismatch reject an unsafe restart',async()=>{
  const {api,store}=await harness();const original=await store.get('fixture-net-ledger');
  const mismatch=new NetAccountLedger(store,api,'fixture-net-ledger','ledger-account',{cashToleranceUsd:10});
  await assert.rejects(mismatch.load(),/POLICY_MISMATCH/);
  const changed=structuredClone(original);changed.baseline.equity=1;await store.put('fixture-net-ledger',changed);
  const tampered=new NetAccountLedger(store,api,'fixture-net-ledger','ledger-account');await assert.rejects(tampered.load(),/INTEGRITY_MISMATCH/);
});

test('an activity with the same id but changed economics requires explicit restatement',async()=>{
  const {api,ledger}=await harness();api.cash('FEE',-1);await ledger.refresh(input(T0+MIN));
  api.activities[0].net_amount='-2';await rejected(ledger,T0+2*MIN,/ACTIVITY_REVISION_REQUIRES_RESTATEMENT/);
});

test('late cost receipts reconstruct historical economics while retaining actual knowledge time',async()=>{
  const {ledger}=await harness({},false);await ledger.refresh({now:T0,instruments:ASSETS});
  await ledger.refresh({now:T0+MIN,instruments:ASSETS});
  const late=cost('late',2,T0+30000,{known_at:T0+2*MIN});
  await ledger.refresh(input(T0+2*MIN,{externalCosts:report(T0+2*MIN,[late])}));
  const v=ledger.exportState(T0+2*MIN);assert.equal(v.accounting.economicNetPnlUsd,-2);
  assert.equal(v.economicComplete,true);assert.equal(v.returnComplete,true);
  assert.equal(v.observations[1].economicKnownAt,T0+2*MIN);assert.equal(v.evidence.economicRestatement.knownAt,T0+2*MIN);
  near(ledger.performanceInput(T0+2*MIN).returns[0],-2/20000,1e-12);
  assert.equal(ledger.performanceInput(T0+2*MIN).returns[1],0);
});

test('real receipt clock exports the closed covered prefix while the current mark remains uncovered',async()=>{
  const store=new Store(),api=new FinancialBroker();
  api.hook=async()=>{await new Promise(resolve=>setTimeout(resolve,2));};
  const ledger=new NetAccountLedger(store,api,'real-clock-fixture','ledger-account',{
    executionNature:'SYNTHETIC_ENGINEERING_ONLY',performanceIntervalMs:100,performanceToleranceMs:49,
  });
  const from=Date.now()-86400000;
  for(let i=0;i<4;i++){
    if(i)await new Promise(resolve=>setTimeout(resolve,80));
    const known=Date.now();
    await ledger.refresh({instruments:ASSETS,externalCosts:{...report(known,[],from),known_at:known}});
    assert(ledger.view().lastSuccess>known,'API receipt time must not be backdated to the supplied cost watermark');
  }
  const view=ledger.view(),full=ledger.exportState(),p=ledger.performanceInput();
  assert.equal(view.reconciled,true);assert.equal(view.economicComplete,false);
  assert.equal(view.accounting.economicNetPnlUsd,null);assert.equal(view.observations_count,4);
  assert.equal(view.closedEconomic.observationCount,3);assert(p,'three real-clock marks covered by a later receipt must yield a diagnostic prefix');
  assert.equal(p.observation_count,3);assert.equal(p.historical_closed_prefix,true);
  assert.equal(p.coverage_through,full.observations[2].at);assert.equal(p.latest_uncovered_at,full.observations[3].at);
  assert(p.coverage_through<p.latest_uncovered_at);assert(p.cost_coverage_through<=p.knowledge_at);
  assert.equal(p.current_economic_net_pnl_usd,null);assert.equal(p.economic_net_pnl_usd,0);
  assert.equal(p.initial_at,new Date(full.observations[0].at).toISOString());
  assert.equal(p.cost_reporting.total_costs_usd,null);assert.equal(p.net_costs_confirmed,false);
  if(process.env.HARPOON_LEDGER_EVIDENCE_DIR){
    const fs=require('node:fs'),path=require('node:path'),dir=process.env.HARPOON_LEDGER_EVIDENCE_DIR;
    fs.mkdirSync(dir,{recursive:true});
    fs.writeFileSync(path.join(dir,'real_clock_closed_prefix_test.json'),JSON.stringify({
      nature:'SYNTHETIC_ENGINEERING_ONLY',clock:'REAL_LOCAL_CLOCK_WITH_2MS_FAKE_HTTP_DELAYS',
      summary:view,observations:full.observations.map(o=>({at:o.at,economicKnownAt:o.economicKnownAt,economicEquity:o.economicEquity})),
      performance_input:p,claim:'Closed historical prefix only; latest economic NAV unknown; no broker or external orders',
    },null,2)+'\n');
  }
});

test('a cost cannot disappear, mutate under the same id, or link the same account fee twice',async()=>{
  {
    const {ledger}=await harness();const c=cost('invoice',2,T0+30000);
    await ledger.refresh(input(T0+MIN,{externalCosts:report(T0+MIN,[c])}));
    await rejectedCost(ledger,T0+2*MIN,/COST_HISTORY_GAP/);
  }
  {
    const {ledger}=await harness();const c=cost('invoice',2,T0+30000);
    await ledger.refresh(input(T0+MIN,{externalCosts:report(T0+MIN,[c])}));
    await rejectedCost(ledger,T0+2*MIN,/COST_REVISION_REQUIRES_RESTATEMENT/,{externalCosts:report(T0+2*MIN,[{...c,amount_usd:3}])});
  }
  {
    const {api,ledger}=await harness();const a=api.cash('FEE',-2);
    const cs=['a','b'].map(id=>cost(id,2,T0+30000,{already_in_account:true,activity_id:a.id}));
    await rejectedCost(ledger,T0+MIN,/COST_RECEIPT_DUPLICATE_ACTIVITY_LINK/,{externalCosts:report(T0+MIN,cs)});
  }
});

test('economic insolvency remains recorded after subsequent deposits and never clips the loss',async()=>{
  const {api,ledger}=await harness();const expenses=[cost('terminal',21000,T0+30000)];
  await ledger.refresh(input(T0+MIN,{externalCosts:report(T0+MIN,expenses)}));
  let v=ledger.view(T0+MIN);assert.equal(v.insolvency.economic,true);assert.equal(v.accounting.economicNetPnlUsd,-21000);
  api.cash('CSD',5000,T0+90000);await ledger.refresh(input(T0+2*MIN,{externalCosts:report(T0+2*MIN,expenses)}));
  v=ledger.view(T0+2*MIN);assert.equal(v.insolvency.economic,true);assert.equal(v.accounting.economicNetPnlUsd,-21000);
  assert.equal(v.accounting.totalReturnEconomic,null);assert.equal(ledger.performanceInput(T0+2*MIN),null);
});

test('actual account equity at zero is stored as insolvency, not hidden by flow or closed-trade metrics',async()=>{
  const {api,ledger}=await harness();api.fill({qty:200,price:100});api.mark('AAPL',0);
  await ledger.refresh(input(T0+MIN));const v=ledger.exportState(T0+MIN);
  assert.equal(v.insolvency.account,true);assert.equal(v.accounting.finalEquityUsd,0);
  assert.equal(v.accounting.accountNetPnlUsd,-20000);assert.equal(v.observations[1].accountReturn,-1);
});

test('comparable finite period exporter has no implied annualization or source authentication',async()=>{
  const {ledger,store}=await harness();await ledger.refresh(input(T0+MIN));await ledger.refresh(input(T0+2*MIN));
  const p=ledger.performanceInput(T0+2*MIN);assert(p);assert.equal(p.sampling,'FIXED_INTERVAL_OBSERVATIONS');
  assert.equal(p.periods_per_year,1);assert.equal(p.rate_basis,'ASSUMED_ZERO_FOR_DIAGNOSTIC');
  assert.equal(p.trade_authorization,false);assert.equal(p.financial_advantage_demonstrated,false);
  assert.equal(p.source_receipt_hash,ledger.view(T0+2*MIN).integrity);
  assert.equal(p.origin,'SYNTHETIC_ENGINEERING_ONLY');
  assert.equal(p.initial_at,new Date(T0).toISOString());
  assert.equal(p.cost_reporting.total_costs_usd,null);assert.equal(p.net_costs_confirmed,false);
  if(process.env.HARPOON_LEDGER_EVIDENCE_DIR){
    const fs=require('node:fs'),path=require('node:path'),dir=process.env.HARPOON_LEDGER_EVIDENCE_DIR;
    fs.mkdirSync(dir,{recursive:true});
    fs.writeFileSync(path.join(dir,'synthetic_ledger_export.json'),JSON.stringify(ledger.exportState(T0+2*MIN),null,2)+'\n');
    fs.writeFileSync(path.join(dir,'synthetic_ledger_durable_state.json'),JSON.stringify(await store.get('fixture-net-ledger'),null,2)+'\n');
    fs.writeFileSync(path.join(dir,'synthetic_performance_input.json'),JSON.stringify(p,null,2)+'\n');
  }
});

test('irregular observations retain continuous PnL but cannot manufacture comparable Sharpe periods',async()=>{
  const {ledger}=await harness();await ledger.refresh(input(T0+MIN));await ledger.refresh(input(T0+3*MIN));
  assert.equal(ledger.view(T0+3*MIN).accounting.economicNetPnlUsd,0);
  assert.equal(ledger.view(T0+3*MIN).performanceInputStatus,'WAIT_COMPARABLE_PERIOD_GRID');
  assert.equal(ledger.performanceInput(T0+3*MIN),null);
});

test('history bounds stop, preserve evidence and do not reset the capital curve',async()=>{
  const {ledger}=await harness({maxObservations:2});await ledger.refresh(input(T0+MIN));
  await rejected(ledger,T0+2*MIN,/OBSERVATION_HISTORY_BOUND/);
  assert.equal(ledger.view(T0+2*MIN).baseline.equity,20000);assert.equal(ledger.view(T0+2*MIN).observations_count,2);
});

test('summary avoids exporting full activity or NAV arrays on operational health paths',async()=>{
  const {ledger}=await harness();const summary=ledger.view(T0),full=ledger.exportState(T0);
  assert.equal(summary.observations,undefined);assert.equal(summary.activities,undefined);assert.equal(summary.baseline.sourceReceipt,undefined);
  assert.equal(summary.observations_count,1);assert.equal(summary.activities_count,0);
  assert(Array.isArray(full.observations));assert(Array.isArray(full.activities));
  full.baseline.equity=1;assert.equal(ledger.view(T0).baseline.equity,20000);
});

test('invalid timestamp does not permanently latch the in-process refresh guard',async()=>{
  const {ledger}=await harness();await assert.rejects(ledger.refresh({now:NaN}),/OBSERVATION_TIME_INVALID/);
  await ledger.refresh(input(T0+MIN));assert.equal(ledger.view(T0+MIN).reconciled,true);
});

test('overlapping refresh is rejected while the first operation remains valid',async()=>{
  const {api,ledger}=await harness();let release;const waiting=new Promise(resolve=>release=resolve);let entered;
  const started=new Promise(resolve=>entered=resolve);let once=true;
  api.hook=async()=>{if(once){once=false;entered();await waiting;}};
  const first=ledger.refresh(input(T0+MIN));await started;
  await assert.rejects(ledger.refresh(input(T0+2*MIN)),/LEDGER_REFRESH_IN_PROGRESS/);
  release();await first;assert.equal(ledger.view(T0+MIN).reconciled,true);
});

test('two instances sharing one Store cannot race its same-owner lease',async()=>{
  const {api,store,ledger}=await harness();
  const next=new NetAccountLedger(store,api,'fixture-net-ledger','ledger-account');await next.load();
  let release,entered;const waiting=new Promise(r=>release=r),started=new Promise(r=>entered=r);let once=true;
  api.hook=async()=>{if(once){once=false;entered();await waiting;}};
  const first=ledger.refresh(input(T0+MIN));await started;
  await assert.rejects(next.refresh(input(T0+MIN)),/LEDGER_IN_PROCESS_WRITER_BUSY/);
  release();await first;assert.equal(ledger.view(T0+MIN).observations_count,2);
});

test('production SQLite transport persists one complete ledger record across process restarts',async()=>{
  const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
  const {DurableStore}=require('../runtime/store30.cjs');
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'harpoon-net-ledger-'));
  let store;
  const close=async()=>{if(store?.process && store.process.exitCode===null){const exit=new Promise(r=>store.process.once('exit',r));await store.close();await exit;}};
  try{
    store=await new DurableStore(path.join(dir,'ledger.sqlite')).open();const api=new FinancialBroker();
    let ledger=new NetAccountLedger(store,api,'sqlite-ledger','ledger-account');
    await ledger.refresh(input(T0));api.cash('FEE',-1);await ledger.refresh(input(T0+MIN));
    const expected=await store.get('sqlite-ledger');await close();
    store=await new DurableStore(path.join(dir,'ledger.sqlite')).open();
    ledger=new NetAccountLedger(store,api,'sqlite-ledger','ledger-account');await ledger.load();
    assert.equal(ledger.view(T0+MIN).integrity,expected.integrity);
    assert.equal(ledger.view(T0+MIN).accounting.accountNetPnlUsd,-1);
    await ledger.refresh(input(T0+2*MIN));assert.equal(ledger.view(T0+2*MIN).activities_count,1);
  }finally{await close();fs.rmSync(dir,{recursive:true,force:true});}
});

module.exports={FinancialBroker,Store,ASSETS,T0,MIN,report,cost,input,harness,preflow};
