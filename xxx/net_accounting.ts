import { createHash } from "node:crypto";
import { performance } from "node:perf_hooks";
import { CostReceiptError, LocalCostReceiptSource, validateCostReceipt, verifyBrokerAccrualCoverage } from "./cost_receipts";
import { NetArchiveError, NetLedgerArchive } from "./net_ledger_archive";
import { verifyLedgerHistoryBundle } from "./net_ledger_verify";
import { Api, Json, Store } from "./types";

/**
 * Read-only account accounting. Broker NAV already contains execution prices,
 * fees reported in cash, and open-position marks: do not subtract them twice.
 * A single Store.put commits the journal and its watermark together. Store must
 * provide atomic replacement (the production SQLite Store does); leases and a
 * revision check prevent a stale writer from replacing a newer journal.
 *
 * Source transport/receipt hashes establish reproducibility, not authenticity.
 * API snapshots have local receipt times, not synchronized market timestamps.
 */
const SCHEMA = "HARPOON_NET_LEDGER_1";
const DAY = 86_400_000;
const COST_CATEGORIES = ["DATA", "INFRASTRUCTURE", "INFERENCE", "OTHER"];
const inProcessWriters = new WeakMap<Store, Set<string>>();
type Classification = "FILL" | "EXTERNAL_FLOW" | "ACCOUNT_CASH" | "FEE" | "BASELINE_INCLUDED";

interface LedgerPolicy {
  currency: "USD";
  pageSize: number;
  maxPages: number;
  maxActivities: number;
  maxObservations: number;
  maxStateBytes: number;
  maxSnapshotSpanMs: number;
  maxAgeMs: number;
  cashToleranceUsd: number;
  navToleranceUsd: number;
  quantityTolerance: number;
  performanceIntervalMs: number;
  performanceToleranceMs: number;
  fillCashBasis: "GROSS_PLUS_SEPARATE_ACTIVITY_FEES";
}
interface Position {
  symbol: string;
  quantity: number;
  marketValueUsd: number;
  multiplier: number;
  currency: "USD";
  sourceHash: string;
}
interface Snapshot {
  at: number;
  equity: number;
  cash: number;
  positions: Position[];
  sourceHash: string;
  marketTimestamp: number | null;
  receiptSpanMs: number;
  sourceReceipt: Json;
}
interface Activity {
  id: string;
  activityType: string;
  classification: Classification;
  at: number | null;
  date: string | null;
  timePrecision: "INSTANT" | "DAY" | "UNKNOWN";
  knownAt: number;
  currency: string | null;
  cashDeltaUsd: number | null;
  quantityDelta: number | null;
  multiplier: number | null;
  symbol: string | null;
  orderId: string | null;
  baselineIncluded: boolean;
  rawHash: string;
  raw: Json;
}
interface Cost {
  id: string;
  at: number;
  known_at: number;
  amount_usd: number;
  reference: string;
  category: string;
  already_in_account: boolean;
  activity_id: string | null;
  rawHash: string;
}
interface CostCoverage {
  from: number;
  through: number;
  known_at: number;
  reference: string;
  categories: string[];
  sourceHash: string;
  basis: "DECLARED_COST_COVERAGE_NOT_INDEPENDENTLY_ATTESTED";
}
interface PreFlowMark {
  activityId: string;
  at: number;
  known_at: number;
  equityBefore: number;
  equityAfter: number;
  reference: string;
  evidenceHash: string;
  evidence: Json;
  basis: "CALLER_SUPPLIED_PRE_FLOW_EVIDENCE_NOT_INDEPENDENTLY_ATTESTED";
}
interface Observation extends Snapshot {
  activitiesThrough: number;
  externalFlowUsd: number;
  cumulativeExternalFlowUsd: number;
  externalCostUsd: number | null;
  cumulativeExternalCostUsd: number | null;
  economicEquity: number | null;
  accountReturn: number | null;
  economicReturn: number | null;
  returnStatus: string;
  preFlowMarks: PreFlowMark[];
  activityIds: string[];
  costCoverageHash: string | null;
  economicKnownAt: number | null;
}
interface LedgerState {
  schema: string;
  accountId: string;
  policyHash: string;
  revision: number;
  status: string;
  lastAttempt: number | null;
  lastSuccess: number | null;
  persisted: boolean;
  reconciled: boolean;
  economicComplete: boolean;
  returnComplete: boolean;
  blockers: string[];
  queryFrom: number | null;
  baseline: Snapshot | null;
  activities: Activity[];
  externalCosts: Cost[];
  costCoverage: CostCoverage | null;
  observations: Observation[];
  accounting: Json;
  closedEconomic: Json;
  reconciliation: Json;
  coverage: Json;
  insolvency: { account: boolean; economic: boolean; firstObservedAt: number | null };
  lastFailure: Json | null;
  evidence: Json;
  integrity: string;
  archiveIndex?: Json;
  costSource?: Json;
  economicRestatementRequired?: boolean;
  brokerAccrualCoverage?: Json | null;
  brokerAccrualLinkedCosts?: Json[];
}

export class NetLedgerError extends Error {
  constructor(public readonly code: string, public readonly detail: Json = {}) {
    super(code);
    this.name = "NetLedgerError";
  }
}

function fail(code: string, detail: Json = {}): never { throw new NetLedgerError(code, detail); }
function object(value: unknown, code: string): Json {
  if (value === null || typeof value !== "object" || Array.isArray(value)) fail(code);
  return value as Json;
}
function finite(value: unknown, code: string): number {
  if ((typeof value !== "number" && typeof value !== "string") ||
      (typeof value === "string" && !value.trim())) fail(code);
  const n = Number(value);
  if (!Number.isFinite(n)) fail(code);
  return n;
}
function positive(value: unknown, code: string): number {
  const n = finite(value, code);
  if (n <= 0) fail(code);
  return n;
}
function text(value: unknown, code: string, max = 1000): string {
  if (typeof value !== "string" || !value.trim() || value.length > max) fail(code);
  return value;
}
function timestamp(value: unknown, code: string): number {
  if (typeof value === "number") return positive(value, code);
  if (typeof value !== "string" || !/T.*(?:Z|[+-]\d{2}:\d{2})$/.test(value)) fail(code);
  const n = Date.parse(value);
  if (!Number.isFinite(n) || n <= 0) fail(code);
  return n;
}
function canonical(value: unknown): string {
  if (value === null) return "null";
  if (Array.isArray(value)) return "[" + value.map(canonical).join(",") + "]";
  if (typeof value === "object") {
    const obj = value as Json;
    return "{" + Object.keys(obj).filter(k => obj[k] !== undefined).sort()
      .map(k => JSON.stringify(k) + ":" + canonical(obj[k])).join(",") + "}";
  }
  if (typeof value === "number" && !Number.isFinite(value)) fail("NONFINITE_EVIDENCE");
  if (!["string", "number", "boolean"].includes(typeof value)) fail("INVALID_EVIDENCE_VALUE");
  return JSON.stringify(value);
}
function walkCanonical(value: unknown, consume: (chunk: string) => void): void {
  if (value === null) { consume("null"); return; }
  if (Array.isArray(value)) {
    consume("[");
    for (let i = 0; i < value.length; i++) { if (i) consume(","); walkCanonical(value[i], consume); }
    consume("]"); return;
  }
  if (typeof value === "object") {
    consume("{"); const row = value as Json;
    const keys = Object.keys(row).filter(k => row[k] !== undefined).sort();
    for (let i = 0; i < keys.length; i++) {
      if (i) consume(","); consume(JSON.stringify(keys[i])); consume(":"); walkCanonical(row[keys[i]!], consume);
    }
    consume("}"); return;
  }
  if (typeof value === "number" && !Number.isFinite(value)) fail("NONFINITE_EVIDENCE");
  if (!["string", "number", "boolean"].includes(typeof value)) fail("INVALID_EVIDENCE_VALUE");
  consume(JSON.stringify(value));
}
export function netLedgerDigest(value: unknown): string {
  // Bounded chunks avoid allocating a second large canonical history string
  // every minute. This is byte-identical to the canonical JSON above.
  const hash = createHash("sha256"); let parts: string[] = [], size = 0;
  const flush = (): void => { if (parts.length) hash.update(parts.join("")); parts = []; size = 0; };
  walkCanonical(value, chunk => { parts.push(chunk); size += chunk.length; if (size >= 32768) flush(); });
  flush(); return hash.digest("hex");
}
export function verifyNetLedgerHistoryBundle(pages: Json[], expectedIntegrity: string): Json {
  return verifyLedgerHistoryBundle(pages, expectedIntegrity, netLedgerDigest);
}
function canonicalBytes(value: unknown): number {
  let bytes = 0; walkCanonical(value, chunk => { bytes += Buffer.byteLength(chunk); }); return bytes;
}
function stateDigest(state: LedgerState): string {
  const copy: Json = { ...state };
  delete copy.integrity;
  return netLedgerDigest(copy);
}
function costPrefixHash(previous: string, entries: { id: string; at: number; rawHash: string }[]): string {
  let head = previous;
  for (const c of [...entries].sort((a, b) => a.at - b.at || a.id.localeCompare(b.id)))
    head = netLedgerDigest({ previous: head, id: c.id, at: c.at, rawHash: c.rawHash });
  return head;
}
function historyRecords(container: string, kind: "ARCHIVE" | "CONTROL", row: Json): Json[] {
  const header = { ...row }; delete header.observations; delete header.activities; delete header.externalCosts;
  return [{ container, kind: "HEADER", storage: kind, value: header },
    ...row.observations.map((value: Json) => ({ container, kind: "OBSERVATION", value })),
    ...row.activities.map((value: Json) => ({ container, kind: "ACTIVITY", value })),
    ...row.externalCosts.map((value: Json) => ({ container, kind: "COST", value }))];
}
function policyFrom(config: Json): LedgerPolicy {
  if (config.currency !== undefined && config.currency !== "USD") fail("UNSUPPORTED_ACCOUNT_CURRENCY");
  if (config.fillCashBasis !== undefined && config.fillCashBasis !== "GROSS_PLUS_SEPARATE_ACTIVITY_FEES") fail("UNSUPPORTED_FILL_CASH_BASIS");
  const p: LedgerPolicy = {
    currency: "USD", pageSize: 100, maxPages: 100, maxActivities: 20000,
    maxObservations: 10000, maxStateBytes: 32 * 1024 * 1024,
    maxSnapshotSpanMs: 15000, maxAgeMs: 180000,
    cashToleranceUsd: 0.02, navToleranceUsd: 0.05, quantityTolerance: 1e-8,
    performanceIntervalMs: 60000, performanceToleranceMs: 5000,
    fillCashBasis: "GROSS_PLUS_SEPARATE_ACTIVITY_FEES",
  };
  for (const key of Object.keys(p) as (keyof LedgerPolicy)[]) {
    if (typeof p[key] === "number" && config[key] !== undefined) {
      (p as unknown as Json)[key] = finite(config[key], "INVALID_LEDGER_POLICY");
    }
  }
  for (const key of ["pageSize", "maxPages", "maxActivities", "maxObservations", "maxStateBytes"]) {
    const n = (p as unknown as Json)[key] as number;
    if (!Number.isSafeInteger(n) || n <= 0) fail("INVALID_LEDGER_BOUND", { key });
  }
  if (p.pageSize > 100 || p.maxPages > 1000 || p.maxActivities > 100000 ||
      p.maxObservations > 100000 || p.maxStateBytes > 128 * 1024 * 1024) fail("LEDGER_BOUND_TOO_LARGE");
  for (const key of ["maxSnapshotSpanMs", "maxAgeMs", "performanceIntervalMs"]) {
    positive((p as unknown as Json)[key], "INVALID_LEDGER_POLICY");
  }
  if (p.maxSnapshotSpanMs >= 25000) fail("SNAPSHOT_EXCEEDS_LEASE_BUDGET");
  for (const key of ["cashToleranceUsd", "navToleranceUsd", "quantityTolerance", "performanceToleranceMs"]) {
    if ((p as unknown as Json)[key] < 0) fail("INVALID_LEDGER_TOLERANCE");
  }
  if (p.performanceToleranceMs >= p.performanceIntervalMs / 2) fail("INVALID_PERFORMANCE_TOLERANCE");
  return p;
}
function emptyState(accountId: string, policyHash: string): LedgerState {
  return {
    schema: SCHEMA, accountId, policyHash, revision: 0, status: "UNVERIFIED",
    lastAttempt: null, lastSuccess: null, persisted: false, reconciled: false,
    economicComplete: false, returnComplete: false, blockers: ["BASELINE_NOT_OBSERVED"],
    queryFrom: null, baseline: null, activities: [], externalCosts: [], costCoverage: null,
    observations: [], accounting: {
      accountNetPnlUsd: null, economicNetPnlUsd: null, externalFlowsUsd: null,
      externalCostsUsd: null, totalReturnAccount: null, totalReturnEconomic: null,
      accountNetPnlBasis: "BROKER_MARKED_EQUITY_MINUS_EXTERNAL_CAPITAL_FLOWS",
      taxTreatment: "AFTER_REPORTED_ACCOUNT_WITHHOLDINGS_ONLY_OTHER_TAXES_NOT_CALCULATED",
    },
    closedEconomic: { from: null, through: null, knownAt: null, observationCount: 0, intervalCount: 0,
      accountNetPnlUsd: null, economicNetPnlUsd: null, totalReturnEconomic: null,
      completeReturns: false, comparablePeriodGrid: false, evidenceHash: null },
    reconciliation: { status: "NOT_RUN" }, coverage: {},
    insolvency: { account: false, economic: false, firstObservedAt: null },
    lastFailure: null, evidence: {}, integrity: "",
  };
}

