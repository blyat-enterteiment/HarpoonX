"use strict";
// SYNTHETIC bookkeeping only. No account connection or financial experiment.
const test=require("node:test"),assert=require("node:assert/strict"),path=require("node:path"),fs=require("node:fs"),os=require("node:os");
const runtime=process.env.HARPOON_NET_COST_TEST_RUNTIME||path.join(__dirname,"../runtime30");
const {NetAccountLedger,netLedgerDigest,verifyNetLedgerHistoryBundle}=require(path.join(runtime,"net_accounting.js"));
const {validateCostReceipt,writeCostReceiptFile}=require(path.join(runtime,"cost_receipts.js"));
const T0=Date.parse("2026-11-02T14:30:00Z"),MIN=60000,ACCOUNT="SYNTHETIC-INLINE-COSTS";
class Store{
  constructor(){this.rows=new Map();}
  async get(k){return structuredClone(this.rows.get(k)??null);}
  async put(k,v){this.rows.set(k,structuredClone(v));return true;}
  async lease(){return true;}
  async close(){}
}
class Broker{
  constructor(){this.cash=20000;this.rows=[];}
  cashFlow(type,amount,at){const row={id:"ACTIVITY-"+(this.rows.length+1),activity_type:type,net_amount:String(amount),
    transaction_time:new Date(at).toISOString(),created_at:new Date(at).toISOString(),date:new Date(at).toISOString().slice(0,10)};
    this.rows.push(row);this.cash+=amount;return row;}
  async request(url,method="GET"){
    assert.equal(method,"GET","cost validation must not create external writes");
    if(url==="/v2/account")return{id:ACCOUNT,currency:"USD",cash:String(this.cash),equity:String(this.cash)};
    if(url==="/v2/positions")return[];
    if(url.startsWith("/v2/account/activities?")){
      const q=new URL(url,"https://synthetic.invalid").searchParams;
      const rows=this.rows.filter(r=>Date.parse(r.created_at)>Date.parse(q.get("after"))&&Date.parse(r.created_at)<=Date.parse(q.get("until")));
      const token=q.get("page_token"),start=token?rows.findIndex(x=>x.id===token)+1:0;
      return structuredClone(rows.slice(start,start+Number(q.get("page_size"))));
    }
    throw Error("UNEXPECTED_READ "+url);
  }
}
function receipt(through=T0,entries=[],changes={}){return {schema:"HARPOON_COST_RECEIPT_1",account_id:ACCOUNT,currency:"USD",
  receipt_id:"SYNTHETIC-RECEIPT-"+through,coverage_complete:true,from:T0,through,known_at:through,
  reference:"SYNTHETIC-DECLARATION-"+through,categories:["DATA","INFRASTRUCTURE","INFERENCE","OTHER"],entries,...changes};}
function cost(id="infra",amount=2,at=T0+1000,extra={}){return {id,at,known_at:at,amount_usd:amount,reference:"SYNTHETIC-INVOICE-"+id,
  category:"INFRASTRUCTURE",already_in_account:false,...extra};}
function harness(cfg={}){const store=new Store(),api=new Broker(),config={executionNature:"SYNTHETIC_ENGINEERING_ONLY",...cfg};
  return{store,api,config,ledger:new NetAccountLedger(store,api,"L",ACCOUNT,config)};}
const refresh=(f,now,r)=>f.ledger.refresh({now,instruments:[],...(r===undefined?{}:{externalCosts:r})});
function view(f,at){return f.ledger.view(at);}
function rejected(v,code){assert.equal(v.reconciled,true);assert.equal(v.economicComplete,false);assert.equal(v.accounting.economicNetPnlUsd,null);
  assert.equal(v.accounting.externalCostsUsd,null);assert.equal(v.costSource.status,"REJECTED_BY_LEDGER");assert.equal(v.costSource.reason,code);}
function preflow(row,before,after,at){const e={activityId:row.id,at,equityBefore:before,equityAfter:after};
  return{...e,known_at:at,reference:"SYNTHETIC-PREFLOW",evidence:e,evidenceHash:netLedgerDigest(e)};}
async function pages(ledger){const result=[];let offset=0;do{const page=await ledger.exportHistory(offset,100);result.push(page);offset=page.next_offset;}while(offset!==null);return result;}

test("inline account, currency and explicit complete coverage use the shared receipt validator",async()=>{
  for(const [change,code]of [[{account_id:"ANOTHER-ACCOUNT"},"COST_RECEIPT_ACCOUNT_MISMATCH"],
    [{currency:"EUR"},"COST_RECEIPT_CURRENCY_UNKNOWN"],[{coverage_complete:false},"COST_RECEIPT_COVERAGE_NOT_DECLARED_COMPLETE"]]){
    const f=harness(),r=receipt(T0,[],change);
    assert.throws(()=>validateCostReceipt(r,ACCOUNT,T0),e=>e.code===code);
    await refresh(f,T0,r);rejected(view(f,T0),code);
    assert.equal(view(f,T0).accounting.accountNetPnlUsd,0);
  }
});

