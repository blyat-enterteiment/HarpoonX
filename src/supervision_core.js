"use strict";
/** Pure supervision contracts: no broker, mutation, credentials or model SDK. */
var HXXI;
(function (HXXI) {
    HXXI.VERSION = '21.0.0';
    HXXI.defaults = { enabled: false, mode: 'adaptive', interval_seconds: 300, heartbeat_seconds: 1800, daily_usd: 2, monthly_usd: 30, max_calls: 300, output_tokens: 1200 };
    function configure(value) {
        if (!value || typeof value !== 'object' || Array.isArray(value))
            throw Error('Configuración de supervisión inválida');
        const c = { ...HXXI.defaults, ...value };
        if (Object.keys(c).some(k => !(k in HXXI.defaults)) || typeof c.enabled !== 'boolean' || !['adaptive', 'periodic', 'logs', 'paused'].includes(c.mode))
            throw Error('Modo de supervisión inválido');
        for (const [k, lo, hi, integer] of [['interval_seconds', 60, 3600, true], ['heartbeat_seconds', 300, 86400, true], ['daily_usd', 0, 100, false], ['monthly_usd', 0, 1000, false], ['max_calls', 1, 1440, true], ['output_tokens', 256, 2000, true]]) {
            const n = c[k];
            if (typeof n !== 'number' || !Number.isFinite(n) || n < lo || n > hi || (integer && !Number.isInteger(n)))
                throw Error('Fuera de rango: ' + k);
        }
        if (c.heartbeat_seconds < c.interval_seconds)
            throw Error('El heartbeat debe ser mayor o igual a la ventana');
        return c;
    }
    HXXI.configure = configure;
    function stable(v) { if (v === undefined)
        return 'null'; if (v === null || typeof v !== 'object')
        return JSON.stringify(v); if (Array.isArray(v))
        return '[' + v.map(stable).join(',') + ']'; return '{' + Object.entries(v).sort(([a], [b]) => a.localeCompare(b)).map(([k, x]) => JSON.stringify(k) + ':' + stable(x)).join(',') + '}'; }
    HXXI.stable = stable;
    async function digest(v) { const b = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(stable(v))); return Array.from(new Uint8Array(b), n => n.toString(16).padStart(2, '0')).join(''); }
    HXXI.digest = digest;
    function finite(v) { return typeof v === 'number' && Number.isFinite(v) ? v : null; }
    HXXI.finite = finite;
    function windowAt(now, seconds, session, cryptoBook) {
        if (!Number.isFinite(now) || !Number.isInteger(seconds) || seconds < 60 || seconds > 3600)
            throw Error('Reloj o intervalo inválido');
        let anchor = cryptoBook ? Math.floor(now / 86400000) * 86400000 : session?.open;
        if (cryptoBook && now - anchor < seconds * 1000)
            anchor = anchor - 86400000;
        const close = cryptoBook ? anchor + 86400000 : session?.close;
        if (anchor == null || close == null || now < anchor)
            return null;
        const boundary = Math.min(close, anchor + Math.floor((now - anchor) / (seconds * 1000)) * seconds * 1000);
        const end = now >= close ? close : boundary;
        if (end <= anchor)
            return null;
        const start = anchor + Math.max(0, Math.ceil((end - anchor) / (seconds * 1000)) - 1) * seconds * 1000;
        return { start, end, key: String(start) + '-' + end };
    }
    HXXI.windowAt = windowAt;
    function validateReview(value, context) {
        if (!value || typeof value !== 'object')
            throw Error('Revisión vacía');
        const r = value;
        const keys = ['snapshot_id', 'config_hash', 'plugin_hash', 'verdict', 'findings', 'next_review_reason'];
        if (Object.keys(r).length !== keys.length || keys.some(k => !(k in r)))
            throw Error('Contrato de revisión inválido');
        for (const k of ['snapshot_id', 'config_hash', 'plugin_hash'])
            if (r[k] !== context[k])
                throw Error('Identidad de revisión incompatible');
        if (!['no_issue_detected', 'investigate', 'insufficient_evidence'].includes(r.verdict) || typeof r.next_review_reason !== 'string' || r.next_review_reason.length > 600 || !Array.isArray(r.findings) || r.findings.length > 6)
            throw Error('Revisión fuera de contrato');
        const ids = new Set(context.evidence.map(e => e.id));
        for (const f of r.findings) {
            if (!f || Object.keys(f).sort().join(',') !== 'evidence_ids,rationale,recommendation,severity,title' || !['low', 'medium', 'high'].includes(f.severity) || !['observe', 'investigate', 'propose_exit_trial'].includes(f.recommendation) || typeof f.title !== 'string' || f.title.length > 160 || typeof f.rationale !== 'string' || f.rationale.length > 800 || !Array.isArray(f.evidence_ids) || f.evidence_ids.length < 1 || f.evidence_ids.length > 8 || f.evidence_ids.some(id => !ids.has(id)))
                throw Error('Hallazgo sin evidencia o permiso válido');
        }
        return r;
    }
    HXXI.validateReview = validateReview;
    function compound(c) {
        if (Object.values(c).some(v => !Number.isFinite(v)) || c.reserve_pct < 0 || c.reserve_pct > 1)
            throw Error('Contabilidad insuficiente');
        const add = Math.max(0, c.realized - c.peak) * c.reserve_pct, reserve = c.reserve + add;
        return { budget: Math.max(0, Math.min(c.capital_limit, c.prior * c.growth_cap, c.prior + c.realized - c.settled - add, c.equity - reserve)), reserve };
    }
    HXXI.compound = compound;
    function takeProfit(rows) {
        const closed = rows.filter(r => r.closed), net = closed.map(r => finite(r.net)), paired = closed.filter(r => finite(r.mfe_r) !== null && finite(r.captured_r) !== null && r.mfe_r > 0);
        return { closed: closed.length, net: net.every(v => v !== null) ? net.reduce((a, b) => a + b, 0) : null, net_complete: net.every(v => v !== null), capture_proxy: paired.length ? paired.reduce((s, r) => s + r.captured_r / r.mfe_r, 0) / paired.length : null, paired: paired.length };
    }
    HXXI.takeProfit = takeProfit;
})(HXXI || (HXXI = {}));