export class NetAccountLedger {
  private readonly policy: LedgerPolicy;
  private state: LedgerState;
  private loaded = false;
  private busy = false;
  private volatileError: { code: string; at: number; persisted: boolean } | null = null;
  private readonly archive: NetLedgerArchive;
  private readonly costFile: LocalCostReceiptSource;
  private archiveVerifiedAt: number | null = null;
  private materializationStatus: string | null = null;

  constructor(private readonly store: Store, private readonly api: Api,
    private readonly key: string, private readonly accountId: string,
    private readonly config: Json = {}) {
    text(accountId, "ACCOUNT_ID_REQUIRED", 200);
    text(key, "LEDGER_KEY_REQUIRED", 500);
    this.policy = policyFrom(config);
    this.archive = new NetLedgerArchive(store, key, accountId, netLedgerDigest, object(config.archive ?? {}, "LEDGER_ARCHIVE_CONFIG_INVALID"));
    this.costFile = new LocalCostReceiptSource(config.costReceiptFile, config.maxCostReceiptBytes);
    this.state = emptyState(accountId, netLedgerDigest(this.policy));
  }

  async load(): Promise<Json> {
    const saved = await this.store.get(this.key);
    if (saved !== null && saved !== undefined) {
      const s = object(saved, "INVALID_STORED_LEDGER") as unknown as LedgerState;
      if (s.schema !== SCHEMA || s.accountId !== this.accountId) fail("LEDGER_IDENTITY_MISMATCH");
      if (s.policyHash !== this.state.policyHash) fail("LEDGER_POLICY_MISMATCH");
      if (!Array.isArray(s.activities) || !Array.isArray(s.observations) || !Array.isArray(s.externalCosts) ||
          !Number.isSafeInteger(s.revision) || s.revision < 1 || s.integrity !== stateDigest(s)) fail("LEDGER_INTEGRITY_MISMATCH");
      this.state = structuredClone(s);
    }
    await this.archive.load(this.state.archiveIndex, this.state.policyHash, this.state.baseline?.sourceHash);
    if (this.state.archiveIndex?.segments.length) {
      const boundary = this.state.archiveIndex.boundary;
      if (!this.state.observations.length || this.state.observations[0]!.at !== boundary.anchor.at ||
          this.state.observations[0]!.sourceHash !== boundary.anchor.sourceHash ||
          !this.state.baseline || boundary.originalBaselineHash !== this.state.baseline.sourceHash) fail("LEDGER_ARCHIVE_ACTIVE_BOUNDARY_MISMATCH");
    }
    this.archiveVerifiedAt = Date.now();
    this.loaded = true;
    return this.view();
  }

  private instrumentMap(input: Json): Map<string, Json> {
    const raw = input.instruments ?? this.config.instruments ?? [];
    const rows: unknown[] = Array.isArray(raw) ? raw : Object.values(object(raw, "INSTRUMENT_CATALOG_INVALID"));
    if (rows.length > 10000) fail("INSTRUMENT_CATALOG_BOUND");
    const out = new Map<string, Json>();
    for (const item of rows) {
      const row = object(item, "INSTRUMENT_INVALID");
      const symbol = text(row.symbol, "INSTRUMENT_SYMBOL_REQUIRED", 100);
      if (out.has(symbol)) fail("DUPLICATE_INSTRUMENT", { symbol });
      out.set(symbol, row);
    }
    return out;
  }

  private multiplier(symbol: string, row: Json, instruments: Map<string, Json>): number {
    const meta = instruments.get(symbol);
    if (row.currency !== undefined && row.currency !== "USD") fail("UNSUPPORTED_ACTIVITY_CURRENCY", { symbol });
    if (meta?.currency !== undefined && meta.currency !== "USD") fail("UNSUPPORTED_INSTRUMENT_CURRENCY", { symbol });
    if (meta?.multiplier !== undefined) return positive(meta.multiplier, "INVALID_MULTIPLIER");
    // Alpaca us_equity quantities are shares. No default option multiplier:
    // adjusted contracts must have instrument metadata, not an invented 100.
    if (row.asset_class === "us_equity" || meta?.book === "equity" || meta?.book === "etf") return 1;
    if ((row.asset_class === "crypto" || meta?.book === "crypto") && (row.currency === "USD" || meta?.currency === "USD" || symbol.endsWith("/USD"))) return 1;
    fail("INSTRUMENT_MULTIPLIER_UNKNOWN", { symbol });
  }

  private snapshot(account: Json, rawPositions: unknown, at: number, span: number,
    instruments: Map<string, Json>): Snapshot {
    if (account.id !== this.accountId) fail("BROKER_ACCOUNT_ID_MISMATCH");
    if (account.currency !== "USD") fail("BROKER_ACCOUNT_CURRENCY_UNVERIFIED");
    if (!Array.isArray(rawPositions) || rawPositions.length > 10000) fail("POSITIONS_RESPONSE_INVALID");
    const positions: Position[] = [], seen = new Set<string>();
    for (const item of rawPositions) {
      const r = object(item, "POSITION_INVALID");
      const symbol = text(r.symbol, "POSITION_SYMBOL_REQUIRED", 100);
      if (seen.has(symbol)) fail("DUPLICATE_POSITION", { symbol });
      seen.add(symbol);
      let qty = finite(r.qty, "POSITION_QTY_INVALID");
      if (r.side === "short") qty = -Math.abs(qty);
      if (r.side === "long" && qty < 0) fail("POSITION_SIDE_MISMATCH", { symbol });
      const mv = finite(r.market_value, "POSITION_MARK_MISSING");
      if ((qty > 0 && mv < 0) || (qty < 0 && mv > 0) || (qty === 0 && Math.abs(mv) > this.policy.navToleranceUsd)) fail("POSITION_MARK_SIGN_MISMATCH", { symbol });
      positions.push({ symbol, quantity: qty, marketValueUsd: mv,
        multiplier: this.multiplier(symbol, r, instruments), currency: "USD", sourceHash: netLedgerDigest(r) });
      if (!instruments.has(symbol)) instruments.set(symbol, { symbol, asset_class: r.asset_class, multiplier: positions.at(-1)!.multiplier, currency: "USD" });
    }
    positions.sort((a, b) => a.symbol.localeCompare(b.symbol));
    const equity = finite(account.equity, "ACCOUNT_EQUITY_MISSING"), cash = finite(account.cash, "ACCOUNT_CASH_MISSING");
    const navDifference = equity - cash - positions.reduce((n, p) => n + p.marketValueUsd, 0);
    if (Math.abs(navDifference) > this.policy.navToleranceUsd) fail("NAV_MISMATCH", { navDifferenceUsd: navDifference });
    // If a transport supplies explicit as_of, validate it. created_at is account
    // creation, never a NAV clock. Missing market time remains null.
    const marketTimestamp = account.as_of === undefined ? null : timestamp(account.as_of, "SNAPSHOT_TIME_INVALID");
    if (marketTimestamp !== null && (marketTimestamp > at || at - marketTimestamp > this.policy.maxAgeMs)) fail("SNAPSHOT_STALE_OR_FUTURE");
    if (account.known_at !== undefined && timestamp(account.known_at, "SNAPSHOT_KNOWN_AT_INVALID") > at) fail("FUTURE_KNOWN_AT");
    const sourceReceipt: Json = { account: structuredClone(account), positions: structuredClone(rawPositions) };
    return { at, equity, cash, positions, sourceHash: netLedgerDigest(sourceReceipt), marketTimestamp, receiptSpanMs: span, sourceReceipt };
  }

