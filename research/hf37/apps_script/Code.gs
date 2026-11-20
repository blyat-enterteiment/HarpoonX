const BATCH = "4e2ee09618e6031ff11945a476ac1510eca7ad76ba33233a3981c7384f18d28a";
const MAX_BYTES = 5 * 1024 * 1024;
const FILE_FIELDS = "id,name,parents,trashed,mimeType,appProperties";

function reply(value) {
  return ContentService.createTextOutput(JSON.stringify(value))
    .setMimeType(ContentService.MimeType.JSON);
}

function hex(bytes) {
  return bytes.map(value => (value & 255).toString(16).padStart(2, "0")).join("");
}

function sameSignature(left, right) {
  if (!/^[0-9a-f]{64}$/.test(left)) return false;
  let difference = 0;
  for (let i = 0; i < 64; i++) difference |= left.charCodeAt(i) ^ right.charCodeAt(i);
  return difference === 0;
}

function doPost(event) {
  const started = Date.now();
  try {
    const body = event.postData.contents;
    if (body.length > 7 * 1024 * 1024) return reply({status: "LIMIT"});
    const properties = PropertiesService.getScriptProperties();
    const secret = properties.getProperty("HF38_BRIDGE_SECRET");
    const folder = properties.getProperty("HF38_GOOGLE_DRIVE_FOLDER_ID");
    const envelope = JSON.parse(body);
    if (!secret || secret.length < 32 || !folder || typeof envelope.payload !== "string" ||
        !sameSignature(envelope.signature, hex(Utilities.computeHmacSha256Signature(
          envelope.payload, secret, Utilities.Charset.UTF_8)))) return reply({status: "DENIED"});
    const request = JSON.parse(envelope.payload);
    if (!Number.isInteger(request.timestamp) || Math.abs(Date.now() - request.timestamp) > 60000 ||
        request.batch_id !== BATCH || request.folder !== folder) return reply({status: "DENIED"});
    const lock = LockService.getScriptLock();
    if (!lock.tryLock(5000)) return reply({status: "BUSY"});
    try {
      const cache = CacheService.getScriptCache();
      if (!/^[0-9a-f]{32}$/.test(request.nonce) || cache.get(request.nonce)) {
        return reply({status: "DENIED"});
      }
      cache.put(request.nonce, "1", 120);
      const result = handle(request, folder, properties);
      result.server_ms = Date.now() - started;
      return reply(result);
    } finally {
      lock.releaseLock();
    }
  } catch (error) {
    return reply({status: "FAILED"});
  }
}

function handle(request, folder, properties) {
  const saved = properties.getProperty("HF38_PILOT_FILE_ID");
  if (request.action === "reserve") {
    const id = saved || Drive.Files.generateIds({count: 1, space: "drive"}).ids[0];
    if (!saved) properties.setProperty("HF38_PILOT_FILE_ID", id);
    return {status: "OK", id: id};
  }
  if (!saved || request.id !== saved) return {status: "DENIED"};
  let file;
  try {
    file = Drive.Files.get(saved, {fields: FILE_FIELDS, supportsAllDrives: true});
  } catch (error) {
    if (!/File not found/i.test(String(error))) throw error;
  }
  if (request.action === "put" && !file) {
    const bytes = Utilities.base64Decode(request.data);
    if (!bytes.length || bytes.length > MAX_BYTES ||
        hex(Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, bytes)) !== request.sha256) {
      return {status: "INVALID_BYTES"};
    }
    const name = BATCH + ".zip";
    Drive.Files.create({
      id: saved, name: name, parents: [folder], mimeType: "application/zip",
      appProperties: {batch_id: BATCH, sha256: request.sha256}
    }, Utilities.newBlob(bytes, "application/zip", name), {supportsAllDrives: true});
    return {status: "OK", id: saved};
  }
  if (!file && request.action === "get") return {status: "MISSING"};
  if (!file || file.trashed || file.parents.length !== 1 || file.parents[0] !== folder ||
      file.name !== BATCH + ".zip" || file.mimeType !== "application/zip" ||
      !file.appProperties || file.appProperties.batch_id !== BATCH) return {status: "CONFLICT"};
  if (request.action === "put") {
    return {status: file.appProperties.sha256 === request.sha256 ? "OK" : "CONFLICT", id: saved};
  }
  if (request.action !== "get") return {status: "DENIED"};
  const bytes = DriveApp.getFileById(saved).getBlob().getBytes();
  if (bytes.length > MAX_BYTES ||
      hex(Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, bytes)) !== file.appProperties.sha256) {
    return {status: "CONFLICT"};
  }
  return {status: "OK", id: saved, sha256: file.appProperties.sha256,
    data: Utilities.base64Encode(bytes)};
}
