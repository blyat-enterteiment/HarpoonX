"use strict";
/**
 * Frozen, opt-in SYNTHETIC research exits. No broker execution route.
 * NATIVE72 deliberately delegates to the unchanged native exit implementation.
 * Every added close-derived decision is activated only at an opening timestamp
 * at or after its receipt time; unreceived observations remain in a small queue.
 */
const HOUR = 3600000;
const PROFILES = Object.freeze({
  NATIVE72: Object.freeze({ profile: "NATIVE72", horizonHours: 72,
    targetsR: Object.freeze([1.5, 3]), partialFraction: .25,
    nativeTrailing: true, activationR: 1.5, nativePeakLockFraction: .6,
    nativeTrailR: 1.5 }),
  PROTECT48: Object.freeze({ profile: "PROTECT48", horizonHours: 48,
    targetsR: Object.freeze([1.5, 3]), partialFraction: .25,
    nativeTrailing: false, activationR: 1, peakLockFraction: .75,
    trailR: 1, costBreakeven: true }),
  RUNNER72: Object.freeze({ profile: "RUNNER72", horizonHours: 72,
    targetsR: Object.freeze([2, null]), partialFraction: .25,
    nativeTrailing: false, activationR: 2, trailR: 2,
    costBreakeven: false }),
  FAST24: Object.freeze({ profile: "FAST24", horizonHours: 24,
    targetsR: Object.freeze([1.5, 3]), partialFraction: .25,
    nativeTrailing: true, activationR: 1.5, nativePeakLockFraction: .6,
    nativeTrailR: 1.5, stalledAfterHours: 6, favorableExcursionR: .5,
    stallPriceBasis: "LATEST_RECEIVED_COMPLETED_CLOSE_AT_OR_BELOW_FILLED_ENTRY",
    excursionBasis: "RECEIVED_COMPLETED_BAR_CLOSE_PEAK_SINCE_ENTRY" })
});
const need = (ok, reason) => { if (!ok) throw new Error(reason); };

function profileFor(signal) {
  const tag = signal?.metadata?.modulation9;
  if (tag === undefined) return null;
  need(tag !== null && typeof tag === "object" && !Array.isArray(tag) &&
    Object.keys(tag).length === 1 && Object.hasOwn(tag, "profile") &&
    Object.hasOwn(PROFILES, tag.profile), "MODULATION9_EXPLICIT_FIXED_PROFILE");
  const profile = PROFILES[tag.profile];
  need(signal.metadata.roadmapHorizonHours === profile.horizonHours,
    "MODULATION9_PROFILE_HORIZON_BINDING");
  return profile;
}

function resolve(signal, options, policy, kind) {
  const profile = profileFor(signal);
  if (profile === null) return null;
  need(options?.researchModulation === true && options.profit8Trace === true &&
    policy === "BASELINE" && kind === "ALPACA_PROXY" &&
    signal.hypothesis === "CLOSED_CHANNEL" && signal.direction === 1,
    "MODULATION9_INTERNAL_NATIVE_RESEARCH_OPT_IN_REQUIRED");
  return profile;
}

function createState(profile) {
  if (profile === null || profile.profile === "NATIVE72") return null;
  return { profile, pendingStops: [], observations: [], latestKnown: null,
    receivedPeak: null };
}

function tighter(direction, left, right) {
  return direction === 1 ? Math.max(left, right) : Math.min(left, right);
}

/** Ready stops cannot be lost when newer observations arrive before receipt. */
function advance(state, at, oldStop, direction) {
  if (state === null) return oldStop;
  let stop = oldStop;
  const pending = [];
  for (const item of state.pendingStops) {
    if (item.knownAt <= at) stop = tighter(direction, stop, item.price);
    else pending.push(item);
  }
  state.pendingStops = pending;
  const unread = [];
  for (const item of state.observations) {
    if (item.knownAt <= at) {
      if (state.latestKnown === null || item.knownAt >= state.latestKnown.knownAt)
        state.latestKnown = item;
      state.receivedPeak = state.receivedPeak === null ? item.favorablePrice
        : tighter(direction, state.receivedPeak, item.favorablePrice);
    } else unread.push(item);
  }
  state.observations = unread;
  return stop;
}

