"use strict";
// Synthetic engineering fixtures only. No broker, model training or financial claim.
const test = require("node:test"), assert = require("node:assert/strict");
const fs = require("node:fs"), path = require("node:path");
const APP = path.resolve(__dirname, "..");
const BUILD = process.env.HARPOON_SESSION_RUNTIME || path.join(APP, "runtime30");
const { Plugins } = require(path.join(BUILD, "plugins.js"));
const { sessionContext, regularClosedBars, openingRange, streakDiagnostics } = require(path.join(BUILD, "sessions.js"));
const MS5 = 300000;
const forbidNetwork = () => { throw Error("NETWORK_FORBIDDEN_IN_SESSION_REGRESSION"); };

function session(date="2026-10-15", close="20:00:00Z", open="13:30:00Z") {
  return { date, open: Date.parse(date+"T"+open), close: Date.parse(date+"T"+close) };
}
function bar(at, fields={}) {
  return {t:new Date(at).toISOString(),o:100,h:101,l:99,c:100.5,v:1000,vw:100.1,...fields};
}
function fixture({premarket=false, currentCount=4, omit=[], duplicate=false, calendar=true}={}) {
  const cfg=JSON.parse(fs.readFileSync(path.join(APP,"config/examples/xxx.json"),"utf8"));
  cfg.universe=cfg.universe.filter(x=>x.symbol==="AAPL"); cfg.enabledPlugins=[]; cfg.optionUnderlyings=[];
  // The signal-only VM captures the guard; do not leave a global mutation for other suites.
  const previousFetch=global.fetch;
  let p;
  try { global.fetch=forbidNetwork; p=new Plugins({},cfg); }
  finally { global.fetch=previousFetch; }
  const current=session(), prior=[], daily=[], calendarRows=[current];
  const now=current.open+currentCount*MS5+5000;
  for(let day=1;daily.length<21;day++) {
    const date=new Date(current.open-day*86400000);
    if([0,6].includes(date.getUTCDay())) continue;
    const name=date.toISOString().slice(0,10), s=session(name);
    calendarRows.push(s);
    daily.push(bar(s.open,{o:99,h:101,l:98,c:100,v:100000,vw:99.8}));
    for(let n=0;n<78;n++) prior.push(bar(s.open+n*MS5,{o:99+n*.01,h:100+n*.01,l:98.8+n*.01,c:99.5+n*.01,vw:99.4+n*.01}));
  }
  const values=[
    {o:100,h:100.6,l:99.9,c:100.4,vw:100.2,v:1000},
    {o:100.4,h:100.9,l:100.3,c:100.7,vw:100.6,v:1100},
    {o:100.7,h:101.2,l:100.6,c:101,vw:100.9,v:1200},
    {o:101,h:101.3,l:100.9,c:101.1,vw:101.1,v:1300},
    {o:101.1,h:101.4,l:100.9,c:101.2,vw:101.1,v:1400},
    {o:101.2,h:101.5,l:101,c:101.3,vw:101.2,v:1500},
  ];
  const regular=values.slice(0,currentCount).map((v,n)=>bar(current.open+n*MS5,v)).filter((_,n)=>!omit.includes(n));
  if(duplicate) regular.push({...regular[1]});
  const raw=[...prior,...(premarket?[bar(current.open-90*60000,{o:90,h:96,l:89,c:95,vw:93,v:50000})]:[]),...regular];
  const quote={ask:101.25,bid:101.2,at:now,received:now};
  const m={bars:{AAPL:raw,SPY:[...raw]},daily:{AAPL:daily},quotes:{AAPL:quote},calendar:calendar?calendarRows:[]};
  return {p,m,now,current,regular,prior};
}

test("premarket cannot change regular opening fields or opening-range eligibility",()=>{
  const a=fixture(), b=fixture({premarket:true});
  const fa=a.p.features(a.m,a.now)[0], fb=b.p.features(b.m,b.now)[0];
  assert(fa&&fb);
  for(const k of ["opening_high","session_change","dollar_volume","rvol","momentum_bps","vwap_distance"])
    assert.equal(fa[k],fb[k],k);
  assert.equal(fa.opening_high,101.2); assert(Math.abs(fa.session_change-.0125)<1e-12);
  const recipe={family:"opening_range",min_rvol:0,momentum_bps:0};
  assert.equal(a.p.legacy.HPEntry.eligible(fa,recipe,0,.001),true);
  assert.equal(b.p.legacy.HPEntry.eligible(fb,recipe,0,.001),true);
  assert.equal(fb.session_context.calendar_verified,true);
});

test("missing first opening bar cannot fabricate opening range or session anchor",()=>{
  const f=fixture({currentCount:5,omit:[0]});
  const row=f.p.features(f.m,f.now)[0]; assert(row);
  assert.equal(row.opening_high,null);assert.equal(row.session_change,null);
  assert.equal(row.streak_diagnostics.first_regular_bar_observed,false);
});

