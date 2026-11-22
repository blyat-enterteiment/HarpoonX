/** HF37 private archive bridge. Deploy: execute as owner, access anyone (URL exposed but HMAC required).
 * Script Properties: HF37_SHARED_KEY (64+ random hex chars), HF37_FOLDER_ID.
 * Google Apps Script cannot bind an HTTP Authorization header via doPost(e); signed body is used.
 * A publicly reachable endpoint is not a private network service. Rotate key on exposure.
 */
const MAX_BYTES = 3 * 1024 * 1024;
const SKEW_MS = 120000;
function hex_(bytes) { return bytes.map(b => ('0'+(b & 255).toString(16)).slice(-2)).join(''); }
function sha_(bytes) { return hex_(Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, bytes)); }
function hmac_(key, text) { return hex_(Utilities.computeHmacSha256Signature(text, key)); }
function equal_(a,b) { if (typeof a !== 'string' || typeof b !== 'string' || a.length !== b.length) return false; let x=0; for(let i=0;i<a.length;i++)x|=a.charCodeAt(i)^b.charCodeAt(i); return x===0; }
function reply_(x) { return ContentService.createTextOutput(JSON.stringify(x)).setMimeType(ContentService.MimeType.JSON); }
function doGet(e) { return reply_({status:'NO_PUBLIC_READ', orders_enabled:false}); }
function doPost(e) {
  const lock=LockService.getScriptLock();
  if(!lock.tryLock(15000))return reply_({status:'BUSY'});
  try {
    const props=PropertiesService.getScriptProperties();
    const key=props.getProperty('HF37_SHARED_KEY'),folderId=props.getProperty('HF37_FOLDER_ID');
    if(!key || key.length<64 || !folderId)return reply_({status:'NOT_CONFIGURED'});
    if(!e || !e.postData || !e.postData.contents || e.postData.contents.length>5*1024*1024)return reply_({status:'INVALID_REQUEST'});
    const p=JSON.parse(e.postData.contents);
    if(p.version!==1 || p.op!=='put' || !/^[a-zA-Z0-9_.-]{1,120}$/.test(p.name||'') || !/^[0-9a-f]{64}$/.test(p.sha256||'') || !/^[a-f0-9]{32}$/.test(p.nonce||'') || !Number.isSafeInteger(p.ts) || Math.abs(Date.now()-p.ts)>SKEW_MS)return reply_({status:'INVALID_METADATA'});
    if(typeof p.data!=='string'||p.data.length>Math.ceil(MAX_BYTES*4/3)+16)return reply_({status:'TOO_LARGE'});
    const signing=[p.version,p.op,p.ts,p.nonce,p.name,p.sha256,p.data].join('\n');
    if(!equal_(hmac_(key,signing),p.mac))return reply_({status:'AUTH_FAILED'});
    const cache=CacheService.getScriptCache();
    if(cache.get('nonce:'+p.nonce))return reply_({status:'REPLAY_REJECTED'});
    cache.put('nonce:'+p.nonce,'1',300);
    const bytes=Utilities.base64Decode(p.data);
    if(bytes.length===0 || bytes.length>MAX_BYTES || sha_(bytes)!==p.sha256)return reply_({status:'HASH_MISMATCH'});
    return archive_(props,folderId,p,bytes);
  } catch(err) { return reply_({status:'FAILED_CLOSED',error_type:String(err&&err.name||'Error')}); }
  finally {lock.releaseLock();}
}

