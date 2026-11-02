"use strict";
/** HARPOON Tensor Library 1.0.0. Float64; explicit masks; no network or order authority. */
var HTensor;
(function (HTensor) {
    HTensor.VERSION = '1.0.0';
    const MAX_CELLS = 2000000;
    function shape(rows, cols) { if (!Number.isInteger(rows) || !Number.isInteger(cols) || rows < 0 || cols < 1 || rows * cols > MAX_CELLS)
        throw Error('Dimensiones fuera del presupuesto tensorial'); return rows * cols; }
    function dot(a, b) { if (a.length !== b.length)
        throw Error('Producto de dimensiones incompatibles'); let sum = 0, c = 0; for (let i = 0; i < a.length; i++) {
        if (!Number.isFinite(a[i]) || !Number.isFinite(b[i]))
            throw Error('Producto no finito');
        const y = a[i] * b[i] - c, t = sum + y;
        c = (t - sum) - y;
        sum = t;
    } return sum; }
    HTensor.dot = dot;
    function matrix(rows) { const n = rows.length, p = n ? rows[0].length : 1, data = new Float64Array(shape(n, p)); rows.forEach((row, i) => { if (row.length !== p || !row.every(Number.isFinite))
        throw Error('Matriz irregular o no finita'); data.set(row, i * p); }); return { rows: n, cols: p, data }; }
    HTensor.matrix = matrix;
    function multiply(a, b) {
        if (a.cols !== b.rows || a.data.length !== shape(a.rows, a.cols) || b.data.length !== shape(b.rows, b.cols))
            throw Error('Multiplicación incompatible');
        const out = { rows: a.rows, cols: b.cols, data: new Float64Array(shape(a.rows, b.cols)) };
        // Compensated inner products; deterministic across browser and Node.
        for (let i = 0; i < a.rows; i++)
            for (let j = 0; j < b.cols; j++) {
                let s = 0, c = 0;
                for (let k = 0; k < a.cols; k++) {
                    const y = a.data[i * a.cols + k] * b.data[k * b.cols + j] - c, t = s + y;
                    c = (t - s) - y;
                    s = t;
                }
                out.data[i * b.cols + j] = s;
            }
        return out;
    }
    HTensor.multiply = multiply;
    function design(xs, means, scales, clip = 5) { if (means.length !== scales.length || !means.every(Number.isFinite) || !scales.every(v => Number.isFinite(v) && v > 0) || !Number.isFinite(clip) || clip <= 0)
        throw Error('Normalización inválida'); const p = means.length + 1, data = new Float64Array(shape(xs.length, p)); xs.forEach((x, i) => { if (x.length !== means.length || !x.every(Number.isFinite))
        throw Error('Características incompletas'); data[i * p] = 1; for (let j = 1; j < p; j++)
        data[i * p + j] = Math.max(-clip, Math.min(clip, (x[j - 1] - means[j - 1]) / scales[j - 1])); }); return { rows: xs.length, cols: p, data }; }
    HTensor.design = design;
    function ridgeSystem(z, targets, lambda = 10) {
        if (z.rows !== targets.length || z.data.length !== shape(z.rows, z.cols) || !targets.every(Number.isFinite) || !Number.isFinite(lambda) || lambda <= 0)
            throw Error('Sistema ridge inválido');
        const p = z.cols, a = Array.from({ length: p }, () => Array(p).fill(0)), b = Array(p).fill(0);
        for (let j = 0; j < p; j++) {
            let sb = 0, cb = 0;
            for (let i = 0; i < z.rows; i++) {
                const y = z.data[i * p + j] * targets[i] - cb, t = sb + y;
                cb = (t - sb) - y;
                sb = t;
            }
            b[j] = sb;
            for (let k = j; k < p; k++) {
                let s = 0, c = 0;
                for (let i = 0; i < z.rows; i++) {
                    const y = z.data[i * p + j] * z.data[i * p + k] - c, t = s + y;
                    c = (t - s) - y;
                    s = t;
                }
                a[j][k] = a[k][j] = s;
            }
            a[j][j] += j ? lambda : 1e-6;
        }
        return { a, b };
    }
    HTensor.ridgeSystem = ridgeSystem;
    function build(records, features, cutoff, maxTimes = 1024) {
        if (!Number.isFinite(cutoff) || !Number.isInteger(maxTimes) || maxTimes < 1 || maxTimes > 4096 || !features.length || features.length > 128 || new Set(features).size !== features.length || records.length > 60000)
            throw Error('Contrato tensorial inválido');
        for (const r of records)
            if (!/^[A-Z][A-Z0-9./\-]{0,15}$/.test(r.asset) || ![r.at, r.availableAt].every(Number.isFinite) || r.at > r.availableAt || r.values.length !== features.length)
                throw Error('Registro tensorial inválido o disponibilidad anterior al evento');
        const valid = records.filter(r => r.availableAt <= cutoff), allTimes = [...new Set(valid.map(r => r.availableAt))].sort((a, b) => a - b), times = allTimes.slice(-maxTimes), timeMap = new Map(times.map((t, i) => [t, i])), selected = valid.filter(r => timeMap.has(r.availableAt)), assets = [...new Set(selected.map(r => r.asset))].sort(), assetMap = new Map(assets.map((s, i) => [s, i])), F = features.length, T = times.length, N = assets.length * T * F;
        if (N > MAX_CELLS)
            throw Error('Tensor supera 2 millones de celdas; reduce la ventana');
        const data = new Float64Array(N), mask = new Uint8Array(N), observed_at = new Float64Array(assets.length * T);
        let duplicates = 0;
        const seen = new Set();
        for (const r of selected) {
            const slot = assetMap.get(r.asset) * T + timeMap.get(r.availableAt), offset = slot * F;
            if (seen.has(slot)) {
                duplicates++;
                const same = observed_at[slot] === r.at && r.values.every((v, j) => typeof v === 'number' && Number.isFinite(v) ? mask[offset + j] === 1 && data[offset + j] === v : mask[offset + j] === 0);
                if (!same)
                    throw Error('Dos observaciones incompatibles en el mismo activo y momento');
                continue;
            }
            seen.add(slot);
            observed_at[slot] = r.at;
            r.values.forEach((v, j) => { if (typeof v === 'number' && Number.isFinite(v)) {
                data[offset + j] = v;
                mask[offset + j] = 1;
            } });
        }
        return { schema: 'HARPOON-TENSOR-1', version: HTensor.VERSION, axes: { assets, times, features: [...features] }, shape: [assets.length, T, F], data, mask, observed_at, cutoff, excluded_future: records.length - valid.length, duplicates, truncated_times: allTimes.length - times.length };
    }
    HTensor.build = build;
    function statistics(cube) {
        const [A, T, F] = cube.shape;
        if (cube.data.length !== A * T * F || cube.mask.length !== cube.data.length || cube.observed_at.length !== A * T)
            throw Error('Forma tensorial incoherente');
        const counts = new Array(F).fill(0), means = new Array(F).fill(0), m2 = new Array(F).fill(0), complete = [];
        for (let row = 0; row < A * T; row++) {
            const x = [];
            for (let j = 0; j < F; j++) {
                const k = row * F + j;
                if (cube.mask[k]) {
                    const v = cube.data[k];
                    counts[j]++;
                    const delta = v - means[j];
                    means[j] += delta / counts[j];
                    m2[j] += delta * (v - means[j]);
                    x.push(v);
                }
            }
            if (x.length === F)
                complete.push(x);
        }
        const cm = Array.from({ length: F }, (_, j) => complete.length ? complete.reduce((s, r) => s + r[j], 0) / complete.length : 0), cov = Array.from({ length: F }, () => Array(F).fill(null));
        if (complete.length >= 2)
            for (let i = 0; i < F; i++)
                for (let j = i; j < F; j++) {
                    const value = complete.reduce((s, r) => s + (r[i] - cm[i]) * (r[j] - cm[j]), 0) / (complete.length - 1);
                    cov[i][j] = cov[j][i] = value;
                }
        const shrinkage = cov.map((row, i) => row.map((v, j) => v === null ? null : v * (i === j ? 1 : .8)));
        return { shape: cube.shape, bytes: cube.data.byteLength + cube.mask.byteLength + cube.observed_at.byteLength, present: counts.reduce((a, b) => a + b, 0), cells: cube.data.length, coverage: cube.data.length ? counts.reduce((a, b) => a + b, 0) / cube.data.length : 0, complete_rows: complete.length, features: cube.axes.features.map((name, j) => ({ name, count: counts[j], mean: counts[j] ? means[j] : null, sd: counts[j] >= 2 ? Math.sqrt(m2[j] / (counts[j] - 1)) : null })), covariance_complete_cases: cov, covariance_shrinkage_20pct: shrinkage, basis: 'Float64 + máscara explícita. Ejes activo × disponibilidad × variable. Sin imputación ni relleno futuro. Covarianza con casos completos; contracción diagonal fija 20%, sólo diagnóstico.' };
    }
    HTensor.statistics = statistics;
    function serialize(cube) { return { ...cube, data: Array.from(cube.data), mask: Array.from(cube.mask), observed_at: Array.from(cube.observed_at), layout: 'row-major: ((asset * time_count) + time) * feature_count + feature', limits: 'Features observed in their availability time. Labels/targets are excluded. Mask=0 is missing, never a measured zero. No order authority.' }; }
    HTensor.serialize = serialize;
})(HTensor || (HTensor = {}));
