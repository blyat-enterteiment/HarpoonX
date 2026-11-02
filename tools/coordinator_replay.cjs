"use strict";
/**
 * OFFLINE, MODELED execution only. This tool invokes the actual compiled
 * Coordinator, Plugins and exit policy. It is never imported by production.
 * A simulated fill is a hypothesis, not an observation from a broker.
 */
const fs = require("node:fs"), path = require("node:path"), crypto = require("node:crypto");
const ROOT = path.resolve(__dirname, "..");
const SCHEMA = "HARPOON_COORDINATOR_REPLAY_1";
const REQUEST_SCHEMA = "HARPOON_COORDINATOR_REPLAY_REQUEST_1";
const TERMINAL = new Set(["filled", "canceled", "rejected", "expired"]);
const BOOKS = ["equity", "etf", "crypto", "options"];
const copy = x => x === undefined ? null : JSON.parse(JSON.stringify(x));
function canonical(x) {
  if (x === null || typeof x !== "object") return JSON.stringify(x);
  if (Array.isArray(x)) return "[" + x.map(canonical).join(",") + "]";
  return "{" + Object.keys(x).filter(k => x[k] !== undefined).sort().map(k => JSON.stringify(k) + ":" + canonical(x[k])).join(",") + "}";
}
const hash = x => crypto.createHash("sha256").update(canonical(x) ?? "null").digest("hex");
const fileHash = name => crypto.createHash("sha256").update(fs.readFileSync(path.join(ROOT, name))).digest("hex");
function need(ok, code) { if (!ok) throw Error(code); }
const finite = x => typeof x === "number" && Number.isFinite(x);
const ms = x => finite(x) && Number.isSafeInteger(x) && x > 0;
const close = (a,b) => Math.abs(a-b) <= 1e-7 * Math.max(1, Math.abs(a), Math.abs(b));
function sourceHashes() {
  const names = ["tools/coordinator_replay.cjs", "runtime/quant_bridge.cjs", "runtime/legacy30.cjs", "runtime/exit_profiles32.cjs"];
  for(const name of ["tools/fixed_predictor_worker.cjs","tools/funded_comparison.cjs"])if(fs.existsSync(path.join(ROOT,name)))names.push(name);
  if(fs.existsSync(path.join(ROOT,"quant/harpoon_quant/fixed_predictor.py")))
    for(const file of fs.readdirSync(path.join(ROOT,"quant/harpoon_quant")).filter(f=>f.endsWith(".py")))names.push("quant/harpoon_quant/"+file);
  if(fs.existsSync(path.join(ROOT,"tools/observation_replay_input.cjs")))names.push("tools/observation_replay_input.cjs");
  for (const [dir,ext] of [["xxx","ts"],["runtime30","js"]])
    for (const file of fs.readdirSync(path.join(ROOT,dir)).filter(f=>f.endsWith("."+ext))) names.push(dir+"/"+file);
  for (const stem of require("../runtime/legacy30.cjs").SIGNAL_MODULES) names.push("src/" + stem + ".js");
  return Object.fromEntries(names.sort().map(name => [name, fileHash(name)]));
}
function validateBar(row, key, decisionAt) {
  const start = Date.parse(row.t), span = {bars:300000,minutes:60000,daily:86400000}[key];
  need(ms(start) && ms(row.known_at) && start + span <= row.known_at && row.known_at <= decisionAt, "BAR_NOT_CLOSED_OR_FUTURE_KNOWLEDGE");
  need([row.o,row.h,row.l,row.c,row.v].every(finite) && row.l > 0 && row.v >= 0 && row.h >= Math.max(row.o,row.c) && row.l <= Math.min(row.o,row.c), "INVALID_BAR");
  if (row.vw !== undefined) need(finite(row.vw) && row.vw > 0, "INVALID_VWAP");
}
function validateRequest(input) {
  need(input && input.schema === REQUEST_SCHEMA, "REPLAY_REQUEST_SCHEMA");
  need(input.mode === "OFFLINE" && input.execution_origin === "MODELED", "OFFLINE_MODELED_REQUIRED");
  need(["SYNTHETIC", "HISTORICAL"].includes(input.data_origin), "DATA_ORIGIN_REQUIRED");
  need(typeof input.id === "string" && input.id.length > 0 && input.id.length <= 200, "REPLAY_ID_REQUIRED");
  need(ms(input.start_at) && finite(input.initial_cash_usd) && input.initial_cash_usd > 0, "INITIAL_ACCOUNT_REQUIRED");
  const cfg = input.config;
  need(cfg && cfg.mode === "paper" && cfg.streaming === false && cfg.nativeProtection === "stop", "SCOPE_REQUIRES_PAPER_STOP_AND_STREAMING_OFF");
  need(typeof cfg.expected_account_id === "string" && cfg.expected_account_id.startsWith("OFFLINE-"), "OFFLINE_ACCOUNT_BINDING_REQUIRED");
  need(cfg.quant?.enabled === false, "PRODUCTION_QUANT_GUARDS_MUST_NOT_BE_OVERRIDDEN");
  need(Array.isArray(cfg.universe) && cfg.universe.length > 0 && cfg.universe.every(i => ["equity","etf","crypto"].includes(i.book) && i.multiplier === 1), "SCOPE_LONG_CASH_EQUITY_ETF_CRYPTO_ONLY");
  need(cfg.exit?.maxHoldHours > 0 && cfg.exit.maxHoldHours <= 72, "HOLD_LIMIT_72H");
  need(Array.isArray(input.calendar) && input.calendar.length > 0 && input.calendar.every(r => typeof r.date === "string" && /^\d\d:\d\d$/.test(r.open) && /^\d\d:\d\d$/.test(r.close)), "EXPLICIT_SESSION_CALENDAR_REQUIRED");
  const model = input.execution_model;
  need(model && model.origin === "MODELED" && model.causal_fills === "STRICTLY_LATER_QUOTE" && model.mark_method === "BID" && model.cancel_mode === "EXPLICIT_CONFIRMATION", "EXPLICIT_EXECUTION_ASSUMPTIONS_REQUIRED");
  for (const key of ["fees_bps_per_side","fee_per_fill_usd","slippage_bps","external_cost_usd"])
    need(finite(model[key]) && model[key] >= 0, "UNKNOWN_COST:" + key);
  if (model.operating_cash_reserve !== undefined) {
    const reserve = model.operating_cash_reserve;
    need(reserve && reserve.method === "FIXED_INITIAL_CASH_RESERVE" &&
      finite(reserve.amount_usd) && reserve.amount_usd >= 0 && reserve.amount_usd <= input.initial_cash_usd &&
      ms(reserve.known_at) && reserve.known_at < input.start_at,
      "OPERATING_RESERVE_MUST_BE_FUNDED_AND_KNOWN_BEFORE_REPLAY");
    need(reserve.amount_usd >= model.external_cost_usd, "OPERATING_RESERVE_INSUFFICIENT_FOR_EXTERNAL_COSTS");
  }
  need(model.ack_latency_ms === 0, "SCOPE_EXPLICIT_ZERO_ACK_LATENCY_ONLY");
  need(typeof model.liquidity_assumption === "string" && model.liquidity_assumption.length > 0, "LIQUIDITY_ASSUMPTION_REQUIRED");
  need(Array.isArray(input.events) && input.events.length > 0 && input.events.length <= 20000, "EVENT_BUDGET");
  let last = input.start_at;
  const ids = new Set();
  for (const e of input.events) {
    need(typeof e.id === "string" && e.id && !ids.has(e.id), "DUPLICATE_OR_MISSING_EVENT_ID"); ids.add(e.id);
    need(ms(e.at) && e.at >= last, "NONCAUSAL_EVENT_ORDER"); last = e.at;
    need(["market", "entries", "evaluate", "reconcile", "manage", "pulse", "cancel_confirm", "restart", "llm_unavailable", "sessions"].includes(e.type), "UNKNOWN_EVENT_TYPE");
    if (e.type === "entries" || e.type === "evaluate") need(BOOKS.includes(e.book), "BOOK_REQUIRED");
    if (e.type === "market") {
      need(Array.isArray(e.quotes), "QUOTES_ARRAY_REQUIRED");
      need(new Set(e.quotes.map(q=>q.symbol)).size===e.quotes.length,"DUPLICATE_QUOTE_IN_EVENT");
      for (const q of e.quotes) {
        need(typeof q.symbol === "string" && q.symbol && ms(q.market_at) && q.market_at <= e.at, "FUTURE_QUOTE");
        if(q.received_at!==undefined)need(ms(q.received_at)&&q.market_at<=q.received_at&&q.received_at<=e.at,"FUTURE_OR_INCONSISTENT_QUOTE_RECEIPT");
        need(finite(q.bid) && q.bid > 0 && finite(q.ask) && q.ask >= q.bid && finite(q.executable_qty) && q.executable_qty >= 0, "INVALID_QUOTE_OR_UNKNOWN_LIQUIDITY");
        need(q.market_at === e.at || e.at - q.market_at <= cfg.quoteAgeMs, "QUOTE_STALE_AT_RECEIPT");
      }
      for (const key of ["bars","minutes","daily"]) for (const rows of Object.values(e[key] || {})) {
        need(Array.isArray(rows), "BARS_ARRAY_REQUIRED");
        let previous = -Infinity;
        for (const row of rows) { validateBar(row,key,e.at); need(Date.parse(row.t) > previous, "BARS_NOT_STRICTLY_ORDERED"); previous = Date.parse(row.t); }
      }
    }
  }
  const variant = input.predictor || {name:"C0",mode:"NATIVE"};
  need(["C0","RIDGE","SVR"].includes(variant.name), "UNKNOWN_PREDICTOR");
  need(variant.mode === "NATIVE" && variant.name === "C0" || variant.mode === "PRECOMPUTED_OFFLINE" || variant.mode === "NUMERICAL_OFFLINE" && variant.name !== "C0", "PREDICTOR_MODE_NOT_SUPPORTED");
  if(variant.mode === "NUMERICAL_OFFLINE"){
    need(variant.external_execution_allowed===false && variant.model && typeof variant.model==="object" && !Array.isArray(variant.model),"FIXED_JSON_MODEL_REQUIRED");
    const modelText=variant.model_json??canonical(variant.model);
    need(typeof modelText==="string"&&Buffer.byteLength(modelText)<=16*1024*1024,"FIXED_MODEL_BYTES_LIMIT");
    need(hash(JSON.parse(modelText))===hash(variant.model),"FIXED_MODEL_TEXT_CONTENT_MISMATCH");
    need(variant.model_hash===crypto.createHash("sha256").update(modelText).digest("hex"),"FIXED_MODEL_HASH_MISMATCH");
    const available=Date.parse(variant.model.available_at);
    need(ms(available)&&available<input.start_at,"FIXED_MODEL_FUTURE_OR_UNAVAILABLE");
    need(variant.name==="RIDGE" && [undefined,"HARPOON_QUANT_CALIBRATION_1"].includes(variant.model.schema) && [undefined,"RIDGE"].includes(variant.model.model_kind)
      || variant.name==="SVR" && variant.model.schema==="HARPOON_QUANT_CALIBRATION_2" && variant.model.model_kind==="SVR_RBF" && variant.model.research_only===true,"FIXED_MODEL_ESTIMATOR_BINDING");
    need(!cfg.quant?.optimizer?.enabled && !cfg.quant?.microstructure?.enabled,"FIXED_INFERENCE_NO_EXTERNAL_MODEL_REGISTRIES");
  }
  if (variant.mode === "PRECOMPUTED_OFFLINE") {
    need(variant.external_execution_allowed === false && Array.isArray(variant.receipts), "RECEIPT_EXTERNAL_EXECUTION_MUST_BE_FALSE");
    need(/^[0-9a-f]{64}$/.test(variant.model_hash || "") && ms(variant.trained_until), "MODEL_PROVENANCE_REQUIRED");
    need(new Set(variant.receipts.map(r=>r.event_id)).size===variant.receipts.length,"DUPLICATE_PREDICTOR_RECEIPT");
    for (const r of variant.receipts) {
      need(typeof r.event_id === "string" && /^[0-9a-f]{64}$/.test(r.request_hash || "") && Array.isArray(r.selected), "RECEIPT_BINDING_REQUIRED");
      const event = input.events.find(e => e.id === r.event_id && e.type === "entries");
      need(event && variant.trained_until < event.at, "FUTURE_MODEL_OR_UNKNOWN_DECISION");
      need(r.receipt_hash === hash({...r,receipt_hash:undefined}), "RECEIPT_HASH_MISMATCH");
      need(r.selected.every(s => typeof s.id === "string" && finite(s.quantity) && s.quantity > 0 && finite(s.robust_net_usd)), "INVALID_PRECOMPUTED_SELECTION");
      need(new Set(r.selected.map(s=>s.id)).size===r.selected.length,"DUPLICATE_PRECOMPUTED_SELECTION");
    }
  }
  return copy(input);
}

