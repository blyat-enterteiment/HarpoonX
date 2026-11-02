/**
 * Conservative, immutable reservations for a modeled funded portfolio.
 *
 * This is not an order manager or broker ledger. Amounts are approved ex-ante
 * ceilings, expressed in USD. No price, future profit or fill price is an input.
 * An entire reservation remains encumbered until an observed complete close
 * or an explicit modeled unfilled resolution. An unfilled resolution is never
 * admissible after any exposure has been observed.
 * Partial exposure observations never release risk, notional or cash headroom.
 */
export interface FundedReservation {
  id: string;
  symbol: string;
  decisionAt: number;
  quantity: number;
  riskUsd: number;
  notionalUsd: number;
  cashUsd: number;
}

export interface FundedReservationObservation {
  id: string;
  kind: "OPENED" | "CLOSED" | "NO_FILL";
  /** Effective modeled event time, distinct from when it becomes known. */
  at: number;
  knownAt: number;
  remainingQuantity: number;
  pendingQuantity: number;
}

export interface FundedReservationRecord extends FundedReservation {
  observations: FundedReservationObservation[];
}

export interface FundedReservationBook {
  schema: "HARPOON_FUNDED_RESERVATIONS_1";
  reservations: FundedReservationRecord[];
}

export interface FundedReservationCapacity {
  /** The caller's causal, authorized equity base, including any capital cap. */
  equity: number;
  /**
   * Cash pool BEFORE deducting this book's reservations. For the conservative
   * replay this is initial cash plus the net result of fully closed campaigns.
   * Do not pass a broker cash balance that already subtracts these purchases.
   */
  cashAvailableUsd: number;
  riskFraction: number;
  openRiskFraction: number;
  grossFraction: number;
  assetFraction: number;
}

const SCHEMA = "HARPOON_FUNDED_RESERVATIONS_1" as const;
const EPSILON_USD = 1e-8;

export class FundedReservationError extends Error {
  readonly economicPnlUsd = null;
  constructor(
    readonly code: string,
    readonly details: Record<string, unknown>,
  ) {
    // Preserve the incident at a worker boundary; never silently discard a
    // conflicting record or a newly reported residual position.
    super(code + ": " + JSON.stringify(details));
    this.name = "FundedReservationError";
  }
}

function need(ok: boolean, code: string, details: Record<string, unknown>) {
  if (!ok) throw new FundedReservationError(code, details);
}

const positive = (v: number) => typeof v === "number" && Number.isFinite(v) && v > 0;
const nonnegative = (v: number) => typeof v === "number" && Number.isFinite(v) && v >= 0;
const time = (v: number) => Number.isSafeInteger(v) && v >= 0;

function copyReservation(r: FundedReservation): FundedReservation {
  return { id: r.id, symbol: r.symbol, decisionAt: r.decisionAt, quantity: r.quantity,
    riskUsd: r.riskUsd, notionalUsd: r.notionalUsd, cashUsd: r.cashUsd };
}

function copyObservation(o: FundedReservationObservation): FundedReservationObservation {
  return { id: o.id, kind: o.kind, at: o.at, knownAt: o.knownAt,
    remainingQuantity: o.remainingQuantity, pendingQuantity: o.pendingQuantity };
}

function validateReservation(r: FundedReservation) {
  need(typeof r?.id === "string" && r.id.length > 0 && typeof r.symbol === "string" &&
    r.symbol.length > 0 && r.symbol.trim() === r.symbol && time(r.decisionAt) &&
    Number.isSafeInteger(r.quantity) && r.quantity > 0 && positive(r.riskUsd) &&
    positive(r.notionalUsd) && positive(r.cashUsd) && r.cashUsd + EPSILON_USD >= r.notionalUsd,
  "INVALID_EX_ANTE_RESERVATION", { reservation: copyReservation(r) });
}

