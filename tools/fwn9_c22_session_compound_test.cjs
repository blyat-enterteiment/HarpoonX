"use strict";
const test=require("node:test"),A=require("node:assert/strict");
const P=require("../runtime30/fwn9_c22_session_compound.cjs");
const utc=x=>Date.parse(x);
const winter={date:"2026-01-15",open:utc("2026-01-15T14:30:00Z"),close:utc("2026-01-15T21:00:00Z")};
const summer={date:"2026-07-15",open:utc("2026-07-15T13:30:00Z"),close:utc("2026-07-15T20:00:00Z")};
const at=utc("2026-01-15T14:35:00Z");
test("C22 DST winter verified NY exchange",()=>{
 const r=P.windowFor({book:"equity",at,calendar:[winter]});
 A.equal(r.eligible,true);
 A.equal(r.window,"RTH_OPEN_30");
 A.equal(r.executionAllowed,false);
});
test("C22 summer DST and RTH late",()=>{
 const a=P.windowFor({book:"etf",at:utc("2026-07-15T13:35:00Z"),calendar:[summer]});
 const b=P.windowFor({book:"etf",at:utc("2026-07-15T19:15:00Z"),calendar:[summer]});
 A.equal(a.window,"RTH_OPEN_30");
 A.equal(b.window,"RTH_LAST_90");
});