class ReplayStore {
  constructor() { this.rows = new Map(); }
  async get(k) { return copy(this.rows.get(k) ?? null); }
  async put(k,v) { this.rows.set(k,copy(v)); return true; }
  async lease() { return true; }
  async scan(prefix,limit=100000) { return [...this.rows].filter(([k])=>k.startsWith(prefix)).sort(([a],[b])=>a.localeCompare(b)).slice(0,limit).map(([,v])=>copy(v)); }
  async close() {}
}

class SimulatedReplayBroker {
  constructor(input, clock) {
    this.origin = "MODELED"; this.input = input; this.clock = clock;
    this.cash = input.initial_cash_usd; this.orders = new Map(); this.inventory = new Map();
    this.quotes = new Map(); this.requests = []; this.fills = []; this.rejected = [];
    this.engine = null; this.nextOrder = 1;
  }
  account() {
    const value = [...this.inventory].reduce((sum,[s,p]) => sum + p.qty * this.quotes.get(s).bid, 0);
    const reserve = this.input.execution_model.operating_cash_reserve;
    // The reserve remains part of initial capital, locked for the whole replay.
    // It reduces spending power; it is not a fee, withdrawal or extra capital.
    const spendable = this.cash - (reserve?.amount_usd ?? 0);
    return {id:this.input.config.expected_account_id,status:"ACTIVE",equity:String(this.cash+value),cash:String(this.cash),buying_power:String(spendable),non_marginable_buying_power:String(spendable),options_buying_power:"0",options_trading_level:0,
      ...(reserve ? {operating_cash_reserve_usd:reserve.amount_usd,operating_reserve_known_at:reserve.known_at} : {})};
  }
  positions() {
    return [...this.inventory].sort(([a],[b])=>a.localeCompare(b)).map(([symbol,p])=>({symbol,qty:String(p.qty),market_value:String(p.qty*this.quotes.get(symbol).bid),avg_entry_price:String(p.avg)}));
  }
  clockResponse() {
    const sessions = this.engine.plugins.legacy.HX.sessions(this.input.calendar);
    const current = sessions.find(s=>s.open<=this.clock.now&&this.clock.now<s.close);
    const next = sessions.find(s=>s.open>this.clock.now);
    const futureClose = current?.close || next?.close;
    need(futureClose, "SESSION_CALENDAR_DOES_NOT_COVER_REPLAY");
    return {timestamp:new Date(this.clock.now).toISOString(),is_open:!!current,next_close:new Date(futureClose).toISOString(),next_open:new Date(next?.open || futureClose+86400000).toISOString()};
  }
  async request(p, method="GET", body, market=false) {
    need(typeof p === "string" && p.startsWith("/") && !p.includes("://"), "EXTERNAL_URL_DENIED");
    this.requests.push({at:this.clock.now,path:p,method,body:copy(body),market,origin:"MODELED"});
    if (p === "/v2/account") return this.account();
    if (p === "/v2/positions") return this.positions();
    if (p === "/v2/clock") return this.clockResponse();
    if (p.startsWith("/v2/calendar?")) return copy(this.input.calendar);
    if (p.startsWith("/v2/assets/")) {
      const symbol=decodeURIComponent(p.split("/").at(-1)), asset=this.input.config.universe.find(a=>a.symbol===symbol);
      need(asset,"UNKNOWN_SIMULATED_ASSET");
      return {symbol,class:asset.book==="crypto"?"crypto":"us_equity",status:"active",tradable:true,min_trade_increment:String(asset.step),min_order_size:String(asset.minQty),price_increment:String(asset.tick)};
    }
    if (p.startsWith("/v2/orders?")) return [...this.orders.values()].filter(o=>!TERMINAL.has(o.status)).map(copy);
    if (p.startsWith("/v2/orders:by_client_order_id")) {
      const id=new URL("https://offline.invalid"+p).searchParams.get("client_order_id"), o=this.orders.get(id);
      if (!o) throw Object.assign(Error("MODELED_ORDER_NOT_FOUND"),{status:404});
      return copy(o);
    }
    if (method === "DELETE" && p.startsWith("/v2/orders/")) {
      const o=[...this.orders.values()].find(o=>o.id===decodeURIComponent(p.split("/").at(-1)));
      need(o,"CANCEL_UNKNOWN_ORDER"); o.cancel_requested_at=this.clock.now;
      // A request ACK is deliberately not a terminal cancel confirmation.
      return null;
    }
    if (p === "/v2/orders" && method === "POST") {
      need(!this.orders.has(body.client_order_id),"DUPLICATE_CLIENT_ORDER_ID");
      need(["limit","market","stop","stop_limit"].includes(body.type) && !body.order_class,"ORDER_TYPE_OUTSIDE_REPLAY_SCOPE");
      const o={...copy(body),id:"modeled-"+this.nextOrder++,status:"new",filled_qty:"0",filled_avg_price:null,created_at:new Date(this.clock.now).toISOString(),created_ms:this.clock.now};
      this.orders.set(o.client_order_id,o); return copy(o);
    }
    throw Error("UNSUPPORTED_OFFLINE_REQUEST:"+method+":"+p);
  }
  confirmCancel(selector) {
    const intent=this.selectIntent(selector), o=this.orders.get(intent.id);
    need(o && o.cancel_requested_at && !TERMINAL.has(o.status),"CANCEL_CONFIRMATION_WITHOUT_PENDING_REQUEST");
    o.status="canceled"; o.canceled_at=new Date(this.clock.now).toISOString();
  }
  selectIntent(selector) {
    need(selector && typeof selector.symbol==="string" && typeof selector.kind==="string","ORDER_SELECTOR_REQUIRED");
    const items=this.engine.state.intents.filter(i=>i.symbol===selector.symbol && i.kind===selector.kind);
    const index=selector.ordinal ?? items.length-1;
    need(Number.isInteger(index) && index>=0 && items[index],"ORDER_SELECTOR_NOT_FOUND"); return items[index];
  }
  quote(eventId, q) {
    const old=this.quotes.get(q.symbol);
    need(!old || q.market_at > old.at,"REGRESSING_OR_DUPLICATE_QUOTE_TIMESTAMP");
    this.quotes.set(q.symbol,{bid:q.bid,ask:q.ask,at:q.market_at,received:q.received_at??this.clock.now});
    let liquidity=q.executable_qty;
    for (const o of this.orders.values()) {
      if (o.symbol!==q.symbol || TERMINAL.has(o.status) || liquidity<=0) continue;
      if (q.market_at<=o.created_ms) continue; // Never execute against the deciding quote/bar.
      const buy=o.side==="buy", price=(buy?q.ask:q.bid)*(1+(buy?1:-1)*this.input.execution_model.slippage_bps/10000);
      if (["stop","stop_limit"].includes(o.type) && q.bid>Number(o.stop_price)) continue;
      if (["limit","stop_limit"].includes(o.type) && (buy?price>Number(o.limit_price):price<Number(o.limit_price))) continue;
      const asset=this.input.config.universe.find(a=>a.symbol===o.symbol), remaining=Number(o.qty)-Number(o.filled_qty);
      let quantity=Math.floor((Math.min(remaining,liquidity)+asset.step*1e-8)/asset.step)*asset.step;
      if (!buy) quantity=Math.min(quantity,this.inventory.get(o.symbol)?.qty || 0);
      if (quantity<asset.minQty) continue;
      this.fill(o,quantity,price,eventId,q); liquidity-=quantity;
    }
  }
  fill(o, qty, price, eventId, q) {
    need(q.market_at>o.created_ms && q.market_at<=this.clock.now,"SAME_TIME_OR_FUTURE_FILL");
    const model=this.input.execution_model, fee=qty*price*model.fees_bps_per_side/10000+model.fee_per_fill_usd;
    const buy=o.side==="buy", current=this.inventory.get(o.symbol)||{qty:0,avg:0};
    need(buy ? this.cash-(model.operating_cash_reserve?.amount_usd??0)>=qty*price+fee : current.qty+1e-9>=qty,"MODELED_CAPITAL_OR_INVENTORY_EXCEEDED");
    const next=current.qty+(buy?qty:-qty);
    this.cash+=(buy?-1:1)*qty*price-fee;
    if (next>1e-9) this.inventory.set(o.symbol,{qty:next,avg:buy?(current.qty*current.avg+qty*price)/next:current.avg});
    else this.inventory.delete(o.symbol);
    const prior=Number(o.filled_qty), total=prior+qty;
    o.filled_avg_price=String((prior*Number(o.filled_avg_price||0)+qty*price)/total);
    o.filled_qty=String(total); o.status=close(total,Number(o.qty))?"filled":"partially_filled";
    this.fills.push({origin:"MODELED",event_id:eventId,client_order_id:o.client_order_id,kind:this.engine.state.intents.find(i=>i.id===o.client_order_id)?.kind,symbol:o.symbol,side:o.side,qty,price,fee_usd:fee,submitted_at:o.created_ms,market_at:q.market_at,received_at:this.clock.now,after_cancel_request:!!o.cancel_requested_at,cash_after:this.cash});
  }
}

