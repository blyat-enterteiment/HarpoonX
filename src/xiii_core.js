"use strict";
/** XIII: paired daily evidence, bounded allocation and conditional survival research. */
var HXIII;
(function (HXIII) {
    HXIII.VERSION = '13.0.0';
    HXIII.POLICY = 'XIII-EVIDENCE-1';
    const avg = (a) => a.length ? a.reduce((s, x) => s + x, 0) / a.length : 0;
    const variance = (a) => { const m = avg(a); return a.length > 1 ? a.reduce((s, x) => s + (x - m) ** 2, 0) / (a.length - 1) : 0; };
    function quantile(a, p) { if (!a.length)
        throw Error('Muestra vacía'); const x = [...a].sort((a, b) => a - b), i = (x.length - 1) * p, k = Math.floor(i); return x[k] + (x[Math.min(k + 1, x.length - 1)] - x[k]) * (i - k); }
    HXIII.quantile = quantile;
    function random(seed) { let s = seed >>> 0; return () => { s = (s + 0x6D2B79F5) >>> 0; let t = s; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }
    HXIII.random = random;
    function validateEvidence(e) {
        if (!e || e.schema !== 'HARPOON-XIII-DAILY-1' || !['PAPER', 'LIVE', 'REPLAY', 'SYNTHETIC'].includes(e.source) || typeof e.policy_id !== 'string' || !e.policy_id || typeof e.costs_confirmed !== 'boolean' || !Array.isArray(e.rows) || e.rows.length > 5000)
            throw Error('Evidencia diaria XIII inválida');
        let prior = '';
        for (const d of e.rows) {
            if (!/^\d{4}-\d{2}-\d{2}$/.test(d.day) || d.day <= prior || !Number.isFinite(Date.parse(d.day)) || !Number.isFinite(d.capital) || d.capital <= 0 || ![d.equity, d.etf].every(Number.isFinite) || d.equity + d.etf <= -1 || Math.abs(d.equity) > 2 || Math.abs(d.etf) > 2 || ![d.equity_closes, d.etf_closes].every(v => Number.isInteger(v) && v >= 0))
                throw Error('Sesiones desordenadas, duplicadas o valores fuera del contrato');
            prior = d.day;
        }
        if (e.rows.length && e.through !== prior)
            throw Error('Fecha final incoherente');
    }
    HXIII.validateEvidence = validateEvidence;
    function correlation(a, b) { const ma = avg(a), mb = avg(b), va = variance(a), vb = variance(b); if (a.length !== b.length || a.length < 2 || va < 1e-20 || vb < 1e-20)
        return null; return Math.max(-1, Math.min(1, a.reduce((s, x, i) => s + (x - ma) * (b[i] - mb), 0) / ((a.length - 1) * Math.sqrt(va * vb)))); }
    HXIII.correlation = correlation;
    function drawdown(r) { let w = 1, p = 1, d = 0; for (const x of r) {
        w *= Math.max(0, 1 + x);
        p = Math.max(p, w);
        d = Math.max(d, 1 - w / p);
    } return d; }
    HXIII.drawdown = drawdown;
    function lowerMean(r, block = 5, paths = 1200, seed = 713) { if (r.length < 30)
        return null; const rng = random(seed), means = []; for (let p = 0; p < paths; p++) {
        let total = 0, n = 0;
        while (n < r.length) {
            const start = Math.floor(rng() * r.length);
            for (let j = 0; j < block && n < r.length; j++, n++)
                total += r[(start + j) % r.length];
        }
        means.push(total / r.length);
    } return quantile(means, .025); }
    HXIII.lowerMean = lowerMean;
    function analyze(e) {
        validateEvidence(e);
        const rows = e.rows, a = rows.map(d => d.equity), b = rows.map(d => d.etf), joint = a.map((v, i) => v + b[i]), both = a.filter((v, i) => v < 0 && b[i] < 0).length, either = a.filter((v, i) => v < 0 || b[i] < 0).length, sd = Math.sqrt(variance(joint));
        const book = (key, r) => ({ sessions: r.length, active_sessions: r.filter(v => Math.abs(v) > 1e-12).length, closed: rows.reduce((s, d) => s + d[key === 'equity' ? 'equity_closes' : 'etf_closes'], 0), contribution_usd: rows.reduce((s, d) => s + d.capital * d[key], 0), daily_mean: r.length ? avg(r) : null, lower_mean_97_5: lowerMean(r), recent_mean: r.length >= 20 ? avg(r.slice(-20)) : null, drawdown: r.length ? drawdown(r) : null });
        return { source: e.source, policy_id: e.policy_id, through: e.through, sessions: rows.length, books: { equity: book('equity', a), etf: book('etf', b) }, correlation: correlation(a, b), downside_correlation: correlation(a.map(v => Math.min(0, v)), b.map(v => Math.min(0, v))), joint_loss_days: both, any_loss_days: either, joint_loss_fraction: either ? both / either : null, diversification_ratio: sd > 1e-12 ? (Math.sqrt(variance(a)) + Math.sqrt(variance(b))) / sd : null, joint_drawdown: rows.length ? drawdown(joint) : null, joint_growth: rows.length ? joint.reduce((s, v) => s * (1 + v), 1) - 1 : null, basis: 'Contribuciones diarias sobre el mismo NAV inicial de sesión; covariance includes no-trade days. Límite por bootstrap circular de bloques, aproximado; no demuestra causalidad ni independencia.' };
    }
    HXIII.analyze = analyze;
    function allocate(e, current, flat, freshEvidence) {
        const a = analyze(e), result = { ...current }, reasons = {};
        for (const key of ['equity', 'etf']) {
            const v = current[key];
            if (![.25, .5, .75, 1].includes(v))
                throw Error('Escala de evidencia inválida');
            const b = a.books[key];
            let target = v, reason = 'RECOPILANDO · sin aumento por falta de evidencia';
            if (!['PAPER', 'LIVE'].includes(e.source)) {
                reason = 'DIAGNÓSTICO · fuente no operativa';
            }
            else if (e.rows.length === 0) {
                reason = 'RECOPILANDO · sin historial; escala inicial conservada';
            }
            else if (!freshEvidence || !e.costs_confirmed) {
                target = .25;
                reason = 'REDUCIR · datos vencidos o costes pendientes';
            }
            else if ((b.drawdown ?? 0) >= .04 || (b.recent_mean !== null && b.recent_mean <= 0)) {
                target = .25;
                reason = 'REDUCIR · deterioro observado';
            }
            else if (b.sessions >= 63 && b.closed >= 30 && b.active_sessions >= 30 && (b.lower_mean_97_5 ?? -1) > 0 && b.contribution_usd > 0) {
                target = Math.min(1, v + .25);
                reason = 'AUMENTO ELEGIBLE · media inferior positiva y cobertura';
            }
            if ((a.correlation ?? 0) > .85 && (a.joint_loss_fraction ?? 0) > .65 && a.sessions >= 63 && target > .5) {
                target = .5;
                reason = 'LIMITAR · pérdidas y retornos muy coincidentes';
            }
            if (target > v && !flat) {
                target = v;
                reason = 'ESPERAR CUENTA PLANA · aumento elegible';
            }
            result[key] = target;
            reasons[key] = reason;
        }
        return { scales: result, reasons, analysis: a, basis: 'Multiplicadores 25–100% de límites existentes. No reasigna riesgo liberado al otro motor; aumentos sólo con cuenta plana. Evidencia descriptiva del tamaño realmente operado.' };
    }
    HXIII.allocate = allocate;
    function wilson(success, n) { const z = 1.959963984540054, p = success / n, d = 1 + z * z / n, c = (p + z * z / (2 * n)) / d, h = z * Math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d; return { estimate: p, lower: Math.max(0, c - h), upper: Math.min(1, c + h), count: success, paths: n }; }
    HXIII.wilson = wilson;
    function validateScenario(s) { if (!s || ![s.initial, s.target, s.monthly_cost, s.monthly_withdrawal, s.capital_cap, s.floor_fraction, s.drawdown_limit].every(Number.isFinite) || s.initial <= 0 || s.initial > 1e9 || s.target <= s.initial || s.target > 1e12 || s.capital_cap <= 0 || s.capital_cap > 1e9 || s.monthly_cost < 0 || s.monthly_withdrawal < 0 || s.monthly_cost > 1e7 || s.monthly_withdrawal > 1e7 || s.floor_fraction <= 0 || s.floor_fraction >= 1 || s.drawdown_limit <= 0 || s.drawdown_limit >= 1 || !Number.isInteger(s.sessions) || s.sessions < 21 || s.sessions > 2520 || !Number.isInteger(s.paths) || s.paths < 500 || s.paths > 5000 || !Number.isInteger(s.seed) || s.seed < 0 || s.seed > 4294967295 || ![5, 10, 21].includes(s.block) || !['empirical', 'conservative'].includes(s.drift))
        throw Error('Escenario fuera de límites'); }
    HXIII.validateScenario = validateScenario;
    function simulate(e, s) {
        validateEvidence(e);
        validateScenario(s);
        const a = analyze(e), reasons = [];
        if (e.rows.length < 126)
            reasons.push('Se requieren 126 sesiones completas de una misma política');
        if (a.books.equity.closed + a.books.etf.closed < 50)
            reasons.push('Se requieren 50 campañas cerradas');
        if (!e.costs_confirmed)
            reasons.push('Falta confirmar costes externos');
        const raw = e.rows.map(d => d.equity + d.etf);
        if (variance(raw) < 1e-16)
            reasons.push('Variación insuficiente para estimar escenarios');
        if (reasons.length)
            return { status: 'EVIDENCIA_INSUFICIENTE', reasons, source: e.source, sessions_observed: e.rows.length, probabilities: null };
        const rng = random(s.seed), cut = s.drift === 'conservative' ? Math.max(0, avg(raw)) * .5 : 0, returns = raw.map(v => v - cut), terminal = [], drawdowns = [], hits = [], fan = { 0: [s.initial] };
        let goal = 0, critical = 0, floor = 0, ddEvent = 0, endGoal = 0;
        for (let path = 0; path < s.paths; path++) {
            let wealth = s.initial, peak = wealth, maxDD = 0, hit = false, breach = false, hitFloor = false, hitDD = false, start = 0;
            for (let t = 0; t < s.sessions; t++) {
                if (t % s.block === 0)
                    start = Math.floor(rng() * returns.length);
                // Sample the paired portfolio return: never resample books independently.
                const r = returns[(start + t % s.block) % returns.length];
                if (!breach)
                    wealth += Math.min(wealth, s.capital_cap) * r;
                wealth = Math.max(0, wealth - s.monthly_cost / 21 - ((t + 1) % 21 === 0 ? s.monthly_withdrawal : 0));
                peak = Math.max(peak, wealth);
                maxDD = Math.max(maxDD, 1 - wealth / peak);
                hitFloor ||= wealth <= s.initial * s.floor_fraction;
                hitDD ||= maxDD >= s.drawdown_limit;
                breach ||= hitFloor || hitDD;
                if (!breach && !hit && wealth >= s.target) {
                    hit = true;
                    hits.push(t + 1);
                }
                if ((t + 1) % 21 === 0 || t === s.sessions - 1)
                    (fan[t + 1] ??= []).push(wealth);
            }
            if (hit)
                goal++;
            if (breach)
                critical++;
            if (hitFloor)
                floor++;
            if (hitDD)
                ddEvent++;
            if (wealth >= s.target)
                endGoal++;
            terminal.push(wealth);
            drawdowns.push(maxDD);
        }
        return { status: 'SIMULACIÓN_CONDICIONAL', source: e.source, policy_id: e.policy_id, through: e.through, sessions_observed: e.rows.length, scenario: s, probabilities: { target_before_breach: wilson(goal, s.paths), critical_breach: wilson(critical, s.paths), floor_breach: wilson(floor, s.paths), drawdown_breach: wilson(ddEvent, s.paths), terminal_target: wilson(endGoal, s.paths) }, terminal: { p05: quantile(terminal, .05), p50: quantile(terminal, .5), p95: quantile(terminal, .95) }, max_drawdown: { p50: quantile(drawdowns, .5), p95: quantile(drawdowns, .95) }, median_sessions_to_goal: hits.length ? quantile(hits, .5) : null, fan: Object.entries(fan).map(([session, v]) => ({ session: Number(session), p05: quantile(v, .05), p50: quantile(v, .5), p95: quantile(v, .95) })), method: 'Bootstrap circular de retornos diarios conjuntos por bloques. Deriva positiva reducida a la mitad en modo conservador. Costes externos diarios y retiro cada 21 sesiones; sin impuestos. Capital invertible limitado; excedente en efectivo sin interés. Tras umbral crítico cesa la exposición, continúan gastos y retiros.', limits: ['Probabilidades condicionadas al historial y supuestos; los intervalos Wilson sólo miden error Monte Carlo, no incertidumbre del mercado.', 'Cero éxitos simulados no significa imposibilidad. La muestra no contiene todas las crisis ni movimientos extremos futuros.', 'No reproduce intradía, reservas por campaña, fills o capacidad futura. Escalar retornos diarios a otro capital es una aproximación; el resultado no modifica límites ni órdenes.', 'PAPER/REPLAY/SYNTHETIC no son rentabilidad LIVE. Extrapolar hasta diez años supone estabilidad no demostrada.'] };
    }
    HXIII.simulate = simulate;
    function survival(e, s) { const primary = simulate(e, s); if (primary.status !== 'SIMULACIÓN_CONDICIONAL')
        return primary; const sensitivity = [5, 10, 21].map(block => block === s.block ? primary : simulate(e, { ...s, block })); return { ...primary, sensitivity: sensitivity.map(r => ({ block: r.scenario?.block, target: r.probabilities?.target_before_breach, critical: r.probabilities?.critical_breach, terminal: r.terminal })), changes_orders: false }; }
    HXIII.survival = survival;
    function variants(base) { return HPCatalog.xiiiVariants(base); }
    HXIII.variants = variants;
})(HXIII || (HXIII = {}));
