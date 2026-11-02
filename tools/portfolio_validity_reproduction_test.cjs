"use strict";
const test=require("node:test"),assert=require("node:assert/strict");
const {serializeResult}=require("./verify_portfolio_validity_study.cjs");
test("optional undefined JS target has the same persisted JSON representation as an absent target",()=>{
 assert.equal(serializeResult({signal:{id:"S",target:undefined},pnl:91.28}),serializeResult({signal:{id:"S"},pnl:91.28}));
});
test("an unknown null financial amount cannot disappear during reproduction",()=>{
 assert.notEqual(serializeResult({pnl:null}),serializeResult({}));
});
test("nonfinite financial values are rejected instead of normalized to unknown",()=>{
 for(const v of [NaN,Infinity,-Infinity])assert.throws(()=>serializeResult({pnl:v}),/Nonfinite/);
});
test("changed profit, risk, order sequence or numeric type changes the compared bytes",()=>{
 const original=serializeResult({pnl:91.28,risk:50,orders:["a","b"]});
 for(const v of [{pnl:91.29,risk:50,orders:["a","b"]},{pnl:91.28,risk:51,orders:["a","b"]},
  {pnl:91.28,risk:50,orders:["b","a"]},{pnl:"91.28",risk:50,orders:["a","b"]}])assert.notEqual(serializeResult(v),original);
});