let running=false;
async function isolated(clock, callback) {
  need(!running,"CONCURRENT_REPLAY_NOT_SUPPORTED"); running=true;
  const restore=[], originalDate=global.Date;
  const patch=(obj,key,value)=>{const old=obj[key];obj[key]=value;restore.push(()=>{obj[key]=old;});};
  const deny=()=>{throw Error("OFFLINE_REPLAY_EXTERNAL_IO_DENIED");};
  class ReplayDate extends originalDate { constructor(...args){super(...(args.length?args:[clock.now]));} static now(){return clock.now;} }
  patch(global,"Date",ReplayDate); patch(global,"fetch",deny);
  if(global.WebSocket) patch(global,"WebSocket",class {constructor(){deny();}});
  for(const moduleName of ["node:http","node:https"]){const m=require(moduleName);patch(m,"request",deny);patch(m,"get",deny);}
  const net=require("node:net");patch(net,"connect",deny);patch(net,"createConnection",deny);patch(net.Socket.prototype,"connect",deny);
  const cp=require("node:child_process");for(const method of ["spawn","exec","execFile","fork","spawnSync","execFileSync","execSync"])patch(cp,method,deny);
  try{return await callback();}finally{for(const undo of restore.reverse())undo();running=false;}
}

function snapshot(engine,broker,event) {
  const intents=engine.state.intents.map(i=>({id:i.id,symbol:i.symbol,kind:i.kind,at:i.at,status:i.status,cancelAt:i.cancelAt||null,payload:copy(i.payload),order:copy(i.order)}));
  const campaigns=engine.state.campaigns.map(c=>({id:c.id,symbol:c.symbol,book:c.book,plugin:c.plugin,created:c.created,closed:c.closed,closedAt:c.closedAt||null,policy:copy(c.policy),risk:c.risk,peak:c.peak,stop:c.stop,deadline:c.deadline,exitPlan:copy(c.exitPlan),partialEntryRisk:copy(c.partialEntryRisk),evaluation:copy(c.evaluation)}));
  return {event_id:event.id,at:event.at,type:event.type,account:broker.account(),positions:broker.positions(),intents,campaigns,entry_ready:engine.entryReady(),reconcile_error:engine.reconcileError,halt:engine.state.halt,coverage:copy(engine.exitCoverage()),sync_at:engine.syncAt,fill_count:broker.fills.length};
}
function invariantChecks(engine,broker) {
  const {fills}=require("../runtime30/policy.js");
  const expectedCash=broker.input.initial_cash_usd+broker.fills.reduce((n,f)=>n+(f.side==="buy"?-1:1)*f.qty*f.price-f.fee_usd,0);
  need(close(expectedCash,broker.cash),"CASH_IDENTITY_FAILED");
  const rows=[];
  if(engine.syncAt && !engine.reconcileError) for(const c of engine.state.campaigns){
    const expected=fills(c,engine.state.intents).qty, observed=Number(engine.position(c.symbol)?.qty||0);
    need(close(expected,observed),"JOURNAL_POSITION_MISMATCH:"+c.symbol);rows.push({symbol:c.symbol,expected,observed});
  }
  return {cash_identity:{expected:expectedCash,observed:broker.cash},inventory:rows};
}

