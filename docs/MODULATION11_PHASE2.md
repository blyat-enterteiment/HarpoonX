# M11 Phase 2 — Comparador de campaña completa y auditoría de dos activos

**Dictamen:** pruebas deterministas completas para los escenarios acotados; N9-S sigue **NO_GO**. No se ha demostrado imposibilidad del motor completo ni rentabilidad real.

## Resultados implementados

- `runtime30/modulation11_stateful_campaign.cjs`: comparador de campañas con inventario remanente, objetivos TP1/TP2 consumidos una sola vez, perfil NATIVE72, PROTECT48 y RUNNER72, trailing recibido causalmente, límites de 48/72 h, apertura IOC fijada por calendario, contabilidad de comisiones, aplicación del stop y precio efectivo del primer cruce de ocho subpasos. Compara por aserciones los fills, cantidades, precio, `at`, `knownAt` y neto contra `replayCampaign` nativo para las fixtures.
- `runtime30/modulation11_dual_asset_anchor.cjs`: audita eventos nativos de SYNA y SYNB en `replayFundedPortfolio`: reserva agregada, límite de admisión, fuente del mark conocida al decidir, presupuestos IOC y retención de la reserva original hasta `knownAt`. Las dos señales cumplen el horario de 60 minutos registrado y ocurren en sesiones distintas para cubrir una posición ya abierta.
- `tools/modulation11_phase2_test.cjs`: seis pruebas nuevas: parcial persistente y stop, objetivo único entre barras, protección recibida de PROTECT48, salida RUNNER72, libro financiado de dos activos y rechazo de subpasos incompatibles. Se mantienen las nueve pruebas M11 previas.

La ejecución CI `42411657623` aprobó **15/15 pruebas**, con chequeo de sintaxis y conservación de todos los hashes M11/M10/M9 registrados. El primer intento CI `42411582163` falló por fixtures incorrectas: PROTECT48 esperaba un STOP el lunes aun habiendo expirado correctamente las 48 horas el domingo; la señal de segundo activo usaba 65 minutos, que no está permitido. Las correcciones se registraron en `research/modulation11/phase2_qa_notes.json`; no se cambió código económico.

## Por qué el teorema sigue sin cerrar

Estos controles validan condiciones **necesarias** en campañas fabricadas: reservas originales, marks disponibles y ejecución IOC contra presupuestos aprobados. No prueban que la valoración contemporánea de todas las posiciones esté acotada en cada evento y subpaso, ni reconstruyen una cuenta sombra universalmente autofinanciada. El 12% sigue siendo límite de reserva/admisión, nunca continuo. La ejecución OHLC interpolada y el primer cruce discreto son mecanismos distintos; el comparador no mide aún la distribución de sus diferencias en una cohorte predeterminada ni es un modelo real de liquidez.

La cota favorable de **0,9051232469572758 pb de log crecimiento esperado por día** en WEAK sigue siendo condicional. Aún falta un puente matemático que cubra la ejecución nativa, o una reformulación demostrada que identifique qué hipótesis falla. No se eleva drift, capital, apalancamiento ni se reducen costes o umbrales para buscar una aprobación.

## Estado y siguiente paso

- Cuentas económicas nuevas: **0**. Semillas finales M10 sin abrir: **3.200**.
- Validaciones N9-S aceptadas: **0**. Alfa prospectivo gastado: **0**.
- Broker: sin conexiones ni órdenes. PR #7 sigue en borrador.
- Siguiente fase estructural: cotejo de un registro completo de decisiones/admisiones, marcas contemporáneas y cuenta sombra para ambos activos; distinguir con pruebas el precio del proceso del umbral OHLC. Incluir parciales de entrada, rechazos, outages e impacto de mercado y coordinador multicelda en puertas operativas posteriores. No abrir nuevos candidatos hasta resolver viabilidad.

Reproducir: `node --test tools/modulation11_fixture_test.cjs tools/modulation11_native_campaign_test.cjs tools/modulation11_phase2_test.cjs`.
