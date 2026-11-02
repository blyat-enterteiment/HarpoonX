"use strict";
var HXX;
(function (HXX) {
    HXX.API = 'harpoon.plugin/1';
    function stable(v) { if (Array.isArray(v))
        return '[' + v.map(stable).join(',') + ']'; if (v && typeof v === 'object')
        return '{' + Object.keys(v).sort().map(k => JSON.stringify(k) + ':' + stable(v[k])).join(',') + '}'; return JSON.stringify(v); }
    HXX.stable = stable;
    async function digest(v) { return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(stable(v))))).map(x => x.toString(16).padStart(2, '0')).join(''); }
    HXX.digest = digest;
    function recipe(p) { const { selective: _, prediction_floor: __, ...r } = p; return HLab.validate(r); }
    HXX.recipe = recipe;
    function validate(raw) {
        if (!raw || typeof raw !== 'object' || Array.isArray(raw))
            throw Error('Plugin inválido');
        const m = raw;
        if (Object.keys(m).sort().join(',') !== 'api,binding,book,family,id,name,params,version' || m.api !== HXX.API || !/^\d+\.\d+\.\d+$/.test(m.version) || !/^[a-z][a-z0-9_-]{2,70}$/.test(m.id) || typeof m.name !== 'string' || !m.name.trim() || m.name.length > 100 || !['equity', 'etf', 'crypto'].includes(m.book) || !['host', 'fixed'].includes(m.binding) || !m.params || Array.isArray(m.params) || typeof m.params !== 'object')
            throw Error('Identidad o contrato de plugin inválido');
        if (m.binding === 'host') {
            if (m.family !== (m.book === 'crypto' ? 'trend_xix' : 'canonical_exit') || Object.keys(m.params).length || m.id !== m.book + '-canonical-host' || m.version !== '1.0.0')
                throw Error('El enlace canónico no admite parámetros');
        }
        else if (m.family === 'astra_second_wave') {
            if (m.book === 'crypto' || !m.version.startsWith('1.'))
                throw Error('ASTRA: libro o versión incompatible');
            HAstra.validate(m.params);
        }
        else if (m.book === 'crypto') {
            HPRecovery.validateManifest({ api: HPRecovery.API, id: m.family, version: '1.0.0', family: m.family, symbols: ['BTC/USD', 'ETH/USD'], params: m.params });
        }
        else {
            const r = recipe(m.params);
            if (r.family !== m.family || typeof m.params.selective !== 'boolean' || typeof m.params.prediction_floor !== 'number' || !Number.isFinite(m.params.prediction_floor) || m.params.prediction_floor < 0 || m.params.prediction_floor > .02)
                throw Error('Perfil de valores inválido');
        }
        return structuredClone(m);
    }
    HXX.validate = validate;
    function host(book) { return { api: HXX.API, id: book + '-canonical-host', version: '1.0.0', name: book === 'crypto' ? 'Tendencia canónica · configuración vigente' : 'Canónica · campeón / laboratorio vigente', book, family: book === 'crypto' ? 'trend_xix' : 'canonical_exit', binding: 'host', params: {} }; }
    HXX.host = host;
    function builtins() {
        const base = { ...DEFAULTS.profile, family: 'canonical_exit', hold_hours: 48, hypothesis: 'Hipótesis heredada; requiere evidencia neta independiente.', stagnation_minutes: 20, progress_r: 1, selection_filter: 'none', trailing_mode: 'entry_atr', exit_layout: 'two_targets' };
        const candidates = [base, ...HPSecurities.profiles().map(p => ({ ...base, ...p })), ...['opening_range', 'trend_pullback', 'vwap_reclaim', 'option_context'].map(f => ({ ...base, family: f, name: f })), ...HPCatalog.xiiVariants(base), ...HPCatalog.xiiiVariants(base)];
        const out = [];
        for (const book of ['equity', 'etf']) {
            out.push(host(book));
            candidates.forEach((p, i) => out.push(validate({ api: HXX.API, id: book + '-strategy-' + String(i + 1).padStart(2, '0'), version: '1.0.0', name: String(p.name), book, family: p.family, binding: 'fixed', params: p })));
        }
        out.push(host('crypto'));
        for (const entryDays of [20, 40])
            for (const holdHours of [0, 72])
                out.push(validate({ api: HXX.API, id: 'crypto-trend-' + entryDays + '-' + holdHours, version: '1.0.0', name: 'Tendencia ' + entryDays + '/' + entryDays / 2 + ' · ' + (holdHours || 'sin') + ' h', book: 'crypto', family: 'trend_xix', binding: 'fixed', params: { entryDays, exitDays: entryDays / 2, atrDays: 20, atrMultiple: 3, holdHours } }));
        out.push(validate({ api: HXX.API, id: 'crypto-shock-recovery', version: '1.0.0', name: 'Recuperación tras shock · experimental', book: 'crypto', family: 'shock_recovery', binding: 'fixed', params: HPRecovery.defaultManifest('shock_recovery').params }));
        return out;
    }
    HXX.builtins = builtins;
    function securities(m, base) { validate(m); if (m.book === 'crypto')
        throw Error('Libro incompatible'); return structuredClone(m.family === 'astra_second_wave' ? HAstra.profile(HAstra.validate(m.params)) : m.binding === 'host' ? base : m.params); }
    HXX.securities = securities;
    function cryptoConfig(m, base) { validate(m); if (m.book !== 'crypto' || m.family !== 'trend_xix')
        throw Error('No es un plugin de tendencia'); if (m.binding === 'host')
        return HC19.validate(base); const p = m.params; return HC19.validate({ ...base, entry_days: p.entryDays, exit_days: p.exitDays, atr_days: p.atrDays, atr_multiple: p.atrMultiple, hold_hours: p.holdHours }); }
    HXX.cryptoConfig = cryptoConfig;
    function recovery(m) { validate(m); if (m.family !== 'shock_recovery')
        throw Error('Familia incompatible'); return HPRecovery.validateManifest({ api: HPRecovery.API, id: 'shock_recovery', version: '1.0.0', family: m.family, symbols: ['BTC/USD', 'ETH/USD'], params: m.params }); }
    HXX.recovery = recovery;
    async function packet(manifests) { const items = manifests.map(validate); return { schema: 'HARPOON-XX-PLUGINS-1', manifests: items, sha256: await digest(items) }; }
    HXX.packet = packet;
    async function unpack(raw) { const p = raw; if (!p || Object.keys(p).sort().join(',') !== 'manifests,schema,sha256' || p.schema !== 'HARPOON-XX-PLUGINS-1' || !Array.isArray(p.manifests) || p.manifests.length > 150 || await digest(p.manifests) !== p.sha256)
        throw Error('Paquete o SHA-256 inválido'); const items = p.manifests.map(validate), keys = items.map(m => m.id + '@' + m.version); if (new Set(keys).size !== keys.length)
        throw Error('Identidades duplicadas'); return items; }
    HXX.unpack = unpack;
    function stamp(m, profile) { return { api: HXX.API, id: m.id, version: m.version, manifest: validate(m), resolved: structuredClone(profile), canonical: stable({ manifest: m, profile }) }; }
    HXX.stamp = stamp;
})(HXX || (HXX = {}));
