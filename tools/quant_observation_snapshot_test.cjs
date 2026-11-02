"use strict";
// Synthetic storage/transport fixtures only. No broker or financial experiment.
const test=require("node:test"),assert=require("node:assert/strict"),fs=require("node:fs"),os=require("node:os"),path=require("node:path"),crypto=require("node:crypto");
const {QuantObservationJournal}=require("../runtime30/quant_observations.js"),{server}=require("../runtime30/server.js");
const {digest}=require("../runtime30/ultimate_contracts.js"),{assemble,verifyManifest}=require("./export_observation_snapshot.cjs");
class Store{constructor(){this.rows=new Map();this.readHook=null;this.reads=[];}async get(k){this.reads.push(k);if(this.readHook)await this.readHook(k);return structuredClone(this.rows.get(k)||null);}async put(k,v){this.rows.set(k,structuredClone(v));return true;}}
const at=Date.parse("2026-10-01T14:00:00Z");
function pair(n,universe=[]){return [{now:at+n*60000,config:{mode:"paper",expected_account_id:"SYNTHETIC-SNAPSHOT",universe},signals:[],market:{calendar:[]}},
 {schema:"HARPOON_RUNTIME_OBSERVATION_1",status:"WAIT_FEATURE_DATA",asof:new Date(at+n*60000).toISOString(),observations:[],rejected:{},selected:[],execution_allowed:false,liveApproved:false}];}
