"use strict";
/** Contracts shared by UI, sandbox and recursive controller. No executable plugins. */
var HF23;
(function (HF23) {
    HF23.SEC = {
        tp1_r: { kind: 'number', min: 1, max: 2.5, step: .125, label: 'Primer beneficio · R' }, tp2_r: { kind: 'number', min: 2.5, max: 5, step: .125, label: 'Segundo beneficio · R' },
        tp1_fraction: { kind: 'number', min: .125, max: .5, step: .125, label: 'Fracción del primer parcial' }, tp2_fraction: { kind: 'number', min: .125, max: .5, step: .125, label: 'Fracción del segundo parcial' },
        trail_atr: { kind: 'number', min: 1.5, max: 4, step: .25, label: 'Trailing · ATR' }, lock_fraction: { kind: 'number', min: .35, max: .7, step: .05, label: 'Fracción de recorrido protegida' },
        hold_hours: { kind: 'enum', values: [1.5, 24, 48, 72], label: 'Salida máxima · horas' }, stagnation_minutes: { kind: 'integer', min: 10, max: 60, step: 5, label: 'Estancamiento · minutos' }, progress_r: { kind: 'number', min: 0, max: 1, step: .1, label: 'Progreso mínimo · R' },
        trailing_mode: { kind: 'enum', values: ['entry_atr', 'realized_vol'], label: 'Modo de trailing' }, exit_layout: { kind: 'enum', values: ['two_targets', 'single_target'], label: 'Distribución de salidas' },
        min_rvol: { kind: 'number', min: 2, max: 4, step: .25, label: 'Volumen relativo mínimo' }, momentum_bps: { kind: 'number', min: 20, max: 100, step: 10, label: 'Momentum · bps' }, reentry: { kind: 'boolean', label: 'Permitir reentrada' }, selection_filter: { kind: 'enum', values: ['none', 'ridge_lcb'], label: 'Filtro de selección' }
    };
    HF23.TREND = { entryDays: { kind: 'integer', min: 10, max: 120, step: 5, label: 'Ruptura · días' }, exitDays: { kind: 'integer', min: 2, max: 60, step: 2, label: 'Salida · días' }, atrDays: { kind: 'integer', min: 5, max: 60, step: 5, label: 'ATR · días' }, atrMultiple: { kind: 'number', min: 1, max: 6, step: .25, label: 'Trailing · ATR' }, holdHours: { kind: 'integer', min: 0, max: 72, step: 1, label: 'Máximo · horas; 0 = tendencia' } };
    HF23.RECOVERY = { shockZ: { kind: 'number', min: 2, max: 4, step: .25, label: 'Shock · z' }, minShockBps: { kind: 'number', min: 100, max: 500, step: 25, label: 'Shock mínimo · bps' }, volumeRatio: { kind: 'number', min: 1.5, max: 4, step: .25, label: 'Volumen relativo' }, sellShare: { kind: 'number', min: .6, max: .85, step: .05, label: 'Proporción vendedora' }, recoveryBuyShare: { kind: 'number', min: .5, max: .7, step: .05, label: 'Recuperación compradora' }, maxSpreadBps: { kind: 'number', min: 2, max: 30, step: 2, label: 'Spread máximo · bps' }, roomCostMultiple: { kind: 'number', min: 2, max: 4, step: .25, label: 'Recorrido / coste' }, minRewardRisk: { kind: 'number', min: 1, max: 3, step: .25, label: 'Beneficio / riesgo' }, holdHours: { kind: 'integer', min: 1, max: 24, step: 1, label: 'Máximo · horas' } };
    HF23.OPTIONS = { min_dte: { kind: 'integer', min: 2, max: 30, step: 1, label: 'DTE mínimo' }, max_dte: { kind: 'integer', min: 7, max: 60, step: 1, label: 'DTE máximo' }, delta_min: { kind: 'number', min: .2, max: .7, step: .05, label: 'Delta mínimo' }, delta_max: { kind: 'number', min: .3, max: .9, step: .05, label: 'Delta máximo' }, max_spread_pct: { kind: 'number', min: .01, max: .15, step: .01, label: 'Spread máximo / mid' }, target_multiple: { kind: 'number', min: 1.1, max: 4, step: .1, label: 'Valor de salida / débito' }, stop_fraction: { kind: 'number', min: .1, max: .5, step: .05, label: 'Pérdida de prima para salida' }, hold_hours: { kind: 'integer', min: 1, max: 72, step: 1, label: 'Máximo · horas' } };
    HF23.ASTRA = { tpR: { kind: 'number', min: 1, max: 2.5, label: 'Beneficio objetivo · R' }, partialFraction: { kind: 'number', min: 0, max: .35, label: 'Fracción del parcial' }, trailAtr: { kind: 'number', min: 1.5, max: 4, label: 'Trailing · ATR' }, lockFraction: { kind: 'number', min: .35, max: .7, label: 'Recorrido protegido' }, stagnationMinutes: { kind: 'number', min: 10, max: 60, label: 'Estancamiento · minutos' }, holdHours: { kind: 'enum', values: [1.5, 24, 48, 72], label: 'Salida máxima · horas' }, impulseMinutes: { kind: 'integer', min: 3, max: 10, label: 'Impulso · minutos' }, pauseMinutes: { kind: 'integer', min: 3, max: 15, label: 'Pausa · minutos' }, minHistoryDays: { kind: 'integer', min: 5, max: 20, label: 'Historia mínima · días' }, impulseZ: { kind: 'number', min: 1, max: 5, label: 'Impulso · z' }, minRvol: { kind: 'number', min: 1.2, max: 5, label: 'Volumen relativo' }, minRetained: { kind: 'number', min: .3, max: .9, label: 'Impulso retenido' }, minRelativeBps: { kind: 'number', min: 0, max: 100, label: 'Fortaleza residual · bps' }, minFlowImbalance: { kind: 'number', min: .05, max: .8, label: 'Desequilibrio de flujo' }, minClassifiedFraction: { kind: 'number', min: .3, max: 1, label: 'Fracción de flujo clasificable' }, minFlowTrades: { kind: 'integer', min: 5, max: 1000, label: 'Trades de flujo mínimos' }, maxSpreadBps: { kind: 'number', min: 2, max: 25, label: 'Spread máximo · bps' }, maxChaseAtr: { kind: 'number', min: .05, max: .5, label: 'Límite de persecución · ATR' }, costMultiple: { kind: 'number', min: 2, max: 8, label: 'Recorrido / coste' }, optionsRequired: { kind: 'boolean', label: 'Requerir evidencia OPRA' }, maxIvRatio: { kind: 'number', min: 1, max: 5, label: 'IV / RV máximo' }, maxPutSkew: { kind: 'number', min: 0, max: .6, label: 'Skew put máximo' } };
    function fields(book, family) { if (book === 'options')
        return HF23.OPTIONS; if (family === 'astra_second_wave')
        return HF23.ASTRA; if (book === 'crypto')
        return family === 'trend_xix' ? HF23.TREND : family === 'shock_recovery' ? HF23.RECOVERY : {}; return HF23.SEC; }
    HF23.fields = fields;
    function patch(book, family, base, change, scope = 'exits') {
        if (!change || typeof change !== 'object' || Array.isArray(change) || !Object.keys(change).length || Object.keys(change).length > 20)
            throw Error('Propuesta vacía o demasiado extensa.');
        const specs = fields(book, family), entry = new Set(['min_rvol', 'momentum_bps', 'reentry', 'selection_filter', 'entryDays', 'shockZ', 'minShockBps', 'volumeRatio', 'sellShare', 'recoveryBuyShare', 'min_dte', 'max_dte', 'delta_min', 'delta_max']);
        const out = { ...base };
        for (const [key, value] of Object.entries(change)) {
            if (!Object.hasOwn(specs, key) || ['__proto__', 'constructor', 'prototype'].includes(key))
                throw Error('Parámetro no autorizado: ' + key);
            if (scope === 'exits' && (entry.has(key) || family === 'astra_second_wave' && !['tpR', 'partialFraction', 'trailAtr', 'lockFraction', 'stagnationMinutes', 'holdHours'].includes(key)))
                throw Error('Este estudio sólo permite salidas: ' + key);
            const f = specs[key];
            if (f.kind === 'boolean') {
                if (typeof value !== 'boolean')
                    throw Error('Se requiere booleano: ' + key);
            }
            else if (f.kind === 'enum') {
                if (!f.values.includes(value))
                    throw Error('Valor fuera del contrato: ' + key);
            }
            else if (typeof value !== 'number' || !Number.isFinite(value) || value < f.min || value > f.max || (f.kind === 'integer' && !Number.isInteger(value)))
                throw Error('Valor fuera de límites: ' + key);
            out[key] = value;
        }
        if ((book === 'equity' || book === 'etf') && family !== 'astra_second_wave') {
            if (!(Number(out.tp2_r) > Number(out.tp1_r)) || Number(out.tp1_fraction) + Number(out.tp2_fraction) > .75 + 1e-12)
                throw Error('Parciales incompatibles: conserva al menos 25% para el runner.');
        }
        if (book === 'crypto' && family === 'trend_xix' && !(Number(out.exitDays) < Number(out.entryDays)))
            throw Error('La salida debe usar menos días que la entrada.');
        if (book === 'options' && (!(Number(out.min_dte) < Number(out.max_dte)) || !(Number(out.delta_min) < Number(out.delta_max))))
            throw Error('Rango DTE o delta incompatible.');
        return out;
    }
    HF23.patch = patch;
    HF23.PREFLIGHT = ['equity-strategy-05', 'equity-strategy-07', 'equity-strategy-16', 'etf-strategy-06', 'etf-strategy-15', 'etf-strategy-17', 'crypto-trend-20-72', 'crypto-trend-40-72', 'crypto-shock-recovery'];
    function emptyPulse() { return { attempt_at: 0, sync_at: 0, market_at: 0, completed_at: 0, failures: 0, error: '', busy: false, duration_ms: 0 }; }
    HF23.emptyPulse = emptyPulse;
    function health(p, connected, armed, reconciled, marketOpen, now = Date.now(), ttl = 60000) {
        const age = p.completed_at ? now - p.completed_at : null, stale = age === null || age < 0 || age > ttl;
        const status = !connected ? 'OFF' : p.error ? 'ERROR' : !reconciled ? 'RECONCILIANDO' : stale ? 'SIN PULSO' : !marketOpen ? 'MERCADO CERRADO' : armed ? 'ON' : 'PAUSADO';
        return { status, age_ms: age, attempt_age_ms: p.attempt_at ? now - p.attempt_at : null, ready: connected && !stale && reconciled && !p.error, reason: p.error || (!connected ? 'Conecta la cuenta' : stale ? 'Sin ciclo completo confirmado recientemente' : !marketOpen ? 'Salidas y entradas sujetas al horario admitido' : armed ? 'Busca señales dentro del riesgo autorizado' : 'Entradas pausadas; gestión de posiciones conserva su política') };
    }
    HF23.health = health;
    HF23.defaults = { cold_on: false, hot_on: false, auto_paper: false, interval_seconds: 300, max_iterations: 8, goal: 'take_profit', scope: 'exits' };
    function policy(p) { if (!p || Object.keys(p).sort().join() !== Object.keys(HF23.defaults).sort().join() || !['cold_on', 'hot_on', 'auto_paper'].every(k => typeof p[k] === 'boolean') || !Number.isInteger(p.interval_seconds) || p.interval_seconds < 60 || p.interval_seconds > 3600 || !Number.isInteger(p.max_iterations) || p.max_iterations < 1 || p.max_iterations > 50 || p.goal !== 'take_profit' || !['exits', 'strategy'].includes(p.scope))
        throw Error('Política del loop inválida.'); return { ...p }; }
    HF23.policy = policy;
    function promotionGates(report, source, mode, auto, flat, baselineCurrent) {
        const gates = { paper_only: mode === 'paper', auto_paper_authorized: auto, flat_and_reconciled: flat, baseline_unchanged: baselineCurrent, native_report: report?.xii_schema === 'XII-ANNUAL-1' || typeof report?.xii_schema === 'string', accepted: report?.status === 'ACEPTADA', all_native_gates: !!report?.gates && Object.keys(report.gates).length >= 15 && Object.values(report.gates).every(v => v === true), independent_evidence: !['SYNTHETIC', 'IMPORTED_UNVERIFIED'].includes(source), prospective: report?.gates?.prospective_holdout === true, diagnostic_excluded: report?.diagnostic_only === false };
        return { gates, allowed: Object.values(gates).every(Boolean), reasons: Object.entries(gates).filter(([, v]) => !v).map(([k]) => k) };
    }
    HF23.promotionGates = promotionGates;
    function stable(x) { if (x === null || typeof x !== 'object')
        return JSON.stringify(x); if (Array.isArray(x))
        return '[' + x.map(stable).join(',') + ']'; return '{' + Object.keys(x).sort().map(k => JSON.stringify(k) + ':' + stable(x[k])).join(',') + '}'; }
    HF23.stable = stable;
    async function digest(x) { const a = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(stable(x))); return [...new Uint8Array(a)].map(v => v.toString(16).padStart(2, '0')).join(''); }
    HF23.digest = digest;
})(HF23 || (HF23 = {}));
