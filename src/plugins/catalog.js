"use strict";
var HPCatalog;
(function (HPCatalog) {
    function xiiVariants(base) { const make = (name, patch) => ({ ...base, ...patch, name: 'XII · ' + name, hypothesis: 'Ablación a riesgo fijo frente a la referencia registrada; rechazar sin mejora fuera de muestra.' }); return [make('Parcial inicial menor', { tp1_fraction: .125 }), make('Trailing de volatilidad', { trailing_mode: 'realized_vol' }), make('Liberar sin progreso', { stagnation_minutes: 10, progress_r: .5 }), make('Dejar desarrollar', { stagnation_minutes: 40, progress_r: 1 }), make('Reentrada confirmada', { reentry: true }), make('Selección ridge', { selection_filter: 'ridge_lcb' }), make('Contexto OPRA', { family: 'option_context' })]; }
    HPCatalog.xiiVariants = xiiVariants;
    function xiiiVariants(base) { const make = (name, patch) => ({ ...base, ...patch, name: 'XIII · ' + name, hypothesis: 'Contrastar captura neta, contribución por motor y riesgo a capital fijo; rechazar sin evidencia anual y prospectiva.' }); return [make('Un parcial y recorrido abierto', { exit_layout: 'single_target', tp1_fraction: .125 }), make('Runner con volatilidad', { exit_layout: 'single_target', tp1_fraction: .125, trailing_mode: 'realized_vol' }), make('Runner con más desarrollo', { exit_layout: 'single_target', tp1_fraction: .125, stagnation_minutes: 40, progress_r: .5 }), make('Dos parciales pequeños', { exit_layout: 'two_targets', tp1_fraction: .125, tp2_fraction: .125 })]; }
    HPCatalog.xiiiVariants = xiiiVariants;
})(HPCatalog || (HPCatalog = {}));
