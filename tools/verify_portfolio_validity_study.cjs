"use strict";
// The registered runner/result remain immutable. Verify their persisted JSON
// representation: optional JS fields with undefined are absent from JSON.
const fs=require("node:fs"),path=require("node:path"),assert=require("node:assert/strict"),crypto=require("node:crypto");
const ROOT=path.resolve(__dirname,".."),DIR=path.join(ROOT,"evidence/portfolio_30_14_0");
const sha=v=>crypto.createHash("sha256").update(v).digest("hex");
function serializeResult(value){
 return JSON.stringify(value,(_key,v)=>{
   assert(typeof v!=="number"||Number.isFinite(v),"Nonfinite numbers cannot be hidden as null in evidence JSON.");
   return v;
 },2)+"\n";
}
function verify(){
 const registered=require("./portfolio_validity_study.cjs");
 const r=registered.requireRegistration("verify"); // Includes all source hashes and REGISTER/COMPLETE chain.
 const attempt=JSON.parse(fs.readFileSync(path.join(DIR,"attempt_started.json"),"utf8"));
 assert.equal(attempt.trial_id,r.trial_id);
 assert.equal(attempt.registration_sha256,sha(fs.readFileSync(path.join(DIR,"registration.json"))));
 assert(Date.parse(attempt.started_at)>=Date.parse(r.registered_at));
 const bytes=fs.readFileSync(path.join(DIR,"result.json"),"utf8");
 const repeated=serializeResult(registered.compute());
 assert.equal(repeated,bytes,"Persisted result bytes did not reproduce under their unchanged registered implementation.");
 return {schema:"HARPOON_PORTFOLIO_RESULT_REPRODUCTION_1",verified:true,trial_id:r.trial_id,
   representation:"EXACT_PERSISTED_JSON_UTF8_BYTES",result_sha256:sha(bytes),
   registration_bindings_and_journal_verified:true,new_financial_variants:0,outputs_rewritten:false,
   original_runner_and_result_unchanged:true,legacy_verify_limitation:"In-memory target:undefined is omitted during JSON persistence; legacy deepStrictEqual did not normalize that representation.",
   financial_acceptance_allowed:false,target_seven_accredited:false};
}
if(require.main===module)console.log(JSON.stringify(verify(),null,2));
module.exports={serializeResult,verify};