test("legacy unbound inline coverage cannot silently declare an economic zero",async()=>{
  const f=harness(),r=receipt();for(const key of["schema","account_id","currency","receipt_id","coverage_complete"])delete r[key];
  await refresh(f,T0,r);rejected(view(f,T0),"COST_RECEIPT_SCHEMA_INVALID");
  assert.equal(view(f,T0).closedEconomic.observationCount,0);
});

test("config.externalCosts and direct refresh reject the same incomplete or wrong-account receipt",async()=>{
  for(const change of[{coverage_complete:false},{account_id:"OTHER"}]){
    const r=receipt(T0,[],change),direct=harness(),configured=harness({externalCosts:r});
    await refresh(direct,T0,r);await refresh(configured,T0);
    const a=view(direct,T0),b=view(configured,T0);
    assert.equal(a.costSource.reason,b.costSource.reason);
    assert.equal(b.accounting.economicNetPnlUsd,null);
    assert.equal(b.reconciled,true);
  }
});

test("only a complete explicit zero is accepted; a missing amount or receipt remains unknown",async()=>{
  const f=harness();await refresh(f,T0,receipt());assert.equal(view(f,T0).accounting.economicNetPnlUsd,0);
  assert.equal(view(f,T0).costSource.receiptValidation,"SHARED_COST_RECEIPT_CONTRACT");
  const bad=cost();delete bad.amount_usd;
  await refresh(f,T0+MIN,receipt(T0+MIN,[bad]));rejected(view(f,T0+MIN),"COST_RECEIPT_AMOUNT_UNKNOWN");
  const missing=harness();await refresh(missing,T0);
  assert.equal(view(missing,T0).accounting.externalCostsUsd,null);assert.equal(view(missing,T0).economicComplete,false);
});

test("future knowledge cannot certify current costs or erase an accepted expense",async()=>{
  const f=harness(),c=cost();await refresh(f,T0,receipt());await refresh(f,T0+MIN,receipt(T0+MIN,[c]));
  const previous=await f.store.get("L");
  await refresh(f,T0+2*MIN,receipt(T0+2*MIN,[],{known_at:T0+3*MIN}));
  rejected(view(f,T0+2*MIN),"COST_RECEIPT_FUTURE_OR_REVERSED");
  const after=await f.store.get("L");assert.deepEqual(after.externalCosts,previous.externalCosts);
  assert.deepEqual(after.observations.slice(0,2),previous.observations);
  assert.equal(after.closedEconomic.economicNetPnlUsd,-2);
});

test("receipt identity is immutable across persistence and reload",async()=>{
  const f=harness();await refresh(f,T0,receipt());
  const c=cost(),original=receipt(T0+MIN,[c]);await refresh(f,T0+MIN,original);
  const accepted=view(f,T0+MIN).costSource;
  f.ledger=new NetAccountLedger(f.store,f.api,"L",ACCOUNT,f.config);await f.ledger.load();
  await refresh(f,T0+2*MIN,receipt(T0+2*MIN,[c],{receipt_id:original.receipt_id}));
  const v=view(f,T0+2*MIN);rejected(v,"COST_RECEIPT_ID_REUSED_WITH_CHANGED_CONTENT");
  assert.equal(v.costSource.lastAccepted.receiptContentHash,accepted.receiptContentHash);
  assert.equal((await f.store.get("L")).externalCosts[0].amount_usd,2);
  await refresh(f,T0+3*MIN,receipt(T0+3*MIN,[c]));
  assert.equal(view(f,T0+3*MIN).accounting.economicNetPnlUsd,-2);
  assert.equal(view(f,T0+3*MIN).observations_count,4);
});

test("an invoice cannot disappear or mutate and a broker-booked fee is not subtracted twice",async()=>{
  const f=harness();await refresh(f,T0,receipt());
  const fee=f.api.cashFlow("FEE",-2,T0+1000),c=cost("in-account",2,T0+1000,{already_in_account:true,activity_id:fee.id});
  await refresh(f,T0+MIN,receipt(T0+MIN,[c]));
  assert.equal(view(f,T0+MIN).accounting.economicNetPnlUsd,-2);assert.equal(view(f,T0+MIN).accounting.externalCostsUsd,0);
  await refresh(f,T0+2*MIN,receipt(T0+2*MIN,[]));rejected(view(f,T0+2*MIN),"COST_HISTORY_GAP");
  assert.equal((await f.store.get("L")).externalCosts.length,1);
  const duplicate={...c,id:"duplicate"};
  await refresh(f,T0+3*MIN,receipt(T0+3*MIN,[c,duplicate]));rejected(view(f,T0+3*MIN),"COST_RECEIPT_DUPLICATE_ACTIVITY_LINK");
  assert.equal(view(f,T0+3*MIN).accounting.accountNetPnlUsd,-2);
});

