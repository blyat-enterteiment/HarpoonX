"use strict";
// Synthetic execution/calendar regression cases. No strategy fits or financial trials.
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs"), path = require("node:path");
const { defaultProtocol } = require("../runtime30/ultimate_contracts.js");
const { replayCampaign, planCalendarHolding, UnresolvedHoldingExposureError } = require("../runtime30/ultimate_replay.js");
const { deadlineFor } = require("../runtime30/policy.js");
const HOUR = 3600000, BAR = 300000;
const at = (value) => Date.parse(value);
function session(date, open="13:30", close="20:00") {
  return {date,open:at(date+"T"+open+":00Z"),close:at(date+"T"+close+":00Z")};
}
function fixture(sessions, decision, firstOpen) {
  const bars=sessions.flatMap(s=>{
    const out=[];
    for(let t=s.open;t<s.close;t+=BAR)out.push({t,end:t+BAR,availableAt:t+BAR+3000,o:100,h:100.1,l:99.9,c:100,v:1000});
    return out;
  });
  const series={symbol:"SPY",root:"SPY",pointValue:1,tick:.01,bars};
  const signal={id:"SYNTHETIC-HOLDING",symbol:"SPY",hypothesis:"CLOSED_CHANNEL",direction:1,at:decision,index:bars.findIndex(b=>b.t===firstOpen),stopDistance:10,regime:.4};
  assert(signal.index>=0);
  return {series,signal,data:{schema:"HARPOON-ULTIMATE-DATA-1",kind:"ALPACA_PROXY",sessions,series:[series],splitEvents:[]},protocol:defaultProtocol("ALPACA_PROXY")};
}
function run(f) {return replayCampaign(f.signal,f.series,f.data,f.protocol,"REGIME",4);}
function weekendFixture() {
  return fixture([session("2026-10-15"),session("2026-10-16"),session("2026-10-19")],
    at("2026-10-15T16:00:03Z"),at("2026-10-15T16:05:00Z"));
}
test("Thursday campaign exits Friday before weekend deadline using runtime calendar policy",()=>{
  const f=weekendFixture(),r=run(f);
  assert(r);assert.equal(r.reason,"TIME");
  assert.equal(r.closed,at("2026-10-16T19:50:00Z"));
  assert.equal(r.holdingDeadlineAt,deadlineFor("equity",f.signal.at,72,f.data.sessions));
  assert(r.closed-f.signal.at<=72*HOUR);
});
test("Friday campaign exits Friday when Monday is a holiday, never at Tuesday's open",()=>{
  const f=fixture([session("2026-09-04"),session("2026-09-08")],at("2026-09-04T16:00:03Z"),at("2026-09-04T16:05:00Z"));
  const r=run(f);assert(r);
  assert.equal(r.closed,at("2026-09-04T19:50:00Z"));
  assert(r.closed<f.data.sessions[1].open);
});
test("early close is scheduled from the supplied calendar with the same ten-minute buffer",()=>{
  const f=fixture([session("2026-11-25","14:30","21:00"),session("2026-11-27","14:30","18:00"),session("2026-11-30","14:30","21:00")],
    at("2026-11-25T16:00:03Z"),at("2026-11-25T16:05:00Z"));
  const r=run(f);assert(r);
  assert.equal(r.closed,at("2026-11-27T17:50:00Z"));
  assert(r.closed-f.signal.at<=72*HOUR);
});
test("intrabar wall-clock deadline rounds earlier on the declared five-minute grid",()=>{
  const sessions=["2026-11-02","2026-11-03","2026-11-04","2026-11-05","2026-11-06"].map(d=>session(d,"14:30","21:00"));
  const f=fixture(sessions,at("2026-11-02T15:32:03Z"),at("2026-11-02T15:35:00Z"));
  const r=run(f);assert(r);
  assert.equal(r.closed,at("2026-11-05T15:30:00Z"));
  assert.equal(r.holdingClockStartedAt,f.signal.at);
  assert(r.closed<=f.signal.at+72*HOUR);
});
test("a pending entry arriving at or after the planned deadline is refused before opening",()=>{
  const f=fixture([session("2026-10-15"),session("2026-10-16"),session("2026-10-19")],
    at("2026-10-15T16:00:03Z"),at("2026-10-16T19:50:00Z"));
  const plan=planCalendarHolding(f.signal,f.series.bars[f.signal.index].t,f.data,f.protocol);
  assert.equal(plan.status,"REFUSED_BEFORE_ENTRY");
  assert.equal(plan.positionOpened,false);
  assert.equal(plan.reason,"ENTRY_AT_OR_AFTER_DEADLINE");
  assert.equal(run(f),null);
  f.signal.index=f.series.bars.findIndex(b=>b.t===at("2026-10-16T19:55:00Z"));
  assert.equal(run(f),null);
});
test("an absent calendar refuses entry; no later price is used to invent an exit session",()=>{
  const f=weekendFixture();f.data.sessions=[];
  assert.equal(planCalendarHolding(f.signal,f.series.bars[f.signal.index].t,f.data,f.protocol).status,"REFUSED_BEFORE_ENTRY");
  assert.equal(run(f),null);
});
test("missing deadline bar after an entry throws unresolved exposure instead of skipping or closing late",()=>{
  const f=weekendFixture(),deadline=at("2026-10-16T19:50:00Z");
  f.series.bars=f.series.bars.filter(b=>b.t!==deadline);
  assert.equal(planCalendarHolding(f.signal,f.series.bars[f.signal.index].t,f.data,f.protocol).status,"SCHEDULED");
  assert.throws(()=>run(f),e=>{
    assert(e instanceof UnresolvedHoldingExposureError);
    assert.equal(e.code,"UNRESOLVED_HOLDING_EXPOSURE");
    assert.equal(e.details.deadlineAt,deadline);
    assert.equal(e.details.remainingQuantity,4);
    assert.equal(e.details.openedAt,at("2026-10-15T16:05:00Z"));
    assert.equal(e.details.economicPnlUsd,null);
    const transported=JSON.parse(e.message.slice(e.message.indexOf(": ")+2));
    assert.equal(JSON.stringify(transported),JSON.stringify(e.details));
    assert(e.details.lastKnownMark);
    assert(e.details.encounteredAt>deadline);
    return true;
  });
});
test("production imports remain loadable while the archived report cannot pass a new code seal",()=>{
  const { ResearchLab }=require("../runtime30/ultimate_lab.js");
  const { Validators }=require("../runtime30/validators.js");
  const { DEFAULT_REPLAY_LIMITS }=require("../runtime30/ultimate_replay.js");
  const lab=new ResearchLab({},"SYNTHETIC-SEAL-ONLY",new Validators(),DEFAULT_REPLAY_LIMITS);
  const report=JSON.parse(fs.readFileSync(path.join(__dirname,"../evidence/ultimate/report.json"),"utf8"));
  const registration=JSON.parse(fs.readFileSync(path.join(__dirname,"../evidence/ultimate/registry.json"),"utf8"));
  assert.throws(()=>lab.verifyBundled(report,registration),/bundled report code\/data\/protocol binding/);
  assert.equal(typeof require("../runtime30/server.js").server,"function");
});
test("data ending with an open position cannot turn into a zero-PnL excluded campaign",()=>{
  const f=weekendFixture(),deadline=at("2026-10-16T19:50:00Z");
  f.series.bars=f.series.bars.filter(b=>b.t<deadline);
  assert.throws(()=>run(f),e=>{
    assert(e instanceof UnresolvedHoldingExposureError);
    assert.equal(e.details.reason,"DATA_ENDED_WITH_OPEN_EXPOSURE");
    assert.equal(e.details.remainingQuantity,4);
    assert.equal(e.details.economicPnlUsd,null);
    assert.equal(e.details.encounteredAt,null);
    return true;
  });
});