  private activity(raw: Json, now: number, baselineIncluded: boolean, instruments: Map<string, Json>): Activity {
    const id = text(raw.id, "ACTIVITY_ID_REQUIRED", 500);
    const type = text(raw.activity_type, "ACTIVITY_TYPE_REQUIRED", 100);
    if (Buffer.byteLength(canonical(raw)) > 65536) fail("ACTIVITY_ROW_BOUND", { id });
    let at: number | null = null, date: string | null = null;
    let precision: Activity["timePrecision"] = "UNKNOWN";
    if (raw.transaction_time !== undefined) { at = timestamp(raw.transaction_time, "ACTIVITY_TIME_INVALID"); precision = "INSTANT"; }
    else if (raw.date !== undefined) {
      date = text(raw.date, "ACTIVITY_DATE_INVALID", 100);
      if (/^\d{4}-\d{2}-\d{2}$/.test(date)) {
        if (!Number.isFinite(Date.parse(date)) || new Date(Date.parse(date)).toISOString().slice(0, 10) !== date) fail("ACTIVITY_DATE_INVALID", { id });
        if (Date.parse(date) > now) fail("FUTURE_ACTIVITY", { id });
        precision = "DAY";
      } else { at = timestamp(date, "ACTIVITY_DATE_INVALID"); precision = "INSTANT"; }
    }
    if (at !== null && at > now) fail("FUTURE_ACTIVITY", { id });
    for (const field of ["known_at", "created_at"]) {
      if (raw[field] !== undefined && timestamp(raw[field], "ACTIVITY_KNOWN_AT_INVALID") > now) fail("FUTURE_KNOWN_AT", { id, field });
    }
    const item: Activity = { id, activityType: type, classification: "BASELINE_INCLUDED", at, date,
      timePrecision: precision, knownAt: now, currency: typeof raw.currency === "string" ? raw.currency : null,
      cashDeltaUsd: null, quantityDelta: null, multiplier: null, symbol: raw.symbol === undefined ? null : text(raw.symbol, "ACTIVITY_SYMBOL_INVALID", 100),
      orderId: raw.order_id === undefined ? null : text(raw.order_id, "ORDER_ID_INVALID", 500),
      baselineIncluded, rawHash: netLedgerDigest(raw), raw: structuredClone(raw) };
    if (baselineIncluded) return item; // Opening snapshot already incorporates these entries.
    if (raw.currency !== undefined && raw.currency !== "USD") fail("UNSUPPORTED_ACTIVITY_CURRENCY", { id, currency: raw.currency });
    item.currency = "USD";
    if (type === "FILL") {
      if (at === null || item.symbol === null || item.orderId === null || !["buy", "sell"].includes(raw.side)) fail("FILL_FIELDS_INVALID", { id });
      if (raw.type !== undefined && !["fill", "partial_fill"].includes(raw.type)) fail("FILL_TYPE_INVALID", { id });
      const qty = positive(raw.qty, "FILL_QTY_INVALID"), price = positive(raw.price, "FILL_PRICE_INVALID");
      const signedQty = (raw.side === "buy" ? 1 : -1) * qty;
      item.multiplier = this.multiplier(item.symbol, raw, instruments);
      const cash = -signedQty * price * item.multiplier;
      if (!Number.isFinite(cash)) fail("FILL_NOTIONAL_OVERFLOW", { id });
      // TradeActivity is documented as gross price*qty. Mixed net cash/embedded
      // commission feeds require an explicit adapter; silently counting both
      // embedded and separate charges would falsify reconciliation.
      for (const field of ["fee", "fees", "commission"]) {
        if (raw[field] !== undefined && finite(raw[field], "EMBEDDED_FEE_INVALID") !== 0) fail("AMBIGUOUS_EMBEDDED_FILL_FEE", { id, field });
      }
      if (raw.net_amount !== undefined && Math.abs(finite(raw.net_amount, "FILL_NET_AMOUNT_INVALID") - cash) > this.policy.cashToleranceUsd) fail("AMBIGUOUS_FILL_NET_AMOUNT", { id });
      if (raw.cum_qty !== undefined && finite(raw.cum_qty, "FILL_CUM_QTY_INVALID") + this.policy.quantityTolerance < qty) fail("FILL_CUM_QTY_INVALID", { id });
      if (raw.leaves_qty !== undefined && finite(raw.leaves_qty, "FILL_LEAVES_QTY_INVALID") < 0) fail("FILL_LEAVES_QTY_INVALID", { id });
      item.classification = "FILL"; item.quantityDelta = signedQty; item.cashDeltaUsd = cash;
      return item;
    }
    if (item.timePrecision === "UNKNOWN") fail("NONTRADE_DATE_MISSING", { id });
    const cash = finite(raw.net_amount, "ACTIVITY_AMOUNT_INVALID");
    if (["CSD", "CSW", "ACATC"].includes(type)) {
      if ((type === "CSD" && cash <= 0) || (type === "CSW" && cash >= 0)) fail("CAPITAL_FLOW_SIGN_INVALID", { id });
      item.classification = "EXTERNAL_FLOW";
    } else if (["FEE", "PTC", "PTR", "DIVFEE", "CFEE"].includes(type)) {
      if (type === "CFEE" && raw.currency !== "USD") fail("CRYPTO_FEE_CURRENCY_UNKNOWN", { id });
      item.classification = "FEE";
    } else if (["DIV", "DIVNRA", "CGD", "INT", "INTNRA", "INTTW"].includes(type)) {
      item.classification = "ACCOUNT_CASH";
    } else fail("UNSUPPORTED_ACTIVITY_TYPE", { id, activityType: type });
    item.cashDeltaUsd = cash;
    return item;
  }

  private async activities(from: number, through: number, receipt: Json): Promise<Json[]> {
    const rows: Json[] = [], ids = new Set<string>();
    let token: string | null = null;
    for (let page = 0; page < this.policy.maxPages; page++) {
      const q = new URLSearchParams({ after: new Date(from).toISOString(), until: new Date(through).toISOString(), direction: "asc", page_size: String(this.policy.pageSize) });
      if (token !== null) q.set("page_token", token);
      const result: unknown = await this.api.request("/v2/account/activities?" + q.toString(), "GET");
      if (!Array.isArray(result) || result.length > this.policy.pageSize) fail("ACTIVITY_PAGE_INVALID", { page });
      receipt.pages = page + 1;
      for (const value of result) {
        const row = object(value, "ACTIVITY_ROW_INVALID"), id = text(row.id, "ACTIVITY_ID_REQUIRED", 500);
        if (ids.has(id)) fail("ACTIVITY_PAGE_OVERLAP_OR_LOOP", { id, page });
        ids.add(id); rows.push(row);
        if (rows.length > this.policy.maxActivities) fail("ACTIVITY_HISTORY_BOUND");
      }
      receipt.activities = rows;
      if (result.length < this.policy.pageSize) { receipt.paginationComplete = true; return rows; }
      token = text(object(result[result.length - 1], "ACTIVITY_ROW_INVALID").id, "ACTIVITY_CURSOR_INVALID", 500);
    }
    fail("ACTIVITY_PAGINATION_INCOMPLETE", { pages: this.policy.maxPages, rows: rows.length });
  }

  private costs(raw: unknown, old: LedgerState, now: number, baselineAt: number,
    activities: Activity[]): { entries: Cost[]; coverage: CostCoverage | null; complete: boolean; reason: string | null } {
    if (raw === undefined || raw === null) return { entries: old.externalCosts, coverage: old.costCoverage,
      complete: old.costCoverage !== null && old.costCoverage.from <= baselineAt && old.costCoverage.through >= now,
      reason: "EXTERNAL_COST_COVERAGE_MISSING" };
    const report = object(raw, "EXTERNAL_COST_REPORT_INVALID");
    const from = timestamp(report.from, "COST_COVERAGE_FROM_INVALID"), through = timestamp(report.through, "COST_COVERAGE_THROUGH_INVALID");
    const known = timestamp(report.known_at, "COST_COVERAGE_KNOWN_AT_INVALID");
    const reference = text(report.reference, "COST_COVERAGE_REFERENCE_REQUIRED");
    if (from > through || through > known || known > now) fail("COST_COVERAGE_FUTURE_OR_REVERSED");
    if (old.costCoverage !== null && (through < old.costCoverage.through || from > old.costCoverage.from)) fail("COST_COVERAGE_REGRESSED");
    if (!Array.isArray(report.categories) || report.categories.length !== COST_CATEGORIES.length ||
        [...new Set(report.categories)].sort().join("|") !== [...COST_CATEGORIES].sort().join("|")) fail("COST_CATEGORIES_INCOMPLETE");
    if (!Array.isArray(report.entries) || report.entries.length > this.policy.maxActivities) fail("COST_ENTRIES_INVALID");
    const prior = new Map(old.externalCosts.map(c => [c.id, c])), entries: Cost[] = [];
    const seen = new Set<string>(), linked = new Set<string>();
    for (const value of report.entries) {
      const row = object(value, "COST_ENTRY_INVALID"), id = text(row.id, "COST_ID_REQUIRED", 500);
      if (seen.has(id)) fail("DUPLICATE_COST_ID", { id });
      seen.add(id);
      const at = timestamp(row.at, "COST_TIME_INVALID"), knownAt = timestamp(row.known_at, "COST_KNOWN_AT_INVALID");
      const amount = finite(row.amount_usd, "COST_AMOUNT_UNKNOWN");
      if (amount < 0 || at < from || at > through || knownAt < at || knownAt > known || knownAt > now) fail("COST_TIME_OR_AMOUNT_INVALID", { id });
      if (!COST_CATEGORIES.includes(row.category)) fail("COST_CATEGORY_INVALID", { id });
      if (typeof row.already_in_account !== "boolean") fail("COST_ACCOUNT_TREATMENT_UNKNOWN", { id });
      const activityId = row.activity_id === undefined || row.activity_id === null ? null : text(row.activity_id, "COST_ACTIVITY_ID_INVALID", 500);
      if (row.already_in_account) {
        const linkedActivity = activities.find(a => a.id === activityId);
        if (!linkedActivity || linkedActivity.baselineIncluded || !["FEE", "ACCOUNT_CASH"].includes(linkedActivity.classification) ||
            linkedActivity.cashDeltaUsd === null || Math.abs(linkedActivity.cashDeltaUsd + amount) > this.policy.cashToleranceUsd) fail("ACCOUNT_COST_LINK_UNVERIFIED", { id });
        if (activityId === null || linked.has(activityId)) fail("ACCOUNT_COST_DOUBLE_LINK", { id });
        linked.add(activityId);
      } else if (activityId !== null) fail("EXTERNAL_COST_LINK_AMBIGUOUS", { id });
      const entry: Cost = { id, at, known_at: knownAt, amount_usd: amount, reference: text(row.reference, "COST_REFERENCE_REQUIRED"),
        category: row.category, already_in_account: row.already_in_account, activity_id: activityId, rawHash: netLedgerDigest(row) };
      if (prior.has(id) && prior.get(id)!.rawHash !== entry.rawHash) fail("COST_REVISION_REQUIRES_RESTATEMENT", { id });
      entries.push(entry);
    }
    for (const id of prior.keys()) if (!seen.has(id)) fail("COST_HISTORY_GAP", { id });
    const coverage: CostCoverage = { from, through, known_at: known, reference,
      categories: [...COST_CATEGORIES], sourceHash: netLedgerDigest(report), basis: "DECLARED_COST_COVERAGE_NOT_INDEPENDENTLY_ATTESTED" };
    const complete = from <= baselineAt && through >= now;
    return { entries, coverage, complete, reason: complete ? null : "EXTERNAL_COST_COVERAGE_INCOMPLETE" };
  }

