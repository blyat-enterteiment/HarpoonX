import { need } from "./ultimate_contracts";
export const mean = (a: number[]) =>
  a.length ? a.reduce((x, y) => x + y, 0) / a.length : 0;
export function quantile(a: number[], q: number) {
  need(
    a.length > 0 && q >= 0 && q <= 1 && a.every(Number.isFinite),
    "quantile input",
  );
  const z = [...a].sort((x, y) => x - y),
    i = (z.length - 1) * q,
    lo = Math.floor(i);
  return z[lo] + (z[Math.ceil(i)] - z[lo]) * (i - lo);
}
export function bootstrapLower(
  a: number[],
  runs: number,
  block: number,
  family: number,
  seed = 30301,
): number | null {
  if (a.length < Math.max(30, block * 6)) return null;
  need(
    a.every(Number.isFinite) && runs >= 500 && block > 0 && family >= 1,
    "bootstrap inputs",
  );
  let state = seed >>> 0;
  const next = () => {
    state ^= state << 13;
    state ^= state >>> 17;
    state ^= state << 5;
    return (state >>> 0) / 4294967296;
  };
  const samples: number[] = [];
  for (let k = 0; k < runs; k++) {
    let sum = 0,
      count = 0;
    while (count < a.length) {
      const start = Math.floor(next() * a.length);
      for (let j = 0; j < block && count < a.length; j++, count++)
        sum += a[(start + j) % a.length];
    }
    samples.push(sum / a.length);
  }
  return quantile(samples, 0.05 / family);
}
export function metrics(returns: number[], campaignR: number[]) {
  need([...returns, ...campaignR].every(Number.isFinite), "nonfinite metrics");
  let nav = 1,
    peak = 1,
    dd = 0,
    ruined = false;
  for (const r of returns) {
    if (r <= -1) ruined = true;
    nav *= Math.max(0, 1 + r);
    peak = Math.max(peak, nav);
    dd = Math.max(dd, 1 - nav / peak);
  }
  const mu = mean(returns),
    variance = mean(returns.map((x) => (x - mu) ** 2));
  let hac = variance;
  for (let lag = 1; lag <= Math.min(5, returns.length - 1); lag++) {
    let covariance = 0;
    for (let i = lag; i < returns.length; i++)
      covariance += (returns[i] - mu) * (returns[i - lag] - mu);
    hac += (2 * (1 - lag / 6) * covariance) / returns.length;
  }
  const gains = campaignR.reduce((v, x) => v + Math.max(x, 0), 0),
    losses = -campaignR.reduce((v, x) => v + Math.min(x, 0), 0);
  const downside = Math.sqrt(mean(returns.map((x) => Math.min(x, 0) ** 2)));
  return {
    campaigns: campaignR.length,
    sessions: returns.length,
    expectancyR: campaignR.length ? mean(campaignR) : null,
    profitFactor: losses > 0 ? gains / losses : null,
    winRate: campaignR.length
      ? campaignR.filter((x) => x > 0).length / campaignR.length
      : null,
    growthLog: returns.length && !ruined ? mean(returns.map(Math.log1p)) : null,
    modelReturn: nav - 1,
    maxDrawdown: dd,
    sharpeHac: hac > 1e-20 ? (mu / Math.sqrt(hac)) * Math.sqrt(252) : null,
    sortino: downside > 1e-15 ? (mu / downside) * Math.sqrt(252) : null,
    expectedShortfall95: returns.length
      ? -mean(
          [...returns]
            .sort((a, b) => a - b)
            .slice(0, Math.max(1, Math.ceil(returns.length * 0.05))),
        )
      : null,
  };
}
function normalCdf(z: number) {
  const t = 1 / (1 + 0.2316419 * Math.abs(z)),
    density = Math.exp((-z * z) / 2) / Math.sqrt(2 * Math.PI);
  const tail =
    density *
    t *
    (0.31938153 +
      t *
        (-0.356563782 +
          t * (1.781477937 + t * (-1.821255978 + t * 1.330274429))));
  return z >= 0 ? 1 - tail : tail;
}
function normalInverse(p: number) {
  let lo = -10,
    hi = 10;
  for (let i = 0; i < 70; i++) {
    const mid = (lo + hi) / 2;
    if (normalCdf(mid) < p) lo = mid;
    else hi = mid;
  }
  return (lo + hi) / 2;
}
/** Daily unannualized DSR; all trials and HAC effective size are disclosed in result. */
export function deflatedSharpe(
  matrix: number[][],
  selected: number,
  familyTrials: number,
  campaigns: number,
) {
  if (!matrix.length || matrix[0].length < 60 || campaigns < 30)
    return { status: "INSUFFICIENT_EVIDENCE", value: null };
  need(
    selected >= 0 &&
      selected < matrix.length &&
      matrix.every(
        (a) => a.length === matrix[0].length && a.every(Number.isFinite),
      ),
    "DSR matrix",
  );
  const sr = (a: number[]) => {
    const m = mean(a),
      sd = Math.sqrt(mean(a.map((x) => (x - m) ** 2)));
    return sd > 1e-12 ? m / sd : 0;
  };
  const sharpes = matrix.map(sr),
    m = mean(sharpes),
    sdSR = Math.sqrt(mean(sharpes.map((x) => (x - m) ** 2)));
  const a = matrix[selected],
    mu = mean(a),
    variance = mean(a.map((x) => (x - mu) ** 2));
  if (variance <= 1e-20) return { status: "DEGENERATE", value: null };
  let autocov = 0;
  for (let lag = 1; lag <= 5; lag++) {
    let c = 0;
    for (let i = lag; i < a.length; i++) c += (a[i] - mu) * (a[i - lag] - mu);
    autocov += (2 * (1 - lag / 6) * c) / a.length;
  }
  const effectiveN = Math.min(
    a.length,
    a.length / Math.max(1, (variance + autocov) / variance),
  );
  const skew = mean(a.map((x) => (x - mu) ** 3)) / variance ** 1.5,
    kurt = mean(a.map((x) => (x - mu) ** 4)) / variance ** 2;
  const trials = Math.max(2, familyTrials, matrix.length),
    gamma = 0.5772156649015329;
  const threshold =
    sdSR *
    ((1 - gamma) * normalInverse(1 - 1 / trials) +
      gamma * normalInverse(1 - 1 / (trials * Math.E)));
  const denom = Math.sqrt(
    Math.max(
      1e-12,
      1 - skew * sharpes[selected] + ((kurt - 1) * sharpes[selected] ** 2) / 4,
    ),
  );
  return {
    status: "ESTIMATE",
    value: normalCdf(
      ((sharpes[selected] - threshold) * Math.sqrt(effectiveN - 1)) / denom,
    ),
    trials,
    effectiveN,
    threshold,
    scope: "DSR_ESTIMATE_NOT_PROFIT_PROBABILITY",
  };
}
/** CSCV on synchronous daily columns, diagnostic only, never a temporal holdout replacement. */
export function probabilityBacktestOverfit(matrix: number[][], segments = 8) {
  if (matrix.length < 3 || !matrix[0] || matrix[0].length < segments * 10)
    return { status: "INSUFFICIENT_EVIDENCE", value: null };
  need(
    segments % 2 === 0 &&
      segments <= 12 &&
      matrix.every(
        (a) => a.length === matrix[0].length && a.every(Number.isFinite),
      ),
    "PBO matrix",
  );
  let cases = 0,
    failed = 0;
  const score = (a: number[], include: Set<number>) => {
    const x = a.filter((_, i) =>
      include.has(
        Math.min(segments - 1, Math.floor((i * segments) / a.length)),
      ),
    );
    const m = mean(x),
      sd = Math.sqrt(mean(x.map((v) => (v - m) ** 2)));
    return sd > 1e-15 ? m / sd : 0;
  };
  for (let mask = 0; mask < 1 << segments; mask++) {
    const train = new Set<number>();
    for (let i = 0; i < segments; i++) if (mask & (1 << i)) train.add(i);
    if (train.size !== segments / 2) continue;
    const test = new Set(
      Array.from({ length: segments }, (_, i) => i).filter(
        (i) => !train.has(i),
      ),
    );
    const scores = matrix.map((a) => score(a, train)),
      winner = scores.indexOf(Math.max(...scores));
    const out = matrix.map((a) => score(a, test)),
      below = out.filter((x) => x < out[winner]).length,
      ties = out.filter((x) => x === out[winner]).length;
    const rank = (below + 0.5 * ties) / matrix.length;
    cases++;
    if (rank <= 0.5) failed++;
  }
  return {
    status: "DIAGNOSTIC",
    value: failed / cases,
    partitions: cases,
    segments,
    scope: "PBO_NOT_FUTURE_RETURN_PROBABILITY",
  };
}
