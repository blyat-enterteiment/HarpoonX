import { NetArchiveError } from "./net_ledger_archive";
import { CostReceiptError, verifyBrokerAccrualCoverage } from "./cost_receipts";
import { Json } from "./types";

function need(value: unknown, code: string): asserts value { if (!value) throw new NetArchiveError(code); }
function number(value: unknown): number {
  need((typeof value === "number" || typeof value === "string" && value.trim()) && Number.isFinite(Number(value)), "LEDGER_BUNDLE_NUMBER_INVALID");
  return Number(value);
}
function near(actual: unknown, expected: number, tolerance = 1e-7): boolean {
  return typeof actual === "number" && Number.isFinite(actual) && Math.abs(actual - expected) <= tolerance;
}

/** Reconstruct exact stored objects, verify their commitments, then independently
 * replay accounting arithmetic. This authenticates neither broker nor invoices. */
export function verifyLedgerHistoryBundle(pages: Json[], expectedIntegrity: string,
  digest: (value: unknown) => string): Json {
  need(/^[0-9a-f]{64}$/.test(expectedIntegrity) && Array.isArray(pages) && pages.length > 0 && pages.length <= 10000, "LEDGER_BUNDLE_ARGUMENTS_INVALID");
  const containers = new Map<string, { storage: string; value: Json }>();
  let offset = 0, total: number | null = null, active: string | null = null, lastKind = 0, bytes = 0;
  const rank: Json = { HEADER: 0, OBSERVATION: 1, ACTIVITY: 2, COST: 3 };
  for (let pageIndex = 0; pageIndex < pages.length; pageIndex++) {
    const page = pages[pageIndex]!;
    need(page.schema === "HARPOON_NET_HISTORY_PAGE_1" && page.ledger_integrity === expectedIntegrity &&
      page.offset === offset && Number.isSafeInteger(page.total_records) && page.total_records > 0 && page.total_records <= 1000000 &&
      (total === null || page.total_records === total) && Array.isArray(page.records) && page.records.length > 0 && page.records.length <= 5000,
    "LEDGER_BUNDLE_PAGINATION_INVALID");
    total = page.total_records;
    bytes += Buffer.byteLength(JSON.stringify(page)); need(bytes <= 576 * 1024 * 1024, "LEDGER_BUNDLE_BYTE_BOUND");
    for (const record of page.records) {
      need(record && typeof record.container === "string" && record.kind in rank && record.value && typeof record.value === "object" && !Array.isArray(record.value), "LEDGER_BUNDLE_RECORD_INVALID");
      if (record.kind === "HEADER") {
        need(!containers.has(record.container) && ["ARCHIVE", "CONTROL"].includes(record.storage) &&
          !["observations", "activities", "externalCosts"].some(k => k in record.value), "LEDGER_BUNDLE_HEADER_INVALID");
        active = record.container; lastKind = 0;
        containers.set(active!, { storage: record.storage, value: { ...record.value, observations: [], activities: [], externalCosts: [] } });
      } else {
        need(record.container === active && rank[record.kind] >= lastKind, "LEDGER_BUNDLE_RECORD_ORDER_INVALID");
        lastKind = rank[record.kind];
        const field: Json = { OBSERVATION: "observations", ACTIVITY: "activities", COST: "externalCosts" };
        containers.get(active!)!.value[field[record.kind]].push(record.value);
      }
    }
    offset += page.records.length;
    need(page.next_offset === (offset < total! ? offset : null) && offset <= total!, "LEDGER_BUNDLE_PAGINATION_INVALID");
    if (pageIndex < pages.length - 1) need(page.next_offset !== null, "LEDGER_BUNDLE_TRAILING_PAGE");
  }
  need(offset === total && pages.at(-1)!.next_offset === null, "LEDGER_BUNDLE_INCOMPLETE");
  const controls = [...containers.entries()].filter(([, c]) => c.storage === "CONTROL");
  need(controls.length === 1 && active === controls[0]![0], "LEDGER_BUNDLE_CONTROL_INVALID");
  const state = controls[0]![1].value;
  const hash = (row: Json): string => { const copy = { ...row }; delete copy.integrity; return digest(copy); };
  need(state.schema === "HARPOON_NET_LEDGER_1" && state.integrity === expectedIntegrity && hash(state) === expectedIntegrity &&
    typeof state.accountId === "string" && state.baseline, "LEDGER_BUNDLE_CONTROL_INTEGRITY");
  need(pages.every(p => p.account_id === state.accountId), "LEDGER_BUNDLE_ACCOUNT_IDENTITY");
  const observations: Json[] = [], activities: Json[] = [], externalCosts: Json[] = [];
  const refs: Json[] = state.archiveIndex?.segments ?? [];
  need(containers.size === refs.length + 1, "LEDGER_BUNDLE_UNREFERENCED_CONTAINER");
  let previous = "GENESIS", boundary: Json | null = null, count = 0, activityCount = 0, costCount = 0;
  for (let i = 0; i < refs.length; i++) {
    const ref = refs[i]!, container = containers.get(ref.key);
    need(container?.storage === "ARCHIVE", "LEDGER_BUNDLE_SEGMENT_MISSING");
    const segment = container!.value;
    need(segment.schema === "HARPOON_NET_ARCHIVE_SEGMENT_1" && segment.accountId === state.accountId &&
      segment.ledgerPolicyHash === state.policyHash && segment.archivePolicyHash === state.archiveIndex.policyHash &&
      segment.originalBaselineHash === state.baseline.sourceHash && segment.sequence === i + 1 && segment.previous === previous &&
      segment.integrity === ref.hash && hash(segment) === ref.hash && Buffer.byteLength(JSON.stringify(segment)) === ref.bytes &&
      segment.observations.length === ref.observations && segment.activities.length === ref.activities && segment.externalCosts.length === ref.costs,
    "LEDGER_BUNDLE_SEGMENT_INTEGRITY");
    need(segment.observations.length > 0 && segment.observations[0].at === ref.from && segment.observations.at(-1).at === ref.through &&
      segment.boundary?.anchor.at === ref.anchorAt && (!boundary || segment.observations[0].at === boundary.anchor.at &&
      segment.observations[0].sourceHash === boundary.anchor.sourceHash), "LEDGER_BUNDLE_SEGMENT_CONTINUITY");
    observations.push(...segment.observations); activities.push(...segment.activities); externalCosts.push(...segment.externalCosts);
    count += segment.observations.length; activityCount += segment.activities.length; costCount += segment.externalCosts.length;
    previous = ref.hash; boundary = segment.boundary;
  }
  if (refs.length) need(state.archiveIndex.head === previous && state.archiveIndex.observationCount === count &&
    state.archiveIndex.activityCount === activityCount && state.archiveIndex.costCount === costCount &&
    digest(state.archiveIndex.boundary) === digest(boundary) && state.observations[0]?.at === boundary!.anchor.at &&
    state.observations[0]?.sourceHash === boundary!.anchor.sourceHash, "LEDGER_BUNDLE_INDEX_TOTAL_MISMATCH");
  observations.push(...state.observations); activities.push(...state.activities); externalCosts.push(...state.externalCosts);
  need(observations.length > 0 && observations[0]!.at === state.baseline.at &&
    observations[0]!.sourceHash === state.baseline.sourceHash, "LEDGER_BUNDLE_BASELINE_MISMATCH");
  const activityMap = new Map<string, Json>();
  for (const a of activities) {
    need(typeof a.id === "string" && !activityMap.has(a.id) && a.raw?.id === a.id && digest(a.raw) === a.rawHash &&
      Number.isFinite(a.knownAt), "LEDGER_BUNDLE_ACTIVITY_INTEGRITY");
    activityMap.set(a.id, a);
    if (a.baselineIncluded) { need(a.knownAt === state.baseline.at, "LEDGER_BUNDLE_BASELINE_ACTIVITY_TIME"); continue; }
    need(a.currency === "USD" && Number.isFinite(a.cashDeltaUsd), "LEDGER_BUNDLE_ACTIVITY_CASH_UNKNOWN");
    if (a.classification === "FILL") {
      const qty = number(a.raw.qty) * (a.raw.side === "buy" ? 1 : -1);
      need(a.raw.activity_type === "FILL" && ["buy", "sell"].includes(a.raw.side) && a.multiplier > 0 &&
        near(a.quantityDelta, qty) && near(a.cashDeltaUsd, -qty * number(a.raw.price) * a.multiplier), "LEDGER_BUNDLE_FILL_ARITHMETIC");
    } else {
      const types: Json = { EXTERNAL_FLOW: ["CSD", "CSW", "ACATC"], FEE: ["FEE", "PTC", "PTR", "DIVFEE", "CFEE"],
        ACCOUNT_CASH: ["DIV", "DIVNRA", "CGD", "INT", "INTNRA", "INTTW"] };
      need(types[a.classification]?.includes(a.raw.activity_type) && near(a.cashDeltaUsd, number(a.raw.net_amount)) &&
        (a.raw.activity_type !== "CSD" || a.cashDeltaUsd > 0) && (a.raw.activity_type !== "CSW" || a.cashDeltaUsd < 0), "LEDGER_BUNDLE_CASH_ARITHMETIC");
    }
  }
  const costsSeen = new Set<string>(), links = new Set<string>();
  for (const c of externalCosts) {
    need(typeof c.id === "string" && !costsSeen.has(c.id) && Number.isFinite(c.amount_usd) && c.amount_usd >= 0 &&
      Number.isFinite(c.at) && c.known_at >= c.at && typeof c.already_in_account === "boolean", "LEDGER_BUNDLE_COST_INVALID");
    costsSeen.add(c.id);
    if (c.already_in_account) {
      const a = activityMap.get(c.activity_id);
      need(a && !a.baselineIncluded && ["FEE", "ACCOUNT_CASH"].includes(a.classification) &&
        !links.has(c.activity_id) && near(a.cashDeltaUsd, -c.amount_usd, 0.02), "LEDGER_BUNDLE_INCLUDED_COST_LINK_INVALID");
      links.add(c.activity_id);
    } else need(c.activity_id === null, "LEDGER_BUNDLE_EXTERNAL_COST_LINK_INVALID");
  }
  const baseline = state.baseline;
  let cash = number(baseline.cash), flows = 0, fees = 0;
  const inventory = new Map<string, number>(baseline.positions.map((p: Json) => [p.symbol, number(p.quantity)]));
  const assigned = new Set<string>();
  const economicCosts = externalCosts.filter(c => !c.already_in_account && c.at > baseline.at).sort((a, b) => a.at - b.at);
  const costPrefix = [0]; for (const c of economicCosts) costPrefix.push(costPrefix.at(-1)! + c.amount_usd);
  const costAt = (at: number): number => {
    let lo = 0, hi = economicCosts.length;
    while (lo < hi) { const mid = Math.floor((lo + hi) / 2); if (economicCosts[mid]!.at <= at) lo = mid + 1; else hi = mid; }
    return costPrefix[lo]!;
  };
  let costIndex = 0, declared = 0, lastAt = 0, accountInsolvent = false;
  for (let i = 0; i < observations.length; i++) {
    const o = observations[i]!;
    need(Number.isFinite(o.at) && o.at > lastAt && o.sourceReceipt?.account?.id === state.accountId &&
      o.sourceReceipt.account.currency === "USD" && digest(o.sourceReceipt) === o.sourceHash &&
      near(o.equity, number(o.sourceReceipt.account.equity)) && near(o.cash, number(o.sourceReceipt.account.cash)) &&
      Array.isArray(o.positions) && Array.isArray(o.activityIds), "LEDGER_BUNDLE_OBSERVATION_SOURCE");
    lastAt = o.at;
    const periodFlows: Json[] = [];
    for (const id of o.activityIds) {
      const a = activityMap.get(id);
      need(a && !a.baselineIncluded && !assigned.has(id) && a.knownAt <= o.at && (i === 0 || a.knownAt > observations[i - 1]!.at), "LEDGER_BUNDLE_ACTIVITY_ASSIGNMENT");
      assigned.add(id); cash += a.cashDeltaUsd;
      if (a.classification === "EXTERNAL_FLOW") { flows += a.cashDeltaUsd; periodFlows.push(a); }
      if (a.classification === "FEE") fees -= a.cashDeltaUsd;
      if (a.classification === "FILL") inventory.set(a.symbol, (inventory.get(a.symbol) ?? 0) + a.quantityDelta);
    }
    let marked = 0; const symbols = new Set<string>();
    for (const p of o.positions) {
      need(!symbols.has(p.symbol) && Number.isFinite(p.marketValueUsd) && near(p.quantity, inventory.get(p.symbol) ?? 0, 1e-8), "LEDGER_BUNDLE_INVENTORY_RECONCILIATION");
      const raw = o.sourceReceipt.positions.find((r: Json) => r.symbol === p.symbol);
      need(raw && digest(raw) === p.sourceHash && near(p.marketValueUsd, number(raw.market_value)) &&
        near(p.quantity, raw.side === "short" ? -Math.abs(number(raw.qty)) : number(raw.qty), 1e-8), "LEDGER_BUNDLE_POSITION_SOURCE");
      marked += p.marketValueUsd; symbols.add(p.symbol);
    }
    need([...inventory].every(([symbol, qty]) => symbols.has(symbol) || Math.abs(qty) <= 1e-8) &&
      near(o.cash, cash, 0.02) && near(o.equity, cash + marked, 0.05) && near(o.cumulativeExternalFlowUsd, flows, 0.02), "LEDGER_BUNDLE_CASH_NAV_RECONCILIATION");
    while (costIndex < economicCosts.length && economicCosts[costIndex]!.at <= o.at) declared += economicCosts[costIndex++]!.amount_usd;
    if (o.economicEquity !== null) need(near(o.economicEquity, o.equity - declared, 0.02) &&
      near(o.cumulativeExternalCostUsd, declared, 0.02), "LEDGER_BUNDLE_ECONOMIC_NAV_RECONCILIATION");
    need(Array.isArray(o.preFlowMarks), "LEDGER_BUNDLE_PREFLOW_INVALID");
    let markAt = i > 0 ? observations[i - 1]!.at : o.at; const markedFlows = new Set<string>();
    for (const m of o.preFlowMarks) {
      const a = periodFlows.find(f => f.id === m.activityId);
      need(a && a.timePrecision === "INSTANT" && a.at === m.at && m.at > markAt && m.at <= o.at && m.known_at >= m.at &&
        m.known_at <= o.at && !markedFlows.has(m.activityId) && digest(m.evidence) === m.evidenceHash &&
        m.evidence.activityId === m.activityId && m.evidence.at === m.at && m.evidence.equityBefore === m.equityBefore &&
        m.evidence.equityAfter === m.equityAfter && near(m.equityAfter - m.equityBefore, a.cashDeltaUsd, 0.05), "LEDGER_BUNDLE_PREFLOW_BINDING");
      markAt = m.at; markedFlows.add(m.activityId);
    }
    const interval = (start: number, end: number, economic: boolean): number | null => {
      if (start <= 0 || end < 0 || markedFlows.size !== periodFlows.length) return null;
      let growth = 1, capital = start;
      for (const m of o.preFlowMarks) {
        const expense = economic ? costAt(m.at) : 0, before = m.equityBefore - expense, after = m.equityAfter - expense;
        if (capital <= 0 || before < 0 || after <= 0) return null;
        growth *= before / capital; capital = after;
      }
      if (capital <= 0) return null;
      const result = growth * end / capital - 1;
      return Number.isFinite(result) && result >= -1 ? result : null;
    };
    const expectedAccount = i > 0 ? interval(observations[i - 1]!.equity, o.equity, false) : null;
    const expectedEconomic = i > 0 && observations[i - 1]!.economicEquity !== null && o.economicEquity !== null ?
      interval(observations[i - 1]!.economicEquity, o.economicEquity, true) : null;
    need(expectedAccount === null ? o.accountReturn === null : near(o.accountReturn, expectedAccount, 1e-10), "LEDGER_BUNDLE_ACCOUNT_RETURN_MISMATCH");
    need(expectedEconomic === null ? o.economicReturn === null : near(o.economicReturn, expectedEconomic, 1e-10), "LEDGER_BUNDLE_ECONOMIC_RETURN_MISMATCH");
    if (o.equity <= 0) accountInsolvent = true;
  }
  need(activities.filter(a => !a.baselineIncluded).every(a => assigned.has(a.id)), "LEDGER_BUNDLE_UNASSIGNED_ACTIVITY");
  const last = observations.at(-1)!, accountPnl = last.equity - baseline.equity - flows;
  need(near(state.accounting.accountNetPnlUsd, accountPnl, 0.02) && near(state.accounting.externalFlowsUsd, flows, 0.02) &&
    near(state.accounting.reportedAccountFeesUsd, fees, 0.02) && (!accountInsolvent || state.insolvency.account === true), "LEDGER_BUNDLE_ACCOUNT_TOTAL_MISMATCH");
  const covered = state.costCoverage !== null && state.costCoverage.from <= baseline.at && state.costCoverage.through >= last.at &&
    state.costCoverage.known_at <= state.lastSuccess && !state.economicRestatementRequired;
  if (state.accounting.economicNetPnlUsd !== null) need(covered && near(state.accounting.economicNetPnlUsd, accountPnl - declared, 0.02), "LEDGER_BUNDLE_ECONOMIC_TOTAL_MISMATCH");
  const accrualAt = (through: number | null): Json => {
    if (through === null || state.economicRestatementRequired) return { verified: false, amountUsd: null,
      reason: state.economicRestatementRequired ? "ECONOMIC_RESTATEMENT_REQUIRED" : "NO_CLOSED_ECONOMIC_PERIOD", sourceAuthenticityVerified: false };
    try { return verifyBrokerAccrualCoverage(state.brokerAccrualCoverage, externalCosts, state.accountId,
      state.lastSuccess, baseline.at, through); }
    catch (error) { return { verified: false, amountUsd: null,
      reason: error instanceof CostReceiptError ? error.code : "BROKER_ACCRUAL_DOCUMENT_INVALID", sourceAuthenticityVerified: false }; }
  };
  const currentAccruals = accrualAt(last.at), closedAccruals = accrualAt(state.closedEconomic?.through ?? null);
  need(state.accounting.unreportedBrokerAccrualsVerified === currentAccruals.verified &&
    state.accounting.unreportedBrokerAccrualsUsd === currentAccruals.amountUsd, "LEDGER_BUNDLE_BROKER_ACCRUAL_CLAIM_MISMATCH");
  if (state.closedEconomic?.brokerAccruals) need(state.closedEconomic.brokerAccruals.verified === closedAccruals.verified &&
    state.closedEconomic.brokerAccruals.amountUsd === closedAccruals.amountUsd, "LEDGER_BUNDLE_CLOSED_ACCRUAL_CLAIM_MISMATCH");
  return { verified: true, state: structuredClone(state), observations: structuredClone(observations),
    activities: structuredClone(activities), externalCosts: structuredClone(externalCosts),
    from: observations[0]!.at, through: last.at, accountId: state.accountId, archiveHead: previous,
    derived: { reconciled: true, accountNetPnlUsd: accountPnl, declaredExternalCostsUsd: declared,
      economicCoverageComplete: covered, economicNetPnlUsd: covered ? accountPnl - declared : null,
      externalFlowsUsd: flows, reportedAccountFeesUsd: fees, accountInsolvent },
    brokerAccrualsVerified: currentAccruals.verified, brokerAccrualsUsd: currentAccruals.amountUsd,
    brokerAccruals: currentAccruals, closedBrokerAccruals: closedAccruals,
    sourceAuthenticityVerified: false, financialAdvantageDemonstrated: false, authorizesOrders: false };
}