  private preFlowMarks(raw: unknown, flows: Activity[], start: number, now: number): PreFlowMark[] {
    if (raw === undefined || raw === null) return [];
    if (!Array.isArray(raw) || raw.length > this.policy.maxActivities) fail("PREFLOW_MARKS_INVALID");
    const out: PreFlowMark[] = [], seen = new Set<string>();
    for (const value of raw) {
      const row = object(value, "PREFLOW_MARK_INVALID"), id = text(row.activityId, "PREFLOW_ACTIVITY_REQUIRED", 500);
      if (seen.has(id)) fail("DUPLICATE_PREFLOW_MARK", { id });
      seen.add(id);
      const activity = flows.find(a => a.id === id);
      const at = timestamp(row.at, "PREFLOW_TIME_INVALID"), known = timestamp(row.known_at, "PREFLOW_KNOWN_AT_INVALID");
      const before = finite(row.equityBefore, "PREFLOW_EQUITY_UNKNOWN"), after = finite(row.equityAfter, "POSTFLOW_EQUITY_UNKNOWN");
      if (!activity || activity.at === null || activity.timePrecision !== "INSTANT" || activity.at !== at ||
          at <= start || at > now || known < at || known > now) fail("PREFLOW_TEMPORAL_BINDING_INVALID", { id });
      if (activity.cashDeltaUsd === null || Math.abs(after - before - activity.cashDeltaUsd) > this.policy.navToleranceUsd) fail("PREFLOW_CAPITAL_RECONCILIATION_FAILED", { id });
      const evidence = object(row.evidence, "PREFLOW_SOURCE_EVIDENCE_REQUIRED");
      const evidenceHash = text(row.evidenceHash, "PREFLOW_SOURCE_HASH_REQUIRED", 64);
      if (evidenceHash !== netLedgerDigest(evidence)) fail("PREFLOW_SOURCE_HASH_MISMATCH", { id });
      // Hash-binding requires the claimed source values to be in the receipt.
      if (evidence.activityId !== id || evidence.at !== at || evidence.equityBefore !== before || evidence.equityAfter !== after) fail("PREFLOW_SOURCE_VALUE_MISMATCH", { id });
      out.push({ activityId: id, at, known_at: known, equityBefore: before, equityAfter: after,
        reference: text(row.reference, "PREFLOW_REFERENCE_REQUIRED"), evidenceHash, evidence: structuredClone(evidence),
        basis: "CALLER_SUPPLIED_PRE_FLOW_EVIDENCE_NOT_INDEPENDENTLY_ATTESTED" });
    }
    out.sort((a, b) => a.at - b.at || a.activityId.localeCompare(b.activityId));
    if (out.some((m, i) => i > 0 && out[i - 1]!.at === m.at)) fail("PREFLOW_ORDER_AMBIGUOUS");
    return out;
  }

  private intervalReturn(startEquity: number, endEquity: number, flows: Activity[],
    marks: PreFlowMark[], cumulativeCost: (at: number) => number): number | null {
    if (startEquity <= 0 || endEquity < 0) return null;
    if (flows.length !== marks.length || flows.some(a => !marks.some(m => m.activityId === a.id))) return null;
    let capital = startEquity, growth = 1;
    for (const mark of marks) {
      const before = mark.equityBefore - cumulativeCost(mark.at);
      const after = mark.equityAfter - cumulativeCost(mark.at);
      if (capital <= 0 || before < 0 || after <= 0) return null;
      growth *= before / capital;
      capital = after;
    }
    if (capital <= 0) return null;
    const result = growth * endEquity / capital - 1;
    return Number.isFinite(result) && result >= -1 ? result : null;
  }

  private costReportForActiveWindow(raw: unknown, state: LedgerState): unknown {
    const boundary = state.archiveIndex?.boundary;
    if (!boundary || raw === undefined || raw === null) return raw;
    const report = object(raw, "EXTERNAL_COST_REPORT_INVALID");
    if (!Array.isArray(report.entries) || report.entries.length > this.policy.maxActivities) fail("COST_ENTRIES_INVALID");
    const seen = new Set<string>(), linked = new Set<string>();
    const prefix: { id: string; at: number; rawHash: string }[] = [], active: Json[] = [];
    for (const value of report.entries) {
      const row = object(value, "COST_ENTRY_INVALID"), id = text(row.id, "COST_ID_REQUIRED", 500);
      if (seen.has(id)) fail("DUPLICATE_COST_ID", { id }); seen.add(id);
      if (row.already_in_account === true) {
        const link = text(row.activity_id, "COST_ACTIVITY_ID_INVALID", 500);
        if (linked.has(link)) fail("ACCOUNT_COST_DOUBLE_LINK", { id }); linked.add(link);
      }
      const at = timestamp(row.at, "COST_TIME_INVALID");
      if (at <= boundary.anchor.at) prefix.push({ id, at, rawHash: netLedgerDigest(row) });
      else active.push(row);
    }
    // A changed or newly reported cost in a sealed period needs an explicit
    // restatement. Do not rewrite immutable evidence or treat the tail as the
    // full economic curve. Account reconciliation can continue independently.
    if (prefix.length !== boundary.costPrefixCount || costPrefixHash("GENESIS", prefix) !== boundary.costPrefixHash)
      fail("ECONOMIC_RESTATEMENT_REQUIRED", { archivedThrough: boundary.anchor.at });
    return { ...report, entries: active };
  }

  private async compact(next: LedgerState): Promise<LedgerState> {
    if (!this.archive.enabled || !next.reconciled || (next.observations.length <= this.policy.maxObservations &&
        next.activities.length <= this.policy.maxActivities && canonicalBytes(next) <= this.policy.maxStateBytes)) return next;
    if (next.observations.length < 2 || !next.baseline) fail("LEDGER_ACTIVE_RECORD_TOO_LARGE_TO_ARCHIVE");
    let anchorIndex = next.observations.length - 1;
    // Keep an uncovered recent tail active when a completed cost prefix exists.
    // With a delayed receipt this normally retains the boundary plus one mark,
    // rather than sealing every file read delay as an irreparable economic gap.
    for (let i = next.observations.length - 2; next.observations.at(-1)!.economicEquity === null && i > 0; i--) {
      if (next.observations[i]!.economicEquity !== null && next.observations[i]!.economicReturn !== null &&
          next.observations.length - i <= this.policy.maxObservations) { anchorIndex = i; break; }
    }
    const anchor = next.observations[anchorIndex]!, prior = next.archiveIndex?.boundary;
    const archivedActivities = next.activities.filter(a => a.knownAt <= anchor.at);
    const costs = next.externalCosts.filter(c => c.at <= anchor.at);
    const declaredCosts = (prior?.declaredExternalCostsUsd ?? 0) + costs.filter(c => !c.already_in_account && c.at > next.baseline!.at)
      .reduce((n, c) => n + c.amount_usd, 0);
    const totalObservations = (next.archiveIndex?.observationCount ?? 0) + anchorIndex + 1;
    const prefix = next.observations.slice(1, anchorIndex + 1);
    const accountComplete = (prior?.accountHistoryComplete ?? true) && prefix.every(o => o.accountReturn !== null) && !next.insolvency.account;
    const economicComplete = (prior?.economicHistoryComplete ?? true) && prefix.every(o => o.economicReturn !== null) && !next.insolvency.economic;
    const boundary: Json = { anchor: structuredClone(anchor), originalBaselineHash: next.baseline.sourceHash,
      externalFlowsUsd: anchor.cumulativeExternalFlowUsd,
      reportedAccountFeesUsd: (prior?.reportedAccountFeesUsd ?? 0) + archivedActivities.filter(a => !a.baselineIncluded && a.classification === "FEE").reduce((n, a) => n - a.cashDeltaUsd!, 0),
      reportedAccountIncomeAndFinancingUsd: (prior?.reportedAccountIncomeAndFinancingUsd ?? 0) + archivedActivities.filter(a => !a.baselineIncluded && a.classification === "ACCOUNT_CASH").reduce((n, a) => n + a.cashDeltaUsd!, 0),
      declaredExternalCostsUsd: declaredCosts,
      costPrefixCount: (prior?.costPrefixCount ?? 0) + costs.length,
      costPrefixHash: costPrefixHash(prior?.costPrefixHash ?? "GENESIS", costs),
      accountGrowth: accountComplete ? prefix.reduce((g, o) => g * (1 + o.accountReturn!), prior?.accountGrowth ?? 1) : null,
      economicGrowth: economicComplete ? prefix.reduce((g, o) => g * (1 + o.economicReturn!), prior?.economicGrowth ?? 1) : null,
      accountHistoryComplete: totalObservations === 1 || accountComplete,
      economicHistoryComplete: anchor.economicEquity !== null && !next.economicRestatementRequired &&
        (totalObservations === 1 || economicComplete),
      comparablePeriodGrid: next.coverage.comparablePeriodGrid,
      closedEconomic: structuredClone(next.closedEconomic), sealedAt: next.lastSuccess,
      sourceAuthenticityVerified: false };
    const index = await this.archive.append(next.archiveIndex, { ledgerPolicyHash: next.policyHash,
      originalBaselineHash: next.baseline.sourceHash, observations: next.observations.slice(0, anchorIndex),
      activities: archivedActivities, externalCosts: costs, costCoverage: next.costCoverage,
      costSource: next.costSource ?? null, brokerAccrualCoverage: next.brokerAccrualCoverage ?? null,
      brokerAccrualLinkedCosts: next.brokerAccrualLinkedCosts ?? [], boundary });
    this.archiveVerifiedAt = Date.now();
    return { ...next, archiveIndex: index, observations: next.observations.slice(anchorIndex),
      activities: next.activities.filter(a => a.knownAt > anchor.at),
      externalCosts: next.externalCosts.filter(c => c.at > anchor.at) };
  }