function stalledExit(state, at, opened, entry, distance, direction) {
  if (state?.profile.profile !== "FAST24" || state.latestKnown === null ||
      at - opened < state.profile.stalledAfterHours * HOUR) return null;
  const peakR = direction * (state.receivedPeak - entry) / distance;
  return peakR < state.profile.favorableExcursionR &&
    direction * (state.latestKnown.close - entry) <= 0
    ? "MODULATION9_STALLED" : null;
}

/** Trigger price sufficient for full-position entry+exit fees, before gap risk. */
function costBreakeven(entry, direction, friction, perSideFee, pointValue, tick) {
  need(friction >= 0 && friction < 1 && pointValue > 0 && tick > 0,
    "MODULATION9_COST_BREAKEVEN_INPUT");
  const price = (entry + direction * 2 * perSideFee / pointValue) /
    (1 - direction * friction);
  return (direction === 1 ? Math.ceil(price / tick - 1e-10)
    : Math.floor(price / tick + 1e-10)) * tick;
}

function nextStop(profile, direction, oldStop, entry, peakClose, distance,
  friction, perSideFee, pointValue, tick) {
  need(profile && !profile.nativeTrailing, "MODULATION9_CUSTOM_TRAIL_ONLY");
  const peakR = direction * (peakClose - entry) / distance;
  if (peakR < profile.activationR) return oldStop;
  let candidate = peakClose - direction * profile.trailR * distance;
  if (profile.peakLockFraction !== undefined)
    candidate = tighter(direction, candidate,
      entry + direction * profile.peakLockFraction * peakR * distance);
  if (profile.costBreakeven)
    candidate = tighter(direction, candidate,
      costBreakeven(entry, direction, friction, perSideFee, pointValue, tick));
  return tighter(direction, oldStop, candidate);
}

function queueStop(state, candidate, knownAt, oldStop, direction) {
  if (direction * (candidate - oldStop) > 0)
    state.pendingStops.push({ price: candidate, knownAt });
}

function observe(state, bar, direction) {
  if (state?.profile.profile !== "FAST24") return;
  state.observations.push({ knownAt: bar.availableAt, close: bar.c,
    favorablePrice: bar.c });
}

/**
 * Per-account read-only causal index. The native scan visits the entire tape
 * at every risk valuation. This index returns exactly its maximum-end known
 * bar, including delayed availability, invalid-timestamp omission and tie
 * order. It never caches across accounts and never changes a bar or signal.
 */
function causalPriceLookup(seriesList, fallback) {
  const indexes = new Map();
  for (const series of seriesList) {
    const items = series.bars.map((bar, index) => ({ bar, index })).filter(({ bar }) =>
      Number.isSafeInteger(bar.t) && Number.isSafeInteger(bar.end) &&
      Number.isSafeInteger(bar.availableAt) && bar.t < bar.end && bar.end <= bar.availableAt)
      .sort((left, right) => left.bar.availableAt - right.bar.availableAt || left.index - right.index);
    let best = null;
    const prefix = items.map(item => {
      if (best === null || item.bar.end > best.bar.end ||
          (item.bar.end === best.bar.end && item.index < best.index)) best = item;
      return best.bar;
    });
    indexes.set(series, { items, prefix });
  }
  return (signal, series) => {
    const index = indexes.get(series);
    if (!index) return fallback(signal, series);
    let lo = 0, hi = index.items.length;
    while (lo < hi) {
      const mid = (lo + hi) >>> 1;
      if (index.items[mid].bar.availableAt <= signal.at) lo = mid + 1;
      else hi = mid;
    }
    const latest = lo ? index.prefix[lo - 1] : undefined;
    const valid = latest !== undefined && Number.isFinite(latest.c) && latest.c > 0;
    return { status: valid ? "AVAILABLE" : "NO_CAUSAL_PRICE",
      price: valid ? latest.c : null, sourceBarAt: latest?.t ?? null,
      sourceAvailableAt: latest?.availableAt ?? null, decisionAt: signal.at,
      reason: valid ? null : latest ? "INVALID_LAST_AVAILABLE_CLOSE" : "NO_AVAILABLE_COMPLETED_BAR" };
  };
}

module.exports = { PROFILES, profileFor, resolve, createState, advance,
  stalledExit, nextStop, queueStop, observe, costBreakeven, causalPriceLookup };
