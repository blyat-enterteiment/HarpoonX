"use strict";
const test=require("node:test"),assert=require("node:assert/strict"),crypto=require("node:crypto");
const {validateJournal}=require("./portfolio_validity_study.cjs");
const sha=s=>crypto.createHash("sha256").update(s).digest("hex");
function event(body){return {...body,hash:sha(JSON.stringify(body))};}
function fixture(){
 const first=event({sequence:1,previous_hash:null,kind:"REGISTER",trial_id:"T",registration_sha256:"a".repeat(64)});
 const last=event({sequence:2,previous_hash:first.hash,kind:"COMPLETE",trial_id:"T",result_sha256:"b".repeat(64)});
 return {first,last,expected:{trial_id:"T",registration_sha256:"a".repeat(64),result_sha256:"b".repeat(64)}};
}
test("completed result is bound to the registered identity and both content hashes",()=>{
 const f=fixture();assert.equal(validateJournal([f.first,f.last].map(JSON.stringify).join("\n"),f.expected).length,2);
});
test("editing a recorded event without updating its chain is rejected",()=>{
 const f=fixture();f.first.trial_id="OTHER";
 assert.throws(()=>validateJournal([f.first,f.last].map(JSON.stringify).join("\n"),f.expected));
});
test("a rehashed substitute registration or result cannot match the fixed identity",()=>{
 const f=fixture();const {hash,...body}=f.first;
 body.registration_sha256="c".repeat(64);
 assert.throws(()=>validateJournal(JSON.stringify(event(body)),{...f.expected,result_sha256:undefined}));
 assert.throws(()=>validateJournal([f.first,f.last].map(JSON.stringify).join("\n"),{...f.expected,result_sha256:"d".repeat(64)}));
});
test("missing completion, extra attempt and swapped stages cannot be certified",()=>{
 const f=fixture();assert.throws(()=>validateJournal(JSON.stringify(f.first),f.expected));
 assert.throws(()=>validateJournal([f.first,f.last,f.last].map(JSON.stringify).join("\n"),f.expected));
 assert.throws(()=>validateJournal([f.last,f.first].map(JSON.stringify).join("\n"),f.expected));
});
