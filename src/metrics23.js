"use strict";
/** XXIII. Pure, daily, net-of-cost comparisons. No order or network authority. */
var HM23;
(function (HM23) {
    HM23.VERSION = '23.0.0';
    const avg = (x) => x.reduce((s, v) => s + v, 0) / x.length;
    const finite = (x) => typeof x === 'number' && Number.isFinite(x);
    const variance = (x) => { const m = avg(x); return x.length > 1 ? x.reduce((s, v) => s + (v - m) ** 2, 0) / (x.length - 1) : 0; };
    const sd = (x) => Math.sqrt(variance(x));
    const quantile = (xs, q) => { const x = [...xs].sort((a, b) => a - b), i = (x.length - 1) * q, l = Math.floor(i); return x[l] + (x[Math.ceil(i)] - x[l]) * (i - l); };
    const guarded = (n, d) => Math.abs(d) > 1e-12 ? n / d : null;
    function validate(s) {
        if (!s || !['SYNTHETIC', 'HISTORICAL_REPLAY', 'PAPER', 'LIVE', 'IMPORTED_UNVERIFIED'].includes(s.source) || !Array.isArray(s.returns) || s.returns.length < 2 || s.returns.length > 20000 || !Array.isArray(s.dates) || s.dates.length !== s.returns.length)
            throw Error('Se requieren entre 2 y 20.000 retornos diarios y fechas coincidentes.');
        if (!s.returns.every(v => finite(v) && v >= -1) || !s.dates.every((v, i) => typeof v === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(v) && Number.isFinite(Date.parse(v)) && new Date(Date.parse(v)).toISOString().slice(0, 10) === v && (!i || v > s.dates[i - 1])))
            throw Error('Retornos inválidos, fechas duplicadas o desordenadas.');
        if (![252, 365].includes(s.annualization) || !finite(s.capital) || s.capital <= 0 || !finite(s.external_costs_usd) || s.external_costs_usd < 0 || ![s.rf_annual, s.mar_annual].every(v => finite(v) && v > -1 && v <= 2))
            throw Error('Capital, anualización o costes inválidos.');
        if (s.benchmark && (!Array.isArray(s.benchmark) || s.benchmark.length !== s.returns.length || !s.benchmark.every(v => finite(v) && v >= -1)))
            throw Error('Benchmark sin las mismas observaciones.');
        if (typeof s.risk_hash !== 'string' || !s.risk_hash || typeof s.policy_hash !== 'string' || !s.policy_hash || !s.cost_basis || typeof s.costs_confirmed !== 'boolean' || !['continuous', 'reset_at_folds'].includes(s.boundary))
            throw Error('Falta el contrato de riesgo, costes o política.');
        if (s.trades && (!Array.isArray(s.trades) || s.trades.length > 100000 || !s.trades.every(t => t && finite(t.net) && Object.entries(t).every(([k, v]) => ['net', 'gross', 'fees', 'mfe', 'captured', 'hours', 'slippage_bps'].includes(k) && finite(v)))))
            throw Error('Operaciones inválidas.');
        if ([s.fees_usd, s.turnover_usd].some(v => v !== undefined && (!finite(v) || v < 0)))
            throw Error('Comisiones o rotación inválidas.');
        return s;
    }
    HM23.validate = validate;
    function hac(x, lag = Math.min(x.length - 1, Math.floor(4 * (x.length / 100) ** (2 / 9)))) {
        const m = avg(x), z = x.map(v => v - m), n = x.length;
        let v = z.reduce((s, y) => s + y * y, 0) / n;
        for (let k = 1; k <= lag; k++) {
            let cov = 0;
            for (let i = k; i < n; i++)
                cov += z[i] * z[i - k];
            v += 2 * (1 - k / (lag + 1)) * cov / n;
        }
        return Math.max(0, v);
    }
    function alphaHAC(r, b, rf, A) {
        const x = b.map(v => v - rf), y = r.map(v => v - rf), mx = avg(x), my = avg(y), den = x.reduce((s, v) => s + (v - mx) ** 2, 0);
        if (den < 1e-18 || x.length < 30)
            return { alpha: null, beta: null, ci: null };
        const beta = x.reduce((s, v, i) => s + (v - mx) * (y[i] - my), 0) / den, a = my - beta * mx, n = x.length;
        // Influence of each residual on OLS intercept; Bartlett/Newey-West covariance.
        const influence = x.map((v, i) => (y[i] - a - beta * v) * (1 / n - mx * (v - mx) / den));
        let v = influence.reduce((s, z) => s + z * z, 0);
        const L = Math.min(n - 1, Math.floor(4 * (n / 100) ** (2 / 9)));
        for (let k = 1; k <= L; k++)
            for (let i = k; i < n; i++)
                v += 2 * (1 - k / (L + 1)) * influence[i] * influence[i - k];
        const se = Math.sqrt(Math.max(0, v * n / (n - 2))) * A;
        return { alpha: a * A, beta, ci: [a * A - 1.96 * se, a * A + 1.96 * se] };
    }
    function summarize(input) {
        const s = validate(input), r = s.returns, n = r.length, A = s.annualization, rf = (1 + s.rf_annual) ** (1 / A) - 1, mar = (1 + s.mar_annual) ** (1 / A) - 1, ex = r.map(v => v - rf), vol = sd(r), mean = avg(ex), down = Math.sqrt(avg(r.map(v => Math.min(0, v - mar) ** 2)));
        let nav = s.capital, peak = nav, maxdd = 0, under = 0, longest = 0;
        const navs = [], dds = [];
        for (const v of r) {
            nav *= 1 + v;
            if (!Number.isFinite(nav))
                throw Error('Patrimonio fuera del rango numérico.');
            peak = Math.max(peak, nav);
            const dd = 1 - nav / peak;
            maxdd = Math.max(maxdd, dd);
            under = dd > 1e-12 ? under + 1 : 0;
            longest = Math.max(longest, under);
            navs.push(nav);
            dds.push(dd);
        }
        const ret = nav / s.capital - 1, years = (Date.parse(s.dates[n - 1]) - Date.parse(s.dates[0]) + 86400000) / (365.25 * 86400000), cagr = years >= 1 ? (nav / s.capital) ** (1 / years) - 1 : null;
        const trades = s.trades, wins = trades?.filter(t => t.net > 0) || [], losses = trades?.filter(t => t.net < 0) || [], loss = -losses.reduce((v, t) => v + t.net, 0), profit = wins.reduce((v, t) => v + t.net, 0), q = quantile(r, .05), tail = r.filter(v => v <= q);
        const alpha = s.benchmark ? alphaHAC(r, s.benchmark, rf, A) : { alpha: null, beta: null, ci: null };
        const track = s.benchmark ? r.map((v, i) => v - s.benchmark[i]) : null;
        const captured = trades?.filter(t => finite(t.mfe) && t.mfe > 0 && finite(t.captured)) || [];
        const m = {};
        const put = (k, v, unit = 'ratio', direction = 'higher') => { m[k] = { value: v !== null && finite(v) ? v : null, unit, direction }; };
        put('net_return', ret, 'percent');
        put('net_trading', nav - s.capital, 'usd');
        put('net_economic', s.costs_confirmed ? nav - s.capital - s.external_costs_usd : null, 'usd');
        put('end_capital', s.costs_confirmed ? nav - s.external_costs_usd : null, 'usd');
        put('sharpe', n >= 30 ? guarded(mean * Math.sqrt(A), sd(ex)) : null);
        put('sharpe_hac', n >= 30 ? guarded(mean * Math.sqrt(A), Math.sqrt(hac(ex))) : null);
        put('sortino', n >= 30 ? guarded((avg(r) - mar) * Math.sqrt(A), down) : null);
        put('max_drawdown', maxdd, 'percent', 'lower');
        put('calmar', cagr !== null ? guarded(cagr, maxdd) : null);
        put('cagr', cagr, 'percent');
        put('volatility', n >= 30 ? vol * Math.sqrt(A) : null, 'percent', 'lower');
        put('alpha', alpha.alpha, 'percent');
        put('beta', alpha.beta, 'ratio', 'neutral');
        put('tracking_error', track && n >= 30 ? sd(track) * Math.sqrt(A) : null, 'percent', 'neutral');
        put('information_ratio', track && n >= 30 ? guarded(avg(track) * Math.sqrt(A), sd(track)) : null);
        put('var95', n >= 60 ? Math.max(0, -q) : null, 'percent', 'lower');
        put('expected_shortfall95', n >= 60 ? Math.max(0, -avg(tail)) : null, 'percent', 'lower');
        put('underwater_days', longest, 'count', 'lower');
        put('trades', trades ? trades.length : null, 'count', 'neutral');
        put('win_rate', trades?.length ? wins.length / trades.length : null, 'percent');
        put('profit_factor', trades?.length ? guarded(profit, loss) : null);
        put('expectancy', trades?.length ? avg(trades.map(t => t.net)) : null, 'usd');
        put('payoff_ratio', wins.length && losses.length ? guarded(avg(wins.map(t => t.net)), -avg(losses.map(t => t.net))) : null);
        put('fees', s.fees_usd ?? null, 'usd', 'lower');
        put('external_costs', s.external_costs_usd, 'usd', 'lower');
        put('turnover', s.turnover_usd === undefined ? null : s.turnover_usd / s.capital, 'ratio', 'neutral');
        put('mfe_capture', captured.length ? captured.reduce((v, t) => v + t.captured, 0) / captured.reduce((v, t) => v + t.mfe, 0) : null, 'percent');
        put('holding_hours', trades?.length && trades.every(t => finite(t.hours)) ? avg(trades.map(t => t.hours)) : null, 'hours', 'neutral');
        put('slippage_bps', trades?.length && trades.every(t => finite(t.slippage_bps)) ? avg(trades.map(t => t.slippage_bps)) : null, 'bps', 'lower');
        const warnings = ['Retornos diarios netos de ejecución; facturas externas se restan al neto económico, no a los ratios diarios.', 'Alpha es anualizado aritméticamente frente al benchmark indicado; no representa gamma de opciones.'];
        if (n < 60)
            warnings.push('Muestra corta: precisión limitada; ratios necesitan 30 observaciones y colas al menos 60.');
        if (!s.costs_confirmed)
            warnings.push('Costes externos no confirmados: neto económico no disponible.');
        if (cagr === null)
            warnings.push('CAGR y Calmar no disponibles antes de un año de calendario.');
        if (s.boundary === 'reset_at_folds')
            warnings.push('Folds reiniciados: NAV enlazado es un índice diagnóstico, no capital compuesto ejecutado.');
        if (s.source === 'IMPORTED_UNVERIFIED')
            warnings.push('Archivo declarado por el usuario: origen y resultados no verificados.');
        if (!s.benchmark)
            warnings.push('Sin benchmark comparable: alpha, beta e information ratio no disponibles.');
        return { schema: 'HARPOON-XXIII-METRICS-1', source: s.source, label: s.label, from: s.dates[0], through: s.dates[n - 1], n, metrics: m, nav: navs, drawdowns: dds, warnings, alpha_ci95: alpha.ci };
    }
    HM23.summarize = summarize;
    function compare(baseline, candidate, attempts = 1, iterations = 1000) {
        const b = validate(baseline), c = validate(candidate);
        for (const k of ['source', 'annualization', 'capital', 'risk_hash', 'cost_basis', 'rf_annual', 'mar_annual', 'boundary'])
            if (b[k] !== c[k])
                throw Error('Comparación inválida: ' + k + ' diferente.');
        if (b.dates.join() !== c.dates.join() || JSON.stringify(b.benchmark || null) !== JSON.stringify(c.benchmark || null))
            throw Error('Fechas o benchmark no coinciden; no se rellenan huecos.');
        if (!Number.isInteger(attempts) || attempts < 1 || attempts > 10000 || !Number.isInteger(iterations) || iterations < 200 || iterations > 5000)
            throw Error('Conteo de búsquedas o bootstrap inválido.');
        const bs = summarize(b), cs = summarize(c), delta = {};
        for (const [k, v] of Object.entries(cs.metrics)) {
            const old = bs.metrics[k].value, d = v.value !== null && old !== null ? v.value - old : null;
            delta[k] = { baseline: old, candidate: v.value, absolute: d, relative: d !== null && old !== null && Math.abs(old) > 1e-12 ? d / Math.abs(old) : null, improved: d === null || v.direction === 'neutral' ? null : v.direction === 'higher' ? d > 0 : d < 0, unit: v.unit };
        }
        // Paired circular block bootstrap. Counts ALL tries; insufficient tail resolution fails closed.
        const d = c.returns.map((v, i) => v - b.returns[i]), block = Math.max(3, Math.ceil(Math.cbrt(d.length))), draws = [];
        let seed = 0x23ab79;
        const rnd = () => { seed ^= seed << 13; seed ^= seed >>> 17; seed ^= seed << 5; return (seed >>> 0) / 4294967296; };
        for (let j = 0; j < iterations; j++) {
            let sum = 0, k = 0;
            while (k < d.length) {
                const at = Math.floor(rnd() * d.length);
                for (let a = 0; a < block && k < d.length; a++, k++)
                    sum += d[(at + a) % d.length];
            }
            draws.push(sum / d.length);
        }
        const q = .05 / attempts, resolutionOK = iterations * q >= 10, lower = resolutionOK ? quantile(draws, q) : null;
        const evidence = { method: 'Bootstrap circular pareado; bloques contiguos; cota unilateral Bonferroni', block_days: block, replications: iterations, attempts, confidence: 1 - q, mean_daily_delta: avg(d), lower_daily_delta: lower, resolution_ok: resolutionOK, positive: lower !== null && lower > 0 };
        return { schema: 'HARPOON-XXIII-COMPARISON-1', baseline: bs, candidate: cs, delta, evidence, policy_before: b.policy_hash, policy_after: c.policy_hash, profitability_verified: false, changes_orders: false };
    }
    HM23.compare = compare;
    function fromEquity(dates, equity, flows, base) {
        if (dates.length !== equity.length || equity.length !== flows.length || !finite(base) || base <= 0)
            throw Error('Serie de patrimonio o flujos inválida.');
        let prior = base;
        return equity.map((v, i) => { if (!finite(v) || v <= 0 || !finite(flows[i]) || prior <= 0)
            throw Error('Patrimonio o flujo no válido'); const r = (v - flows[i]) / prior - 1; if (r < -1)
            throw Error('Flujos incompatibles con patrimonio'); prior = v; return r; });
    }
    HM23.fromEquity = fromEquity;
})(HM23 || (HM23 = {}));
