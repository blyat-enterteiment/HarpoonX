"use strict";
// Fixed local inference transport. Never loaded by the production bridge.
const fs = require("node:fs"), path = require("node:path"), crypto = require("node:crypto");
const ROOT = path.resolve(__dirname, "..");
const sha = text => crypto.createHash("sha256").update(text).digest("hex");
const need = (ok, reason) => { if (!ok) throw Error(reason); };
function pythonSources() {
  return Object.fromEntries(fs.readdirSync(path.join(ROOT,"quant/harpoon_quant")).filter(f=>f.endsWith(".py")).sort()
    .map(f=>["quant/harpoon_quant/"+f,sha(fs.readFileSync(path.join(ROOT,"quant/harpoon_quant",f)))]));
}
function openFixedPredictor(variant, canonical) {
  // The caller creates the one allowed child before the replay's external-I/O
  // deny hooks. No user-supplied action, module, arguments or shell is accepted.
  const python = process.env.HARPOON_QUANT_PYTHON || "python3";
  need(python === "python3" || path.isAbsolute(python) && /^python(?:\d+(?:\.\d+)*)?$/.test(path.basename(python)), "LOCAL_PYTHON_EXECUTABLE_REQUIRED");
  const timeout = variant.timeout_ms ?? 8000;
  need(Number.isInteger(timeout) && timeout > 0 && timeout <= 30000, "PREDICTOR_TIMEOUT_BUDGET");
  const child = require("node:child_process").spawn(python, ["-B", "-m", "harpoon_quant.fixed_predictor"], {
    cwd:path.join(ROOT,"quant"), shell:false, stdio:["pipe","pipe","pipe"],
    env:{PATH:process.env.PATH||"/usr/bin:/bin",LANG:"C.UTF-8",PYTHONHASHSEED:"0",OPENBLAS_NUM_THREADS:"1",OMP_NUM_THREADS:"1",MKL_NUM_THREADS:"1"},
  });
  let pending = null, buffer = "", stderr = "", closed = false;
  const fail = error => {
    if (pending) { clearTimeout(pending.timer); pending.reject(error); pending=null; }
  };
  child.on("error", error => { closed=true; fail(Error("FIXED_PREDICTOR_UNAVAILABLE:"+error.message)); });
  child.on("close", () => { closed=true; fail(Error("FIXED_PREDICTOR_CLOSED:"+stderr.slice(-1000))); });
  child.stdin.on("error", error=>fail(Error("FIXED_PREDICTOR_INPUT:"+error.message)));
  child.stderr.on("data", data=>{stderr=(stderr+data.toString("utf8")).slice(-4000);});
  child.stdout.on("data", data=>{
    buffer+=data.toString("utf8");
    if (Buffer.byteLength(buffer)>2*1024*1024) { fail(Error("FIXED_PREDICTOR_OUTPUT_LIMIT")); child.kill("SIGKILL"); return; }
    let end;
    while((end=buffer.indexOf("\n"))>=0){
      const line=buffer.slice(0,end);buffer=buffer.slice(end+1);
      if(!pending){child.kill("SIGKILL");return;}
      const job=pending;pending=null;clearTimeout(job.timer);
      try{job.resolve(JSON.parse(line));}catch{job.reject(Error("FIXED_PREDICTOR_OUTPUT_SCHEMA"));}
    }
  });
  return {
    async evaluate(request) {
      need(!closed && !pending,"FIXED_PREDICTOR_NOT_READY_OR_CONCURRENT");
      const request_json=canonical(request), model_json=variant.model_json??canonical(variant.model);
      need(canonical(JSON.parse(model_json))===canonical(variant.model),"FIXED_MODEL_TEXT_CONTENT_MISMATCH");
      need(variant.model_hash===sha(model_json),"FIXED_MODEL_BYTES_BINDING");
      const packet={schema:"HARPOON_FIXED_PREDICTOR_PACKET_1",predictor:variant.name,request_json,request_hash:sha(request_json),model_json,model_hash:sha(model_json)};
      const text=JSON.stringify(packet)+"\n";
      need(Buffer.byteLength(text)<=32*1024*1024,"FIXED_PREDICTOR_INPUT_LIMIT");
      const receipt=await new Promise((resolve,reject)=>{
        const timer=setTimeout(()=>{fail(Error("FIXED_PREDICTOR_TIMEOUT"));child.kill("SIGKILL");},timeout);
        pending={resolve,reject,timer};child.stdin.write(text);
      });
      need(receipt.schema==="HARPOON_FIXED_PREDICTOR_RECEIPT_1"&&receipt.status==="COMPUTED","FIXED_PREDICTOR_BLOCKED:"+(receipt.reason||"SCHEMA"));
      need(receipt.request_hash===packet.request_hash&&receipt.model_hash===packet.model_hash&&receipt.predictor===variant.name,"FIXED_PREDICTOR_RESPONSE_BINDING");
      need(receipt.result_hash===sha(receipt.result_json),"FIXED_PREDICTOR_RESULT_HASH");
      need(receipt.execution_allowed===false&&receipt.liveApproved===false&&receipt.financial_acceptance_allowed===false&&receipt.training_executed===false,"FIXED_PREDICTOR_AUTHORITY");
      need(canonical(receipt.source_hashes)===canonical(pythonSources()),"FIXED_PREDICTOR_SOURCE_BINDING");
      const result=JSON.parse(receipt.result_json);
      need(Array.isArray(result.selected)&&typeof result.execution_allowed==="boolean","FIXED_PREDICTOR_RESULT_SCHEMA");
      if(variant.name==="SVR")need(result.execution_allowed===false&&result.liveApproved===false,"SVR_SHADOW_GUARD_LOST");
      return {receipt,result};
    },
    close() { if(!closed){closed=true;fail(Error("FIXED_PREDICTOR_STOPPED"));child.stdin.end();child.kill("SIGKILL");} },
  };
}
module.exports={openFixedPredictor,pythonSources};