const ARCHIVE_FOLDER = '1OQnmZLBIXflEQR-ZKIcOOsyhKBCAoUBJ';
const PILOT_NAME = '4dc3b6d1e26338417a1b25a049e423c4d2ffbdba5f95024824591fc6bb5bce17.json.gz';
const FILE_FIELDS = 'id,name,parents,size,trashed,ownedByMe,shared,mimeType,appProperties';
function read_(id, query) {
  if (!/^[A-Za-z0-9_-]+$/.test(id)) throw Error('INVALID_ID');
  const response = UrlFetchApp.fetch('https://www.googleapis.com/drive/v3/files/' + id + '?' + query, {
    headers: {Authorization:'Bearer ' + ScriptApp.getOAuthToken()}, followRedirects:false, muteHttpExceptions:true
  });
  if (response.getResponseCode() === 404) return null;
  if (response.getResponseCode() !== 200) throw Error('DRIVE_READ_FAILED');
  return response;
}
function metadata_(id) {
  const response = read_(id, 'fields=' + encodeURIComponent(FILE_FIELDS));
  return response ? JSON.parse(response.getContentText()) : null;
}
function private_(f) { return f && f.trashed === false && f.ownedByMe === true && f.shared === false; }
function reservedId_(props, name) {
  const tag = 'file:' + name;
  let id = props.getProperty(tag);
  if (!id) {
    id = Drive.Files.generateIds({count:1,space:'drive',type:'files'}).ids[0];
    props.setProperty(tag,id);
  }
  return id;
}
function preparePilot() {
  const lock = LockService.getScriptLock(); lock.waitLock(15000);
  try {
    const props = PropertiesService.getScriptProperties();
    if (props.getProperty('HF37_FOLDER_ID') !== ARCHIVE_FOLDER) throw Error('FOLDER_MISMATCH');
    const folder = metadata_(ARCHIVE_FOLDER);
    if (folder && private_(folder) && folder.mimeType === 'application/vnd.google-apps.folder') {
      console.log('ARCHIVE_FOLDER_ACCESSIBLE'); return;
    }
    if (folder) throw Error('FOLDER_NOT_PRIVATE');
    const id = reservedId_(props,PILOT_NAME);
    if (!metadata_(id)) Drive.Files.create({id:id,name:'HF37-pilot.pending',mimeType:'application/octet-stream',
      appProperties:{hf37Name:PILOT_NAME}}, null, {fields:'id'});
    console.log('PILOT_FILE_TO_MOVE ' + id);
  } finally { lock.releaseLock(); }
}
function archive_(props, folderId, p, bytes) {
  if (folderId !== ARCHIVE_FOLDER) return reply_({status:'FOLDER_MISMATCH'});
  const id = reservedId_(props,p.name);
  let f = metadata_(id);
  const blob = Utilities.newBlob(bytes,'application/octet-stream',p.name);
  let duplicate = true;
  if (!f) {
    const folder = metadata_(folderId);
    if (!private_(folder) || folder.mimeType !== 'application/vnd.google-apps.folder') return reply_({status:'FOLDER_ACCESS_REQUIRED'});
    const matches = Drive.Files.list({q:"'"+folderId+"' in parents and trashed = false and name = '"+p.name+"'",fields:'files(id)',pageSize:1});
    if ((matches.files || []).length) return reply_({status:'NAME_COLLISION'});
    Drive.Files.create({id:id,name:p.name,parents:[folderId],mimeType:'application/octet-stream',appProperties:{hf37Name:p.name}}, blob, {fields:'id'});
    duplicate = false;
  } else {
    if (!private_(f) || !f.parents || f.parents.length !== 1 || f.parents[0] !== folderId || !f.appProperties || f.appProperties.hf37Name !== p.name) return reply_({status:'FILE_NOT_AUTHORIZED'});
    if (p.name === PILOT_NAME && f.name === 'HF37-pilot.pending' && Number(f.size) === 0) {
      Drive.Files.update({name:p.name},id,blob,{fields:'id'}); duplicate=false;
    } else if (f.name !== p.name) return reply_({status:'NAME_COLLISION'});
  }
  f = metadata_(id);
  if (!private_(f) || !f.parents || f.parents.length !== 1 || f.parents[0] !== folderId || f.name !== p.name || Number(f.size) !== bytes.length) return reply_({status:'READBACK_FAILED'});
  const response = read_(id,'alt=media');
  if (!response) return reply_({status:'READBACK_FAILED'});
  const raw = response.getContent(); const actual = sha_(raw);
  if (raw.length !== bytes.length || actual !== p.sha256) return reply_({status:'READBACK_FAILED'});
  return reply_({status:'DRIVE_READBACK_VERIFIED',folder_id:folderId,file_id:id,sha256:actual,bytes:raw.length,duplicate:duplicate});
}