  private async commit(next: LedgerState, previousIntegrity: string): Promise<void> {
    if (!await this.store.lease(this.key + "-writer")) fail("LEDGER_WRITER_LEASE_LOST");
    const current = await this.store.get(this.key);
    if ((current?.integrity ?? "") !== previousIntegrity) fail("LEDGER_CONCURRENT_REVISION");
    next = await this.compact(next);
    next.revision = this.state.revision + 1;
    next.persisted = true;
    next.integrity = stateDigest(next);
    if (canonicalBytes(next) > this.policy.maxStateBytes) fail("LEDGER_STATE_BOUND");
    try {
      const ok = await this.store.put(this.key, next);
      if (ok === false) fail("LEDGER_PERSISTENCE_REJECTED");
    } catch { fail("LEDGER_PERSISTENCE_FAILURE"); }
    this.state = next;
    this.volatileError = null;
    this.materializationStatus = null;
  }

  async refresh(input: Json = {}): Promise<Json> {
    if (this.busy) fail("LEDGER_REFRESH_IN_PROGRESS");
    let now = input.now === undefined ? Date.now() : timestamp(input.now, "OBSERVATION_TIME_INVALID");
    const queryThrough = now;
    const writers = inProcessWriters.get(this.store) ?? new Set<string>();
    if (writers.has(this.key)) fail("LEDGER_IN_PROCESS_WRITER_BUSY");
    writers.add(this.key); inProcessWriters.set(this.store, writers);
    this.busy = true;
    const receipt: Json = { requestedThrough: now, pages: 0, paginationComplete: false, activities: [] };
    let acquired = false;
    try {
      if (!this.loaded) await this.load();
      acquired = await this.store.lease(this.key + "-writer");
      if (!acquired) fail("LEDGER_WRITER_BUSY");
      if (this.state.lastSuccess !== null && now <= this.state.lastSuccess) fail("NONMONOTONIC_OBSERVATION_TIME");
      if (!this.archive.enabled && this.state.observations.length >= this.policy.maxObservations) fail("OBSERVATION_HISTORY_BOUND");
      const timer = performance.now(), instruments = this.instrumentMap(input);
      const from = this.archive.enabled && this.state.coverage.untilCreatedAt !== undefined ?
        Math.max(this.state.queryFrom ?? 1, this.state.coverage.untilCreatedAt - this.archive.activityOverlapMs) :
        this.state.queryFrom ?? Math.floor(now / DAY) * DAY;
      receipt.requestedFrom = from;
      const beforeAccount = object(await this.api.request("/v2/account", "GET"), "ACCOUNT_RESPONSE_INVALID");
      const beforePositions: unknown = await this.api.request("/v2/positions", "GET");
      receipt.beforeAccount = beforeAccount; receipt.beforePositions = beforePositions;
      const rawActivities = await this.activities(from, now, receipt);
      const afterAccount = object(await this.api.request("/v2/account", "GET"), "ACCOUNT_RESPONSE_INVALID");
      const afterPositions: unknown = await this.api.request("/v2/positions", "GET");
      receipt.afterAccount = afterAccount; receipt.afterPositions = afterPositions;
      // In production, knowledge time is after receipt, never the start of an
      // HTTP call. input.now is the explicit deterministic fixture clock.
      if (input.now === undefined) now = Date.now();
      receipt.receivedAt = now;
      const span = performance.now() - timer;
      receipt.receiptSpanMs = span;
      if (span > this.policy.maxSnapshotSpanMs) fail("NONATOMIC_SNAPSHOT_SPAN_EXCEEDED");
      const before = this.snapshot(beforeAccount, beforePositions, now, span, instruments);
      const end = this.snapshot(afterAccount, afterPositions, now, span, instruments);
      if (Math.abs(before.cash - end.cash) > this.policy.cashToleranceUsd ||
          netLedgerDigest(before.positions.map(p => [p.symbol, p.quantity])) !== netLedgerDigest(end.positions.map(p => [p.symbol, p.quantity]))) fail("SNAPSHOT_CHANGED_DURING_COLLECTION");
      end.sourceReceipt.bracketBefore = before.sourceReceipt;
      end.sourceReceipt.receiptSpanMs = span;
      end.sourceReceipt.receiptTime = now;
      end.sourceHash = netLedgerDigest(end.sourceReceipt);
      const old = this.state, initial = old.baseline === null;
      const previousActivities = new Map(old.activities.map(a => [a.id, a]));
      const activities: Activity[] = this.archive.enabled ? [...old.activities] : [];
      const receivedIds = new Set<string>();
      for (const row of rawActivities) {
        receivedIds.add(row.id);
        const previous = previousActivities.get(row.id);
        if (previous) {
          if (previous.rawHash !== netLedgerDigest(row)) fail("ACTIVITY_REVISION_REQUIRES_RESTATEMENT", { id: row.id });
          if (!this.archive.enabled) activities.push(previous);
          previousActivities.delete(row.id);
        } else {
          const archived = this.archive.enabled ? await this.archive.findActivity(old.archiveIndex, row.id) : null;
          if (archived) {
            if (archived.rawHash !== netLedgerDigest(row)) fail("ARCHIVED_ACTIVITY_REVISION_REQUIRES_RESTATEMENT", { id: row.id });
          } else activities.push(this.activity(row, now, initial, instruments));
        }
      }
      if (!this.archive.enabled && previousActivities.size) fail("ACTIVITY_HISTORY_GAP", { missingIds: [...previousActivities.keys()].slice(0, 20), count: previousActivities.size });
      if (this.archive.enabled) {
        for (const a of old.activities) if (a.raw.created_at !== undefined) {
          const created = timestamp(a.raw.created_at, "ACTIVITY_KNOWN_AT_INVALID");
          if (created > from && created <= queryThrough && !receivedIds.has(a.id)) fail("ACTIVITY_HISTORY_GAP", { missingIds: [a.id] });
        }
      }
      const baseline = old.baseline ?? end;
      const carry = old.archiveIndex?.boundary;
      const windowBaseline: Snapshot = carry?.anchor ?? baseline;
      const included = activities.filter(a => !a.baselineIncluded);
      const expectedCash = windowBaseline.cash + included.reduce((n, a) => n + (a.cashDeltaUsd ?? fail("ACTIVITY_CASH_UNRESOLVED")), 0);
      const expectedQty = new Map(windowBaseline.positions.map(p => [p.symbol, p.quantity]));
      for (const a of included) if (a.classification === "FILL" && a.symbol !== null && a.quantityDelta !== null) expectedQty.set(a.symbol, (expectedQty.get(a.symbol) ?? 0) + a.quantityDelta);
      const positions = new Map(end.positions.map(p => [p.symbol, p.quantity]));
      const inventoryDifferences = [...new Set([...expectedQty.keys(), ...positions.keys()])]
        .map(symbol => ({ symbol, expected: expectedQty.get(symbol) ?? 0, observed: positions.get(symbol) ?? 0 }))
        .filter(r => Math.abs(r.observed - r.expected) > this.policy.quantityTolerance);
      const cashDifference = end.cash - expectedCash;
      const reconciliation: Json = { status: "RECONCILED", at: now, expectedCashUsd: expectedCash, observedCashUsd: end.cash,
        cashDifferenceUsd: cashDifference, inventoryDifferences,
        navDifferenceUsd: end.equity - end.cash - end.positions.reduce((n, p) => n + p.marketValueUsd, 0),
        basis: "BROKER_SNAPSHOT_MARKS_AND_REPORTED_ACTIVITY_CASH", snapshotAtomic: false,
        limitations: ["Broker marks can differ from realizable liquidation prices.", "Local receipt age does not establish quote freshness or clock synchronization.", "API pagination cannot prove that the upstream source never omitted an unseen activity."] };
      if (Math.abs(cashDifference) > this.policy.cashToleranceUsd || inventoryDifferences.length) fail("CASH_OR_INVENTORY_MISMATCH", reconciliation);
      let rawCosts: unknown = input.externalCosts ?? this.config.externalCosts;
      let costSource: Json = { type: "INLINE_DECLARED_COST_COVERAGE", status: rawCosts === undefined || rawCosts === null ? "NOT_CONFIGURED" : "READ",
        sourceAuthenticityVerified: false, receivedAt: now };
      if (this.costFile.filename !== null && (rawCosts === undefined || rawCosts === null)) {
        const imported = await this.costFile.read(this.accountId, now, old.costSource);
        rawCosts = imported.report; costSource = imported.source;
      }
      let costs: ReturnType<NetAccountLedger["costs"]>, economicRestatementRequired = old.economicRestatementRequired ?? false;
      try {
        // Both ingress routes have the same contract. An inline object is not
        // evidence that omitted account/currency/completeness fields are true.
        // Validate the complete receipt before slicing its archived prefix.
        if (rawCosts !== undefined && rawCosts !== null) {
          const validated = validateCostReceipt(rawCosts, this.accountId, now);
          const contentHash = netLedgerDigest(validated);
          const accepted = old.costSource?.status === "READ" ? old.costSource : old.costSource?.lastAccepted;
          if (accepted?.receiptId === validated.receipt_id &&
              typeof accepted.receiptContentHash === "string" && accepted.receiptContentHash !== contentHash)
            throw new CostReceiptError("COST_RECEIPT_ID_REUSED_WITH_CHANGED_CONTENT");
          rawCosts = validated;
          costSource = { ...costSource, receiptId: validated.receipt_id, receiptContentHash: contentHash,
            receiptSchema: validated.schema, accountId: validated.account_id, currency: validated.currency,
            coverageDeclaredComplete: true, receiptValidation: "SHARED_COST_RECEIPT_CONTRACT",
            producerKnownAt: timestamp(validated.known_at, "COST_COVERAGE_KNOWN_AT_INVALID"),
            coverageFrom: timestamp(validated.from, "COST_COVERAGE_FROM_INVALID"),
            coverageThrough: timestamp(validated.through, "COST_COVERAGE_THROUGH_INVALID") };
        }
        const activeReport = this.costReportForActiveWindow(rawCosts, old);
        costs = this.costs(activeReport, old, now, baseline.at, activities);
        if (economicRestatementRequired) costs = { ...costs, complete: false, reason: "ECONOMIC_RESTATEMENT_REQUIRED" };
        if (this.costFile.filename !== null && ["MISSING", "INVALID"].includes(costSource.status))
          costs = { ...costs, complete: false, reason: costSource.reason };
      } catch (error) {
        if (!(error instanceof NetLedgerError) && !(error instanceof CostReceiptError)) throw error;
        economicRestatementRequired = economicRestatementRequired || error.code === "ECONOMIC_RESTATEMENT_REQUIRED";
        costs = { entries: old.externalCosts, coverage: old.costCoverage, complete: false, reason: error.code };
        costSource = { ...costSource, status: "REJECTED_BY_LEDGER", reason: error.code,
          lastAccepted: old.costSource?.status === "READ" ? old.costSource : old.costSource?.lastAccepted ?? null };
      }
      const costsInOrder = costs.entries.filter(c => !c.already_in_account && c.at > baseline.at).sort((a, b) => a.at - b.at);
      const costPrefix = [carry?.declaredExternalCostsUsd ?? 0];
      for (const cost of costsInOrder) costPrefix.push(costPrefix.at(-1)! + cost.amount_usd);
      const cumulativeCost = (at: number): number => {
        let lo = 0, hi = costsInOrder.length;
        while (lo < hi) { const mid = Math.floor((lo + hi) / 2); if (costsInOrder[mid]!.at <= at) lo = mid + 1; else hi = mid; }
        return costPrefix[lo]!;
      };
      const flows = included.filter(a => a.classification === "EXTERNAL_FLOW");
      const totalFlow = (carry?.externalFlowsUsd ?? 0) + flows.reduce((n, a) => n + a.cashDeltaUsd!, 0);
      const previous = old.observations.at(-1);
      const previousIds = new Set(old.activities.map(a => a.id));
      const newActivities = included.filter(a => !previousIds.has(a.id));
      const newFlows = newActivities.filter(a => a.classification === "EXTERNAL_FLOW");
      const marks = this.preFlowMarks(input.preFlowMarks, newFlows, previous?.at ?? now, now);
      const accountReturn = previous ? this.intervalReturn(previous.equity, end.equity, newFlows, marks, () => 0) : null;
      const economicEquity = costs.complete ? end.equity - cumulativeCost(now) : null;
      const economicReturn = previous && costs.complete && previous.economicEquity !== null ?
        this.intervalReturn(previous.economicEquity, economicEquity!, newFlows, marks, cumulativeCost) : null;
      let returnStatus = initial ? "BASELINE" : accountReturn === null ? "WAIT_PRE_FLOW_OR_INSOLVENCY_EVIDENCE" :
        !costs.complete || economicReturn === null ? "WAIT_ECONOMIC_COST_COVERAGE" : "COMPLETE";
      if (newFlows.some(a => a.timePrecision !== "INSTANT")) returnStatus = "FLOW_TIME_PRECISION_INSUFFICIENT";
      const observation: Observation = { ...end, activitiesThrough: queryThrough,
        externalFlowUsd: newFlows.reduce((n, a) => n + a.cashDeltaUsd!, 0), cumulativeExternalFlowUsd: totalFlow,
        externalCostUsd: costs.complete && previous?.cumulativeExternalCostUsd !== null ? cumulativeCost(now) - (previous?.cumulativeExternalCostUsd ?? 0) : null,
        cumulativeExternalCostUsd: costs.complete ? cumulativeCost(now) : null, economicEquity,
        accountReturn, economicReturn, returnStatus, preFlowMarks: marks,
        activityIds: newActivities.map(a => a.id), costCoverageHash: costs.complete ? costs.coverage!.sourceHash : null,
        economicKnownAt: costs.complete ? now : null };
      const observations = [...old.observations, observation];
      // Cost receipts can arrive after their service period. Reconstruct the
      // economic curve from immutable broker marks, recording when the revised
      // calculation became knowable. Never revise old source observations or
      // pretend later-known costs were available to an earlier trading model.
      const restatedAt: number[] = [];
      const activityById = new Map(activities.map(a => [a.id, a]));
      const economicallyCoveredThrough = !economicRestatementRequired && costs.coverage !== null && costs.coverage.from <= baseline.at ? costs.coverage.through : null;
      for (let i = 0; economicallyCoveredThrough !== null && i < observations.length && observations[i]!.at <= economicallyCoveredThrough; i++) {
        if (carry && i === 0) continue; // Do not silently restate immutable archived intervals.
        const original = observations[i]!, preceding = observations[i - 1];
        const o = { ...original };
        const cumulative = cumulativeCost(o.at), equity = o.equity - cumulative;
        const periodFlows = o.activityIds.map(id => activityById.get(id) ?? fail("ACTIVITY_OBSERVATION_LINK_MISSING")).filter(a => a.classification === "EXTERNAL_FLOW");
        const ret = preceding ? this.intervalReturn(preceding.economicEquity!, equity, periodFlows, o.preFlowMarks, cumulativeCost) : null;
        if (o.economicEquity !== equity || o.economicReturn !== ret || o.cumulativeExternalCostUsd === null) {
          if (i < observations.length - 1) restatedAt.push(o.at);
          o.economicKnownAt = now;
          o.costCoverageHash = costs.coverage!.sourceHash;
        }
        o.economicEquity = equity; o.cumulativeExternalCostUsd = cumulative;
        o.externalCostUsd = cumulative - (preceding?.cumulativeExternalCostUsd ?? 0);
        o.economicReturn = ret;
        if (i > 0 && o.accountReturn !== null && ret !== null) o.returnStatus = "COMPLETE";
        observations[i] = o;
      }
      const observedAccountInsolvency = end.equity <= 0 || marks.some(m => m.equityBefore <= 0 || m.equityAfter <= 0);
      const observedEconomicInsolvency = observations.some((o, i) => !(carry && i === 0) && o.economicEquity !== null &&
        (o.economicEquity <= 0 || o.preFlowMarks.some(m => m.equityBefore - cumulativeCost(m.at) <= 0 || m.equityAfter - cumulativeCost(m.at) <= 0)));
      const accountInsolvent = old.insolvency.account || observedAccountInsolvency;
      const economicInsolvent = old.insolvency.economic || observedEconomicInsolvency;
      const returnsAccountComplete = (carry?.accountHistoryComplete ?? true) && observations.length >= 2 && observations.slice(1).every(o => o.accountReturn !== null) && !accountInsolvent;
      const returnsEconomicComplete = !economicRestatementRequired && (carry?.economicHistoryComplete ?? true) && observations.length >= 2 && observations.slice(1).every(o => o.economicReturn !== null) && !economicInsolvent;
      const observationsHash = old.archiveIndex?.segments.length ? netLedgerDigest({ archiveHead: old.archiveIndex.head, activeObservations: observations }) : netLedgerDigest(observations);
      let closedCount = 0, closedGrid = carry?.comparablePeriodGrid ?? true;
      let closedReturns = carry?.economicHistoryComplete ?? true, closedGrowth = carry?.economicGrowth ?? 1;
      for (let i = 0; i < observations.length; i++) {
        const o = observations[i]!;
        if (o.economicEquity === null || economicallyCoveredThrough === null || o.at > economicallyCoveredThrough) break;
        closedCount++;
        if (i > 0) {
          closedGrid = closedGrid && Math.abs(o.at - observations[i - 1]!.at - this.policy.performanceIntervalMs) <= this.policy.performanceToleranceMs;
          closedReturns = closedReturns && o.economicReturn !== null;
          if (o.economicReturn !== null) closedGrowth *= 1 + o.economicReturn;
        }
      }
      const closedLast = closedCount ? observations[closedCount - 1]! : null;
      const closedTotal = closedCount ? (old.archiveIndex?.observationCount ?? 0) + closedCount : 0;
      const closedEconomic: Json = { from: closedLast === null ? null : baseline.at,
        through: closedLast?.at ?? null, costCoverageThrough: economicallyCoveredThrough,
        knownAt: closedCount ? now : null, costReceiptKnownAt: costs.coverage?.known_at ?? null,
        observationCount: closedTotal, intervalCount: Math.max(0, closedTotal - 1), activeObservationCount: closedCount,
        accountNetPnlUsd: closedLast === null ? null : closedLast.equity - baseline.equity - closedLast.cumulativeExternalFlowUsd,
        economicNetPnlUsd: closedLast === null ? null : closedLast.equity - baseline.equity - closedLast.cumulativeExternalFlowUsd - closedLast.cumulativeExternalCostUsd!,
        totalReturnEconomic: closedTotal >= 2 && closedReturns && !economicInsolvent ? closedGrowth - 1 : null,
        completeReturns: closedTotal >= 2 && closedReturns && !economicInsolvent,
        comparablePeriodGrid: closedGrid, latestUncoveredAt: closedCount < observations.length ? now : null,
        evidenceHash: closedCount === observations.length ? observationsHash : closedCount ? netLedgerDigest(observations.slice(0, closedCount)) : null };
      let brokerAccrualCoverage = old.brokerAccrualCoverage ?? null;
      let brokerAccrualLinkedCosts: Json[] = old.brokerAccrualLinkedCosts ?? [];
      if (rawCosts !== null && typeof rawCosts === "object" && (rawCosts as Json).broker_accrual_coverage &&
          !["INVALID", "MISSING", "REJECTED_BY_LEDGER"].includes(costSource.status)) {
        brokerAccrualCoverage = structuredClone((rawCosts as Json).broker_accrual_coverage);
        const ids = new Set(brokerAccrualCoverage?.cost_ids ?? []);
        brokerAccrualLinkedCosts = structuredClone((rawCosts as Json).entries.filter((c: Json) => ids.has(c.id))
          .map((c: Json) => ({ ...c, at: timestamp(c.at, "COST_TIME_INVALID"), amount_usd: finite(c.amount_usd, "COST_AMOUNT_UNKNOWN") })));
      }
      const accrualAt = (through: number | null): Json => {
        if (through === null || economicRestatementRequired) return { verified: false, amountUsd: null,
          reason: economicRestatementRequired ? "ECONOMIC_RESTATEMENT_REQUIRED" : "NO_CLOSED_ECONOMIC_PERIOD", sourceAuthenticityVerified: false };
        try { return verifyBrokerAccrualCoverage(brokerAccrualCoverage, brokerAccrualLinkedCosts, this.accountId, now, baseline.at, through); }
        catch (error) { return { verified: false, amountUsd: null,
          reason: error instanceof CostReceiptError ? error.code : "BROKER_ACCRUAL_DOCUMENT_INVALID", sourceAuthenticityVerified: false }; }
      };
      const currentAccruals = accrualAt(now), closedAccruals = accrualAt(closedLast?.at ?? null);
      closedEconomic.brokerAccruals = closedAccruals;
      const blockers = [];
      if (!costs.complete) blockers.push(costs.reason ?? "EXTERNAL_COST_COVERAGE_MISSING");
      if (!initial && !returnsAccountComplete) blockers.push("FLOW_ADJUSTED_ACCOUNT_RETURN_INCOMPLETE");
      if (!initial && !returnsEconomicComplete) blockers.push("FLOW_ADJUSTED_ECONOMIC_RETURN_INCOMPLETE");
      if (accountInsolvent || economicInsolvent) blockers.push("INSOLVENCY_OBSERVED_NO_CAPITAL_RESET");
      const next: LedgerState = { ...old, status: costs.complete ? "OBSERVED_ECONOMIC_NET" : "OBSERVED_ACCOUNT_NET",
        lastAttempt: now, lastSuccess: now, reconciled: true, economicComplete: costs.complete,
        returnComplete: returnsEconomicComplete, blockers, queryFrom: old.queryFrom ?? from, baseline, activities,
        externalCosts: costs.entries, costCoverage: costs.coverage, observations, closedEconomic,
        costSource, economicRestatementRequired, brokerAccrualCoverage, brokerAccrualLinkedCosts,
        accounting: { ...old.accounting, initialEquityUsd: baseline.equity, finalEquityUsd: end.equity,
          openPositionMarketValueUsd: end.positions.reduce((n, p) => n + p.marketValueUsd, 0),
          accountNetPnlUsd: end.equity - baseline.equity - totalFlow,
          economicNetPnlUsd: costs.complete ? end.equity - baseline.equity - totalFlow - cumulativeCost(now) : null,
          externalFlowsUsd: totalFlow, externalCostsUsd: costs.complete ? cumulativeCost(now) : null,
          reportedAccountFeesUsd: (carry?.reportedAccountFeesUsd ?? 0) + included.filter(a => a.classification === "FEE").reduce((n, a) => n - a.cashDeltaUsd!, 0),
          reportedAccountIncomeAndFinancingUsd: (carry?.reportedAccountIncomeAndFinancingUsd ?? 0) + included.filter(a => a.classification === "ACCOUNT_CASH").reduce((n, a) => n + a.cashDeltaUsd!, 0),
          totalReturnAccount: returnsAccountComplete ? observations.slice(1).reduce((g, o) => g * (1 + o.accountReturn!), carry?.accountGrowth ?? 1) - 1 : null,
          totalReturnEconomic: returnsEconomicComplete ? observations.slice(1).reduce((g, o) => g * (1 + o.economicReturn!), carry?.economicGrowth ?? 1) - 1 : null,
          economicCostBasis: costs.complete ? "DECLARED_EXTERNAL_COSTS_PLUS_BROKER_NAV" : null,
          economicNetPnlClassification: costs.complete ? "ESTIMATION_FROM_REPORTED_NAV_AND_DECLARED_COSTS" : null,
          economicCompletenessScope: currentAccruals.verified ? "REPORTED_AND_DECLARED_WITH_DOCUMENT_BOUND_BROKER_ACCRUALS_NOT_EXTERNALLY_AUTHENTICATED" : "REPORTED_AND_DECLARED_AS_OF_OBSERVATION_NOT_UNREPORTED_BROKER_ACCRUALS",
          unreportedBrokerAccrualsUsd: currentAccruals.amountUsd, unreportedBrokerAccrualsVerified: currentAccruals.verified,
          brokerAccrualVerification: currentAccruals,
          feesAlreadyInNav: true, spreadAndSlippageAlreadyInExecutionPrices: true },
        reconciliation,
        coverage: { afterCreatedAt: from, untilCreatedAt: queryThrough, paginationComplete: true,
          pages: receipt.pages, activityCount: (old.archiveIndex?.activityCount ?? 0) + activities.length,
          activeActivityCount: activities.length, postBaselineActivityCount: included.length,
          comparablePeriodGrid: (old.coverage.comparablePeriodGrid ?? true) && (!previous ||
            Math.abs(now - previous.at - this.policy.performanceIntervalMs) <= this.policy.performanceToleranceMs),
          baselineScope: "FIRST_RECONCILED_OBSERVATION_NOT_HISTORICAL_ACCOUNT_INCEPTION",
          expenseInterval: "STRICTLY_AFTER_BASELINE_THROUGH_OBSERVATION",
          lateActivityHandling: this.archive.enabled ? "COMPLETE_CREATED_AT_WINDOWS_WITH_OVERLAP_AND_ARCHIVED_ID_DEDUPLICATION; SETTLEMENT_DATE_NOT_A_WATERMARK" : "FULL_RESCAN_FROM_BASELINE_DAY_CREATED_AT_NOT_SETTLEMENT_DATE" },
        insolvency: { account: accountInsolvent, economic: economicInsolvent,
          firstObservedAt: old.insolvency.firstObservedAt ?? (accountInsolvent || economicInsolvent ? now : null) },
        lastFailure: null,
        evidence: { source: "ALPACA_ACCOUNT_ACTIVITIES_AND_SNAPSHOTS", authenticity: "NOT_INDEPENDENTLY_VERIFIED",
          executionNature: this.config.executionNature ?? "UNVERIFIED", receiptHash: netLedgerDigest(receipt),
          activitiesHash: netLedgerDigest(activities), observationsHash,
          costsHash: netLedgerDigest(costs.entries), configHash: old.policyHash,
          observedAt: now, knownAt: now, marketClockSynchronization: null,
          economicRestatement: restatedAt.length ? { knownAt: now, observationCount: restatedAt.length,
            from: restatedAt[0], through: restatedAt.at(-1),
            previousObservationsHash: old.evidence.observationsHash ?? null,
            reason: "COST_COVERAGE_BECAME_KNOWN_OR_NEW_LATE_COST_RECEIPTS" } : null,
          snapshotTimeBasis: "LOCAL_RECEIPT_CLOCK_NOT_MARKET_TIMESTAMP", financialAdvantageDemonstrated: false },
      };
      await this.commit(next, old.integrity);
      return this.view(now);
    } catch (error) {
      const code = error instanceof NetLedgerError || error instanceof NetArchiveError ? error.code : "LEDGER_SOURCE_READ_FAILED";
      if (code === "LEDGER_CONCURRENT_REVISION") this.loaded = false;
      this.volatileError = { code, at: now, persisted: false };
      if (acquired && this.loaded && !["LEDGER_PERSISTENCE_FAILURE", "LEDGER_PERSISTENCE_REJECTED", "LEDGER_CONCURRENT_REVISION"].includes(code)) {
        const failed: LedgerState = { ...this.state, status: "BLOCKED", lastAttempt: now,
          reconciled: false, economicComplete: false, returnComplete: false, blockers: [code],
          lastFailure: { code, at: now, detail: error instanceof NetLedgerError || error instanceof NetArchiveError ? error.detail : {},
            receiptHash: netLedgerDigest(receipt), receipt, preservedLastSuccessfulCurve: true } };
        try { await this.commit(failed, this.state.integrity); }
        catch { this.volatileError = { code: "LEDGER_PERSISTENCE_FAILURE", at: now, persisted: false }; }
      }
      throw error instanceof NetLedgerError ? error : new NetLedgerError(code);
    } finally {
      if (acquired) {
        try { await this.store.lease(this.key + "-writer", true); }
        catch { this.volatileError = { code: "LEDGER_LEASE_RELEASE_FAILED", at: now, persisted: false }; }
      }
      this.busy = false;
      writers.delete(this.key);
    }
  }

