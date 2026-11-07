"use strict";
const test = require("node:test"), assert = require("node:assert/strict");
const {terminalTimeline} = require("../runtime30/replay_chronology.cjs");

test("late TIME mark cannot overwrite a known liquidation or its peak", () => {
  const raw = [{at:10,pnl:2},{at:31,pnl:500},{at:30,pnl:-3}];
  const snapshot = structuredClone(raw), result = terminalTimeline(raw,30,-3);
  assert.deepEqual(raw,snapshot);
  assert.deepEqual(result.marks,[{at:10,pnl:2},{at:30,pnl:-3}]);
  assert.equal(result.peak,2);
  assert.equal(result.lateNonterminalMarks,1);
});
test("delayed intrabar exit remains unknown until receipt", () => {
  const result = terminalTimeline([{at:10,pnl:2},{at:31,pnl:-3}],31,-3);
  assert.equal(result.marks.at(-1).at,31);
  assert.equal(result.marks.findLast(m=>m.at<=30).pnl,2);
});
test("terminal receipt supersedes conflicting marks at the same timestamp", () => {
  assert.deepEqual(terminalTimeline([{at:10,pnl:2},{at:30,pnl:8}],30,7).marks,
    [{at:10,pnl:2},{at:30,pnl:7}]);
});
test("reject invalid numbers and earlier unexplained temporal inversions", () => {
  assert.throws(()=>terminalTimeline([{at:10,pnl:NaN}],20,0),/INVALID_CAMPAIGN/);
  assert.throws(()=>terminalTimeline([{at:11,pnl:0},{at:10,pnl:0}],20,0),/NONTERMINAL_MARK_ORDER/);
});
test("changes after terminal receipt cannot change prior observable marks", () => {
  const a=terminalTimeline([{at:10,pnl:2},{at:31,pnl:5},{at:30,pnl:1}],30,1);
  const b=terminalTimeline([{at:10,pnl:2},{at:31,pnl:1e9},{at:30,pnl:1}],30,1);
  assert.deepEqual(a,b);
});
