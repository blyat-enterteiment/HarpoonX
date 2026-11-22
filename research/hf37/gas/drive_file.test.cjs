const assert = require('node:assert/strict');
const { createHash } = require('node:crypto');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');
const vm = require('node:vm');

const folder = '1OQnmZLBIXflEQR-ZKIcOOsyhKBCAoUBJ';
const pilot = '4dc3b6d1e26338417a1b25a049e423c4d2ffbdba5f95024824591fc6bb5bce17.json.gz';
const bytes = [0, 255, 0, 128, 21];
const hash = data => createHash('sha256').update(Buffer.from(data)).digest();
const code = readFileSync(path.join(__dirname, 'Code.gs'), 'utf8');

function fixture(authorized) {
  const records = new Map();
  const contents = new Map();
  const props = new Map([['HF37_FOLDER_ID', folder]]);
  const store = {getProperty:k=>props.get(k), setProperty:(k,v)=>props.set(k,v)};
  const common = {trashed:false, ownedByMe:true, shared:false};
  if (authorized) records.set(folder, {...common, mimeType:'application/vnd.google-apps.folder'});
  const files = {
    generateIds:()=>({ids:['fixture-id']}),
    list:()=>({files:[]}),
    create(meta, data) {
      assert.ok(!records.has(meta.id));
      const raw = data || [];
      records.set(meta.id, {...common,parents:['root'],...meta,size:String(raw.length)});
      contents.set(meta.id,raw);
    },
    update(meta,id,data) {
      records.set(id,{...records.get(id),...meta,size:String(data.length)});
      contents.set(id,data);
    }
  };
  const sandbox = {
    Drive:{Files:files}, PropertiesService:{getScriptProperties:()=>store},
    LockService:{getScriptLock:()=>({waitLock(){},releaseLock(){}})},
    Utilities:{newBlob:d=>d, DigestAlgorithm:{SHA_256:'SHA_256'},computeDigest:(_,d)=>[...hash(d)]},
    ContentService:{createTextOutput:s=>({setMimeType:()=>JSON.parse(s)}),MimeType:{JSON:'json'}},
    ScriptApp:{getOAuthToken:()=>'fixture'},console:{log(){}},
    UrlFetchApp:{fetch(url,opts) {
      const u=new URL(url); assert.equal(u.origin,'https://www.googleapis.com');
      assert.equal(opts.followRedirects,false);
      const id=u.pathname.split('/').pop();
      return {getResponseCode:()=>records.has(id)?200:404,
        getContentText:()=>JSON.stringify(records.get(id)),getContent:()=>contents.get(id)};
    }}
  };
  vm.runInNewContext(code,sandbox);
  const send=()=>sandbox.archive_(store,folder,{name:pilot,sha256:hash(bytes).toString('hex')},bytes);
  return {prepare:sandbox.preparePilot,send,records,contents,files};
}

test('manifest grants per-file Drive access and pins the HTTPS destination',()=>{
  const manifest=JSON.parse(readFileSync(path.join(__dirname,'appsscript.json')));
  assert.deepEqual(manifest.oauthScopes,['https://www.googleapis.com/auth/drive.file','https://www.googleapis.com/auth/script.external_request']);
  assert.deepEqual(manifest.urlFetchWhitelist,['https://www.googleapis.com/drive/v3/files/']);
  assert.doesNotMatch(code,/\bDriveApp\./);
});

test('authorized parent, immutable reattempt and corrupt binary readback',()=>{
  const f=fixture(true);
  f.prepare(); const first=f.send();
  assert.equal(first.status,'DRIVE_READBACK_VERIFIED'); assert.equal(first.duplicate,false);
  assert.equal(f.send().duplicate,true);
  f.contents.set(first.file_id,[0,1,2,3,4]);
  assert.equal(f.send().status,'READBACK_FAILED');
});

test('app-created reservation admits bytes only after move to private archive',()=>{
  const f=fixture(false);
  assert.equal(f.send().status,'FOLDER_ACCESS_REQUIRED');
  f.prepare(); f.prepare();
  const file=f.records.get('fixture-id');
  assert.equal(file.size,'0'); assert.equal(f.send().status,'FILE_NOT_AUTHORIZED');
  file.parents=[folder]; file.shared=true;
  assert.equal(f.send().status,'FILE_NOT_AUTHORIZED');
  file.shared=false;
  const proof=f.send();
  assert.equal(proof.folder_id,folder); assert.equal(proof.file_id,'fixture-id');
  assert.equal(proof.sha256,hash(bytes).toString('hex')); assert.equal(f.send().duplicate,true);
});

test('a same-name file visible to the app prevents creation',()=>{
  const f=fixture(true); f.files.list=()=>({files:[{id:'existing'}]});
  assert.equal(f.send().status,'NAME_COLLISION');
  assert.equal(f.contents.size,0);
});
