"use strict";
// SYNTHETIC_ENGINEERING_ONLY. Read-only broker double; no financial trial.
const test=require("node:test"), assert=require("node:assert/strict"), fs=require("node:fs"), os=require("node:os"), path=require("node:path");
const {NetAccountLedger,netLedgerDigest,verifyNetLedgerHistoryBundle}=require("../runtime30/net_accounting.js");
const {LocalCostReceiptSource,writeCostReceiptFile,validateCostReceipt}=require("../runtime30/cost_receipts.js");
const T0=Date.UTC(2026,9,15,13,30), MIN=60000, ACCOUNT="SYNTHETIC-CONTINUITY-ACCOUNT";
const assets=[{symbol:"SPY",book:"etf",currency:"USD",multiplier:1}];
class Store {
  constructor(){this.rows=new Map();this.calls=[];this.fail=null;}
  async get(k){this.calls.push(["get",k]);return structuredClone(this.rows.get(k)??null);}
  async put(k,v){this.calls.push(["put",k]);if(this.fail?.(k))throw Error("SYNTHETIC_STORE_FAILURE");this.rows.set(k,structuredClone(v));return true;}
  async lease(){return true;}
  async close(){}
}
class Broker {
  constructor(){this.cash=20000;this.qty=0;this.price=100;this.rows=[];this.calls=[];this.full=false;}
  activity(type,amount,at,extra={}){
    const r={id:"A"+(this.rows.length+1),activity_type:type,net_amount:String(amount),date:new Date(at).toISOString().slice(0,10),
      created_at:new Date(at).toISOString(),...extra};this.rows.push(r);this.cash+=amount;return r;
  }
  fill(qty,price,at){this.qty+=qty;this.price=price;this.cash-=qty*price;
    const r={id:"A"+(this.rows.length+1),activity_type:"FILL",side:qty>0?"buy":"sell",qty:String(Math.abs(qty)),price:String(price),
      symbol:"SPY",order_id:"order-"+(this.rows.length+1),transaction_time:new Date(at).toISOString(),created_at:new Date(at).toISOString()};this.rows.push(r);return r;}
  async request(url,method="GET"){
    assert.equal(method,"GET");this.calls.push(url);
    if(url==="/v2/account")return{id:ACCOUNT,currency:"USD",cash:String(this.cash),equity:String(this.cash+this.qty*this.price)};
    if(url==="/v2/positions")return this.qty?[{symbol:"SPY",qty:String(this.qty),market_value:String(this.qty*this.price),asset_class:"us_equity"}]:[];
    const q=new URL(url,"https://synthetic.invalid").searchParams;
    const rows=this.rows.filter(r=>this.full || Date.parse(r.created_at)>Date.parse(q.get("after"))&&Date.parse(r.created_at)<=Date.parse(q.get("until")));
    const token=q.get("page_token"), start=token?rows.findIndex(r=>r.id===token)+1:0;
    return structuredClone(rows.slice(start,start+Number(q.get("page_size"))));
  }
}
function coverage(at,entries=[]){return {schema:"HARPOON_COST_RECEIPT_1",account_id:ACCOUNT,currency:"USD",
  receipt_id:"SYNTHETIC-RECEIPT-"+at,coverage_complete:true,
  from:T0,through:at,known_at:at,reference:"SYNTHETIC-COVERAGE-"+at,categories:["DATA","INFRASTRUCTURE","INFERENCE","OTHER"],entries};}