  view(now = Date.now(), includeRows = false): Json {
    const s = this.state;
    const out: Json = includeRows ? structuredClone(s) : structuredClone({
      schema: s.schema, accountId: s.accountId, policyHash: s.policyHash, revision: s.revision,
      status: s.status, lastAttempt: s.lastAttempt, lastSuccess: s.lastSuccess, persisted: s.persisted,
      reconciled: s.reconciled, economicComplete: s.economicComplete, returnComplete: s.returnComplete,
      blockers: s.blockers, baseline: s.baseline === null ? null : {
        at: s.baseline.at, equity: s.baseline.equity, cash: s.baseline.cash,
        sourceHash: s.baseline.sourceHash, positions_count: s.baseline.positions.length,
      },
      accounting: s.accounting, closedEconomic: s.closedEconomic, reconciliation: s.reconciliation, coverage: s.coverage,
      insolvency: s.insolvency, evidence: s.evidence, integrity: s.integrity,
      costSource: s.costSource ?? null, economicRestatementRequired: s.economicRestatementRequired ?? false,
      brokerAccrualCoverage: s.brokerAccrualCoverage ? { from: s.brokerAccrualCoverage.from, through: s.brokerAccrualCoverage.through,
        known_at: s.brokerAccrualCoverage.known_at, reference: s.brokerAccrualCoverage.reference,
        document_sha256: s.brokerAccrualCoverage.document?.sha256 ?? null,
        sourceAuthenticityVerified: false } : null,
      costCoverage: s.costCoverage, lastFailure: s.lastFailure === null ? null : {
        code: s.lastFailure.code, at: s.lastFailure.at, receiptHash: s.lastFailure.receiptHash,
        preservedLastSuccessfulCurve: true,
      },
    });
    out.observations_count = (s.archiveIndex?.observationCount ?? 0) + s.observations.length;
    out.activities_count = (s.archiveIndex?.activityCount ?? 0) + s.activities.length;
    out.external_costs_count = (s.archiveIndex?.costCount ?? 0) + s.externalCosts.length;
    out.active_observations_count = s.observations.length;
    out.archive = { ...this.archive.summary(s.archiveIndex), verified: this.archiveVerifiedAt !== null,
      verifiedAt: this.archiveVerifiedAt, activeObservations: s.observations.length, totalObservations: out.observations_count };
    if (includeRows) out.rowsScope = s.archiveIndex?.segments.length ? "ACTIVE_WINDOW_ONLY_USE_EXPORT_HISTORY_FOR_COMPLETE_RECORDS" : "COMPLETE_RETAINED_HISTORY";
    out.receiptAgeMs = out.lastSuccess === null ? null : Math.max(0, now - out.lastSuccess);
    out.accountingPeriod = out.baseline === null ? null : { from: out.baseline.at, through: out.lastSuccess };
    out.sourceAuthenticityVerified = false;
    out.authorizesOrders = false;
    out.marketDataFreshnessVerified = false;
    if (this.volatileError) {
      out.status = "ERROR"; out.persisted = false; out.reconciled = false;
      out.economicComplete = false; out.returnComplete = false;
      out.blockers = [this.volatileError.code]; out.lastAttempt = this.volatileError.at;
    } else if (out.lastSuccess !== null && now - out.lastSuccess > this.policy.maxAgeMs) {
      out.status = "STALE"; out.reconciled = false; out.economicComplete = false; out.returnComplete = false;
      out.blockers = [...out.blockers, "LEDGER_RECEIPT_STALE"];
    }
    out.performanceInputStatus = this.performanceReadiness(now);
    return out;
  }

