"use strict";
var HPPolicy;
(function (HPPolicy) {
    const finite = (x) => Number.isFinite(x);
    const tradingMillis = (a, b, c) => HX.tradingMillis(a, b, c);
    const finishShadow = (s, q, r) => HX.finishShadow(s, q, r);
    const marked = (s, b) => HX.marked(s, b);
    function parts(q, profile) {
        if (!Number.isInteger(q) || q < 4)
            throw Error('Tramo menor de cuatro títulos');
        if (profile.astra) {
            const f = profile.astra.partialFraction;
            if (!(f >= 0 && f <= .35))
                throw Error('ASTRA: fracción inválida');
            const a = f === 0 ? 0 : Math.max(1, Math.floor(q * f));
            return [a, 0, q - a];
        }
        const f = profile.tp1_fraction ?? .25, g = profile.tp2_fraction ?? .25;
        if (!(f >= HContract.min_partial && g >= HContract.min_partial && f + g <= HContract.partial_max))
            throw Error('Reparto de parciales inválido');
        const a = Math.max(1, Math.floor(q * f)), b = profile.exit_layout === 'single_target' ? 0 : Math.max(1, Math.floor(q * g));
        return [a, b, q - a - b];
    }
    HPPolicy.parts = parts;
    function reentry(f, history, now, enabled) {
        if (!history.length)
            return null;
        if (history.some(c => !c.closed))
            return 'POSICIÓN ABIERTA';
        if (!enabled)
            return 'REENTRADA DESACTIVADA';
        if (history.length >= 2)
            return 'MÁXIMO DOS CAMPAÑAS';
        const last = history[history.length - 1], closed = Date.parse(last.closed_at ?? '');
        if (!finite(closed) || now - closed < 1800000)
            return 'ESPERA 30 MINUTOS';
        if (!finite(f.volume_acceleration ?? NaN) || (f.volume_acceleration ?? 0) < 1.1)
            return 'VOLUMEN SIN RENOVACIÓN';
        if (!finite(f.consolidation_atr ?? NaN) || (f.consolidation_atr ?? 99) > 2.5)
            return 'SIN CONSOLIDACIÓN';
        if (f.ask <= (f.reentry_trigger ?? Infinity) || f.ask <= last.peak + .1 * f.atr || Date.parse(f.bar_end ?? '') <= closed + 900000)
            return 'SIN NUEVA RUPTURA';
        return null;
    }
    HPPolicy.reentry = reentry;
    function quality(f, p, minDollarVolume, maxCostFraction, lv, costsBps) {
        const reasons = [];
        if (!(f.dollar_volume !== undefined && finite(f.dollar_volume) && f.dollar_volume >= minDollarVolume))
            reasons.push('LIQUIDEZ INSUFICIENTE');
        const costR = (f.ask * (f.spread_bps + 2 * costsBps) / 10000) / lv.risk_unit;
        if (!finite(costR) || costR > maxCostFraction)
            reasons.push('COSTE / R EXCESIVO');
        if (p.selective) {
            if (f.vwap_distance > 3 * f.atr_pct || f.vwap_distance < -.5 * f.atr_pct)
                reasons.push('EXTENSIÓN VWAP');
            if ((f.relative_bps ?? -Infinity) < 0)
                reasons.push('FUERZA RELATIVA DÉBIL');
            if ((f.volume_acceleration ?? 0) < 1)
                reasons.push('VOLUMEN DECRECIENTE');
        }
        const score = Math.log1p(Math.max(0, f.rvol)) * 20 + Math.min(100, f.momentum_bps) / 5 + Math.max(-20, Math.min(20, (f.relative_bps ?? 0) / 10)) - costR * 30 - Math.max(0, f.vwap_distance / Math.max(f.atr_pct, 1e-9) - 2) * 8;
        return { score, reasons, cost_r: costR };
    }
    HPPolicy.quality = quality;
    function newShadow(f, lv, p, until, costsBps, plannedQty) {
        const at = Date.parse(f.asof);
        const first = plannedQty === undefined ? .5 : Math.floor(plannedQty * .5) / plannedQty;
        return { plannedQty, at, deadline: until, last: at, lastBid: f.bid, anchor: lv.limit, risk: lv.risk_unit, atr: f.atr, profile: { ...p }, costs: costsBps / 10000, paid: 0, proceeds: 0, opened: 0, riskSpent: 0, riskBudget: lv.risk_unit + 2 * lv.limit * costsBps / 10000, peak: lv.limit, stop: lv.stop, entry: lv.limit, levels: 1, first: false, peakAt: at, lots: [], pending: { at, weight: first, levels: lv }, marks: {}, done: false, valid: true, reason: 'OBSERVANDO', entryAt: null, mfe: 0, mae: 0, exitAt: until, tradingStagnation: 0 };
    }
    HPPolicy.newShadow = newShadow;
    function stepShadow(s, q, day, calendar, makeLevels) {
        if (s.done)
            return;
        const elapsed = tradingMillis(s.last, q.received, calendar);
        if (q.received < s.last || elapsed > 60000 || q.received - q.at > 15000) {
            s.valid = false;
            s.reason = 'HUECO DE COTIZACIÓN';
        }
        s.tradingStagnation += elapsed;
        s.last = q.received;
        s.lastBid = q.bid;
        const vol = HXII.updateVol(s.vol, q.bid, q.received, s.atr);
        s.vol = vol.state;
        s.dynamicAtr = vol.atr;
        if (s.pending && q.received > s.pending.at) {
            if (q.received - s.pending.at > 30000)
                s.pending = null;
            else if (q.ask <= s.pending.levels.limit) {
                const p = s.pending, l = p.levels;
                const sizes = s.plannedQty === undefined ? null : parts(Math.round(p.weight * s.plannedQty), s.profile);
                s.paid += p.weight * l.limit;
                s.opened += p.weight;
                s.riskSpent += p.weight * (l.risk_unit + 2 * l.limit * s.costs);
                s.lots.push({ firstWeight: sizes ? sizes[0] / s.plannedQty : undefined, secondWeight: sizes ? sizes[1] / s.plannedQty : undefined, weight: p.weight, left: p.weight, entry: l.limit, stop: l.stop, tp1: l.tp1, tp2: l.tp2, first: false, second: false });
                s.entry = s.paid / s.opened;
                s.entryAt ??= q.received;
                s.pending = null;
            }
        }
        if (!s.opened && !s.pending) {
            finishShadow(s, q, 'SIN FILL');
            s.marks[day] = 0;
            return;
        }
        if (s.opened) {
            s.mfe = Math.max(s.mfe, (q.bid - s.entry) / s.risk);
            s.mae = Math.min(s.mae, (q.bid - s.entry) / s.risk);
            for (const l of s.lots) {
                if (!l.left)
                    continue;
                if (q.bid <= Math.max(l.stop, s.stop)) {
                    s.proceeds += l.left * q.bid * (1 - s.costs);
                    l.left = 0;
                    continue;
                }
                for (const first of [true, false]) {
                    if (!first && s.profile.exit_layout === 'single_target')
                        continue;
                    const hit = first ? l.first : l.second, target = first ? l.tp1 : l.tp2, frac = first ? (s.profile.tp1_fraction ?? .25) : (s.profile.tp2_fraction ?? .25);
                    if (!hit && q.bid >= target) {
                        const sold = Math.min(l.left, (first ? l.firstWeight : l.secondWeight) ?? l.weight * frac);
                        s.proceeds += sold * target * (1 - s.costs);
                        l.left -= sold;
                        if (first) {
                            l.first = true;
                            s.first = true;
                            s.firstTargetAt ??= q.received;
                        }
                        else
                            l.second = true;
                    }
                }
            }
            if (s.lots.every(l => l.left < 1e-12)) {
                finishShadow(s, q, 'STOP / OBJETIVOS');
            }
            else {
                if (q.bid > s.peak) {
                    s.peak = q.bid;
                    s.peakAt = q.received;
                    s.tradingStagnation = 0;
                }
                s.stop = Math.max(s.stop, s.peak - s.profile.trail_atr * (s.profile.trailing_mode === 'realized_vol' ? (s.dynamicAtr ?? s.atr) : s.atr));
                if (s.peak >= s.entry + 2.5 * s.risk)
                    s.stop = Math.max(s.stop, s.entry + s.profile.lock_fraction * (s.peak - s.entry));
                if (s.first)
                    s.stop = Math.max(s.stop, s.entry / (1 - s.costs));
                if (q.bid <= s.stop)
                    finishShadow(s, q, 'TRAILING');
                else if (s.tradingStagnation >= (s.profile.stagnation_minutes ?? 20) * 60000 && q.bid * (1 - s.costs) - s.entry < (s.profile.progress_r ?? 1) * s.risk)
                    finishShadow(s, q, 'SIN CONTINUIDAD');
                else if (q.received >= s.deadline)
                    finishShadow(s, q, 'PLAZO');
                else if (!s.pending && s.levels < 3 && !s.first && q.bid >= s.anchor + s.levels * .75 * s.risk && s.stop >= s.entry) {
                    const lv = makeLevels(q.ask, q.bid), unit = lv.risk_unit + 2 * lv.limit * s.costs;
                    let weight = Math.max(0, Math.min(.25, Math.min(.25 * s.riskBudget, s.riskBudget - s.riskSpent) / unit, (s.anchor - s.paid) / lv.limit));
                    if (s.plannedQty !== undefined) {
                        const n = Math.floor(weight * s.plannedQty + 1e-9);
                        weight = n >= 4 ? n / s.plannedQty : 0;
                    }
                    if (weight > 0) {
                        s.pending = { at: q.received, weight, levels: lv };
                        s.levels++;
                    }
                }
            }
        }
        if (q.received >= s.deadline && !s.done)
            finishShadow(s, q, 'PLAZO');
        s.marks[day] = marked(s, q.bid);
    }
    HPPolicy.stepShadow = stepShadow;
})(HPPolicy || (HPPolicy = {}));
/** HARPOON X: deterministic, strictly typed research and execution primitives. */
var HX;
(function (HX) {
    HX.VERSION = '12.0.0';
    HX.finite = (x) => Number.isFinite(x);
    function nyTime(day, clock) {
        if (!/^\d{4}-\d{2}-\d{2}$/.test(day) || !/^\d{2}:\d{2}(?::\d{2})?$/.test(clock))
            throw Error('Calendario inválido');
        const desired = Date.parse(day + 'T' + clock.slice(0, 5) + ':00Z');
        const fmt = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });
        let value = desired;
        for (let i = 0; i < 3; i++) {
            const parts = Object.fromEntries(fmt.formatToParts(new Date(value)).map(p => [p.type, p.value]));
            const shown = Date.parse(`${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}:00Z`);
            value += desired - shown;
        }
        if (!HX.finite(value))
            throw Error('Fecha de mercado inválida');
        return value;
    }
    HX.nyTime = nyTime;
    function sessions(raw) {
        return raw.map(s => ({ date: s.date, open: nyTime(s.date, s.open), close: nyTime(s.date, s.close) })).sort((a, b) => a.open - b.open);
    }
    HX.sessions = sessions;
    function deadline(at, hours, calendar, bufferMinutes = 10) {
        if (![1.5, 24, 48, 72].includes(hours) || bufferMinutes < 1)
            throw Error('Plazo no permitido');
        const cap = at + hours * 3600000;
        if (!calendar.length || calendar[calendar.length - 1].close < cap)
            throw Error('Calendario insuficiente para la salida');
        let latest = NaN;
        for (const s of calendar) {
            const last = s.close - bufferMinutes * 60000;
            if (s.open > cap)
                break;
            if (cap - 30000 < s.open)
                continue;
            if (last >= at && s.open <= cap)
                latest = Math.max(HX.finite(latest) ? latest : at, Math.min(cap - 30000, last));
        }
        if (!HX.finite(latest) || latest <= at)
            throw Error('Sin ventana de salida válida');
        return latest;
    }
    HX.deadline = deadline;
    function tradingMillis(a, b, calendar) {
        return calendar.reduce((v, s) => v + Math.max(0, Math.min(b, s.close) - Math.max(a, s.open)), 0);
    }
    HX.tradingMillis = tradingMillis;
    function parts(q, profile) { return HPPolicy.parts(q, profile); }
    HX.parts = parts;
    function reentry(f, history, now, enabled) { return HPPolicy.reentry(f, history, now, enabled); }
    HX.reentry = reentry;
    function quality(f, p, minDollarVolume, maxCostFraction, lv, costsBps) { return HPPolicy.quality(f, p, minDollarVolume, maxCostFraction, lv, costsBps); }
    HX.quality = quality;
    function newShadow(f, lv, p, until, costsBps, plannedQty) { return HPPolicy.newShadow(f, lv, p, until, costsBps, plannedQty); }
    HX.newShadow = newShadow;
    function marked(s, bid) {
        return (s.proceeds + s.lots.reduce((v, l) => v + l.left * bid * (1 - s.costs), 0) - s.paid) / s.anchor;
    }
    HX.marked = marked;
    function finishShadow(s, q, reason) {
        for (const l of s.lots) {
            s.proceeds += l.left * q.bid * (1 - s.costs);
            l.left = 0;
        }
        s.pending = null;
        s.done = true;
        s.reason = reason;
        s.exitAt = q.received;
    }
    HX.finishShadow = finishShadow;
    function stepShadow(s, q, day, calendar, makeLevels) { return HPPolicy.stepShadow(s, q, day, calendar, makeLevels); }
    HX.stepShadow = stepShadow;
    function outcome(s) {
        return { first_target_minutes: s.firstTargetAt && s.entryAt ? (s.firstTargetAt - s.entryAt) / 60000 : null, risk_weight: s.riskSpent / s.riskBudget, return: marked(s, s.lastBid), filled: s.opened > 0, entry_at: s.entryAt, exit_at: s.exitAt, marks: { ...s.marks }, mfe_r: s.mfe, mae_r: s.mae, reason: s.reason, held_hours: s.entryAt === null ? 0 : (s.exitAt - s.entryAt) / 3600000 };
    }
    HX.outcome = outcome;
    function normalCDF(x) { const z = Math.abs(x), t = 1 / (1 + .2316419 * z), d = .3989422804014327 * Math.exp(-z * z / 2), p = 1 - d * t * (.319381530 + t * (-.356563782 + t * (1.781477937 + t * (-1.821255978 + t * 1.330274429)))); return x >= 0 ? p : 1 - p; }
    HX.normalCDF = normalCDF;
    function normalQuantile(p) { if (!(p > 0 && p < 1))
        throw Error('Probabilidad inválida'); let lo = -9, hi = 9; for (let i = 0; i < 80; i++) {
        const mid = (lo + hi) / 2;
        if (normalCDF(mid) < p)
            lo = mid;
        else
            hi = mid;
    } return (lo + hi) / 2; }
    HX.normalQuantile = normalQuantile;
    function dsr(returns, trialSharpes, trials) {
        const n = returns.length, m = returns.reduce((a, b) => a + b, 0) / n, v = returns.reduce((a, b) => a + (b - m) ** 2, 0) / n;
        if (n < 30 || v <= 1e-20 || trialSharpes.length < 3)
            return { probability: null, effective_n: n, trials, threshold: null };
        const sd = Math.sqrt(v), sr = m / sd, skew = returns.reduce((a, b) => a + ((b - m) / sd) ** 3, 0) / n, kurt = returns.reduce((a, b) => a + ((b - m) / sd) ** 4, 0) / n;
        let vif = 1;
        for (let lag = 1; lag <= 5; lag++)
            vif += 2 * (1 - lag / 6) * returns.slice(lag).reduce((a, b, i) => a + (b - m) * (returns[i] - m), 0) / (n * v);
        const effective = Math.min(n, n / Math.max(1, vif)), tmean = trialSharpes.reduce((a, b) => a + b, 0) / trialSharpes.length, tvar = trialSharpes.reduce((a, b) => a + (b - tmean) ** 2, 0) / Math.max(1, trialSharpes.length - 1), k = Math.max(3, trials);
        const threshold = Math.sqrt(tvar) * ((1 - .5772156649) * normalQuantile(1 - 1 / k) + .5772156649 * normalQuantile(1 - 1 / (k * Math.E)));
        const den = Math.sqrt(Math.max(1e-12, 1 - skew * sr + (kurt - 1) * sr * sr / 4));
        return { probability: normalCDF((sr - threshold) * Math.sqrt(effective - 1) / den), effective_n: effective, trials: k, threshold };
    }
    HX.dsr = dsr;
})(HX || (HX = {}));
