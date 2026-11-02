import { floorStep, positive } from "./types";
import type { Campaign, Config, Intent, Json, Quote } from "./types";
import { fills } from "./policy";

export const urgentExit = (kind: Intent["kind"]) =>
  ["stop", "flatten", "expiry", "time", "signal", "stagnation"].includes(kind);
export function rememberExit(
  c: Campaign,
  intents: Intent[],
  decision: { kind: Intent["kind"]; qty: number } | null,
  q: Quote | undefined,
  cfg: Config,
  now: number,
) {
  const f = fills(c, intents),
    tol = c.instrument.step * 1e-6;
  // A cancel-pending entry can fill again after an urgent close was detected.
  // Expand the durable close-all target only from confirmed fills, before completion.
  if (c.exitPlan && c.exitPlan.status !== "COMPLETE" && urgentExit(c.exitPlan.kind))
    c.exitPlan.targetSold = Math.max(c.exitPlan.targetSold, f.bought);
  if (c.exitPlan && f.sold >= c.exitPlan.targetSold - tol)
    c.exitPlan.status = "COMPLETE";
  if (!decision) return;
  const old = c.exitPlan,
    urgent = urgentExit(decision.kind);
  if (old && old.status !== "COMPLETE" && (urgentExit(old.kind) || !urgent))
    return;
  const cost =
    (f.entry *
      ((c.book === "crypto" ? 2 * cfg.cryptoFeeBps : 0) +
        2 * cfg.slippageBps)) /
      10000 +
    (c.book === "options"
      ? (2 * cfg.optionsFeePerContract) / c.instrument.multiplier
      : 0);
  c.exitPlan = {
    id: c.id + "-exit-" + now,
    kind: decision.kind,
    detectedAt: now,
    quoteAt: q?.at,
    targetSold: Math.min(f.bought, f.sold + decision.qty),
    status: "CANCELING",
    ...(!urgent
      ? {
          minimumPrice:
            f.entry +
            cost +
            c.risk * (decision.kind === "tp2" ? c.policy.tp2R : c.policy.tp1R),
        }
      : {}),
  };
}
export function remainingExit(c: Campaign, intents: Intent[], held: number) {
  const p = c.exitPlan;
  if (!p || p.status === "COMPLETE") return null;
  const f = fills(c, intents),
    qty = floorStep(
      Math.min(held, Math.max(0, p.targetSold - f.sold)),
      c.instrument.step,
    );
  if (qty < c.instrument.minQty) {
    p.status = "COMPLETE";
    return null;
  }
  return { kind: p.kind, qty };
}
/** Real broker order trees are flattened by identity. No synthetic linked fills. */
export function orderTree(rows: Json[]): Json[] {
  const result = new Map<string, Json>();
  const visit = (o: Json, depth: number) => {
    if (depth > 4 || !o || typeof o.id !== "string")
      throw Error("Invalid native order tree");
    const prior = result.get(o.id);
    if (prior && JSON.stringify(prior) !== JSON.stringify(o))
      throw Error("Conflicting native order identity");
    result.set(o.id, o);
    if (o.legs != null && !Array.isArray(o.legs))
      throw Error("Invalid native order legs");
    for (const child of o.legs || []) visit(child, depth + 1);
  };
  for (const r of rows) visit(r, 0);
  return [...result.values()];
}
export function nativeGroups(
  c: Campaign,
  intents: Intent[],
  held: number,
  cfg: Config,
  q: Quote,
): {
  role: "tp1" | "tp2" | "runner";
  qty: number;
  type: "oco" | "stop" | "trailing_stop";
  target?: number;
  trail?: number;
}[] {
  if (
    !["equity", "etf"].includes(c.book) ||
    !cfg.nativeProtection ||
    cfg.nativeProtection === "stop"
  )
    return [];
  const f = fills(c, intents),
    step = c.instrument.step;
  const first = Math.min(
    held,
    floorStep(Math.max(0, f.bought * c.policy.tp1Fraction - f.tpSold), step),
  );
  const second = Math.min(
    held - first,
    floorStep(
      Math.max(
        0,
        f.bought * (c.policy.tp1Fraction + c.policy.tp2Fraction) -
          f.tpSold -
          first,
      ),
      step,
    ),
  );
  const cost = (f.entry * 2 * cfg.slippageBps) / 10000;
  const rows: {
    role: "tp1" | "tp2" | "runner";
    qty: number;
    type: "oco" | "stop" | "trailing_stop";
    target?: number;
    trail?: number;
  }[] = [
    {
      role: "tp1",
      qty: first,
      type: "oco",
      target: Math.max(
        c.stop + c.instrument.tick,
        f.entry + cost + c.policy.tp1R * c.risk,
      ),
    },
    {
      role: "tp2",
      qty: second,
      type: "oco",
      target: Math.max(
        c.stop + c.instrument.tick,
        f.entry + cost + c.policy.tp2R * c.risk,
      ),
    },
    {
      role: "runner",
      qty: floorStep(Math.max(0, held - first - second), step),
      type: cfg.nativeProtection === "oco_trailing" ? "trailing_stop" : "stop",
      trail: q.bid - c.stop,
    },
  ];
  if (rows.some((r) => r.type === "trailing_stop" && !positive(r.trail)))
    throw Error("Trailing runner requires bid above desired stop");
  return rows.filter((r) => r.qty >= c.instrument.minQty);
}
export function protectionSnapshot(
  c: Campaign,
  intents: Intent[],
  held: number,
  now: number,
) {
  const active = intents.filter(
    (i) =>
      i.campaign === c.id &&
      !new Set(["filled", "canceled", "expired", "rejected", "replaced"]).has(
        i.status,
      ),
  );
  const stops = active.filter(
    (i) =>
      i.kind === "protect" &&
      !i.cancelAt &&
      (!i.parentId || !intents.find((p) => p.id === i.parentId)?.cancelAt) &&
      i.order?.id &&
      (["new", "accepted", "partially_filled"].includes(i.status) ||
        (i.status === "held" && !!i.parentId && intents.some((p) =>
          p.id === i.parentId && p.campaign === c.id && p.payload.order_class === "oco" &&
          !p.cancelAt && ["new", "accepted", "partially_filled"].includes(p.status)))) &&
      ["stop", "stop_limit", "trailing_stop"].includes(
        i.order.type || i.payload.type,
      ),
  );
  let covered = 0;
  const floors: { qty: number; stop: number | null; id: string }[] = [];
  for (const i of stops) {
    const n = Math.max(0, Number(i.order!.qty) - Number(i.order!.filled_qty));
    const px = Number(i.order!.stop_price || i.payload.stop_price);
    covered += n;
    floors.push({ qty: n, stop: positive(px) ? px : null, id: i.id });
  }
  const nativeFloor =
    floors.length && floors.every((x) => x.stop !== null)
      ? Math.min(...floors.map((x) => x.stop!))
      : null;
  const quantityCovered =
    held > 0 && covered >= held - c.instrument.step * 1e-6;
  const aligned =
    quantityCovered &&
    nativeFloor !== null &&
    nativeFloor >=
      Number(
        (
          Math.floor((c.stop + 1e-9) / c.instrument.tick) * c.instrument.tick
        ).toFixed(9),
      ) -
        c.instrument.tick * 1e-6;
  return {
    sampledAt: now,
    held,
    covered,
    quantityCovered,
    aligned,
    desiredStop: c.stop,
    confirmedStop: nativeFloor,
    drift:
      quantityCovered && nativeFloor !== null
        ? Math.max(0, c.stop - nativeFloor)
        : null,
    floors,
  };
}
export function sampleProtection(
  c: Campaign,
  intents: Intent[],
  held: number,
  q: Quote | undefined,
  now: number,
) {
  const snap = protectionSnapshot(c, intents, held, now),
    t = c.protectionTelemetry ?? {
      sampledAt: now,
      uncoveredSince: null,
      uncoveredTotalMs: 0,
      observedPeakPnl: 0,
      samples: 0,
    };
  if (t.uncoveredSince !== null)
    t.uncoveredTotalMs += Math.max(0, now - t.sampledAt);
  t.uncoveredSince =
    held > 0 && !snap.quantityCovered ? (t.uncoveredSince ?? now) : null;
  t.sampledAt = now;
  t.samples++;
  if (q) {
    const f = fills(c, intents);
    t.observedPeakPnl = Math.max(
      t.observedPeakPnl,
      f.gross + (q.bid - f.entry) * held * c.instrument.multiplier,
    );
  }
  c.protectionTelemetry = t;
  return snap;
}