async function executeReplay(raw) {
  const input=validateRequest(raw), clock={now:input.start_at};
  need(!running,"CONCURRENT_REPLAY_NOT_SUPPORTED");
  // Load trusted module definitions before patching process APIs, so no cached
  // production module retains a reference to a temporary test-only deny hook.
  const {Coordinator}=require("../runtime30/coordinator.js"),bridge=require("../runtime/quant_bridge.cjs");
  const numeric=input.predictor?.mode==="NUMERICAL_OFFLINE"?require("./fixed_predictor_worker.cjs").openFixedPredictor(input.predictor,canonical):null;
  try{return await isolated(clock,async()=>{
    const store=new ReplayStore(),broker=new SimulatedReplayBroker(input,clock);
    const cfg=copy(input.config),variant=input.predictor||{name:"C0",mode:"NATIVE"};
    const decisions=[],snapshots=[],checks=[],ioFailures=[];let restarts=0,currentEvent=null;
    const originalPlan=bridge.plan;
    bridge.plan=async()=>{throw Error("OFFLINE_REPLAY_NUMERICAL_WORKER_NOT_AUTHORIZED");};
    // This adapter is local to the isolated tools invocation. The real worker and
    // its SVR research guards are neither invoked nor modified. Its result is not
    // a broker authorization; there is no transport capable of external orders.
    if(variant.mode==="PRECOMPUTED_OFFLINE"||variant.mode==="NUMERICAL_OFFLINE"){
      cfg.quant={...copy(input.config.quant),enabled:true,discovery:false,microstructure:{enabled:false},optimizer:{enabled:false}};
      bridge.plan=async(e,signals)=>{
        need(e.api?.inner===broker || e.broker?.api===broker || broker.engine===e,"SIMULATED_TRANSPORT_BINDING_LOST");
        const request=bridge.request(e,signals),normalized={...request,config:input.config},requestHash=hash(normalized);
        if(variant.mode==="NUMERICAL_OFFLINE"){
          const calculated=await numeric.evaluate(normalized),receipt=calculated.receipt,plan=calculated.result;
          for(const selected of plan.selected){
            const source=request.signals.find(s=>s.plugin+"|"+s.symbol===selected.id);
            need(source&&finite(selected.quantity)&&selected.quantity>0&&selected.quantity<=source.max_qty&&finite(selected.robust_net_usd),"NUMERICAL_SELECTION_OUTSIDE_REAL_SIGNAL_OR_SIZE");
          }
          need(new Set(plan.selected.map(s=>s.id)).size===plan.selected.length,"DUPLICATE_NUMERICAL_SELECTION");
          decisions.push({event_id:currentEvent.id,request_hash:requestHash,request:copy(normalized),receipt_hash:hash(receipt),numerical_receipt:receipt,model_hash:variant.model_hash,origin:"REEXECUTED_FIXED_JSON_MODEL",external_execution_allowed:false,simulation_selection_allowed:true,original_engine_execution_allowed:plan.execution_allowed});
          // This flag is consumed exclusively by the simulated coordinator.
          // The raw numerical receipt and all externally returned authority flags
          // remain untouched; the SVR production guard is still false.
          return {...plan,execution_allowed:true,reason:"OFFLINE_NUMERICAL_SELECTION_ONLY",decision_inputs:{...plan.decision_inputs,origin:"NUMERICAL_OFFLINE",external_execution_allowed:false}};
        }
        const receipt=variant.receipts.find(r=>r.event_id===currentEvent.id);
        need(receipt && receipt.request_hash===requestHash,"PRECOMPUTED_REQUEST_HASH_MISMATCH");
        for(const selected of receipt.selected){const source=request.signals.find(s=>s.plugin+"|"+s.symbol===selected.id);need(source && selected.quantity<=source.max_qty,"RECEIPT_SELECTION_OUTSIDE_REAL_SIGNAL_OR_SIZE");}
        decisions.push({event_id:currentEvent.id,request_hash:requestHash,request:copy(normalized),receipt_hash:receipt.receipt_hash,external_execution_allowed:false,simulation_selection_allowed:true});
        return {execution_allowed:true,selected:copy(receipt.selected),rejected:{},reason:"OFFLINE_MODELED_RECEIPT_ONLY",model_hash:variant.model_hash,config_hash:hash(input.config),decision_inputs:{origin:"PRECOMPUTED_OFFLINE",external_execution_allowed:false}};
      };
    }
    let engine;
    const initialize=async()=>{
      engine=new Coordinator(store,broker,cfg);broker.engine=engine;
      engine.decisionRunId="offline-"+hash({id:input.id,restarts}).slice(0,20);
      await engine.initialize(true);await engine.market.catalog();
    };
    try{
      await initialize();
      for(const event of input.events){
        currentEvent=event;clock.now=event.at;
        if(event.type==="market"){
          for(const key of ["bars","minutes","daily"])for(const [symbol,rows]of Object.entries(event[key]||{}))engine.market[key][symbol]=copy(rows);
          for(const q of event.quotes){broker.quote(event.id,q);engine.market.quotes[q.symbol]={bid:q.bid,ask:q.ask,at:q.market_at,received:q.received_at??event.at};}
        }else if(event.type==="entries" || event.type==="evaluate"){
          const signals=engine.plugins.evaluate(event.book,engine.market,engine.state.plugins);
          const request=bridge.request(engine,signals);request.config=copy(input.config);
          decisions.push({event_id:event.id,book:event.book,signals:copy(signals),diagnostics:copy(engine.plugins.diagnostics),request_hash:hash(request),request:copy(request),origin:"REAL_PLUGIN_EVALUATION",external_execution_allowed:false});
          if(event.type==="entries")await engine.entries(event.book);
        }else if(event.type==="cancel_confirm")broker.confirmCancel(event.order);
        else if(event.type==="restart"){
          const market={};for(const key of ["quotes","bars","minutes","daily","snapshots","metadata","chains","microData","h4"])market[key]=copy(engine.market[key]);
          await engine.save();engine.plugins.stop();restarts++;await initialize();
          Object.assign(engine.market,market);
        }else if(event.type==="llm_unavailable"){
          try{await global.fetch("https://offline-llm.invalid");}catch(error){ioFailures.push({event_id:event.id,error:String(error),external_request_sent:false});}
          await engine.pulse();
        }else await engine[event.type]();
        checks.push({event_id:event.id,...invariantChecks(engine,broker)});
        snapshots.push(snapshot(engine,broker,event));
      }
      const final=snapshots.at(-1),equity=Number(final.account.equity),accountPnl=equity-input.initial_cash_usd;
      const external=input.execution_model.external_cost_usd;
      const metrics={initial_cash_usd:input.initial_cash_usd,account_equity_final_usd:equity,account_pnl_net_usd:accountPnl,fees_usd:broker.fills.reduce((n,f)=>n+f.fee_usd,0),external_cost_usd:external,economic_pnl_net_usd:accountPnl-external,open_inventory:copy(final.positions),valuation:"BID_MODEL",stale_valuation_symbols:[...broker.inventory.keys()].filter(s=>clock.now-broker.quotes.get(s).at>input.config.quoteAgeMs),realized_pnl_only:false};
      return {candidate:variant.name,decisions,snapshots,order_actions:broker.requests.filter(r=>r.method!=="GET"),fills:copy(broker.fills),invariants:checks,io_failures:ioFailures,metrics,restarts,final_state:final};
    }finally{bridge.plan=originalPlan;engine?.plugins.stop();}
  });}finally{numeric?.close();}
}

