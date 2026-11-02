"use strict";
var HPEntry;
(function (HPEntry) {
    const validate = (r) => HLab.validate(r);
    function eligible(f, r, breakout, chase) {
        if (!(f.ask >= 5 && f.perf5 > 0 && f.rvol >= r.min_rvol && f.momentum_bps >= r.momentum_bps))
            return false;
        if (r.family === 'option_context' && !(f.option_valid === 1 && f.option_proxy === 0 && f.option_horizon_hours > 0 && f.option_max_hours >= r.hold_hours && f.option_range_r * Math.sqrt(r.hold_hours / f.option_horizon_hours) >= r.tp1_r))
            return false;
        if (r.family === 'canonical_exit' || r.family === 'option_context') {
            const trigger = f.base * (1 + breakout);
            return f.ask >= trigger && f.ask <= trigger * (1 + chase);
        }
        if (r.family === 'opening_range')
            return Number.isFinite(f.opening_high) && f.session_minutes >= 15 && f.session_minutes <= 120 && f.ask > f.opening_high && f.ask <= f.opening_high * (1 + chase);
        if (r.family === 'trend_pullback')
            return f.vwap_distance >= 0 && f.vwap_distance <= f.atr / f.ask && f.relative_bps > 0 && f.volume_acceleration >= 1.1;
        return Number.isFinite(f.previous_vwap_distance) && f.previous_vwap_distance <= 0 && f.vwap_distance > 0 && f.vwap_distance <= 1.5 * f.atr / f.ask && f.volume_acceleration >= 1.1;
    }
    HPEntry.eligible = eligible;
    function localCandidate(base, iteration) {
        const r = structuredClone(base), k = iteration % 16;
        r.family = HLab.families[Math.floor(iteration / 16) % HLab.families.length];
        r.name = 'XI-' + String(iteration + 1).padStart(3, '0');
        r.hypothesis = 'Contrastar un reparto y recorrido de salidas a igual riesgo; rechazar sin mejora neta fuera de muestra.';
        r.tp1_r = [1.25, 1.5, 1.75, 2][k % 4];
        r.tp2_r = [3, 3.5, 4, 4.5][Math.floor(k / 4)];
        r.tp1_fraction = [.25, .375][Math.floor(k / 8)];
        r.tp2_fraction = .25;
        r.trail_atr = [2, 2.5, 3, 3.5][(k + Math.floor(k / 4)) % 4];
        r.reentry = false;
        return validate(r);
    }
    HPEntry.localCandidate = localCandidate;
})(HPEntry || (HPEntry = {}));