function cost(id,amount,at,extra={}){return {id,at,known_at:at,amount_usd:amount,category:"INFRASTRUCTURE",reference:"SYNTHETIC-INVOICE-"+id,already_in_account:false,...extra};}
function receipt(at,entries=[]){return {schema:"HARPOON_COST_RECEIPT_1",account_id:ACCOUNT,currency:"USD",receipt_id:"SYNTHETIC-RECEIPT-"+at,coverage_complete:true,...coverage(at,entries)};}
function accrualProof(through,amount=0,costIds=[]){
  const fields={account_id:ACCOUNT,currency:"USD",from:T0,through,known_at:through,applicable_categories:["COMMISSIONS","EXCHANGE_CLEARING","REGULATORY","FINANCING","BORROW","OTHER"],coverage_complete:true,pending_total_usd:amount,explicit_zero:amount===0};
  const content=JSON.stringify({statement:fields});
  return {schema:"HARPOON_BROKER_ACCRUAL_COVERAGE_1",...fields,reference:"SYNTHETIC-ACCRUAL-DECLARATION",cost_ids:costIds,
    document:{reference:"SYNTHETIC-ORIGINAL-JSON-STATEMENT",content_type:"application/json",content,sha256:require("node:crypto").createHash("sha256").update(content).digest("hex"),bindings:Object.fromEntries(Object.keys(fields).map(k=>[k,"/statement/"+k]))}};
}
function mark(a,before,after,at){const e={activityId:a.id,at,equityBefore:before,equityAfter:after};return {...e,known_at:at,reference:"SYNTHETIC-PREFLOW",evidence:e,evidenceHash:netLedgerDigest(e)};}
async function fixture(config={}){
  const store=new Store(),api=new Broker(),cfg={executionNature:"SYNTHETIC_ENGINEERING_ONLY",maxObservations:3,
    archive:{enabled:true,maxSegments:16,maxStoredBytes:32*1024*1024,activityOverlapMs:MIN},...config};
  const ledger=new NetAccountLedger(store,api,"N",ACCOUNT,cfg);
  return {store,api,cfg,ledger};
}
async function step(f,i,extra={}){return f.ledger.refresh({now:T0+i*MIN,instruments:assets,externalCosts:coverage(T0+i*MIN),...extra});}
async function pages(ledger,size=3){const all=[];let offset=0;do{const p=await ledger.exportHistory(offset,size);all.push(p);offset=p.next_offset;}while(offset!==null);return all;}
function close(a,b,tol=1e-8){assert(Math.abs(a-b)<=tol,`${a} != ${b}`);}
function temp(t){const dir=fs.mkdtempSync(path.join(os.tmpdir(),"hx-cost-receipt-"));t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));return path.join(dir,"costs.json");}

