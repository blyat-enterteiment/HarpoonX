import type { Bar, Json } from "./types";

/** Session labels are diagnostics. They never confer broker/order authority. */
export type SessionPhase =
  | "PREOPEN"
  | "OPENING_90"
  | "MID_SESSION"
  | "PRECLOSE_90"
  | "POSTCLOSE_90"
  | "CLOSED"
  | "UNKNOWN";
export interface SessionContext {
  date: string | null;
  open: number | null;
  close: number | null;
  phase: SessionPhase;
  source: "EXCHANGE_CALENDAR" | "LEGACY_TIME_ONLY_UNVERIFIED" | "NO_SESSION" | "INVALID_CALENDAR";
  calendar_verified: boolean;
  authorizes_orders: false;
  opening_window: boolean;
  preclose_window: boolean;
  reason: string | null;
}

const MINUTE = 60000;
const BAR_MS = 5 * MINUTE;
const CLOSE_BUFFER_MS = 3000; // Preserve the inherited closed-bar safety buffer.
const nyFormat = new Intl.DateTimeFormat("en-CA", {
  timeZone: "America/New_York", year: "numeric", month: "2-digit", day: "2-digit",
  hour: "2-digit", minute: "2-digit", hourCycle: "h23",
});
const localCache = new Map<number, { date: string; minute: number }>();
function nyParts(at: number) {
  const key = Math.floor(at / MINUTE);
  const cached = localCache.get(key);
  if (cached) return cached;
  const parts = Object.fromEntries(nyFormat.formatToParts(new Date(key * MINUTE)).map(p => [p.type, p.value]));
  const value = { date: `${parts.year}-${parts.month}-${parts.day}`, minute: Number(parts.hour) * 60 + Number(parts.minute) };
  if (localCache.size >= 32768) localCache.clear();
  localCache.set(key, value);
  return value;
}

function epoch(value: unknown): number {
  if (typeof value === "number") return value;
  // Do not silently interpret an unzoned source clock in the host's timezone.
  return typeof value === "string" && /T.*(?:Z|[+-]\d{2}:?\d{2})$/i.test(value) ? Date.parse(value) : NaN;
}

function legacyBoundary(date: string, minute: number): number {
  // Convert a NY wall-clock minute using Intl, rather than a fixed UTC offset.
  const target = Date.parse(date + "T00:00:00Z") + minute * MINUTE;
  let at = target;
  for (let i = 0; i < 3; i++) {
    const p = nyParts(at);
    const apparent = Date.parse(p.date + "T00:00:00Z") + p.minute * MINUTE;
    at += target - apparent;
  }
  return at;
}

function boundaries(date: string, calendar: readonly Json[]): { open: number; close: number; verified: boolean } | null {
  if (calendar.length) {
    const rows = calendar.filter(s => s.date === date);
    if (rows.length !== 1) return null;
    const open = epoch(rows[0].open), close = epoch(rows[0].close);
    if (!Number.isFinite(open) || !Number.isFinite(close) || close <= open ||
        nyParts(open).date !== date || nyParts(close - 1).date !== date) return null;
    return { open, close, verified: true };
  }
  const weekday = new Date(date + "T12:00:00Z").getUTCDay();
  if (weekday === 0 || weekday === 6) return null;
  return { open: legacyBoundary(date, 570), close: legacyBoundary(date, 960), verified: false };
}

export function sessionContext(now: number, calendar: readonly Json[] = []): SessionContext {
  const empty: SessionContext = {
    date: null, open: null, close: null, phase: "UNKNOWN", source: "INVALID_CALENDAR",
    calendar_verified: false, authorizes_orders: false,
    opening_window: false, preclose_window: false, reason: "INVALID_DECISION_TIME",
  };
  if (!Number.isFinite(now)) return empty;
  const date = nyParts(now).date, session = boundaries(date, calendar);
  if (!session) {
    const invalid = calendar.some(s => s.date === date);
    return { ...empty, date, phase: invalid ? "UNKNOWN" : "CLOSED",
      source: invalid ? "INVALID_CALENDAR" : "NO_SESSION",
      reason: invalid ? "INVALID_OR_DUPLICATE_SESSION" : "SESSION_NOT_IN_CALENDAR" };
  }
  const { open, close, verified } = session;
  const opening = now >= open && now < Math.min(open + 90 * MINUTE, close);
  const preclose = now >= Math.max(open, close - 90 * MINUTE) && now < close;
  // Short-session overlap has one primary label; flags preserve both memberships.
  const phase: SessionPhase = now < open ? "PREOPEN" : now >= close
    ? now < close + 90 * MINUTE ? "POSTCLOSE_90" : "CLOSED"
    : opening ? "OPENING_90" : preclose ? "PRECLOSE_90" : "MID_SESSION";
  return { date, open, close, phase,
    source: verified ? "EXCHANGE_CALENDAR" : "LEGACY_TIME_ONLY_UNVERIFIED",
    calendar_verified: verified, authorizes_orders: false,
    opening_window: opening, preclose_window: preclose,
    reason: verified ? null : "MISSING_CALENDAR_TIME_FILTER_ONLY" };
}

