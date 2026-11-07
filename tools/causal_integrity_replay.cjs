"use strict";
// Offline comparison of a hash-frozen predecessor with a measurement correction.
const fs=require("node:fs"), path=require("node:path"), zlib=require("node:zlib");
const crypto=require("node:crypto"), Module=require("node:module");
const root=path.resolve(__dirname,".."), mode=process.argv[2], output=process.argv[3];
if(!["control","corrected"].includes(mode)||!output) throw Error("MODE_AND_NEW_OUTPUT_REQUIRED");
fs.mkdirSync(output,{recursive:false});
const protocol=JSON.parse(fs.readFileSync(path.join(root,"research/causal_integrity/protocol.json"),"utf8"));
for(const [name,expected] of Object.entries(protocol.bound_files)) {
  const actual=crypto.createHash("sha256").update(fs.readFileSync(path.join(root,name))).digest("hex");
  if(actual!==expected) throw Error("SOURCE_HASH_MISMATCH:"+name);
}
if(mode==="control") {
  const enginePath=path.join(root,"runtime30/profit8_replay.js");
  const source=zlib.gunzipSync(fs.readFileSync(path.join(root,"research/causal_integrity/control_profit8_replay.js.gz")));
  if(crypto.createHash("sha256").update(source).digest("hex")!==protocol.control_engine_sha256)
    throw Error("CONTROL_HASH");
  const frozen=new Module(enginePath,module);
  frozen.filename=enginePath;frozen.paths=Module._nodeModulePaths(path.dirname(enginePath));
  frozen._compile(source.toString("utf8"),enginePath);
  require.cache[enginePath]=frozen;
}
const {run}=require("./profit8_replay.cjs");
const p=JSON.parse(fs.readFileSync(path.join(root,"research/technical_swing/protocol.json"),"utf8"));
const data=JSON.parse(fs.readFileSync(path.join(root,p.dataset),"utf8"));
const signals=JSON.parse(zlib.gunzipSync(fs.readFileSync(path.join(root,"evidence/technical_swing/signals.json.gz"))).toString("utf8"));
for(const scenario of ["NOMINAL","STRESS"]) for(const policy of ["SIMPLE","CONFIRMED","CASH"]) {
  const result=run(p,data,signals,policy,scenario);
  fs.writeFileSync(path.join(output,scenario+"_"+policy+".json.gz"),zlib.gzipSync(JSON.stringify(result)+"\n"));
}
