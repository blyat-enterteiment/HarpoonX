"use strict";
// Signal-only module loader. It does not instantiate, connect or arm any legacy executor.
const fs = require("node:fs"),
  path = require("node:path"),
  vm = require("node:vm"),
  { webcrypto } = require("node:crypto");
const SIGNAL_MODULES = [
  "defaults",
  "contract",
  "plugins/securities_rules",
  "canonical",
  "plugins/catalog",
  "tensor_core",
  "xii_core",
  "x_core",
  "xi_core",
  "plugins/securities_entries",
  "lab_rules",
  "core",
  "crypto_core",
  "plugins/crypto_recovery",
  "plugins/astra",
  "plugin_registry",
  "warroom3",
  "io",
  "engine",
  "x_engine",
  "crypto_tape",
];
function create() {
  const context = vm.createContext({
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
    ArrayBuffer,
    TextEncoder,
    TextDecoder,
    crypto: webcrypto,
    setTimeout,
    clearTimeout,
    performance,
    URL,
    URLSearchParams,
    AbortController,
    fetch,
    WebSocket,
  });
  for (const name of SIGNAL_MODULES)
    vm.runInContext(
      fs.readFileSync(path.join(__dirname, "../src", name + ".js"), "utf8"),
      context,
      { filename: name + ".js" },
    );
  return vm.runInContext(
    `({catalog:()=>[...HXX.builtins(),...HAstra.manifests(),...HWarRoom3.RECIPES.map(r=>HWarRoom3.plugin(r.id))],
    CryptoTape,MarketStream,HWarRoom3,HC19,HPRecovery,HAstra,HXX,HX,HXII,HXI,HPSecurities,HPEntry,feature,ny,
    localLevels,localSelected,settings:structuredClone(DEFAULTS)})`,
    context,
  );
}
module.exports = { create, SIGNAL_MODULES };
