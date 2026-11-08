# HarpoonX M11 — 9M-C1: no identificabilidad del orden causal desde OHLC

**Veredicto: NO_GO N9-S. Unidad estructural completada; no es otra búsqueda de señales.**

## Hallazgo contrastable

El replay M9 calcula stops/targets con la barra OHLC completa, prioriza el stop si dentro de la barra aparecen simultáneamente el stop y un target y paga determinados niveles interpolados. La trayectoria de ocho subpasos conserva información de orden que OHLC descarta.

Construimos dos ejecuciones sintéticas deterministas con **idéntica apertura 100, máximo 104, mínimo 96, cierre 100, tick, cantidad, reloj, costes y multiconjunto de ocho precios**, pero con distinto orden: `[100.2,104,103,96,97,99,100,100]` y `[100.2,96,103,104,97,99,100,100]`.

Sobre **la misma señal y las mismas 8 acciones** con entrada 100,03, stop 98,03 y primer target 103,03, la ruta nativa produce un neto de **−16,32 USD** en ambos casos porque el stop OHLC tiene prioridad. El comparador de primer cruce en subpasos da **−16,58 USD** cuando se cruza antes el target y **−32,56 USD** cuando se cruza primero el stop; son **15,98 USD de diferencia causal** entre ordenaciones sin diferencia alguna en OHLC. Se incluyen spread 2 bp, slippage 2 bp, comisión de 0,005 USD/acción/lado y tick de 0,01 USD. El benchmark CASH del fixture de 8 días cierra en 19.992 USD tras 8 USD de cargos fijos; no es un caso prospectivo.

El código compara la ejecución nativa invocando `modulation11_stateful_campaign.cjs` contra las dos ordenaciones y confronta caja y comisiones en enteros de microdólares y mediante **un segundo contador independiente Decimal-46**. Rechaza variaciones en OHLC, multiconjunto de subpasos, costes, procedencia sintética y cronología de publicación. Los estados de salida llevan tanto tiempo efectivo como `knownAt`: un subpaso no se convierte por ello en información disponible para el selector antes del cierre.

El contraejemplo **refuta la equivalencia universal por trayectoria entre OHLC y primer cruce discreto**. No demuestra que la esperanza WEAK nativa supere o no la cota de factibilidad; tampoco refuta una ley estocástica completa o demuestra rentabilidad. La cota condicional de **0,905124 pb/día**, menor que el requisito original de 1 pb/día, continúa sin ser certificado aplicable al replay nativo. No se cambió el límite de admisión/reserva del 12% para convertirlo artificialmente en un cap continuo.

## Evidencia y pruebas

Prerregistro, hipótesis de falsificación, catálogo finito y presupuestos cero: `research/modulation11/fwn9_phase9m_c1_protocol.json` (lease CAS `ad497ba00f25b38b5bee3f5fb887ae08e96f18c7`). Implementación `runtime30/fwn9_p9m_c_order_witness.cjs`; pruebas `tools/fwn9_p9m_c_order_test.cjs`; revisión independiente `tools/fwn9_p9m_c_accountant.py`; manifiesto `evidence/modulation11/fwn9_phase9m_c1.json`.

La CI focal [42468588675](https://github.com/blyat-enterteiment/HarpoonX/actions/runs/42468588675) dio **8/8 pruebas PASS**, sintaxis Node PASS, compilación Python PASS, cuenta Decimal-46 PASS y benchmark 20 verificaciones en **80,459 ms**. Checksums exactos SHA-256 en el manifiesto y stdout de CI. Las suites existentes P9M-A y P9M-B volvieron a pasar en esta revisión; el resultado de la regresión general debe consultarse de forma separada antes de considerarla cerrada.

Este certificado es **ingeniería sintética**: los caminos se construyeron para distinguir semánticas, no se extrajeron de holdout ni de ejecuciones de mercado. No se gastó alfa prospectivo, ni se agregaron cuentas económicas, ni se abrieron las 3.200 finales de M10. Se preservaron los 47 orígenes registrados, las decisiones y los intentos previos.

## Próxima unidad acotada

Continuar 9M-C con comprobación de **admisiones consecutivas, cobertura de marcas contemporáneas, liberación de reservas IOC NO_FILL y valoración de caja/inventario desde recibos** en los dos activos. Para trasladar una cota de riqueza al contrato realmente implementado hace falta una representación de los precios de ejecución causal y autofinanciada, o una cota nueva que soporte explícitamente la semántica OHLC nativa sin cambiar ley ni umbrales. Las dos brechas operativas originales (parciales/rechazos/outage/impact y coordinador multicelda) siguen bloqueando N9-S.

**Sin broker, órdenes, despliegue, fusionar PR, contacto externo ni declaración de rentabilidad real.** PR #7 permanece DRAFT apilada sobre #6.