test("a missing middle opening bar is not replaced by a later bar",()=>{
  const f=fixture({currentCount:5,omit:[1]});
  const row=f.p.features(f.m,f.now)[0]; assert(row);
  assert.equal(row.opening_high,null);
  assert.equal(f.p.legacy.HPEntry.eligible(row,{family:"opening_range",min_rvol:0,momentum_bps:0},0,.001),false);
});

test("duplicate bar timestamps are ambiguous and do not complete opening range",()=>{
  const f=fixture({currentCount:5,duplicate:true});
  const row=f.p.features(f.m,f.now)[0];assert(row);assert.equal(row.opening_high,null);
});

test("incomplete and future bars remain unavailable through inherited close buffer",()=>{
  const s=session(), bars=[bar(s.open),bar(s.open+MS5),bar(s.open+2*MS5)];
  assert.equal(regularClosedBars(bars,s.open+MS5+2999,[s]).length,0);
  assert.equal(regularClosedBars(bars,s.open+MS5+3000,[s]).length,1);
  assert.equal(regularClosedBars(bars,s.open+MS5+5000,[s]).length,1);
});

test("explicit delayed availability cannot be used before receipt",()=>{
  const s=session(), at=s.open+MS5+5000;
  const bars=[bar(s.open,{known_at:new Date(at+10000).toISOString()})];
  assert.equal(regularClosedBars(bars,at,[s]).length,0);
  assert.equal(regularClosedBars(bars,at+10000,[s]).length,1);
  assert.equal(regularClosedBars([bar(s.open,{known_at:"invalid"})],at,[s]).length,0);
  assert.equal(regularClosedBars([bar(s.open,{received:at+1})],at,[s]).length,0);
});

test("source timestamps without an explicit timezone cannot establish availability",()=>{
  const s=session(), at=s.open+MS5+5000;
  assert.equal(regularClosedBars([bar(s.open,{known_at:"2026-10-14T09:35:00"})],at,[s]).length,0);
  const local=new Date(s.open), two=x=>String(x).padStart(2,"0");
  const unzoned=`${local.getFullYear()}-${two(local.getMonth()+1)}-${two(local.getDate())}T${two(local.getHours())}:${two(local.getMinutes())}:${two(local.getSeconds())}`;
  assert.equal(Date.parse(unzoned),s.open,"Fixture matches host parsing but carries no source timezone");
  assert.equal(regularClosedBars([bar(s.open,{t:unzoned})],at,[s]).length,0);
  assert.equal(regularClosedBars([bar(s.open,{known_at:"2026-10-15T13:35:00+00:00"})],at,[s]).length,1);
});

test("premarket afterhours and misaligned bars are excluded from regular selection",()=>{
  const s=session(), bars=[bar(s.open-MS5),bar(s.open),bar(s.open+120000),bar(s.close-MS5),bar(s.close),bar(s.close+MS5)];
  const kept=regularClosedBars(bars,s.close+2*MS5+5000,[s]);
  assert.deepEqual(kept.map(b=>Date.parse(b.t)),[s.open,s.close-MS5]);
});

test("early close uses calendar boundary and rejects thirteen-o-clock and later bars",()=>{
  const s=session("2026-11-27","18:00:00Z","14:30:00Z");
  const kept=regularClosedBars([bar(s.open),bar(s.close-MS5),bar(s.close)],s.close+MS5+5000,[s]);
  assert.deepEqual(kept.map(b=>Date.parse(b.t)),[s.open,s.close-MS5]);
  assert.equal(sessionContext(s.close-90*60000,[s]).phase,"PRECLOSE_90");
  assert.equal(sessionContext(s.close,[s]).phase,"POSTCLOSE_90");
});

for(const [label,offset,phase] of [
  ["09:30",0,"OPENING_90"],["10:59:59.999",90*60000-1,"OPENING_90"],
  ["11:00",90*60000,"MID_SESSION"],["14:29:59.999",300*60000-1,"MID_SESSION"],
  ["14:30",300*60000,"PRECLOSE_90"],["16:00",390*60000,"POSTCLOSE_90"],
  ["17:30",480*60000,"CLOSED"],
]) test("session label at exact boundary "+label,()=>{
  const s=session(), c=sessionContext(s.open+offset,[s]);
  assert.equal(c.phase,phase);assert.equal(c.authorizes_orders,false);assert.equal(c.calendar_verified,true);
});

test("calendar omission of a trading date does not invent a holiday session",()=>{
  const previous=session("2026-11-25","21:00:00Z","14:30:00Z"), holiday=Date.parse("2026-11-26T15:30:00Z");
  assert.equal(sessionContext(holiday,[previous]).phase,"CLOSED");
  assert.equal(sessionContext(holiday,[previous]).source,"NO_SESSION");
  assert.equal(regularClosedBars([bar(holiday-MS5-5000)],holiday,[previous]).length,0);
});

