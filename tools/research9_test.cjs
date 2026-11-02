"use strict";
const test=require('node:test'),assert=require('node:assert/strict');
const {latest,residualZ,exitReason}=require('../runtime30/research_residual_exit.js');
function fixture(z){
 const meta={stock:'AAPL',stockOpen:100,sectorOpen:100,beta:1,mu:0,sigma:.01,mode:'NORMALIZE'};
 return {signal:{at:0,plannedEntryAt:1,metadata:{researchExit:meta}},data:{series:[
 {symbol:'AAPL',bars:[{t:0,availableAt:2,c:100*Math.exp(z*.01)}]},
 {symbol:'XLK',bars:[{t:0,availableAt:2,c:100}]}],splitEvents:[]}};
}
test('future bar cannot change known mark',()=>{const a=[{t:0,availableAt:2,c:100},{t:1,availableAt:4,c:999}];assert.equal(latest(a,3).c,100);});
test('normalization only at known open after entry',()=>{const {signal,data}=fixture(0);assert.equal(exitReason(signal,data,1),null);assert.equal(exitReason(signal,data,3),'RESEARCH_NORMALIZE');});
test('invalidation retains stop and triggers at frozen boundary',()=>{const {signal,data}=fixture(-4);signal.metadata.researchExit.mode='INVALIDATE';assert.equal(exitReason(signal,data,3),'RESEARCH_INVALIDATE');});
test('unobserved marks are rejected',()=>{const {signal,data}=fixture(0);assert.throws(()=>residualZ(signal.metadata.researchExit,data,1));});
test('unsupported exit cannot silently default',()=>{const {signal,data}=fixture(0);signal.metadata.researchExit.mode='UNKNOWN';assert.throws(()=>exitReason(signal,data,3));});
test('benchmark split with inventory remains an incident',()=>{const {signal,data}=fixture(0);data.splitEvents=[{symbol:'XLK',at:2}];assert.throws(()=>exitReason(signal,data,3),/SPLIT_WITH_OPEN_EXPOSURE/);});
test('overnight open keeps native stops until a fresh residual is known',()=>{const {signal,data}=fixture(0);assert.equal(exitReason(signal,data,90000000),null);});
