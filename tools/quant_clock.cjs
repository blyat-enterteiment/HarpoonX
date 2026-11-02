'use strict';
// Test clock only. Explicit market-open anchor; production never imports this file.
// Suites whose protocol cutoff is later may select a later explicit test date.
// This changes only the synthetic clock, never the historical-availability gate.
const Original=global.Date,anchor=Original.parse(process.env.HARPOON_TEST_CLOCK_ANCHOR || '2026-10-15T15:00:00Z'),start=performance.now();
if(!Number.isFinite(anchor))throw Error('Invalid HARPOON_TEST_CLOCK_ANCHOR');
const now=()=>anchor+Math.floor(performance.now()-start);
class TestDate extends Original { constructor(...args){if(args.length)super(...args);else super(now());} static now(){return now();} }
global.Date=TestDate;