test("duplicate or invalid calendar entries fail closed",()=>{
  const s=session(), now=s.open+60000;
  for(const cal of [[s,s],[{...s,close:s.open}],[{...s,open:NaN}]]) {
    assert.equal(sessionContext(now,cal).phase,"UNKNOWN");
    assert.equal(sessionContext(now,cal).calendar_verified,false);
    assert.equal(regularClosedBars([bar(s.open)],now+MS5,cal).length,0);
  }
});

test("legacy time-only fallback is explicit and never authorizes orders",()=>{
  const s=session(), c=sessionContext(s.open,[]);
  assert.equal(c.phase,"OPENING_90");assert.equal(c.calendar_verified,false);
  assert.equal(c.source,"LEGACY_TIME_ONLY_UNVERIFIED");assert.equal(c.authorizes_orders,false);
  assert.equal(sessionContext(Date.parse("2026-10-17T14:00:00Z"),[]).phase,"CLOSED");
  const f=fixture({premarket:true,calendar:false}), row=f.p.features(f.m,f.now)[0];
  assert(row);assert.equal(row.opening_high,101.2);assert.equal(row.session_context.calendar_verified,false);
});

test("NY daylight saving changes UTC opening without a fixed offset",()=>{
  for(const [date,utc] of [["2026-03-06","14:30:00Z"],["2026-03-09","13:30:00Z"],["2026-10-30","13:30:00Z"],["2026-11-02","14:30:00Z"]]) {
    const now=Date.parse(date+"T"+utc), c=sessionContext(now,[]);
    assert.equal(c.open,now,date);assert.equal(c.phase,"OPENING_90",date);
  }
});

test("short-session overlap has one primary label and explicit membership flags",()=>{
  const s=session();s.close=s.open+120*60000;
  const c=sessionContext(s.open+60*60000,[s]);
  assert.equal(c.phase,"OPENING_90");assert.equal(c.opening_window,true);assert.equal(c.preclose_window,true);
});

test("streaks separate observed overnight gap and within-session returns",()=>{
  const s=session(), prev=session("2026-10-14"), old=bar(prev.close-MS5,{c:100});
  const current=[bar(s.open,{o:105,c:106}),bar(s.open+MS5,{o:106,c:107}),bar(s.open+2*MS5,{o:107,c:108})];
  const d=streakDiagnostics(current,[old,...current],sessionContext(s.open+3*MS5+5000,[prev,s]),[prev,s]);
  assert.equal(d.length,2);assert.equal(d.direction,"UP");assert.equal(d.previous_close_complete,true);
  assert(Math.abs(d.overnight_gap-.05)<1e-12);assert(Math.abs(d.intraday_return-(108/105-1))<1e-12);
  assert.equal(d.scope,"DIAGNOSTIC_ONLY_NOT_A_PREDICTOR_INPUT");
});

test("a zero return ends a streak and a missing bar breaks continuity",()=>{
  const s=session(), c=sessionContext(s.open+5*MS5,[s]);
  const zero=[bar(s.open,{c:101}),bar(s.open+MS5,{c:102}),bar(s.open+2*MS5,{c:102})];
  const dz=streakDiagnostics(zero,zero,c,[s]);assert.equal(dz.direction,"FLAT");assert.equal(dz.length,0);
  const gap=[bar(s.open,{c:101}),bar(s.open+2*MS5,{c:102}),bar(s.open+3*MS5,{c:103})];
  assert.equal(streakDiagnostics(gap,gap,c,[s]).length,1);
  assert.equal(streakDiagnostics(gap.slice(0,2),gap,c,[s]).length,null);
});

test("incomplete prior close is not silently presented as overnight gap",()=>{
  const s=session(), prev=session("2026-10-14"), old=bar(prev.open,{c:100}), current=[bar(s.open,{o:105,c:106})];
  const d=streakDiagnostics(current,[old,...current],sessionContext(s.open+MS5+5000,[prev,s]),[prev,s]);
  assert.equal(d.previous_close_complete,false);assert.equal(d.overnight_gap,null);
  assert(Math.abs(d.gap_to_previous_observed_regular_bar-.05)<1e-12);
});

test("relative momentum requires benchmark timestamps and continuity to align",()=>{
  const f=fixture({currentCount:5});
  const first=f.p.features(f.m,f.now)[0];assert(first);assert.notEqual(first.relative_bps,null);
  f.m.bars.SPY=f.m.bars.SPY.filter(b=>Date.parse(b.t)!==f.current.open+3*MS5);
  const second=f.p.features(f.m,f.now)[0];assert(second);assert.equal(second.relative_bps,null);
});

test("opening-range helper requires exactly the three bars starting at session open",()=>{
  const s=session(), c=sessionContext(s.open+4*MS5,[s]);
  assert.equal(openingRange([bar(s.open),bar(s.open+2*MS5),bar(s.open+3*MS5)],c),null);
  assert.equal(openingRange([bar(s.open+MS5),bar(s.open+2*MS5),bar(s.open+3*MS5)],c),null);
});
