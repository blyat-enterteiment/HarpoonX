# M11 phase1: campaña nativa integrada y cronología IOC

**Alcance:** una unidad de ingeniería determinista; ninguna cuenta económica nueva, ningún candidato, ningún holdout abierto ni gasto de alfa. El motor original M9/M10, el generador, los costes, la exposición de admisión y los umbrales no se modifican.

## Contraste ejecutado
`tools/modulation11_native_campaign_test.cjs` llama a `replayCampaign`, `replayFundedPortfolio` y `ultimate_reservations` reales. El caso construido emplea ocho acciones a 100,03 USD; la primera barra ejecuta TP1 de dos títulos y la segunda cierra seis títulos por STOP. Compara contra el modelo discreto de ocho subpasos con las mismas barras OHLC, tamaño, tick, comisiones y tiempos de recepción.

Resultado de la **fixture fabricada**, no de mercado: PnL nativo OHLC **−6,34 USD** y PnL al primer cruce discreto **−8,58 USD**. La diferencia de **+2,24 USD** a favor del nativo muestra que los precios de ejecución no son equivalentes, incluso cuando el inventario y las decisiones TP1/STOP coinciden. La comparación independiente reproduce el PnL nativo de la campaña y todos sus fills.

La prueba financiada verifica una admisión real, plan IOC, presupuesto de riesgo y efectivo, estado `RESERVED`, observación `OPENED`, posterior `CLOSED` y no liberación del importe reservado antes de `knownAt`. En una segunda fixture los parciales no disminuyen la reserva original. No prueba un techo de exposición continua de 12%.

## Límites explícitos
Las tres pruebas nuevas y seis de fase0 pasan localmente. Este contraste conserva los parciales conocidos de una campaña de dos barras; **no** es un comparador general con estado persistente para trailing, múltiples targets, gaps, interrupciones y órdenes parciales de entrada. Tampoco establece las desigualdades de la cuenta sombra para cada evento posible de una cartera multicelda. La cota WEAK de 0,905123 pb/día sigue siendo condicional, no un certificado de imposibilidad para el replay. Los dos controles operativos pendientes siguen bloqueando N9-S.

Reproducir: `node --test tools/modulation11_fixture_test.cjs tools/modulation11_native_campaign_test.cjs`. Evidencia y checksums en `evidence/modulation11/phase1_native_fixture.json`. El workflow `modulation11_phase1.yml` verifica la ejecución en GitHub. Dictamen: **NO_GO**; final M10 (3.200 cuentas) permanece sellado.

**Siguiente paso estructural:** comparador que persista trailing y targets en una campaña completa y auditor de cada evento de reserva/IOC para los dos activos; sólo después reconsiderar si existe una cota aplicable o se justifica un diagnóstico económico prerregistrado.
