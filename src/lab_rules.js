"use strict";
var HLab;
(function (HLab) {
    HLab.bounds = HContract.bounds;
    HLab.families = HContract.families;
    function validate(value) {
        if (!value || typeof value !== 'object' || Array.isArray(value))
            throw Error('Receta inválida');
        const r = { ...HContract.defaults, ...value }, keys = ['name', 'hypothesis', 'family', 'hold_hours', 'reentry', ...Object.keys(HContract.enums), ...Object.keys(HLab.bounds)];
        if (Object.keys(r).length !== keys.length || Object.keys(r).some(k => !keys.includes(k)))
            throw Error('La receta contiene campos no permitidos');
        if (typeof r.name !== 'string' || !r.name.trim() || r.name.length > 80 || typeof r.hypothesis !== 'string' || r.hypothesis.length > 1200)
            throw Error('Nombre o hipótesis inválidos');
        if (!HLab.families.includes(r.family) || ![1.5, 24, 48, 72].includes(r.hold_hours) || typeof r.reentry !== 'boolean')
            throw Error('Familia, plazo o reentrada inválidos');
        for (const [key, [low, high]] of Object.entries(HLab.bounds))
            if (typeof r[key] !== 'number' || !Number.isFinite(r[key]) || r[key] < low || r[key] > high)
                throw Error('Fuera de límites: ' + key);
        if (r.tp2_r <= r.tp1_r || r.tp1_fraction + r.tp2_fraction > HContract.partial_max)
            throw Error('Objetivos o fracciones incompatibles');
        for (const [key, values] of Object.entries(HContract.enums))
            if (!values.includes(r[key]))
                throw Error('Fuera de contrato: ' + key);
        return structuredClone(r);
    }
    HLab.validate = validate;
    function taskGuard(r, reference, task) { if (!['operations', 'profitability', 'sandbox'].includes(task))
        throw Error('Tarea desconocida'); const fields = task === 'operations' ? Object.keys(reference) : task === 'profitability' ? ['family', 'min_rvol', 'momentum_bps', 'reentry', 'selection_filter'] : []; if (fields.some(k => r[k] !== reference[k]))
        throw Error('La propuesta excede el alcance de esta interacción'); }
    HLab.taskGuard = taskGuard;
    function profile(r) { return { ...r, selective: false, prediction_floor: 0 }; }
    HLab.profile = profile;
    function eligible(f, r, breakout, chase) { return HPEntry.eligible(f, r, breakout, chase); }
    HLab.eligible = eligible;
    function diff(a, b) { return Object.entries(b).filter(([k, v]) => !['name', 'hypothesis'].includes(k) && a[k] !== v).map(([field, after]) => ({ field, before: a[field] ?? null, after })); }
    HLab.diff = diff;
    function stable(x) { if (x === null || typeof x !== 'object')
        return JSON.stringify(x); if (Array.isArray(x))
        return '[' + x.map(stable).join(',') + ']'; const o = x; return '{' + Object.keys(o).sort().map(k => JSON.stringify(k) + ':' + stable(o[k])).join(',') + '}'; }
    HLab.stable = stable;
    function localCandidate(base, iteration) { return HPEntry.localCandidate(base, iteration); }
    HLab.localCandidate = localCandidate;
})(HLab || (HLab = {}));