test("rollovers retain the original capital, complete record export and bounded active marks",async()=>{
  const f=await fixture();for(let i=0;i<10;i++)await step(f,i);
  const v=f.ledger.view(T0+9*MIN), raw=await f.store.get("N");assert.equal(v.observations_count,10);assert(v.archive.segments>0);
  assert(raw.observations.length<=3);assert.equal(raw.baseline.equity,20000);assert.equal(v.accounting.accountNetPnlUsd,0);
  const bundle=await pages(f.ledger), checked=verifyNetLedgerHistoryBundle(bundle,v.integrity);
  assert.equal(checked.observations.length,10);assert.equal(checked.from,T0);assert.equal(checked.through,T0+9*MIN);
  assert.equal(checked.derived.reconciled,true);assert.equal(checked.sourceAuthenticityVerified,false);
  assert.equal(f.ledger.performanceInput(T0+9*MIN),null);
  const p=await f.ledger.performanceInputWithArchive(T0+9*MIN);assert.equal(p.returns.length,9);assert.equal(p.initial_at,new Date(T0).toISOString());
  assert.equal(p.current_account_net_pnl_usd,0);assert.equal(p.trade_authorization,false);
});
test("open losses, partial inventory, broker fees and external costs survive rollover without double counting",async()=>{
  const f=await fixture({maxObservations:2});await step(f,0);f.api.fill(2,100,T0+1000);
  const fee=f.api.activity("FEE",-1,T0+2000), expenses=[cost("broker",1,T0+2000,{already_in_account:true,activity_id:fee.id}),cost("compute",2,T0+3000)];
  await step(f,1,{externalCosts:coverage(T0+MIN,expenses)});f.api.price=90;
  await step(f,2,{externalCosts:coverage(T0+2*MIN,expenses)});f.api.fill(-1,90,T0+2*MIN+1000);
  await step(f,3,{externalCosts:coverage(T0+3*MIN,expenses)});
  const v=f.ledger.view(T0+3*MIN);close(v.accounting.accountNetPnlUsd,-21);close(v.accounting.economicNetPnlUsd,-23);
  assert.equal(v.accounting.externalCostsUsd,2);assert.equal(v.accounting.reportedAccountFeesUsd,1);assert.equal(v.accounting.openPositionMarketValueUsd,90);
  const checked=verifyNetLedgerHistoryBundle(await pages(f.ledger),v.integrity);assert.equal(checked.activities.length,3);assert.equal(checked.externalCosts.length,2);
  assert.equal(checked.derived.economicNetPnlUsd,-23);const p=await f.ledger.performanceInputWithArchive(T0+3*MIN);assert.equal(p.cost_reporting.reported_broker_costs_usd,1);assert.equal(p.cost_reporting.declared_external_costs_usd,2);
});
test("deposits and withdrawals across archive boundaries preserve pre-flow marks and account growth",async()=>{
  const f=await fixture({maxObservations:2});await step(f,0);const at=T0+30000;
  const d=f.api.activity("CSD",500,at,{transaction_time:new Date(at).toISOString()});
  await step(f,1,{preFlowMarks:[mark(d,20000,20500,at)]});await step(f,2);
  const at2=T0+2*MIN+30000,w=f.api.activity("CSW",-200,at2,{transaction_time:new Date(at2).toISOString()});
  await step(f,3,{preFlowMarks:[mark(w,20500,20300,at2)]});await step(f,4);
  const v=f.ledger.view(T0+4*MIN);assert.equal(v.accounting.externalFlowsUsd,300);assert.equal(v.accounting.accountNetPnlUsd,0);assert.equal(v.accounting.totalReturnAccount,0);
  const checked=verifyNetLedgerHistoryBundle(await pages(f.ledger),v.integrity);assert.equal(checked.observations.reduce((n,o)=>n+o.preFlowMarks.length,0),2);
  assert.deepEqual((await f.ledger.performanceInputWithArchive(T0+4*MIN)).returns,[0,0,0,0]);
});
test("incremental created-at windows retain fees created later than their settlement date",async()=>{
  const f=await fixture({maxObservations:2});for(let i=0;i<4;i++)await step(f,i);
  f.api.activity("FEE",-3,T0+3*MIN+1000,{date:"2026-10-14"});await step(f,4);
  const query=new URL(f.api.calls.filter(x=>x.includes("activities?")).at(-1),"https://synthetic.invalid");
  assert.equal(Date.parse(query.searchParams.get("after")),T0+2*MIN);assert.equal(f.ledger.view(T0+4*MIN).accounting.accountNetPnlUsd,-3);
});
test("replayed archived activities are deduplicated and revisions fail closed",async()=>{
  const f=await fixture({maxObservations:2});await step(f,0);f.api.activity("FEE",-1,T0+1000);for(let i=1;i<4;i++)await step(f,i);
  f.api.full=true;await step(f,4);assert.equal(f.ledger.view(T0+4*MIN).accounting.reportedAccountFeesUsd,1);
  f.api.rows[0].net_amount="-2";await assert.rejects(step(f,5),/ARCHIVED_ACTIVITY_REVISION_REQUIRES_RESTATEMENT/);
});
test("restart validates every archive and resumes with cumulative totals and identity",async()=>{
  const f=await fixture({maxObservations:2});await step(f,0);f.api.activity("DIV",2,T0+1000);for(let i=1;i<5;i++)await step(f,i);
  const old=f.ledger.view(T0+4*MIN);const restored=new NetAccountLedger(f.store,f.api,"N",ACCOUNT,f.cfg);await restored.load();
  assert.equal(restored.view(T0+4*MIN).integrity,old.integrity);assert.equal(restored.view(T0+4*MIN).archive.head,old.archive.head);
  f.ledger=restored;await step(f,5);assert.equal(restored.view(T0+5*MIN).accounting.accountNetPnlUsd,2);assert.equal(restored.view(T0+5*MIN).observations_count,6);
  await assert.rejects(new NetAccountLedger(f.store,f.api,"N","OTHER",f.cfg).load(),/IDENTITY_MISMATCH/);
});
test("archive corruption and missing segments reject restart and complete export",async()=>{
  const f=await fixture({maxObservations:2});for(let i=0;i<3;i++)await step(f,i);const raw=await f.store.get("N"),key=raw.archiveIndex.segments[0].key,good=await f.store.get(key);
  const bad=structuredClone(good);bad.observations[0].equity=1;f.store.rows.set(key,bad);
  await assert.rejects(new NetAccountLedger(f.store,f.api,"N",ACCOUNT,f.cfg).load(),/SEGMENT_INTEGRITY/);await assert.rejects(f.ledger.exportHistory(),/SEGMENT_INTEGRITY/);
  f.store.rows.delete(key);await assert.rejects(new NetAccountLedger(f.store,f.api,"N",ACCOUNT,f.cfg).load(),/SEGMENT_MISSING/);
});
test("archive quota and accounting boundary tampering are detected independently",async()=>{
  const f=await fixture({maxObservations:2});for(let i=0;i<3;i++)await step(f,i);
  const original=await f.store.get("N-archive-budget"),bad=structuredClone(original);bad.reservedBytes=0;f.store.rows.set("N-archive-budget",bad);
  await assert.rejects(new NetAccountLedger(f.store,f.api,"N",ACCOUNT,f.cfg).load(),/BUDGET_INTEGRITY/);
  f.store.rows.set("N-archive-budget",original);const state=await f.store.get("N");state.archiveIndex.boundary.externalFlowsUsd=123;delete state.integrity;state.integrity=netLedgerDigest(state);f.store.rows.set("N",state);
  await assert.rejects(new NetAccountLedger(f.store,f.api,"N",ACCOUNT,f.cfg).load(),/INDEX_TOTAL_MISMATCH/);
});
test("segment budget survives restart and never deletes or resets capital",async()=>{
  const f=await fixture({maxObservations:2,archive:{enabled:true,maxSegments:1,maxStoredBytes:1e6}});for(let i=0;i<4;i++)await step(f,i);
  f.ledger=new NetAccountLedger(f.store,f.api,"N",ACCOUNT,f.cfg);await f.ledger.load();await assert.rejects(step(f,4),/SEGMENT_BUDGET_EXHAUSTED/);
  const v=f.ledger.view(T0+4*MIN);assert.equal(v.observations_count,4);assert.equal(v.baseline.equity,20000);assert.equal(v.archive.segments,1);
});
test("byte budget is checked before segment writes",async()=>{
  const f=await fixture({maxObservations:2,archive:{enabled:true,maxStoredBytes:1024}});await step(f,0);await step(f,1);
  await assert.rejects(step(f,2),/BYTE_BUDGET_EXHAUSTED/);assert.equal(f.ledger.view(T0+2*MIN).observations_count,2);
  assert(![...f.store.rows.keys()].some(k=>k.startsWith("N-archive-")&&k!=="N-archive-budget"));
});
test("failed control commit keeps old curve and durable orphan reservations are bounded",async()=>{
  const f=await fixture({maxObservations:2});await step(f,0);await step(f,1);const old=await f.store.get("N");
  f.store.fail=k=>k==="N";await assert.rejects(step(f,2),/PERSISTENCE_FAILURE/);assert.deepEqual(await f.store.get("N"),old);
  const reserved=(await f.store.get("N-archive-budget")).reservedBytes;assert(reserved>0);
  f.store.fail=null;f.ledger=new NetAccountLedger(f.store,f.api,"N",ACCOUNT,f.cfg);await f.ledger.load();assert.equal(f.ledger.view(T0+MIN).observations_count,2);
  await step(f,2);const v=f.ledger.view(T0+2*MIN);assert.equal(v.observations_count,3);assert(v.archive.reservedBytes>=reserved);assert(v.archive.reservedSegments<=16);
});
test("missing costs remain null through rollovers, without preventing account reconciliation",async()=>{
  const f=await fixture({maxObservations:2});for(let i=0;i<5;i++)await step(f,i,{externalCosts:null});
  const v=f.ledger.view(T0+4*MIN);assert.equal(v.reconciled,true);assert.equal(v.accounting.economicNetPnlUsd,null);assert.equal(v.economicComplete,false);
  const reads=f.store.calls.length;assert.equal(await f.ledger.performanceInputWithArchive(T0+4*MIN),null);assert.equal(f.store.calls.length,reads);
});
test("late costs contradicting a sealed prefix demand explicit restatement, never reset economic history",async()=>{
  const f=await fixture({maxObservations:2});for(let i=0;i<3;i++)await step(f,i);const old=f.ledger.view(T0+2*MIN);
  await step(f,3,{externalCosts:coverage(T0+3*MIN,[cost("late",4,T0+1000,{known_at:T0+3*MIN})])});
  let v=f.ledger.view(T0+3*MIN);assert.equal(v.reconciled,true);assert.equal(v.economicRestatementRequired,true);assert.equal(v.accounting.economicNetPnlUsd,null);assert(v.blockers.includes("ECONOMIC_RESTATEMENT_REQUIRED"));
  await step(f,4,{externalCosts:null});v=f.ledger.view(T0+4*MIN);assert.equal(v.economicRestatementRequired,true);
  assert((await f.store.get("N")).archiveIndex.segments.some(r=>r.hash===old.archive.head),"the previously sealed evidence remains retained");
  assert.equal(await f.ledger.performanceInputWithArchive(T0+4*MIN),null);
  await step(f,5);assert.equal(f.ledger.view(T0+5*MIN).economicRestatementRequired,true);
  assert.equal(f.ledger.view(T0+5*MIN).accounting.economicNetPnlUsd,null,"replaying an earlier empty declaration cannot silently clear a known restatement requirement");
});
test("a delayed cost receipt preserves a closed anchor and complete historical performance across rollover",async()=>{
  const f=await fixture({maxObservations:3});await step(f,0);for(let i=1;i<7;i++)await step(f,i,{externalCosts:coverage(T0+i*MIN-1)});
  const v=f.ledger.view(T0+6*MIN);assert.equal(v.economicComplete,false);assert.equal(v.archive.economicHistorySealedComplete,true);
  const p=await f.ledger.performanceInputWithArchive(T0+6*MIN);assert(p);assert.equal(p.initial_at,new Date(T0).toISOString());assert.equal(p.times.length,5);
  assert.equal(p.coverage_through,T0+5*MIN);assert.equal(p.latest_uncovered_at,T0+6*MIN);
});
test("materialization refuses count and byte budgets without loading archived payloads",async()=>{
  const f=await fixture({maxObservations:2,maxMaterializationBytes:1024});for(let i=0;i<4;i++)await step(f,i);
  const before=f.store.calls.length;assert.equal(await f.ledger.performanceInputWithArchive(T0+3*MIN),null);assert.equal(f.store.calls.length,before);
  assert.equal(f.ledger.view(T0+3*MIN).performanceInputStatus,"WAIT_OFFLINE_MATERIALIZATION_BUDGET");
});
test("complete export rejects missing pages, mixed revisions and altered row payloads",async()=>{
  const f=await fixture({maxObservations:2});for(let i=0;i<5;i++)await step(f,i);const bundle=await pages(f.ledger,2),head=f.ledger.view(T0+4*MIN).integrity;
  assert.throws(()=>verifyNetLedgerHistoryBundle(bundle.slice(1),head),/PAGINATION/);
  const mixed=structuredClone(bundle);mixed.at(-1).ledger_integrity="0".repeat(64);assert.throws(()=>verifyNetLedgerHistoryBundle(mixed,head),/PAGINATION/);
  const altered=structuredClone(bundle),record=altered.flatMap(p=>p.records).find(r=>r.kind==="OBSERVATION");record.value.cash=1;
  assert.throws(()=>verifyNetLedgerHistoryBundle(altered,head),/INTEGRITY/);
});
test("offline verifier recomputes arithmetic rather than trusting rehashed accounting flags",async()=>{
  const f=await fixture({archive:{enabled:false}});await step(f,0);await step(f,1);const bundle=await pages(f.ledger,100),header=bundle[0].records.find(r=>r.kind==="HEADER");
  const state=await f.store.get("N");state.accounting.accountNetPnlUsd=999;delete state.integrity;state.integrity=netLedgerDigest(state);
  header.value.accounting.accountNetPnlUsd=999;header.value.integrity=state.integrity;bundle[0].ledger_integrity=state.integrity;
  assert.throws(()=>verifyNetLedgerHistoryBundle(bundle,state.integrity),/ACCOUNT_TOTAL_MISMATCH/);
});
test("receipt producer/importer is traceable, literal and bound to account and currency",async t=>{
  const file=temp(t),r=receipt(T0),written=await writeCostReceiptFile(file,r,ACCOUNT,T0);
  const source=new LocalCostReceiptSource(file),loaded=await source.read(ACCOUNT,T0,undefined);assert.equal(loaded.source.fileSha256,written.fileSha256);assert.equal(loaded.report.coverage_complete,true);
  assert.equal(loaded.source.sourceAuthenticityVerified,false);assert.equal(written.financialAuthorization,false);assert.equal(fs.statSync(file).mode&0o777,0o600);
  const first=fs.readFileSync(file);await assert.rejects(writeCostReceiptFile(file,{...r,account_id:"OTHER"},ACCOUNT,T0),/ACCOUNT_MISMATCH/);assert.deepEqual(fs.readFileSync(file),first);
});
test("exact example externalCosts:null configuration imports the configured receipt",async t=>{
  const file=temp(t),cfg=JSON.parse(fs.readFileSync(path.join(__dirname,"../config/examples/xxx.json"),"utf8")).quant.accounting;
  await writeCostReceiptFile(file,receipt(T0),ACCOUNT,T0);const f=await fixture({...cfg,executionNature:"SYNTHETIC_ENGINEERING_ONLY",externalCosts:null,costReceiptFile:file,maxObservations:2});
  await f.ledger.refresh({now:T0,instruments:assets});assert.equal(f.ledger.view(T0).costSource.status,"READ");assert.equal(f.ledger.view(T0).economicComplete,true);
  await writeCostReceiptFile(file,receipt(T0+MIN,[cost("infra",2,T0+1000)]),ACCOUNT,T0+MIN);
  await f.ledger.refresh({now:T0+MIN,instruments:assets});assert.equal(f.ledger.view(T0+MIN).accounting.economicNetPnlUsd,-2);
});
test("missing, malformed, duplicate-key and oversized cost files cannot declare zero",async t=>{
  const file=temp(t),source=new LocalCostReceiptSource(file,1024);assert.equal((await source.read(ACCOUNT,T0)).source.status,"MISSING");
  fs.writeFileSync(file,'{"schema":"x","schema":"HARPOON_COST_RECEIPT_1"}');assert.equal((await source.read(ACCOUNT,T0)).source.reason,"COST_RECEIPT_DUPLICATE_JSON_KEY");
  fs.writeFileSync(file,"x".repeat(1025));assert.equal((await source.read(ACCOUNT,T0)).source.reason,"COST_RECEIPT_FILE_NOT_REGULAR_OR_TOO_LARGE");
  const f=await fixture({costReceiptFile:file});await step(f,0,{externalCosts:null});const v=f.ledger.view(T0);assert.equal(v.reconciled,true);assert.equal(v.accounting.economicNetPnlUsd,null);assert.equal(v.costSource.status,"INVALID");
});
test("receipt validator rejects absent amounts, future knowledge, incomplete categories, ambiguous links and unknown fields",()=>{
  const valid=receipt(T0+MIN,[cost("one",1,T0+1000)]);
  const cases=[r=>r.entries[0].amount_usd=null,r=>r.known_at=T0+2*MIN,r=>r.categories.pop(),r=>r.coverage_complete=false,
    r=>r.currency="EUR",r=>r.entries[0].activity_id="fee",r=>r.entries.push({...r.entries[0]}),r=>r.unknown="x"];
  for(const mutate of cases){const r=structuredClone(valid);mutate(r);assert.throws(()=>validateCostReceipt(r,ACCOUNT,T0+MIN),/COST_RECEIPT_/);}
});
test("changing bytes under the same receipt identity is rejected across source restarts",async t=>{
  const file=temp(t),r=receipt(T0+MIN);await writeCostReceiptFile(file,r,ACCOUNT,T0+MIN);
  const first=await new LocalCostReceiptSource(file).read(ACCOUNT,T0+MIN);r.entries=[cost("added",1,T0+1000)];fs.writeFileSync(file,JSON.stringify(r));
  const second=await new LocalCostReceiptSource(file).read(ACCOUNT,T0+MIN,first.source);assert.equal(second.source.reason,"COST_RECEIPT_ID_REUSED_WITH_CHANGED_BYTES");assert.equal(second.report,null);
});
test("a rejected or missing receipt keeps declared costs unknown while reported account fees remain reconciled",async t=>{
  const file=temp(t);await writeCostReceiptFile(file,receipt(T0),ACCOUNT,T0);const f=await fixture({costReceiptFile:file});await step(f,0,{externalCosts:null});
  f.api.activity("FEE",-2,T0+1000);fs.unlinkSync(file);await step(f,1,{externalCosts:null});const v=f.ledger.view(T0+MIN);
  assert.equal(v.accounting.accountNetPnlUsd,-2);assert.equal(v.accounting.externalCostsUsd,null);assert.equal(v.accounting.economicNetPnlUsd,null);assert.equal(v.costSource.status,"MISSING");assert(v.costSource.lastAccepted.fileSha256);
});
test("archive configuration and materialization bounds are explicit",()=>{
  for(const archive of [{enabled:"yes"},{enabled:true,maxSegments:-1},{enabled:true,maxStoredBytes:0},{enabled:true,activityOverlapMs:0}])
    assert.throws(()=>new NetAccountLedger(new Store(),new Broker(),"N",ACCOUNT,{archive}),/ARCHIVE_CONFIG/);
});
test("archive write failures reserve quota without advancing the committed curve",async()=>{
  const f=await fixture({maxObservations:2});await step(f,0);await step(f,1);const old=await f.store.get("N");
  f.store.fail=k=>k.startsWith("N-archive-")&&k!=="N-archive-budget";await assert.rejects(step(f,2));
  const saved=await f.store.get("N");assert.equal(saved.lastSuccess,old.lastSuccess);assert.equal(saved.observations.length,2);assert(!saved.archiveIndex);
  assert((await f.store.get("N-archive-budget")).reservedBytes>0);assert.equal(f.ledger.view(T0+2*MIN).reconciled,false);
});
test("economic insolvency and accrued losses survive archival and subsequent capital contributions",async()=>{
  const f=await fixture({maxObservations:2});await step(f,0);const cs=[cost("expense",21000,T0+1000)];
  for(let i=1;i<3;i++)await step(f,i,{externalCosts:coverage(T0+i*MIN,cs)});
  f.api.activity("CSD",5000,T0+2*MIN+1000);await step(f,3,{externalCosts:coverage(T0+3*MIN,cs)});
  const v=f.ledger.view(T0+3*MIN);assert.equal(v.insolvency.economic,true);assert.equal(v.accounting.economicNetPnlUsd,-21000);
  assert.equal(v.accounting.externalFlowsUsd,5000);assert.equal(v.accounting.totalReturnEconomic,null);assert.equal(await f.ledger.performanceInputWithArchive(T0+3*MIN),null);
});
test("a cached file remains account bound and invalid calendar dates are rejected",async t=>{
  const file=temp(t);await writeCostReceiptFile(file,receipt(T0),ACCOUNT,T0);const source=new LocalCostReceiptSource(file);
  assert((await source.read(ACCOUNT,T0)).report);assert.equal((await source.read("OTHER",T0)).source.reason,"COST_RECEIPT_ACCOUNT_MISMATCH");
  assert.throws(()=>validateCostReceipt({...receipt(T0),from:"2026-02-30T00:00:00Z"},ACCOUNT,T0),/TIME_INVALID/);
});
test("offline verifier rejects invented time-weighted returns despite a consistent rehashed control",async()=>{
  const f=await fixture({archive:{enabled:false}});await step(f,0);await step(f,1);const bundle=await pages(f.ledger,100),state=await f.store.get("N");
  state.observations[1].accountReturn=0.1;delete state.integrity;state.integrity=netLedgerDigest(state);
  bundle[0].records.filter(r=>r.kind==="OBSERVATION")[1].value.accountReturn=0.1;
  bundle[0].records.find(r=>r.kind==="HEADER").value.integrity=state.integrity;bundle[0].ledger_integrity=state.integrity;
  assert.throws(()=>verifyNetLedgerHistoryBundle(bundle,state.integrity),/ACCOUNT_RETURN_MISMATCH/);
});
test("production SQLite persists archives, quota and active control across a worker restart",async()=>{
  const {DurableStore}=require("../runtime/store30.cjs"),dir=fs.mkdtempSync(path.join(os.tmpdir(),"hx-archive-sqlite-"));let store;
  const closeStore=async()=>{if(store?.process&&store.process.exitCode===null){const exited=new Promise(r=>store.process.once("exit",r));await store.close();await exited;}};
  try{
    const api=new Broker(),cfg={executionNature:"SYNTHETIC_ENGINEERING_ONLY",maxObservations:2,archive:{enabled:true}};
    store=await new DurableStore(path.join(dir,"ledger.sqlite")).open();let ledger=new NetAccountLedger(store,api,"N",ACCOUNT,cfg);
    for(let i=0;i<4;i++)await ledger.refresh({now:T0+i*MIN,instruments:assets,externalCosts:coverage(T0+i*MIN)});
    const expected=ledger.view(T0+3*MIN);await closeStore();store=await new DurableStore(path.join(dir,"ledger.sqlite")).open();
    ledger=new NetAccountLedger(store,api,"N",ACCOUNT,cfg);await ledger.load();assert.equal(ledger.view(T0+3*MIN).integrity,expected.integrity);
    const checked=verifyNetLedgerHistoryBundle(await pages(ledger),expected.integrity);assert.equal(checked.observations.length,4);
    await ledger.refresh({now:T0+4*MIN,instruments:assets,externalCosts:coverage(T0+4*MIN)});assert.equal(ledger.view(T0+4*MIN).observations_count,5);
  }finally{await closeStore();fs.rmSync(dir,{recursive:true,force:true});}
});
test("missing broker accrual documentation remains unknown even with complete declared external expense coverage",async()=>{
  const f=await fixture();await step(f,0);await step(f,1);const v=f.ledger.view(T0+MIN);
  assert.equal(v.accounting.unreportedBrokerAccrualsUsd,null);assert.equal(v.accounting.unreportedBrokerAccrualsVerified,false);
  const verified=verifyNetLedgerHistoryBundle(await pages(f.ledger),v.integrity);assert.equal(verified.brokerAccrualsVerified,false);assert.equal(verified.brokerAccrualsUsd,null);
});
test("explicit documented zero accrual is verified locally without source authentication or financial authorization",async t=>{
  const file=temp(t),f=await fixture({costReceiptFile:file});
  for(let i=0;i<2;i++){const at=T0+i*MIN;await writeCostReceiptFile(file,{...receipt(at),broker_accrual_coverage:accrualProof(at)},ACCOUNT,at);await step(f,i,{externalCosts:null});}
  const v=f.ledger.view(T0+MIN);assert.equal(v.accounting.unreportedBrokerAccrualsUsd,0);assert.equal(v.accounting.unreportedBrokerAccrualsVerified,true);
  assert.equal(v.accounting.brokerAccrualVerification.sourceAuthenticityVerified,false);
  const verified=verifyNetLedgerHistoryBundle(await pages(f.ledger),v.integrity);assert.equal(verified.brokerAccrualsVerified,true);assert.equal(verified.brokerAccrualsUsd,0);assert.equal(verified.authorizesOrders,false);
});
test("documented nonzero pending charges link to existing external costs without a second subtraction",async()=>{
  const f=await fixture({maxObservations:2});await step(f,0);const cs=[cost("pending-broker-charge",2,T0+1000,{category:"OTHER",reference:"SYNTHETIC-ACCRUAL-DECLARATION"})];
  for(let i=1;i<4;i++){const at=T0+i*MIN;await step(f,i,{externalCosts:{...coverage(at,cs),broker_accrual_coverage:accrualProof(at,2,[cs[0].id])}});}
  const v=f.ledger.view(T0+3*MIN);assert.equal(v.accounting.accountNetPnlUsd,0);assert.equal(v.accounting.economicNetPnlUsd,-2);
  assert.equal(v.accounting.unreportedBrokerAccrualsUsd,2);assert.equal(v.accounting.externalCostsUsd,2);
  const checked=verifyNetLedgerHistoryBundle(await pages(f.ledger),v.integrity);assert.equal(checked.brokerAccrualsVerified,true);assert.equal(checked.brokerAccrualsUsd,2);assert.equal(checked.derived.economicNetPnlUsd,-2);
});
test("accrual document hash, field bindings, external links and exact totals cannot be replaced by a positive flag",()=>{
  const at=T0+MIN,cs=[cost("p",2,T0+1000,{category:"OTHER",reference:"SYNTHETIC-ACCRUAL-DECLARATION"})],valid={...receipt(at,cs),broker_accrual_coverage:accrualProof(at,2,["p"])};
  const cases=[r=>r.broker_accrual_coverage.document.sha256="0".repeat(64),r=>r.broker_accrual_coverage.document.bindings.pending_total_usd="/missing",
    r=>r.broker_accrual_coverage.pending_total_usd=3,r=>r.broker_accrual_coverage.cost_ids=["missing"],
    r=>{r.entries[0].already_in_account=true;r.entries[0].activity_id="posted-fee";},r=>r.broker_accrual_coverage.explicit_zero=true,
    r=>r.entries[0].category="DATA",r=>r.entries[0].reference="UNRELATED-INVOICE"];
  for(const mutate of cases){const r=structuredClone(valid);mutate(r);assert.throws(()=>validateCostReceipt(r,ACCOUNT,at),/BROKER_ACCRUAL_/);}
});
test("broker accrual coverage is account, currency, knowledge-time and applicable-category bound",()=>{
  const at=T0+MIN,valid={...receipt(at),broker_accrual_coverage:accrualProof(at)};
  for(const mutate of [r=>r.account_id="OTHER",r=>r.currency="EUR",r=>r.known_at=at+1,r=>r.applicable_categories=[],r=>r.coverage_complete=false]){
    const r=structuredClone(valid);mutate(r.broker_accrual_coverage);assert.throws(()=>validateCostReceipt(r,ACCOUNT,at),/BROKER_ACCRUAL_/);
  }
  const noZero=structuredClone(valid);delete noZero.broker_accrual_coverage.explicit_zero;assert.throws(()=>validateCostReceipt(noZero,ACCOUNT,at),/EXPLICIT_ZERO/);
});
test("delayed documentary accrual coverage verifies only the closed compared prefix",async()=>{
  const f=await fixture({maxObservations:3});await step(f,0);
  for(let i=1;i<6;i++){const through=T0+i*MIN-1;await step(f,i,{externalCosts:{...coverage(through),broker_accrual_coverage:accrualProof(through)}});}
  const v=f.ledger.view(T0+5*MIN);assert.equal(v.accounting.unreportedBrokerAccrualsVerified,false);assert.equal(v.accounting.unreportedBrokerAccrualsUsd,null);
  assert.equal(v.closedEconomic.brokerAccruals.verified,true);assert.equal(v.closedEconomic.brokerAccruals.comparedThrough,T0+4*MIN);
  const checked=verifyNetLedgerHistoryBundle(await pages(f.ledger),v.integrity);assert.equal(checked.brokerAccrualsVerified,false);assert.equal(checked.closedBrokerAccruals.verified,true);
  assert.equal(checked.closedBrokerAccruals.comparedThrough,T0+4*MIN);assert(checked.closedBrokerAccruals.through<T0+5*MIN);
});
