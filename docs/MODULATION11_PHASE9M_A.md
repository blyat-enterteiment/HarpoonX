# HarpoonX — FWN9 M11 Fase 9M-A: prevalidación causal de recibos y journal

**Dictamen: PASS de ingeniería offline; N9-S NO_GO.** Se realizó una sola unidad acotada, sin nuevos mercados, semillas, operaciones ni cambios del contrato M9/M10. La PR #7 permanece en borrador.

## Resultado reproducible

El nuevo módulo `quant/harpoon_quant/fwn9_observed_gate.py` verifica un lote finito de recibos de ingeniería con inventario, caja física y tarifas por evento usando `Decimal`; comprueba los relojes `effective_at <= known_at`, el sello temporal `label_known_at`, conservación de posiciones tras salidas parciales, cierre en <=72h, 180 días consecutivos de desarrollo, embargo y únicamente *declaración* de holdout de al menos 60 días. Rechaza explícitamente la carga del holdout, las cantidades inconsistentes, las etiquetas de OHLC modelado, recibos futuros, sellos alterados y reejecuciones no idempotentes. El resultado queda fijado en el `Journal` SQLite existente mediante hashes tanto de eventos **como de etiquetas**; la corrupción registrada bloquea su apertura. 

La fixture artificial de diez acciones/cierres parcialmente ejecutados **no es un estudio económico**. Su única campaña con cuatro eventos presenta PnL contable de recibos **+41,90 USD**, caja final **20.041,90 USD**, **sin costes fijos de calendario ni MTM diario**. No constituye retorno neto del protocolo M9 ni medida de edge y no altera CASH ni M9_BEST.

**GitHub Actions final:** [P9M-A focal #42458274059](https://github.com/blyat-enterteiment/HarpoonX/actions/runs/42458274059): 13 pruebas aprobadas, Ruff, mypy y compilación Python, 200 revisiones en 44,585 ms. [Regresión cuantitativa #42458274061](https://github.com/blyat-enterteiment/HarpoonX/actions/runs/42458274061): 1.075 pruebas HEAD y 12 históricas, además de P9I–P9L. [Fixturas ley exacta #42458274082](https://github.com/blyat-enterteiment/HarpoonX/actions/runs/42458274082): SUCCESS. Quedan registrados los primeros fallos de mypy ([#42458054026](https://github.com/blyat-enterteiment/HarpoonX/actions/runs/42458054026), [#42458050074](https://github.com/blyat-enterteiment/HarpoonX/actions/runs/42458050074)); los protocolos correctivos R2 y R3 registran el estrechamiento de tipos, reloj y el defecto de checksum de etiquetas, sin borrar intentos.

## Brecha material y regla de parada

**Un SHA-256 de recibos aportado por el mismo emisor no verifica independencia ni procedencia de broker.** El módulo retorna `independent_source_authentication=false`, `optimizer_eligible=false`, `execution_allowed=false` y `n9s_certified=false` incluso cuando supera la conciliación. Tampoco se ha construido un panel observado íntegro: faltan cotizaciones MTM por fecha, universo completo de oportunidades, costes fijos calendario, evidencia de recibos prospectivos, un ancla externa auténtica y datos de 180 días realmente observados. La integración con `recursive.tick` permanece bloqueada y no se abrieron finales.

No se ha probado la cota universal para OHLC nativo M9; las dos brechas operativas (parciales/rechazos/caídas/impacto calibrados y coordinador real multicelda) continúan abiertas. El límite 12% es exclusivamente **admisión/reserva**, no un techo continuo. No hubo cambio de drift, capital, costes, apalancamiento, horizonte 72h, ni hurdle.

El próximo trabajo estructural admisible es cerrar anclaje de datos externos, marca a mercado diaria y cobertura completa de oportunidades sin promover datos modelados como observados. No se abrirá nueva cuadrícula económica antes de las pruebas causales originales y del cierre de las brechas. 3.200 finales M10 selladas; alfa prospectivo gastado: 0; cuentas económicas nuevas: 0.

## Integridad

Fuente (SHA-256): `590a353eca767250fee338ad8329f09aa75cd08c428cfeeb4c2ac68cee764fb0`; prueba (SHA-256): `df96c2f729da6d324d977b14b5566ab14b7d8f2ba1d30533382400ca6cc3604f`. Prerregistro: `8e38d161fb2a3b1a4fa9cbeb0865c9e897da5c20`. Código examinado y probado: `48ed1174160f4fe1418ae78003c867df60c30b2c`.
