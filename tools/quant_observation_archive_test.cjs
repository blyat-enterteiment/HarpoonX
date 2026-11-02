"use strict";
// SYNTHETIC durable-store faults only; no account, broker or external storage.
const test=require("node:test"),assert=require("node:assert/strict");
const {QuantObservationJournal}=require("../runtime30/quant_observations.js");
const {digest}=require("../runtime30/ultimate_contracts.js");
class Store{
  constructor(){this.rows=new Map();this.fail=null;this.calls=[];}
  async get(k){return structuredClone(this.rows.get(k)||null);}
  async put(k,v){this.calls.push(k);if(this.fail?.(k))throw Error("INJECTED_STORE_FAILURE:"+k);this.rows.set(k,structuredClone(v));return true;}
}
function pair(at){const input={now:at,config:{expected_account_id:"ARCHIVE-ACCOUNT"},signals:[],market:{calendar:[]}};return [input,{schema:"HARPOON_RUNTIME_OBSERVATION_1",status:"WAIT_FEATURE_DATA",asof:new Date(at).toISOString(),observations:[],rejected:{},selected:[],execution_allowed:false,liveApproved:false}];}
async function fixture(config={}){const store=new Store(),cfg={maxFrames:2,...config},j=new QuantObservationJournal(store,"Q","ARCHIVE-ACCOUNT",cfg);await j.load();return {store,cfg,j,start:Date.now()-100000};}
async function capture(f,index){return f.j.capture(...pair(f.start+index*1000));}