  summary(now = Date.now()): Json { return this.view(now); }
  exportState(now = Date.now()): Json { return this.view(now, true); }

  private performanceReadiness(now: number): string {
    if (this.volatileError || !this.state.reconciled || !this.state.persisted || this.state.lastSuccess === null || now - this.state.lastSuccess > this.policy.maxAgeMs) return "WAIT_RECONCILED_CURRENT_LEDGER";
    if (!this.state.closedEconomic.completeReturns) return "WAIT_ECONOMIC_RETURN_EVIDENCE";
    if (this.state.closedEconomic.observationCount < 3) return "WAIT_AT_LEAST_TWO_RETURN_PERIODS";
    if (this.state.insolvency.account || this.state.insolvency.economic) return "INSOLVENCY";
    if (!this.state.closedEconomic.comparablePeriodGrid) return "WAIT_COMPARABLE_PERIOD_GRID";
    if (this.state.archiveIndex?.segments.length) return this.materializationStatus ?? "WAIT_ARCHIVE_MATERIALIZATION_REQUIRED";
    return "DIAGNOSTIC_INPUT_AVAILABLE";
  }

  performanceInput(now = Date.now()): Json | null {
    if (this.performanceReadiness(now) !== "DIAGNOSTIC_INPUT_AVAILABLE") return null;
    const observations = this.state.observations.slice(0, this.state.closedEconomic.observationCount);
    return this.makePerformanceInput(this.state, observations, this.state.activities);
  }

