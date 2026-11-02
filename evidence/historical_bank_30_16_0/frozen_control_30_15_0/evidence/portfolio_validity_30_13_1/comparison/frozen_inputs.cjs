"use strict";
const fs=require("node:fs"),path=require("node:path"),crypto=require("node:crypto"),assert=require("node:assert/strict");
const sha=bytes=>crypto.createHash("sha256").update(bytes).digest("hex");
const fileHash=file=>sha(fs.readFileSync(file));
function loadBaseline(app){
  app=path.resolve(app);
  const read=relative=>JSON.parse(fs.readFileSync(path.join(app,relative),"utf8"));
  const report=read("evidence/ultimate/report.json"),registered=read("evidence/ultimate/protocol.json"),protocol=registered.protocol;
  const rawBytes=fs.readFileSync(path.join(app,"evidence/tp32/prepared.json")),raw=JSON.parse(rawBytes);
  const sourceFiles=raw.fingerprints.map(f=>({name:f.path,sha256:f.sha256}));
  const expectedPrepared=report.source.files.find(f=>f.name==="evidence/tp32/prepared.json");
  assert(expectedPrepared,"Retained prepared source reference absent");
  assert.equal(sha(rawBytes),expectedPrepared.sha256,"Prepared bytes changed");
  const data={schema:"HARPOON-ULTIMATE-DATA-1",kind:"ALPACA_PROXY",
    provenance:{source:"RETAINED_OBSERVED_ALPACA_BARS_REUSED_HISTORY",feed:"SIP",execution:"MODELED_OHLCV",files:[...sourceFiles,{name:"evidence/tp32/prepared.json",sha256:sha(rawBytes)}]},
    sessions:raw.calendar,
    splitEvents:raw.splits.filter(s=>protocol.universe.includes(s.symbol)).map(s=>({symbol:s.symbol,at:raw.calendar.find(d=>d.date===s.ex_date)?.open??Date.parse(s.ex_date+"T13:30:00Z"),ratio:Number(s.new_rate)/Number(s.old_rate)})),
    series:protocol.universe.map(symbol=>({symbol,root:symbol,pointValue:1,tick:.01,bars:raw.series[symbol].map(b=>({t:b[0],end:b[0]+300000,availableAt:b[0]+303000,o:b[1],h:b[2],l:b[3],c:b[4],v:b[5],...(b[6]?{vw:b[6]}:{})}))}))};
  const {digest}=require(path.join(app,"runtime30/ultimate_contracts.js"));
  assert.equal(digest(protocol),report.protocolHash,"Protocol changed");
  assert.equal(digest(data),report.datasetHash,"Dataset changed");
  assert.equal(registered.registeredAt,report.registeredAt,"Registration changed");
  return {app,report,registered,protocol,data,digest,preparedSha256:sha(rawBytes)};
}
module.exports={sha,fileHash,loadBaseline};