test("archive rollover preserves global frame sequence and cross-segment paginated export",async()=>{
  const f=await fixture();for(let i=0;i<5;i++)await capture(f,i);
  const view=f.j.view();assert.equal(view.frames,5);assert.equal(view.active_frames,1);assert.equal(view.archived_segments,2);assert.equal(view.cursor,5*12);
  const index=await f.store.get("Q");assert.equal(index.frames[0].sequence,5);assert.equal(index.archives[0].last_sequence,2);assert.equal(index.archives[1].first_sequence,3);
  const page=await f.j.exportFrames(1,3);assert.equal(page.frames.length,3);assert.equal(page.next_offset,4);assert.equal(page.total_frames,5);assert.equal(page.complete_export,false);
  assert.deepEqual(page.frames.map(x=>x.runtime_input.now),[f.start+1000,f.start+2000,f.start+3000]);
  const all=await f.j.exportFrames();assert.equal(all.complete_export,true);assert.equal(all.frames.length,5);assert(view.stored_bytes>=view.committed_bytes);
});
test("restart restores continuous cursor, archive hashes and retained byte budget",async()=>{
  const f=await fixture();for(let i=0;i<5;i++)await capture(f,i);const before=f.j.view(),exported=await f.j.exportFrames();
  const restored=new QuantObservationJournal(f.store,"Q","ARCHIVE-ACCOUNT",f.cfg);await restored.load();
  for(const key of ["frames","active_frames","archived_segments","cursor","head","stored_bytes","committed_bytes"])assert.equal(restored.view()[key],before[key]);
  assert.deepEqual(await restored.exportFrames(),exported);await restored.capture(...pair(f.start+5000));assert.equal(restored.view().frames,6);
});
test("altered or missing archive cannot be loaded or exported as complete evidence",async()=>{
  const f=await fixture();for(let i=0;i<3;i++)await capture(f,i);const index=await f.store.get("Q"),key=index.archives[0].segment_key,good=await f.store.get(key),bad=structuredClone(good);bad.frames[0].at++;
  await f.store.put(key,bad);await assert.rejects(f.j.exportFrames(),/ARCHIVE_INTEGRITY/);
  const restored=new QuantObservationJournal(f.store,"Q","ARCHIVE-ACCOUNT",f.cfg);await assert.rejects(restored.load(),/ARCHIVE_INTEGRITY/);
  f.store.rows.delete(key);await assert.rejects(f.j.exportFrames(),/ARCHIVE_MISSING/);
  await f.store.put(key,good);assert.equal((await f.j.exportFrames()).frames.length,3);
});
test("failed rollover index commit retains the old control and retries without duplicate quota",async()=>{
  const f=await fixture();await capture(f,0);await capture(f,1);const before=f.j.view(),old=await f.store.get("Q");
  f.store.fail=k=>k==="Q";await assert.rejects(capture(f,2),/INJECTED/);
  assert.deepEqual(await f.store.get("Q"),old);assert.equal(f.j.view().cursor,before.cursor);assert.equal(f.j.view().frames,2);assert.equal(f.j.view().archived_segments,0);
  assert.equal((await f.j.exportFrames()).frames.length,2);const reserved=f.j.view().stored_bytes;assert(reserved>before.stored_bytes);
  f.store.fail=null;const restored=new QuantObservationJournal(f.store,"Q","ARCHIVE-ACCOUNT",f.cfg);await restored.load();assert.equal(restored.view().frames,2);
  await restored.capture(...pair(f.start+2000));assert.equal(restored.view().frames,3);assert.equal(restored.view().archived_segments,1);assert.equal(restored.view().stored_bytes,reserved);
});
test("archive write failure cannot advance cursor or expose the uncommitted segment",async()=>{
  const f=await fixture();await capture(f,0);await capture(f,1);const old=await f.store.get("Q"),before=f.j.view();f.store.fail=k=>k.includes("-archive-");
  await assert.rejects(capture(f,2),/INJECTED/);assert.deepEqual(await f.store.get("Q"),old);assert.equal(f.j.view().frames,2);assert.equal(f.j.view().cursor,before.cursor);
  const reserved=f.j.view().stored_bytes;f.store.fail=null;await capture(f,2);assert.equal(f.j.view().stored_bytes,reserved);assert.equal(f.j.view().frames,3);
});
test("maxArchives zero retains the explicit stop after one segment without deleting evidence",async()=>{
  const f=await fixture({maxArchives:0});await capture(f,0);await capture(f,1);const count=f.store.rows.size;
  await assert.rejects(capture(f,2),/ARCHIVE_REQUIRED/);assert.equal(f.j.view().frames,2);assert.equal(f.j.view().archived_segments,0);assert.equal(f.store.rows.size,count);assert.equal((await f.j.exportFrames()).frames.length,2);
});
test("archive count budget is total across restarts and never silently resets",async()=>{
  const f=await fixture({maxArchives:1});for(let i=0;i<4;i++)await capture(f,i);
  const restored=new QuantObservationJournal(f.store,"Q","ARCHIVE-ACCOUNT",f.cfg);await restored.load();await assert.rejects(restored.capture(...pair(f.start+4000)),/SEGMENT_BUDGET_EXHAUSTED/);
  assert.equal(restored.view().frames,4);assert.equal(restored.view().archived_segments,1);assert.equal((await restored.exportFrames()).frames.length,4);
});
test("retained byte cap is checked before immutable frame or archive writes",async()=>{
  const probe=await fixture();await capture(probe,0);const bytes=probe.j.view().stored_bytes;
  const f=await fixture({maxStoredBytes:Math.max(1024,bytes+10)});await capture(f,0);const old=await f.store.get("Q"),keys=[...f.store.rows.keys()].sort();
  await assert.rejects(capture(f,1),/STORAGE_BUDGET_EXHAUSTED/);assert.deepEqual(await f.store.get("Q"),old);assert.deepEqual([...f.store.rows.keys()].sort(),keys);assert.equal(f.j.view().frames,1);assert(f.j.view().stored_bytes<=f.j.maxStoredBytes);
});
test("repeated failed commits cannot create unbudgeted orphan frames",async()=>{
  const probe=await fixture();await capture(probe,0);const bytes=probe.j.view().stored_bytes;
  const f=await fixture({maxStoredBytes:Math.max(1024,2*bytes+30)});f.store.fail=k=>k==="Q";
  await assert.rejects(capture(f,0),/INJECTED/);await assert.rejects(capture(f,1),/INJECTED/);await assert.rejects(capture(f,2),/STORAGE_BUDGET_EXHAUSTED/);
  assert.equal(f.j.view().frames,0);assert.equal(f.j.view().cursor,0);assert.equal([...f.store.rows.keys()].filter(k=>k.includes("-frame-")).length,2);assert(f.j.view().stored_bytes<=f.j.maxStoredBytes);
  f.store.fail=null;const restored=new QuantObservationJournal(f.store,"Q","ARCHIVE-ACCOUNT",f.cfg);await restored.load();assert.equal(restored.view().stored_bytes,f.j.view().stored_bytes);assert.equal(restored.view().frames,0);
});
test("budget and cross-segment chain tampering is rejected independently of an intact frame payload",async()=>{
  const f=await fixture();for(let i=0;i<3;i++)await capture(f,i);
  const budget=await f.store.get("Q-storage-budget");budget.charged_bytes=0;await f.store.put("Q-storage-budget",budget);
  await assert.rejects(new QuantObservationJournal(f.store,"Q","ARCHIVE-ACCOUNT",f.cfg).load(),/STORAGE_BUDGET_INTEGRITY/);
  const index=await f.store.get("Q");index.archives[0].first_sequence=2;delete index.integrity_hash;index.integrity_hash=digest(index);await f.store.put("Q",index);
  await assert.rejects(new QuantObservationJournal(f.store,"Q","ARCHIVE-ACCOUNT",f.cfg).load(),/ARCHIVE_SEQUENCE/);
});
test("changing retained compressed representation cannot evade its committed byte count",async()=>{
  const f=await fixture();await capture(f,0);const index=await f.store.get("Q"),row=index.frames[0],packed=await f.store.get(row.frame_key);
  const z=require("node:zlib"),plain=z.gunzipSync(Buffer.from(packed.data,"base64"));packed.data=z.gzipSync(plain,{level:0}).toString("base64");await f.store.put(row.frame_key,packed);
  await assert.rejects(f.j.exportFrames(),/STORED_BYTES_MISMATCH/);await assert.rejects(new QuantObservationJournal(f.store,"Q","ARCHIVE-ACCOUNT",f.cfg).load(),/STORED_BYTES_MISMATCH/);
});
test("legacy single-segment journal migrates without rewriting retained frame chains",async()=>{
  const f=await fixture();await capture(f,0);await capture(f,1);const index=await f.store.get("Q");
  for(const key of ["archives","total_frames","committed_bytes","layout_version","integrity_hash"])delete index[key];
  let previous="GENESIS";for(const row of index.frames){delete row.stored_bytes;delete row.chain_hash;row.previous=previous;row.chain_hash=digest(row);previous=row.chain_hash;}index.head=previous;index.integrity_hash=digest(index);await f.store.put("Q",index);f.store.rows.delete("Q-storage-budget");
  const restored=new QuantObservationJournal(f.store,"Q","ARCHIVE-ACCOUNT",f.cfg);await restored.load();assert.equal(restored.view().frames,2);assert(restored.view().stored_bytes>0);
  await restored.capture(...pair(f.start+2000));assert.equal(restored.view().archived_segments,1);assert.equal((await restored.exportFrames()).frames.length,3);
});
test("archive and byte configuration reject unbounded or non-integer budgets",()=>{
  for(const config of [{maxArchives:-1},{maxArchives:257},{maxArchives:1.5},{maxStoredBytes:0},{maxStoredBytes:2147483649},{maxStoredBytes:NaN}])assert.throws(()=>new QuantObservationJournal(new Store(),"Q","ARCHIVE-ACCOUNT",config),/OBSERVATION_CONFIG/);
});