export function barKnownAt(bar: Bar): number | null {
  const row = bar as Bar & { known_at?: string | number; received?: number };
  if (row.known_at !== undefined) return epoch(row.known_at);
  if (row.received !== undefined) return epoch(row.received);
  return null;
}

/** Sorted, complete, available regular bars. An absent calendar never invents a verified session. */
export function regularClosedBars(
  raw: readonly Bar[], now: number, calendar: readonly Json[] = [], currentOnly = true,
): Bar[] {
  if (!Number.isFinite(now)) return [];
  const today = nyParts(now).date;
  const sessions = new Map<string, ReturnType<typeof boundaries>>();
  const accepted = raw.filter(b => {
    const at = epoch(b.t), known = barKnownAt(b);
    if (!Number.isFinite(at) || at + BAR_MS + CLOSE_BUFFER_MS > now ||
        (known !== null && (!Number.isFinite(known) || known > now))) return false;
    const day = nyParts(at).date;
    if (currentOnly && day !== today) return false;
    if (!sessions.has(day)) sessions.set(day, boundaries(day, calendar));
    const session = sessions.get(day);
    return !!session && at >= session.open && at + BAR_MS <= session.close &&
      (at - session.open) % BAR_MS === 0;
  }).sort((a, b) => Date.parse(a.t) - Date.parse(b.t));
  // Duplicated timestamps are ambiguous, not an extra bar in an opening range.
  const counts = new Map<number, number>();
  for (const bar of accepted) {
    const at = Date.parse(bar.t); counts.set(at, (counts.get(at) || 0) + 1);
  }
  return accepted.filter(b => counts.get(Date.parse(b.t)) === 1);
}

export function contiguousBars(bars: readonly Bar[]): boolean {
  return bars.length > 0 && bars.every((b, i) => i === 0 || Date.parse(b.t) - Date.parse(bars[i - 1].t) === BAR_MS);
}

export function openingRange(bars: readonly Bar[], session: SessionContext): number | null {
  if (session.open === null || session.close === null || session.close - session.open < 3 * BAR_MS) return null;
  const opening = bars.filter(b => Date.parse(b.t) < session.open! + 3 * BAR_MS);
  if (opening.length !== 3 || Date.parse(opening[0].t) !== session.open || !contiguousBars(opening)) return null;
  return opening.every(b => Number.isFinite(b.h) && b.h > 0) ? Math.max(...opening.map(b => b.h)) : null;
}

export function streakDiagnostics(bars: readonly Bar[], history: readonly Bar[], session: SessionContext, calendar: readonly Json[] = []): Json {
  const first = bars[0], last = bars.at(-1);
  const anchored = !!first && session.open !== null && Date.parse(first.t) === session.open;
  const previous = session.open === null ? undefined : history.filter(b => Date.parse(b.t) < session.open!).at(-1);
  const previousSession = previous ? boundaries(nyParts(Date.parse(previous.t)).date, calendar) : null;
  const previousCloseComplete = !!previous && !!previousSession && Date.parse(previous.t) + BAR_MS === previousSession.close;
  let direction: "UP" | "DOWN" | "FLAT" | null = null, length: number | null = null;
  if (bars.length >= 2 && contiguousBars(bars.slice(-2))) {
    const sign = Math.sign(last!.c - bars.at(-2)!.c);
    direction = sign > 0 ? "UP" : sign < 0 ? "DOWN" : "FLAT";
    length = 0;
    if (sign) for (let i = bars.length - 1; i > 0; i--) {
      if (Date.parse(bars[i].t) - Date.parse(bars[i - 1].t) !== BAR_MS ||
          Math.sign(bars[i].c - bars[i - 1].c) !== sign) break;
      length++;
    }
  }
  return {
    scope: "DIAGNOSTIC_ONLY_NOT_A_PREDICTOR_INPUT",
    basis: "CONTIGUOUS_SAME_SESSION_CLOSE_TO_CLOSE_ZERO_BREAKS_RUN",
    direction, length,
    intraday_return: anchored && first.o > 0 && last ? last.c / first.o - 1 : null,
    previous_observed_regular_close: previous?.c ?? null,
    previous_observed_regular_bar_end: previous ? Date.parse(previous.t) + BAR_MS : null,
    previous_close_complete: previousCloseComplete,
    overnight_gap: anchored && previousCloseComplete && previous!.c > 0 ? first.o / previous!.c - 1 : null,
    // This is explicitly a gap to the prior observed regular bar; completeness is retained.
    gap_to_previous_observed_regular_bar: anchored && previous && previous.c > 0 ? first.o / previous.c - 1 : null,
    first_regular_bar_observed: anchored,
    last_closed_bar_end: last ? Date.parse(last.t) + BAR_MS : null,
    last_closed_bar_known_at: last ? barKnownAt(last) : null,
    availability: last && barKnownAt(last) !== null ? "EXPLICIT_AVAILABILITY" : "SNAPSHOT_AND_INHERITED_CLOSE_BUFFER",
  };
}
