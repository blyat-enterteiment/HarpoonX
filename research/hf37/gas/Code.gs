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
    const folder=DriveApp.getFolderById(folderId);
    // Collision safe: existing filename must have same hash; do not overwrite.
    if(folderId!=='1OQnmZLBIXflEQR-ZKIcOOsyhKBCAoUBJ' || folder.getSharingAccess()!==DriveApp.Access.PRIVATE)return reply_({status:'FOLDER_MISMATCH'});
    const found=folder.getFilesByName(p.name);
    while(found.hasNext()) {
      const f=found.next();
      if(found.hasNext() || f.getSharingAccess()!==DriveApp.Access.PRIVATE)return reply_({status:'NAME_COLLISION'});
      const actual=sha_(f.getBlob().getBytes());
      if(actual===p.sha256)return reply_({status:'DRIVE_READBACK_VERIFIED',folder_id:folderId,file_id:f.getId(),sha256:actual,bytes:bytes.length,duplicate:true});
      return reply_({status:'NAME_COLLISION'});
    }
    const file=folder.createFile(Utilities.newBlob(bytes,'application/octet-stream',p.name));
    file.setSharing(DriveApp.Access.PRIVATE,DriveApp.Permission.NONE);
    const readback=file.getBlob().getBytes();const actual=sha_(readback);
    if(actual!==p.sha256 || readback.length!==bytes.length) { file.setTrashed(true);return reply_({status:'READBACK_FAILED'}); }
    return reply_({status:'DRIVE_READBACK_VERIFIED',folder_id:folderId,file_id:file.getId(),sha256:actual,bytes:readback.length,duplicate:false});
  } catch(err) { return reply_({status:'FAILED_CLOSED',error_type:String(err&&err.name||'Error')}); }
  finally {lock.releaseLock();}
}