function validateObservation(o: FundedReservationObservation, r: FundedReservation) {
  need(o?.id === r.id && (o.kind === "OPENED" || o.kind === "CLOSED" || o.kind === "NO_FILL") &&
    time(o.at) && time(o.knownAt) && o.at >= r.decisionAt && o.knownAt >= o.at &&
    Number.isSafeInteger(o.remainingQuantity) && o.remainingQuantity >= 0 &&
    Number.isSafeInteger(o.pendingQuantity) && o.pendingQuantity >= 0 &&
    o.remainingQuantity + o.pendingQuantity <= r.quantity,
  "INVALID_RESERVATION_OBSERVATION", { reservation: copyReservation(r), observation: copyObservation(o) });
  if (o.kind === "CLOSED" || o.kind === "NO_FILL")
    need(o.remainingQuantity === 0 && o.pendingQuantity === 0,
      "CLOSE_WITH_RESIDUAL_EXPOSURE", { observation: copyObservation(o) });
  else need(o.remainingQuantity > 0, "OPEN_WITHOUT_OBSERVED_EXPOSURE", { observation: copyObservation(o) });
}

function validateBook(book: FundedReservationBook) {
  need(book?.schema === SCHEMA && Array.isArray(book.reservations), "RESERVATION_BOOK_SCHEMA", {});
  const seen = new Set<string>();
  let priorDecision = -1;
  for (const r of book.reservations) {
    validateReservation(r);
    need(!seen.has(r.id) && r.decisionAt >= priorDecision && Array.isArray(r.observations),
      "RESERVATION_BOOK_ID_OR_CHRONOLOGY", { id: r.id });
    seen.add(r.id); priorDecision = r.decisionAt;
    let opened = false, closed = false, priorKnown = r.decisionAt, priorEffective = r.decisionAt;
    const keys = new Set<string>();
    for (const o of r.observations) {
      validateObservation(o, r);
      const key = o.kind + ":" + o.at + ":" + o.knownAt;
      need(!keys.has(key) && o.knownAt >= priorKnown && o.at >= priorEffective && !closed,
        "RESERVATION_OBSERVATION_CHRONOLOGY", { id: r.id, observation: copyObservation(o) });
      if (o.kind === "CLOSED") need(opened, "CLOSE_WITHOUT_OBSERVED_OPEN", { id: r.id });
      if (o.kind === "NO_FILL") need(!opened, "NO_FILL_AFTER_OBSERVED_OPEN", { id: r.id });
      opened = opened || o.kind === "OPENED";
      closed = o.kind === "CLOSED" || o.kind === "NO_FILL";
      priorKnown = o.knownAt; priorEffective = o.at; keys.add(key);
    }
  }
}

function copyBook(book: FundedReservationBook): FundedReservationBook {
  return { schema: SCHEMA, reservations: book.reservations.map(r => ({ ...copyReservation(r),
    observations: r.observations.map(copyObservation) })) };
}

export function emptyFundedReservationBook(): FundedReservationBook {
  return { schema: SCHEMA, reservations: [] };
}

export function snapshotFundedReservations(book: FundedReservationBook, at: number) {
  validateBook(book);
  need(time(at), "RESERVATION_SNAPSHOT_TIME", { at });
  const retained = book.reservations.filter(r => r.decisionAt <= at).flatMap(r => {
    const observed = r.observations.filter(o => o.at <= at && o.knownAt <= at).at(-1);
    if (observed?.kind === "CLOSED" || observed?.kind === "NO_FILL") return [];
    return [{ ...copyReservation(r), state: observed ? "OPENED" as const : "PENDING" as const,
      observedAt: observed?.at ?? null, observationKnownAt: observed?.knownAt ?? null,
      observedRemainingQuantity: observed?.remainingQuantity ?? null,
      observedPendingQuantity: observed?.pendingQuantity ?? null }];
  });
  const riskUsd = retained.reduce((n, r) => n + r.riskUsd, 0);
  const notionalUsd = retained.reduce((n, r) => n + r.notionalUsd, 0);
  const cashUsd = retained.reduce((n, r) => n + r.cashUsd, 0);
  need([riskUsd, notionalUsd, cashUsd].every(nonnegative), "NONFINITE_AGGREGATE_RESERVATION", { at });
  return { at, riskUsd, notionalUsd, cashUsd,
    symbols: [...new Set(retained.map(r => r.symbol))].sort(),
    pending: retained.filter(r => r.state === "PENDING").length,
    opened: retained.filter(r => r.state === "OPENED").length,
    reservations: retained };
}