function receiptCheck(id,expected,observed){
  const expected_hash=hash(expected),observed_hash=hash(observed),passed=expected_hash===observed_hash;
  return {id,method:"DIRECT_REAL_COORDINATOR_REEXECUTION",expected_hash,observed_hash,passed,mismatches:passed?[]:[id]};
}
async function runReplay(input){
  validateRequest(input);
  const before=sourceHashes(),first=await executeReplay(input),second=await executeReplay(input),after=sourceHashes();
  need(hash(before)===hash(after),"SOURCE_CHANGED_DURING_REPLAY");
  const checks=[receiptCheck("execution_actions",first.order_actions,second.order_actions),receiptCheck("positions_and_exit_state",first.snapshots,second.snapshots),receiptCheck("account_cash_fees_and_costs",first.metrics,second.metrics),receiptCheck("real_plugin_and_receipt_decisions",first.decisions,second.decisions),receiptCheck("causal_fills",first.fills,second.fills)];
  const eventTypes=new Set(input.events.map(e=>e.type)),components=["Coordinator.initialize","Coordinator.reconcile"];
  if(eventTypes.has("evaluate")||eventTypes.has("entries"))components.push("Plugins.evaluate");
  if(eventTypes.has("entries"))components.push("Coordinator.entries");
  if(eventTypes.has("manage")||eventTypes.has("pulse")||eventTypes.has("llm_unavailable"))components.push("Coordinator.manage");
  if(eventTypes.has("pulse")||eventTypes.has("llm_unavailable"))components.push("Coordinator.pulse");
  if(first.fills.length&&components.includes("Coordinator.manage"))components.push("policy.exitDecision","exits");
  const scope={components,books:[...new Set(input.config.universe.map(a=>a.book))],native_protection:"stop",inventory:"LONG_ONLY_CASH",execution_model:"EXPLICIT_MODELED_CROSSING_AND_LIQUIDITY",entry_predictor:input.predictor?.mode||"NATIVE_C0",restart_count:first.restarts,event_types:[...eventTypes].sort(),observation_adapter:input.source_evidence||null,not_covered:["live_broker_execution","queue_priority","hidden_liquidity","options","native_oco","shorts","production_scheduler_concurrency","empirical_model_edge","exhaustive_multiasset_parity"]};
  const numerical=first.decisions.filter(d=>d.origin==="REEXECUTED_FIXED_JSON_MODEL");
  const predictorVerified=(input.predictor?.mode||"NATIVE")==="NATIVE" || input.predictor?.mode==="NUMERICAL_OFFLINE" && numerical.some(d=>d.numerical_receipt.forecast_checks.some(f=>f.status==="COMPUTED")) && checks.every(c=>c.passed);
  const report={schema:SCHEMA,id:input.id,input_hash:hash(input),source_hashes:before,execution_origin:"MODELED",data_origin:input.data_origin,scope,scope_hash:hash(scope),checks,policy_parity_verified:checks.every(c=>c.passed),parity_interpretation:"Same real source reexecuted against the same bounded event contract; determinism and state equivalence, not independent financial validation.",predictor_parity_verified:predictorVerified,external_execution_allowed:false,financial_acceptance_allowed:false,advantage_verdict:"VENTAJA_NO_DEMOSTRADA",period:{start_at:input.start_at,end_at:input.events.at(-1).at},result:first,limitations:["All fills, fees, acknowledgements and cancellations are explicitly MODELED.","Two deterministic executions share source and inputs; this is not an independent audit.","Precomputed predictor receipts verify binding and causality, not predictor training or numerical provenance.","NUMERICAL_OFFLINE reproduces the real bridge with fixed JSON models; it does not certify training provenance or empirical edge.","No inference of liquidity, order queue or execution speed from bars.","Outstanding inventory remains marked; no artificial terminal close or capital reset." ]};
  report.artifact_hash=hash(report);return report;
}
async function verifyReport(input,report){
  const mismatches=[];
  if(report?.schema!==SCHEMA)mismatches.push("schema");
  if(report?.artifact_hash!==hash({...report,artifact_hash:undefined}))mismatches.push("artifact_hash");
  if(report?.input_hash!==hash(input))mismatches.push("input_hash");
  if(hash(report?.source_hashes)!==hash(sourceHashes()))mismatches.push("source_hashes");
  const reproduced=await runReplay(input);
  for(const key of ["scope","checks","result","policy_parity_verified","predictor_parity_verified","external_execution_allowed","financial_acceptance_allowed"])
    if(hash(report?.[key])!==hash(reproduced[key]))mismatches.push(key);
  return {schema:"HARPOON_COORDINATOR_REPLAY_VERIFICATION_1",verified:mismatches.length===0,mismatches,input_hash:hash(input),observed_artifact_hash:report?.artifact_hash||null,expected_artifact_hash:reproduced.artifact_hash,external_execution_allowed:false,financial_acceptance_allowed:false};
}
async function compareReplays(inputs){
  need(Array.isArray(inputs)&&inputs.length>=2&&inputs.length<=3,"COMPARE_REQUIRES_TWO_OR_THREE_VARIANTS");
  const common=x=>({...x,id:undefined,predictor:undefined}),commonHash=hash(common(inputs[0]));
  need(inputs.every(x=>hash(common(x))===commonHash),"COMPARISON_POLICY_COSTS_UNIVERSE_OR_EVENTS_DIFFER");
  const names=inputs.map(x=>x.predictor?.name||"C0");need(new Set(names).size===names.length,"DUPLICATE_COMPARISON_CANDIDATE");
  const reports=[];for(const input of inputs)reports.push(await runReplay(input));
  return {schema:"HARPOON_COORDINATOR_COMPARISON_1",common_input_hash:commonHash,execution_origin:"MODELED",changed_dimension:"PREDICTOR_ONLY",reports,financial_acceptance_allowed:false,external_execution_allowed:false,dictamen:"VENTAJA_NO_DEMOSTRADA"};
}