async function fixture(cfg={}){const store=new Store(),j=new QuantObservationJournal(store,"S","SYNTHETIC-SNAPSHOT",{maxFrames:2,...cfg});await j.load();return {store,j,cfg:{maxFrames:2,...cfg}};}
function save(root,name,body){const bytes=Buffer.from(JSON.stringify(body));fs.writeFileSync(path.join(root,name),bytes);return {path:name,sha256:crypto.createHash("sha256").update(bytes).digest("hex")};}
test("pinned pages keep the committed header while capture and archive rotation advance",async()=>{
 const f=await fixture();await f.j.capture(...pair(0));await f.j.capture(...pair(1));
 const pin=await f.j.snapshotExport(),first=await f.j.exportSnapshot(pin.snapshot_id,0,1);
 await f.j.capture(...pair(2));await f.j.capture(...pair(3));
 const second=await f.j.exportSnapshot(pin.snapshot_id,1,100);
 assert.equal(first.head,second.head);assert.equal(second.total_frames,2);assert.equal(second.next_offset,2);assert.equal(second.frames.length,1);assert.equal(f.j.view().frames,4);
 const root=fs.mkdtempSync(path.join(os.tmpdir(),"harpoon-snapshot-test-"));
 try{const refs=[save(root,"first.json",first),save(root,"second.json",second)],manifest=assemble(pin,refs,{kind:"SYNTHETIC_SELECTION"},root);assert.equal(verifyManifest(manifest,root).total_frames,2);assert.throws(()=>assemble(pin,refs.slice(1),manifest.selection,root),/CONTINUITY/);}finally{fs.rmSync(root,{recursive:true,force:true});}
});
test("snapshot token and pages survive restart and metadata contributes to the existing byte quota",async()=>{
 const f=await fixture();await f.j.capture(...pair(0));const pin=await f.j.snapshotExport(),before=await f.j.exportSnapshot(pin.snapshot_id);
 const restored=new QuantObservationJournal(f.store,"S","SYNTHETIC-SNAPSHOT",f.cfg);await restored.load();
 assert.deepEqual(await restored.exportSnapshot(pin.snapshot_id),before);assert.deepEqual(await restored.snapshotExport(),pin);
 assert(restored.view().export_snapshot_metadata_bytes>0);assert.equal(restored.view().total_reserved_bytes,restored.view().stored_bytes+restored.view().export_snapshot_metadata_bytes);assert(restored.view().total_reserved_bytes<=restored.maxStoredBytes);
});
test("two snapshots are retained and old tokens never silently bind to the newest head",async()=>{
 const f=await fixture();await f.j.capture(...pair(0));const a=await f.j.snapshotExport();await f.j.capture(...pair(1));const b=await f.j.snapshotExport();await f.j.capture(...pair(2));const c=await f.j.snapshotExport();
 assert.equal(f.j.view().retained_export_snapshots,2);await assert.rejects(f.j.exportSnapshot(a.snapshot_id),/MISSING_OR_EVICTED/);assert.equal((await f.j.exportSnapshot(b.snapshot_id)).total_frames,2);assert.equal((await f.j.exportSnapshot(c.snapshot_id)).total_frames,3);
 await assert.rejects(f.j.exportSnapshot("arbitrary"),/SNAPSHOT_ID/);await assert.rejects(f.j.exportSnapshot(c.snapshot_id,4),/OFFSET/);
});
test("restart validates snapshot archives once and cached pages do not rescan the full history",async()=>{
 const f=await fixture();for(let i=0;i<5;i++)await f.j.capture(...pair(i));const pin=await f.j.snapshotExport();
 const restored=new QuantObservationJournal(f.store,"S","SYNTHETIC-SNAPSHOT",f.cfg);await restored.load();
 f.store.reads=[];await restored.exportSnapshot(pin.snapshot_id,0,1);await restored.exportSnapshot(pin.snapshot_id,3,1);
 assert.equal(f.store.reads.filter(k=>k.includes("-archive-")).length,0);assert.equal(f.store.reads.filter(k=>k.includes("-frame-")).length,2);
});
test("long index validation yields cooperatively without changing the pinned prefix",async()=>{
 const f=await fixture({maxFrames:512});for(let i=0;i<512;i++)await f.j.capture(...pair(i));
 let callbackRan=false;setImmediate(()=>{callbackRan=true;});const snapshot=await f.j.snapshotExport();
 assert.equal(callbackRan,true);assert.equal(snapshot.total_frames,512);assert.equal(snapshot.head,f.j.view().head);
});
test("an uncertain snapshot write keeps its metadata quota reserved until restart verifies storage",async()=>{
 const f=await fixture();await f.j.capture(...pair(0));const put=f.store.put.bind(f.store);
 f.store.put=async(k,v)=>{await put(k,v);if(k==="S-export-snapshots")throw Error("ACK_LOST_AFTER_WRITE");};
 await assert.rejects(f.j.snapshotExport(),/ACK_LOST/);assert.equal(f.j.view().retained_export_snapshots,0);assert(f.j.view().export_snapshot_metadata_bytes>0);
 f.store.put=put;const restored=new QuantObservationJournal(f.store,"S","SYNTHETIC-SNAPSHOT",f.cfg);await restored.load();
 assert.equal(restored.view().retained_export_snapshots,1);assert(restored.view().total_reserved_bytes<=restored.maxStoredBytes);
});
test("mutated snapshot account, head or raw frame fails closed after restart or read",async()=>{
 const f=await fixture();await f.j.capture(...pair(0));const pin=await f.j.snapshotExport();
 const saved=await f.store.get("S-export-snapshots"),bad=structuredClone(saved);bad.snapshots[0].descriptor.account_id="ANOTHER";const {integrity_hash,...body}=bad;await f.store.put("S-export-snapshots",{...body,integrity_hash:digest(body)});
 await assert.rejects(new QuantObservationJournal(f.store,"S","SYNTHETIC-SNAPSHOT",f.cfg).load(),/SNAPSHOT_BINDING/);
 await f.store.put("S-export-snapshots",saved);const index=await f.store.get("S"),key=index.frames[0].frame_key,payload=await f.store.get(key);payload.data="tampered";await f.store.put(key,payload);
 await assert.rejects(f.j.exportSnapshot(pin.snapshot_id),/INTEGRITY|MISMATCH|incorrect|header|buffer/i);
});
test("snapshot metadata cannot increase the retained byte limit",async()=>{
 const probe=await fixture();await probe.j.capture(...pair(0));const bytes=probe.j.view().stored_bytes;
 const f=await fixture({maxStoredBytes:Math.max(1024,bytes+100)});await f.j.capture(...pair(0));
 await assert.rejects(f.j.snapshotExport(),/METADATA_BUDGET/);assert.equal(f.j.view().retained_export_snapshots,0);assert.equal(f.j.view().frames,1);
});
test("snapshot HTTP routes require existing authentication and never query a broker",async()=>{
 const f=await fixture();await f.j.capture(...pair(0));let brokerCalls=0;
 const engine={quantObservations:f.j,api:{request(){brokerCalls++;throw Error("NO_BROKER_ALLOWED");}}};
 const password="synthetic-snapshot-password-at-least-32-characters",app=server(engine,password,"<html></html>");
 function call(url,auth=true){return new Promise(resolve=>{const req={method:"GET",url,headers:auth?{authorization:"Basic "+Buffer.from("trader:"+password).toString("base64")}:{}};const res={statusCode:200,setHeader(){},end(v){resolve({status:this.statusCode,body:JSON.parse(v)});}};app.emit("request",req,res);});}
 try{assert.equal((await call("/v1/quant/observations/snapshot",false)).status,401);const pinned=await call("/v1/quant/observations/snapshot");assert.equal(pinned.status,200);const url="/v1/quant/observations?snapshot_id="+pinned.body.snapshot_id;assert.equal((await call(url,false)).status,401);assert.equal((await call(url)).body.total_frames,1);assert.equal(brokerCalls,0);}finally{app.close();}
});