  private makePerformanceInput(state: LedgerState, observations: Observation[], activities: Activity[]): Json {
    const prefixIds = new Set(observations.flatMap(o => o.activityIds));
    const prefixFees = activities.filter(a => !a.baselineIncluded && prefixIds.has(a.id) && a.classification === "FEE")
      .reduce((n, a) => n - a.cashDeltaUsd!, 0);
    return {
      origin: this.config.executionNature === "SYNTHETIC_ENGINEERING_ONLY" ? "SYNTHETIC_ENGINEERING_ONLY" : "OBSERVED",
      return_basis: "NET_FLOW_ADJUSTED", execution_nature: this.config.executionNature ?? "UNVERIFIED",
      // This worker schema requires periods_per_year. One is a diagnostic unit,
      // not an inferred exchange calendar; this sampling forbids annualization.
      sampling: "FIXED_INTERVAL_OBSERVATIONS", periods_per_year: 1,
      risk_free_annual: 0, target_annual: 0, rate_basis: "ASSUMED_ZERO_FOR_DIAGNOSTIC",
      annualization_authorized: false, declared_interval_ms: this.policy.performanceIntervalMs,
      initial_at: new Date(observations[0]!.at).toISOString(),
      initial_equity: observations[0]!.economicEquity,
      times: observations.slice(1).map(o => new Date(o.at).toISOString()),
      returns: observations.slice(1).map(o => o.economicReturn),
      cashflows_confirmed: true, net_costs_confirmed: false,
      reported_costs_reconciled: true, declared_external_costs_covered: true,
      net_costs_status: state.closedEconomic.brokerAccruals?.verified ?
        "REPORTED_AND_DECLARED_WITH_DOCUMENT_BOUND_ACCRUALS_FULL_COST_BREAKDOWN_NOT_CERTIFIED" : "REPORTED_AND_DECLARED_ONLY_UNREPORTED_ACCRUALS_UNKNOWN",
      broker_accrual_coverage: state.closedEconomic.brokerAccruals ?? null,
      cost_reporting: { total_costs_usd: null, reported_broker_costs_usd: prefixFees,
        declared_external_costs_usd: observations.at(-1)!.cumulativeExternalCostUsd,
        scope: "REPORTED_FEE_PTC_PTR_DIVFEE_CFEE_NET_AND_DECLARED_EXTERNAL_COSTS; UNREPORTED_ACCRUALS_UNKNOWN; FINANCING_AND_DIVIDENDS_REMAIN_IN_NAV_NOT_RECLASSIFIED_AS_FEES",
        costs_already_in_returns: true, does_not_authorize_additional_cost_subtraction: true },
      confirmation_scope: "RECONCILED_ACCOUNT_AND_DECLARED_COST_COVERAGE_NOT_SOURCE_AUTHENTICATION",
      account_net_pnl_usd: state.closedEconomic.accountNetPnlUsd,
      economic_net_pnl_usd: state.closedEconomic.economicNetPnlUsd,
      historical_closed_prefix: true, coverage_through: state.closedEconomic.through,
      cost_coverage_through: state.closedEconomic.costCoverageThrough,
      knowledge_at: state.lastSuccess, latest_uncovered_at: state.closedEconomic.latestUncoveredAt,
      current_account_net_pnl_usd: state.accounting.accountNetPnlUsd,
      current_economic_net_pnl_usd: state.accounting.economicNetPnlUsd,
      economic_prefix_hash: state.archiveIndex?.segments.length ? netLedgerDigest(observations) : state.closedEconomic.evidenceHash,
      source_authenticity_verified: false, source_receipt_hash: state.integrity,
      source_evidence: state.evidence, observation_count: observations.length,
      archive_head: state.archiveIndex?.head ?? null, historical_scope: "COMPLETE_CLOSED_PREFIX_FROM_ORIGINAL_BASELINE",
      financial_advantage_demonstrated: false, trade_authorization: false,
    };
  }

  async exportHistory(offset = 0, limit = 1000): Promise<Json> {
    if (!Number.isSafeInteger(offset) || offset < 0 || !Number.isSafeInteger(limit) || limit < 1 || limit > 5000) fail("LEDGER_EXPORT_PAGE_INVALID");
    if (!this.loaded) await this.load();
    const state = this.state, refs: Json[] = state.archiveIndex?.segments ?? [];
    const total = refs.reduce((n, r) => n + 1 + r.observations + r.activities + r.costs, 0) +
      1 + state.observations.length + state.activities.length + state.externalCosts.length;
    if (offset > total) fail("LEDGER_EXPORT_OFFSET_OUT_OF_RANGE");
    const records: Json[] = []; let position = 0;
    try {
      for (const ref of refs) {
        const count = 1 + ref.observations + ref.activities + ref.costs;
        if (offset < position + count && offset + limit > position) {
          const segment = await this.archive.read(ref);
          records.push(...historyRecords(ref.key, "ARCHIVE", segment).slice(Math.max(0, offset - position), offset + limit - position));
        }
        position += count; await new Promise<void>(resolve => setImmediate(resolve));
      }
      if (offset + limit > position) records.push(...historyRecords(this.key, "CONTROL", state)
        .slice(Math.max(0, offset - position), offset + limit - position));
      if (this.state.integrity !== state.integrity) fail("LEDGER_EXPORT_REVISION_CHANGED");
      return { schema: "HARPOON_NET_HISTORY_PAGE_1", account_id: this.accountId, ledger_integrity: state.integrity,
        archive_head: state.archiveIndex?.head ?? "GENESIS", offset, total_records: total,
        next_offset: offset + records.length < total ? offset + records.length : null,
        complete_export: offset === 0 && records.length === total,
        records: structuredClone(records), sourceAuthenticityVerified: false, authorizesOrders: false,
        offset_unit: "HEADER_OBSERVATION_ACTIVITY_COST_RECORDS" };
    } catch (error) {
      if (error instanceof NetArchiveError) {
        this.archiveVerifiedAt = null;
        this.volatileError = { code: error.code, at: Date.now(), persisted: false };
      }
      throw error;
    }
  }

  async performanceInputWithArchive(now = Date.now(), maxObservations = 100000): Promise<Json | null> {
    if (!this.state.archiveIndex?.segments.length) return this.performanceInput(now);
    this.materializationStatus = null;
    const readiness = this.performanceReadiness(now);
    if (readiness !== "WAIT_ARCHIVE_MATERIALIZATION_REQUIRED") return null;
    if (this.state.economicRestatementRequired || !this.state.archiveIndex.boundary.economicHistoryComplete) {
      this.materializationStatus = "WAIT_ARCHIVED_ECONOMIC_RESTATEMENT"; return null;
    }
    const configured = this.config.maxMaterializationBytes ?? 32 * 1024 * 1024;
    if (!Number.isSafeInteger(maxObservations) || maxObservations < 3 || maxObservations > 100000 ||
        !Number.isSafeInteger(configured) || configured < 1024 || configured > 64 * 1024 * 1024) fail("LEDGER_MATERIALIZATION_CONFIG_INVALID");
    const state = this.state;
    const rows = state.archiveIndex!.observationCount + state.observations.length;
    const bytes = state.archiveIndex!.segments.reduce((n: number, r: Json) => n + r.bytes, 0) + canonicalBytes(state);
    if (rows > maxObservations || bytes > configured) {
      this.materializationStatus = "WAIT_OFFLINE_MATERIALIZATION_BUDGET"; return null;
    }
    const observations: Observation[] = [], activities: Activity[] = [];
    try {
      for (const ref of state.archiveIndex!.segments) {
        const segment = await this.archive.read(ref);
        observations.push(...segment.observations); activities.push(...segment.activities);
        await new Promise<void>(resolve => setImmediate(resolve));
      }
      observations.push(...state.observations); activities.push(...state.activities);
      if (this.state.integrity !== state.integrity) {
        this.materializationStatus = "WAIT_LEDGER_REVISION_CHANGED"; return null;
      }
      const prefix = observations.slice(0, state.closedEconomic.observationCount);
      if (prefix.length !== state.closedEconomic.observationCount || prefix[0]?.at !== state.baseline?.at ||
          prefix.some((o, i) => o.economicEquity === null || (i > 0 && (o.economicReturn === null || o.at <= prefix[i - 1]!.at)))) fail("LEDGER_ARCHIVED_PERFORMANCE_INCOMPLETE");
      this.archiveVerifiedAt = now; this.materializationStatus = "DIAGNOSTIC_ARCHIVE_MATERIALIZATION_AVAILABLE";
      return { ...this.makePerformanceInput(state, prefix, activities), materialized_at: now,
        materialization_bytes: bytes, materialization_limit_bytes: configured,
        materialization_limit_observations: maxObservations };
    } catch (error) {
      this.archiveVerifiedAt = null;
      this.volatileError = { code: error instanceof NetArchiveError || error instanceof NetLedgerError ? error.code : "LEDGER_ARCHIVE_VERIFICATION_FAILED", at: now, persisted: false };
      throw error;
    }
  }
}
