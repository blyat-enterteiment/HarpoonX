"use strict";
const fs = require("node:fs"),
  path = require("node:path"),
  vm = require("node:vm");
const MODULES = [
  "defaults",
  "contract",
  "plugins/securities_rules",
  "canonical",
  "plugins/catalog",
  "xiii_core",
  "tensor_core",
  "xii_core",
  "x_core",
  "xi_core",
  "xi_replay",
  "plugins/securities_entries",
  "lab_rules",
  "core",
  "x_research",
  "lab_core",
  "xii_research",
  "xiii_research",
];
function context() {
  const c = vm.createContext({
    console,
    Intl,
    Date,
    Set,
    Map,
    Math,
    JSON,
    Number,
    structuredClone,
    Uint8Array,
    TextEncoder,
    TextDecoder,
  });
  for (const name of MODULES)
    vm.runInContext(
      fs.readFileSync(path.join(__dirname, "../src", name + ".js"), "utf8"),
      c,
      { filename: name + ".js" },
    );
  return c;
}
function fitRows(rows, cutoff) {
  const c = context();
  c.rows = rows;
  c.cutoff = cutoff;
  return vm.runInContext("HXII.fitSelector(rows,cutoff)", c);
}
function evaluate(input) {
  const c = context();
  c.input = input;
  return vm.runInContext(
    `(()=>{
    const report=xiiCompare(input);
    const prepared=Object.keys(input.sessions).length>=40 && input.samples.length>=240 ? labReplay(input) : {rows:[],invalid:[]};
    const labels=prepared.rows.filter(r=>r.outcomes[1]?.filled&&HLab.eligible(r.feature,input.trial.reference,input.cfg.breakout_pct,input.cfg.chase_pct))
      .map(r=>{const lv=localLevels(r.feature,{...input.cfg,profile:HLab.profile(input.trial.reference)});return {at:Date.parse(r.at),end:Date.parse(r.end_at),day:r.day,feature:r.feature,target:r.outcomes[1].return*lv.limit/lv.risk_unit};});
    const cutoff=Object.values(input.sessions).length?Math.max(...Object.values(input.sessions).map(s=>s.close)):Date.now();
    const diagnosticFit=labels.length>=240?HXII.fitSelector(labels,cutoff):null;
    return {schema:"HARPOON-SELECTOR-30-1",report,diagnosticFit,trainingLabels:labels.length,invalidLabels:prepared.invalid.length,
      source:input.source,prospectiveVerified:input.prospectiveVerified,scope:"PAPER experiment; replay estimates and selector fit are not audited trading returns"};
  })()`,
    c,
    { timeout: 55000 },
  );
}
module.exports = {
  MODULES,
  evaluate,
  fitRows,
  contract: "HARPOON-SELECTOR-30-1",
};