async function main(argv){
  const args={};for(let i=0;i<argv.length;i+=2){need(["--input","--output","--verify"].includes(argv[i])&&argv[i+1],"USAGE: --input request.json --output result.json [--verify result.json]");args[argv[i]]=argv[i+1];}
  need(args["--input"]&&args["--output"],"INPUT_AND_OUTPUT_REQUIRED");
  const input=JSON.parse(fs.readFileSync(args["--input"],"utf8"));
  const result=args["--verify"]?await verifyReport(input,JSON.parse(fs.readFileSync(args["--verify"],"utf8"))):await runReplay(input);
  fs.mkdirSync(path.dirname(path.resolve(args["--output"])),{recursive:true});fs.writeFileSync(args["--output"],JSON.stringify(result,null,2)+"\n");
  process.stdout.write(JSON.stringify({schema:result.schema,output:path.resolve(args["--output"]),verified:result.verified??result.policy_parity_verified,financial_acceptance_allowed:false})+"\n");
  if(result.verified===false)process.exitCode=2;
}
module.exports={SCHEMA,REQUEST_SCHEMA,canonical,hash,sourceHashes,validateRequest,SimulatedReplayBroker,executeReplay,runReplay,verifyReport,compareReplays};
if(require.main===module)main(process.argv.slice(2)).catch(error=>{process.stderr.write(String(error)+"\n");process.exitCode=1;});