test("valid file and inline receipts retain the same costs and economic account result",async t=>{
  const directory=fs.mkdtempSync(path.join(os.tmpdir(),"hx-inline-file-parity-"));t.after(()=>fs.rmSync(directory,{recursive:true,force:true}));
  const file=path.join(directory,"costs.json"),inline=harness(),fromFile=harness({costReceiptFile:file});
  for(const now of[T0,T0+MIN]){
    const r=receipt(now,now===T0?[]:[cost()]);await writeCostReceiptFile(file,r,ACCOUNT,now);
    await refresh(inline,now,r);await refresh(fromFile,now);
  }
  const a=view(inline,T0+MIN),b=view(fromFile,T0+MIN);
  assert.equal(a.accounting.economicNetPnlUsd,-2);assert.equal(a.accounting.economicNetPnlUsd,b.accounting.economicNetPnlUsd);
  assert.equal(a.costSource.receiptContentHash,b.costSource.receiptContentHash);
  const bad=receipt(T0+2*MIN,[],{coverage_complete:false});fs.writeFileSync(file,JSON.stringify(bad));
  await refresh(inline,T0+2*MIN,bad);await refresh(fromFile,T0+2*MIN);
  assert.equal(view(inline,T0+2*MIN).costSource.reason,view(fromFile,T0+2*MIN).costSource.reason);
  assert.equal(view(fromFile,T0+2*MIN).accounting.economicNetPnlUsd,null);
});

test("a malformed inline override cannot be replaced silently by a valid configured file",async t=>{
  const directory=fs.mkdtempSync(path.join(os.tmpdir(),"hx-inline-file-override-"));t.after(()=>fs.rmSync(directory,{recursive:true,force:true}));
  const file=path.join(directory,"costs.json");await writeCostReceiptFile(file,receipt(),ACCOUNT,T0);
  const f=harness({costReceiptFile:file});await refresh(f,T0,receipt(T0,[],{account_id:"OTHER"}));
  rejected(view(f,T0),"COST_RECEIPT_ACCOUNT_MISMATCH");
});

test("deposits and withdrawals stay neutral while real-dated declared costs affect compound",async()=>{
  const f=harness();await refresh(f,T0,receipt());
  const depositAt=T0+30000,d=f.api.cashFlow("CSD",1000,depositAt),c=cost("compute",10,T0+45000);
  await f.ledger.refresh({now:T0+MIN,instruments:[],externalCosts:receipt(T0+MIN,[c]),preFlowMarks:[preflow(d,20000,21000,depositAt)]});
  const withdrawalAt=T0+90000,w=f.api.cashFlow("CSW",-500,withdrawalAt);
  await f.ledger.refresh({now:T0+2*MIN,instruments:[],externalCosts:receipt(T0+2*MIN,[c]),preFlowMarks:[preflow(w,21000,20500,withdrawalAt)]});
  const v=view(f,T0+2*MIN);assert.equal(v.accounting.accountNetPnlUsd,0);assert.equal(v.accounting.externalFlowsUsd,500);
  assert.equal(v.accounting.economicNetPnlUsd,-10);
  assert(Math.abs(v.accounting.totalReturnEconomic+10/21000)<1e-12);
  const verified=verifyNetLedgerHistoryBundle(await pages(f.ledger),v.integrity);
  assert.equal(verified.derived.externalFlowsUsd,500);assert.equal(verified.derived.economicNetPnlUsd,-10);
});

test("invalid receipts cannot clear the restatement latch or rewrite sealed accounting evidence",async()=>{
  const f=harness({maxObservations:2,archive:{enabled:true,maxSegments:16,maxStoredBytes:32*1024*1024,activityOverlapMs:MIN}});
  const c=cost();for(let i=0;i<3;i++)await refresh(f,T0+i*MIN,receipt(T0+i*MIN,i?[c]:[]));
  const sealed=[...f.store.rows].filter(([,v])=>v.schema==="HARPOON_NET_ARCHIVE_SEGMENT_1").map(([k,v])=>[k,JSON.stringify(v)]);
  assert(sealed.length>0);
  await refresh(f,T0+3*MIN,receipt(T0+3*MIN,[{...c,amount_usd:3}]));
  assert.equal(view(f,T0+3*MIN).economicRestatementRequired,true);
  await refresh(f,T0+4*MIN,receipt(T0+4*MIN,[],{coverage_complete:false}));
  assert.equal(view(f,T0+4*MIN).economicRestatementRequired,true);
  f.ledger=new NetAccountLedger(f.store,f.api,"L",ACCOUNT,f.config);await f.ledger.load();
  await refresh(f,T0+5*MIN,receipt(T0+5*MIN,[c]));
  const v=view(f,T0+5*MIN);assert.equal(v.economicRestatementRequired,true);assert.equal(v.accounting.economicNetPnlUsd,null);
  for(const[k,bytes]of sealed)assert.equal(JSON.stringify(f.store.rows.get(k)),bytes);
  assert.equal(v.baseline.equity,20000);
});
