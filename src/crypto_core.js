"use strict";
/* HARPOON XIX: causal daily spot trend research. No transport or model calls. */
var HC19;
(function (HC19) {
    HC19.VERSION = '19.0.0', HC19.DAY = 86400000, HC19.SYMBOLS = ['BTC/USD', 'ETH/USD'];
    HC19.defaults = { entry_days: 20, exit_days: 10, atr_days: 20, atr_multiple: 3, risk_fraction: .0025, asset_cap: .25, total_cap: .5, fee_bps: 25, slippage_bps: 10, max_spread_bps: 30, capital: 20000, capital_limit: 50000, hold_hours: 0, drawdown_limit: .15 };
    const avg = (a) => a.reduce((s, x) => s + x, 0) / Math.max(1, a.length);
    const finite = (x) => typeof x === 'number' && Number.isFinite(x);
    function validate(c) {
        const ranges = { entry_days: [10, 120], exit_days: [2, 60], atr_days: [5, 60], atr_multiple: [1, 6], risk_fraction: [.0001, .01], asset_cap: [.01, .5], total_cap: [.02, 1], fee_bps: [0, 100], slippage_bps: [0, 100], max_spread_bps: [1, 100], capital: [100, 1000000], capital_limit: [100, 1000000], hold_hours: [0, 720], drawdown_limit: [.01, .5] };
        for (const k of Object.keys(ranges)) {
            const [lo, hi] = ranges[k];
            if (!finite(c[k]) || c[k] < lo || c[k] > hi)
                throw Error('Parámetro cripto inválido: ' + k);
        }
        if (Object.keys(c).some(k => !(k in ranges)) || c.exit_days >= c.entry_days || c.asset_cap > c.total_cap || c.capital_limit < c.capital || !['entry_days', 'exit_days', 'atr_days', 'hold_hours'].every(k => Number.isInteger(c[k])))
            throw Error('Contrato de estrategia cripto incompatible');
        return { ...c };
    }
    HC19.validate = validate;
    function normalize(raw, cutoff = Date.now()) {
        if (!Array.isArray(raw) || raw.length > 8000 || !Number.isFinite(cutoff))
            throw Error('Historial cripto inválido o demasiado grande');
        const map = new Map();
        for (const r of raw) {
            if (!r || typeof r !== 'object')
                throw Error('Barra inválida');
            const t = typeof r.t === 'number' ? r.t : Date.parse(r.t);
            if (!Number.isFinite(t) || t % HC19.DAY !== 0)
                throw Error('Barras diarias requeridas a las 00:00 UTC');
            if (t + HC19.DAY > cutoff)
                continue;
            const b = { t, o: Number(r.o), h: Number(r.h), l: Number(r.l), c: Number(r.c), v: Number(r.v) };
            if (![b.o, b.h, b.l, b.c, b.v].every(Number.isFinite) || Math.min(b.o, b.h, b.l, b.c) <= 0 || b.v <= 0 || b.h < Math.max(b.o, b.c, b.l) || b.l > Math.min(b.o, b.c, b.h))
                throw Error('OHLCV inválido');
            const prior = map.get(t);
            if (prior && JSON.stringify(prior) !== JSON.stringify(b))
                throw Error('Revisión conflictiva en ' + new Date(t).toISOString());
            map.set(t, b);
        }
        const out = [...map.values()].sort((a, b) => a.t - b.t);
        for (let i = 1; i < out.length; i++)
            if (out[i].t - out[i - 1].t !== HC19.DAY)
                throw Error('Faltan días cripto: no se interpolan precios');
        return out;
    }
    HC19.normalize = normalize;
    function dataset(input, cutoff = Date.now()) {
        const root = input;
        const raw = (root?.bars || input);
        if (!raw || typeof raw !== 'object')
            throw Error('Se requiere {bars:{"BTC/USD":[],"ETH/USD":[]}}');
        const result = {};
        for (const s of HC19.SYMBOLS)
            result[s] = normalize(raw[s], cutoff);
        if (!result['BTC/USD'].length || result['BTC/USD'].length !== result['ETH/USD'].length || result['BTC/USD'].some((b, i) => b.t !== result['ETH/USD'][i].t))
            throw Error('BTC y ETH deben compartir días completos; corrige el historial');
        return result;
    }
    HC19.dataset = dataset;
    function signal(b, c, index = b.length - 1) {
        if (index < Math.max(c.entry_days, c.atr_days, c.exit_days) || index >= b.length)
            throw Error('Se necesitan más barras cerradas');
        const last = b[index], prior = b.slice(index - c.entry_days, index), upper = Math.max(...prior.map(x => x.h)), lower = Math.min(...b.slice(index - c.exit_days, index).map(x => x.l));
        const tr = [], ret = [];
        for (let i = index - c.atr_days + 1; i <= index; i++) {
            tr.push(Math.max(b[i].h - b[i].l, Math.abs(b[i].h - b[i - 1].c), Math.abs(b[i].l - b[i - 1].c)));
            ret.push(Math.log(b[i].c / b[i - 1].c));
        }
        const atr = avg(tr), mu = avg(ret), volatility = Math.sqrt(ret.reduce((s, x) => s + (x - mu) ** 2, 0) / Math.max(1, ret.length - 1) * 365);
        return { at: last.t, available_at: last.t + HC19.DAY, close: last.c, upper, lower, atr, volatility, enter: last.c > upper, exit: last.c < lower, stop: Math.max(last.c * .01, last.c - c.atr_multiple * atr) };
    }
    HC19.signal = signal;
    function floorQty(q, step) { if (!finite(q) || !finite(step) || q < 0 || step <= 0)
        throw Error('Cantidad o precisión inválida'); return Number((Math.floor((q + step * 1e-9) / step) * step).toFixed(Math.min(12, Math.max(0, Math.ceil(-Math.log10(step)) + 2)))); }
    HC19.floorQty = floorQty;
    function quantity(equity, cash, used, price, atr, c, step) {
        if (![equity, cash, used, price, atr].every(Number.isFinite) || equity <= 0 || cash < 0 || used < 0 || price <= 0 || atr <= 0)
            return 0;
        equity = Math.min(equity, c.capital_limit);
        const riskDistance = c.atr_multiple * atr + price * (2 * c.fee_bps + 2 * c.slippage_bps) / 10000;
        const nominal = Math.min(equity * c.asset_cap, Math.max(0, equity * c.total_cap - used), cash / (1 + c.fee_bps / 10000), equity * c.risk_fraction / riskDistance * price);
        return floorQty(Math.max(0, nominal) / price, step);
    }
    HC19.quantity = quantity;
    function metrics(returns, trades, initial, fees = 0, turnover = 0) {
        const m = avg(returns), variance = returns.reduce((s, x) => s + (x - m) ** 2, 0) / Math.max(1, returns.length - 1), down = Math.sqrt(avg(returns.map(x => Math.min(0, x) ** 2)));
        let equity = initial, peak = initial, dd = 0;
        for (const r of returns) {
            equity *= 1 + r;
            peak = Math.max(peak, equity);
            dd = Math.max(dd, 1 - equity / peak);
        }
        const wins = trades.filter(t => t.net > 0), loss = -trades.filter(t => t.net < 0).reduce((s, t) => s + t.net, 0);
        return { net: equity - initial, return_pct: equity / initial - 1, cagr: returns.length ? Math.pow(equity / initial, 365 / returns.length) - 1 : 0, sharpe: variance > 1e-20 ? m / Math.sqrt(variance) * Math.sqrt(365) : null, sortino: down > 1e-12 ? m / down * Math.sqrt(365) : null, drawdown: dd, trades: trades.length, win_rate: trades.length ? wins.length / trades.length : null, profit_factor: loss ? wins.reduce((s, t) => s + t.net, 0) / loss : null, fees, turnover, days: returns.length };
    }
    HC19.metrics = metrics;
    function replay(data, cfg, start = 0, end = data['BTC/USD'].length, costMultiplier = 1, passive = false) {
        const c = validate(cfg), bars = data['BTC/USD'], warm = Math.max(c.entry_days, c.atr_days, c.exit_days) + 1;
        start = Math.max(start, warm);
        if (!Number.isInteger(start) || !Number.isInteger(end) || end > bars.length || end - start < 2 || !Number.isFinite(costMultiplier) || costMultiplier < 1)
            throw Error('Ventana de replay insuficiente');
        const fee = c.fee_bps / 10000 * costMultiplier, slip = c.slippage_bps / 10000 * costMultiplier;
        const positions = {}, trades = [], returns = [], nav = [], days = [];
        let cash = c.capital, previous = c.capital, peak = c.capital, fees = 0, turnover = 0, halt = false;
        const close = (s, price, t, reason) => { const p = positions[s]; if (!p)
            return; const nominal = p.qty * price, charge = nominal * fee; cash += nominal - charge; fees += charge; turnover += nominal; trades.push({ symbol: s, opened: p.opened, closed: t, entry: p.entry, exit: price, qty: p.qty, net: nominal - charge - p.cost, reason }); delete positions[s]; };
        for (let i = start; i < end; i++) {
            for (const s of HC19.SYMBOLS) {
                const b = data[s][i], sig = signal(data[s], c, i - 1);
                let p = positions[s];
                const had = Boolean(p);
                if (p && !passive) {
                    const timed = c.hold_hours > 0 && b.t - p.opened >= c.hold_hours * 3600000;
                    if (sig.exit || timed || halt)
                        close(s, b.o * (1 - slip), b.t, sig.exit ? 'TENDENCIA' : timed ? 'PLAZO' : 'DRAWDOWN');
                    else if (b.o <= p.stop)
                        close(s, b.o * (1 - slip), b.t, 'GAP STOP');
                    else if (b.l <= p.stop)
                        close(s, p.stop * (1 - slip), b.t, 'STOP INTRADÍA');
                }
                if (!had && !positions[s] && !halt && (passive ? i === start : sig.enter)) {
                    const used = HC19.SYMBOLS.reduce((sum, k) => sum + (positions[k]?.qty || 0) * data[k][i].o, 0), equity = cash + used, price = b.o * (1 + slip);
                    const qty = passive ? Math.min(cash / (1 + fee), c.capital * c.total_cap / 2) / price : quantity(equity, cash, used, price, sig.atr, { ...c, fee_bps: c.fee_bps * costMultiplier, slippage_bps: c.slippage_bps * costMultiplier }, .00000001);
                    if (qty * price >= 10) {
                        const nominal = qty * price, charge = nominal * fee;
                        cash -= nominal + charge;
                        fees += charge;
                        turnover += nominal;
                        positions[s] = { qty, entry: price, cost: nominal + charge, opened: b.t, stop: price - c.atr_multiple * sig.atr, high: price };
                        if (!passive && b.l <= positions[s].stop)
                            close(s, Math.min(b.o, positions[s].stop) * (1 - slip), b.t, 'STOP EN DÍA DE ENTRADA');
                    }
                }
                p = positions[s];
                if (p && !passive) {
                    p.high = Math.max(p.high, b.c);
                    p.stop = Math.max(p.stop, p.high - c.atr_multiple * signal(data[s], c, i).atr);
                }
            }
            if (i === end - 1)
                for (const s of HC19.SYMBOLS)
                    close(s, data[s][i].c * (1 - slip), bars[i].t + HC19.DAY - 1, 'FIN DE VENTANA');
            const equity = cash + HC19.SYMBOLS.reduce((sum, s) => sum + (positions[s]?.qty || 0) * data[s][i].c, 0);
            if (equity <= 0 || !Number.isFinite(equity))
                throw Error('Capital inválido en replay');
            peak = Math.max(peak, equity);
            if (!passive && 1 - equity / peak >= c.drawdown_limit)
                halt = true;
            returns.push(equity / previous - 1);
            nav.push(equity);
            days.push(bars[i].t);
            previous = equity;
        }
        return { metrics: metrics(returns, trades, c.capital, fees, turnover), returns, nav, days, trades, config: c, basis: 'Replay OHLC diario: fills aproximados; stop previo al parcial; costes explícitos; liquidación al final de ventana. No son fills reales.' };
    }
    HC19.replay = replay;
    function variants(base) { return [{ name: 'Tendencia 20/10', config: { ...base, entry_days: 20, exit_days: 10, hold_hours: 0 } }, { name: 'Tendencia 20/10 · 72h', config: { ...base, entry_days: 20, exit_days: 10, hold_hours: 72 } }, { name: 'Tendencia 40/20', config: { ...base, entry_days: 40, exit_days: 20, hold_hours: 0 } }, { name: 'Tendencia 40/20 · 72h', config: { ...base, entry_days: 40, exit_days: 20, hold_hours: 72 } }]; }
    HC19.variants = variants;
    function walkForward(data, base) {
        const n = data['BTC/USD'].length, hold = 180, train = 365, test = 90, gap = 1, warm = 121, holdStart = n - hold;
        if (n < 938)
            throw Error('Walk-forward: se requieren al menos 938 días completos comunes (365 entrenamiento, ≥3 bloques de 90, embargo y 180 finales)');
        const recipes = variants(validate(base)), folds = [], joined = [], benchmark = [], stressed = [], trades = [], stressTrades = [], benchmarkTrades = [];
        let attempts = 0, oosFees = 0, stressFees = 0, benchmarkFees = 0, oosTurnover = 0, stressTurnover = 0, benchmarkTurnover = 0;
        const choose = (a, b) => { const ranked = recipes.map(v => { attempts++; const result = replay(data, v.config, a, b); return { ...v, result, score: result.metrics.net > 0 && result.metrics.trades >= 4 ? (result.metrics.sharpe ?? -100) - 2 * result.metrics.drawdown : -100 }; }).sort((a, b) => b.score - a.score); return ranked[0]; };
        for (let at = warm + train + gap; at + test <= holdStart - gap; at += test) {
            const winner = choose(at - gap - train, at - gap), out = replay(data, winner.config, at, at + test), stress = replay(data, winner.config, at, at + test, 2), bench = replay(data, base, at, at + test, 1, true);
            folds.push({ start: data['BTC/USD'][at].t, end: data['BTC/USD'][at + test - 1].t, selected: winner.name, training: winner.result.metrics, test: out.metrics });
            joined.push(...out.returns);
            stressed.push(...stress.returns);
            benchmark.push(...bench.returns);
            trades.push(...out.trades);
            stressTrades.push(...stress.trades);
            benchmarkTrades.push(...bench.trades);
            oosFees += out.metrics.fees;
            stressFees += stress.metrics.fees;
            benchmarkFees += bench.metrics.fees;
            oosTurnover += out.metrics.turnover;
            stressTurnover += stress.metrics.turnover;
            benchmarkTurnover += bench.metrics.turnover;
        }
        if (folds.length < 3)
            throw Error('Historia insuficiente para tres bloques fuera de muestra');
        const winner = choose(holdStart - gap - train, holdStart - gap), final = replay(data, winner.config, holdStart, n), finalStress = replay(data, winner.config, holdStart, n, 2), finalBenchmark = replay(data, base, holdStart, n, 1, true), oos = metrics(joined, trades, base.capital, oosFees, oosTurnover), stress = metrics(stressed, stressTrades, base.capital, stressFees, stressTurnover), bench = metrics(benchmark, benchmarkTrades, base.capital, benchmarkFees, benchmarkTurnover);
        const gates = { oos_positive: oos.net > 0, holdout_positive: final.metrics.net > 0, cost_stress: stress.net > 0 && finalStress.metrics.net > 0, drawdown: oos.drawdown <= base.drawdown_limit && final.metrics.drawdown <= base.drawdown_limit, trade_count: oos.trades >= 20 && final.metrics.trades >= 5, sharpe_vs_passive: (oos.sharpe ?? -100) > (bench.sharpe ?? -100), fold_stability: folds.filter(f => f.test.net > 0).length >= Math.ceil(folds.length * .6) };
        return { schema: 'HARPOON-XIX-CRYPTO-WF-1', version: HC19.VERSION, metric_series23: { dates: folds.flatMap(f => data['BTC/USD'].filter(b => b.t >= f.start && b.t <= f.end).map(b => new Date(b.t).toISOString().slice(0, 10))), candidate: joined, baseline: benchmark, benchmark, annualization: 365, boundary: 'reset_at_folds', costs_confirmed: false, capital: base.capital, external_candidate_usd: 0, external_baseline_usd: 0, cost_basis: JSON.stringify({ fee_bps: base.fee_bps, slippage_bps: base.slippage_bps }), risk_hash: JSON.stringify({ risk: base.risk_fraction, cap: base.total_cap }), policy_before: 'PASSIVE50', policy_after: winner.name }, source: 'REPLAY', status: Object.values(gates).every(Boolean) ? 'CANDIDATA PARA PAPER' : 'RECHAZADA', gates, selected: winner.name, config: winner.config, attempts, folds, oos, stress, benchmark: bench, holdout: final.metrics, holdout_stress: finalStress.metrics, holdout_benchmark: finalBenchmark.metrics, holdout_start: data['BTC/USD'][holdStart].t, through: data['BTC/USD'][n - 1].t, changes_orders: false, protocol: { train_days: train, test_days: test, gap_days: gap, final_days: hold, warmup_days: warm, flat_boundaries: true, annualization: 365 }, basis: 'Selección exclusivamente en entrenamiento; posiciones liquidadas antes de fronteras y un día excluido. Retornos OOS enlazados; tamaño reiniciado en cada bloque. Comisiones USD sumadas por bloques, no reescaladas al patrimonio enlazado. Cuatro recetas, sin ML ni promoción automática; estadística descriptiva, sin certificación DSR o significación.' };
    }
    HC19.walkForward = walkForward;
})(HC19 || (HC19 = {}));