export function reserveFundedEntry(
  book: FundedReservationBook,
  reservation: FundedReservation,
  capacity: FundedReservationCapacity,
) {
  validateBook(book); validateReservation(reservation);
  const r = copyReservation(reservation);
  const duplicate = book.reservations.find(x => x.id === r.id);
  if (duplicate) {
    need(JSON.stringify(copyReservation(duplicate)) === JSON.stringify(r),
      "CONFLICTING_RESERVATION_ID", { existing: copyReservation(duplicate), proposed: r });
    return { status: "UNCHANGED" as const, reason: null, book: copyBook(book),
      snapshot: snapshotFundedReservations(book, r.decisionAt) };
  }
  need(r.decisionAt >= (book.reservations.at(-1)?.decisionAt ?? -1),
    "RESERVATION_DECISION_REGRESSION", { decisionAt: r.decisionAt });
  need(positive(capacity?.equity) && nonnegative(capacity.cashAvailableUsd) &&
    [capacity.riskFraction, capacity.openRiskFraction, capacity.grossFraction, capacity.assetFraction]
      .every(v => positive(v) && v <= 1) && capacity.riskFraction <= capacity.openRiskFraction &&
    capacity.assetFraction <= capacity.grossFraction,
  "INVALID_RESERVATION_CAPACITY", { capacity });
  const before = snapshotFundedReservations(book, r.decisionAt);
  const reason = before.symbols.includes(r.symbol) ? "SYMBOL_RESERVED"
    : r.riskUsd > capacity.equity * capacity.riskFraction + EPSILON_USD ? "PER_ENTRY_RISK_CAPACITY"
    : r.notionalUsd > capacity.equity * capacity.assetFraction + EPSILON_USD ? "PER_ENTRY_NOTIONAL_CAPACITY"
    : before.riskUsd + r.riskUsd > capacity.equity * capacity.openRiskFraction + EPSILON_USD ? "PORTFOLIO_RISK_CAPACITY"
    : before.notionalUsd + r.notionalUsd > capacity.equity * capacity.grossFraction + EPSILON_USD ? "PORTFOLIO_NOTIONAL_CAPACITY"
    : before.cashUsd + r.cashUsd > capacity.cashAvailableUsd + EPSILON_USD ? "PORTFOLIO_CASH_CAPACITY"
    : null;
  if (reason) return { status: "REFUSED" as const, reason, book: copyBook(book), snapshot: before };
  const next = copyBook(book);
  next.reservations.push({ ...r, observations: [] });
  return { status: "RESERVED" as const, reason: null, book: next,
    snapshot: snapshotFundedReservations(next, r.decisionAt) };
}

/** Record facts in their observed order. No cancellation request releases funds. */
export function recordFundedReservationObservation(
  book: FundedReservationBook,
  observation: FundedReservationObservation,
): FundedReservationBook {
  validateBook(book);
  const r = book.reservations.find(x => x.id === observation.id);
  need(!!r, "OBSERVATION_WITHOUT_RESERVATION", { observation: copyObservation(observation) });
  validateObservation(observation, r!);
  const o = copyObservation(observation);
  const duplicate = r!.observations.find(x => x.kind === o.kind && x.at === o.at && x.knownAt === o.knownAt);
  if (duplicate) {
    need(JSON.stringify(duplicate) === JSON.stringify(o), "CONFLICTING_RESERVATION_OBSERVATION", {
      existing: copyObservation(duplicate), proposed: o });
    return copyBook(book);
  }
  const prior = r!.observations.at(-1);
  need(prior?.kind !== "CLOSED" && prior?.kind !== "NO_FILL", "EXPOSURE_REPORTED_AFTER_COMPLETE_CLOSE", {
    reservation: copyReservation(r!), observation: o, economicPnlUsd: null });
  need(o.knownAt >= (prior?.knownAt ?? r!.decisionAt) && o.at >= (prior?.at ?? r!.decisionAt),
    "RESERVATION_OBSERVATION_REGRESSION", { observation: o });
  if (o.kind === "CLOSED") need(prior?.kind === "OPENED", "CLOSE_WITHOUT_OBSERVED_OPEN", { observation: o });
  if (o.kind === "NO_FILL") need(prior === undefined, "NO_FILL_AFTER_OBSERVED_OPEN", { observation: o });
  const next = copyBook(book);
  next.reservations.find(x => x.id === o.id)!.observations.push(o);
  validateBook(next);
  return next;
}
