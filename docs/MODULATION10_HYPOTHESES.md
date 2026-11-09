# MODULATION10: hipótesis causales y contrato de falsación

Fecha: 2026-11-07. Documento anterior a medir las estrategias de esta ronda. Se preservan la ley del generador, los costes, el capital de USD 20,000 y los límites de admisión del protocolo. Este documento no acredita rentabilidad ni un óptimo global.

## Problema que se intenta resolver

MODULATION9 rechazó la promoción: las 36 recetas tuvieron medias netas negativas en las diez combinaciones de mundo y coste. Su seleccionado, `QUALITY_RUNNER72_R0625`, conservó esa pérdida media en las diez combinaciones finales. Operar menos redujo el drawdown observado, pero no cubrió los USD 176 nominales o USD 352 bajo estrés cobrados en 176 días naturales. Véanse `evidence/modulation9/qa/independent_review.json` y `evidence/modulation9/final_analysis/report.json`.

La familia anterior exige una ruptura del rango inicial, condiciones de volumen y, en QUALITY, filtros adicionales de tendencia. En contraste, el generador de TREND/WEAK asigna un estado de drift persistente a cada activo. El drift aparece durante la sesión; los multiplicadores overnight están compensados y no aportan el mismo drift. Una señal de días completos puede acumular información que una ruptura de una hora descarta. Esta es una hipótesis sobre la ley sintética conocida, no sobre mercados observados.

Con probabilidad de refresco 0.08 por sesión, el coeficiente de persistencia del estado es 0.92. Su vida media de correlación es aproximadamente 8.31 sesiones, derivada de `log(0.5)/log(0.92)`. Una ventana corta reacciona antes y acumula menos información; una ventana larga suaviza ruido y tarda más en reconocer un cambio. Las ventanas 3 y 8 se fijan antes de medir. No se ensayan todas las ventanas hasta encontrar una favorable.

Fuentes del modelo: `quant/harpoon_quant/modulation9.py`, `quant/harpoon_quant/technical_swing.py` y `research/modulation10/protocol.json`.

## Familias y catálogo cerrado

### H1. Momentum de sesiones completas

Para cada activo, usar solamente los últimos W retornos intradía completos `r_d = log(C_d/O_d)`, con W en {3, 8}. Excluir el retorno overnight del estimador de tendencia. La media y la desviación estándar se calculan en las mismas unidades diarias. El score `mean(r) * sqrt(W) / sample_sd(r)` es una característica de selección; no es un contraste válido de significación ni una afirmación de W observaciones independientes del régimen.

Los umbrales son 0 y 0.75, con comparación estricta. Si la dispersión es degenerada, no finita o falta información, la señal se rechaza. Elegir el activo con mayor score que supere el umbral y resolver empates por símbolo. No exigir ruptura inicial, superioridad frente al benchmark ni RVOL para esta familia: así puede distinguirse si esos filtros estaban eliminando exposición útil.

El cálculo usa sesiones anteriores completas. La decisión se toma a apertura + 5 minutos + 1 segundo, para disponer de una cotización causal de la sesión actual; la entrada IOC ocurre en la apertura de los 10 minutos. El precio del primer intervalo sirve para cotizar y dimensionar, no para convertir datos de la sesión en una sesión completa. No se permite decidir con un cierre futuro, con la etiqueta del mundo, el estado latente o una semilla.

Las dos salidas son HOLD24 y HOLD72: stop protector inicial de un ATR diario causal de 20 sesiones, plazo natural de 24 o 72 horas, sin objetivos de beneficio, parciales ni trailing. El reloj no se reinicia al recibir un fill o una nueva señal. Los riesgos por entrada son 0.00125 y 0.0025; las restricciones agregadas, las reservas, las comisiones y los lotes enteros siguen vigentes.

**16 recetas:** 2 ventanas × 2 umbrales × 2 riesgos × 2 horizontes.

Hipótesis contrastable: mayor ocupación útil durante estados positivos mejora el retorno neto y la utilización de capital sin violar el riesgo. Refutación: más operaciones elevan costes o exposición a estados negativos, el score de desarrollo no supera el umbral de aceptación, o la ventaja desaparece al contrastar contra controles emparejados.

### H2. Reparación de la cola como ablación separada

Dos nuevas políticas cambian únicamente la conservación de actualizaciones pendientes del stop. Conservan entrada, riesgo, objetivos, cantidades parciales, función de trailing y plazo nativos:

| Nueva receta | Control emparejado | Cambio permitido |
|---|---|---|
| `CONFIRMED_NATIVE_QUEUE72_R2500` | `CURRENT` | Cola de recibos del stop |
| `QUALITY_NATIVE_QUEUE72_R0625` | `QUALITY_NATIVE72_R0625` | Cola de recibos del stop |

La cola debe activar una observación al llegar `knownAt`; una observación posterior todavía no recibida no puede borrar una actualización ya disponible. Las órdenes pendientes y los saldos conservan sus contratos anteriores. Una diferencia de P&L identifica el efecto de esta reparación bajo la simulación; no constituye alpha atribuible a cambiar parámetros de entrada o de salida.

**2 recetas de ablación. Total de nuevas políticas: 18.** Ambas se contabilizan aunque sus diferencias económicas sean nulas.

### H3. EWMA o actualización intradía: alternativa fuera de esta ronda

Una EWMA causal de retornos intradía de sesiones anteriores podría adaptar el compromiso entre ruido y retraso; una actualización intradía podría reconocer antes un refresco del régimen. También puede multiplicar el turnover, reaccionar al ruido contemporáneo y agravar el sesgo de ejecución. No se implementa ni mide esta familia en el catálogo actual. Añadirla después de observar resultados sería otra ronda con nuevos intentos registrados; no una corrección gratis de H1.

## Presupuesto y separación de datos

El catálogo de desarrollo contiene 18 candidatas y 5 controles: CURRENT, SIMPLE, CASH, M9_BEST y QUALITY_NATIVE72_R0625. M9_BEST conserva la política seleccionada por MODULATION9. El último control sólo sirve a la ablación de desarrollo.

| Fase | Políticas | Costes | Mundos | Semillas por mundo | Cuentas máximas |
|---|---:|---:|---:|---:|---:|
| Desarrollo | 23 | 2 | 5 | 8 | 1,840 |
| Final reservado | 5 | 2 | 5 | 64 | 3,200 |
| Máximo de la ronda | | | | | **5,040** |

El final contiene un único candidato y CURRENT, SIMPLE, CASH y M9_BEST. QUALITY_NATIVE72_R0625 no se añade al final por haber resultado favorable una ablación. Los 46 pares política-coste de desarrollo se registran además de las cuentas; el total histórico provisional de esa unidad pasa a 275, sin borrar la deuda anterior. Las cuentas sobre el mismo mundo/semilla son contrafactuales emparejados, no observaciones independientes adicionales.

La selección considera únicamente variantes con `role == candidate`. Primero filtra riesgo, conciliación y plazos. Su score es el mínimo, sobre TREND/WEAK y los dos costes, de `mean_daily_log - 1.645 * standard_error - hurdle`. El hurdle nominal es 0.0001 de logretorno diario; el de estrés es cero. Los empates se resuelven por menor p95 de drawdown de estrés, menor riesgo y, finalmente, identificador. La frontera de Pareto es descriptiva y sólo usa candidatas factibles.

**No se abre el final si no existe candidata factible o el score seleccionado no es estrictamente positivo.** Un promedio bruto positivo que no cubra el hurdle no habilita el final. La selección, el hash del manifiesto de desarrollo y los contratos se congelan antes de leer el final. El validador reconstruye la selección desde desarrollo; recalcular el hash de una selección manipulada no autoriza cambiar el ganador.

## Control de error entre rondas y parada opcional

El nuevo programa prospectivo asigna `alpha_k = 0.05 / 2**k`; esta primera validación futura usa 0.025. La suma del presupuesto futuro es 0.05. Esto no convierte retroactivamente el historial anterior, que incluyó una familia a 0.05, en un programa global al 95%. El protocolo registra expresamente esa limitación.

Hay 50 endpoints finales: 5 mundos × 2 costes × (absoluto + 4 controles). Bonferroni produce alpha unilateral de 0.0005 por endpoint. Las 50,000 réplicas de bootstrap dejan aproximadamente 25 réplicas en cada cola. La unidad de remuestreo es una trayectoria completa por semilla; se preserva conjuntamente el emparejamiento de políticas, activos y costes. La cobertura del bootstrap percentil es aproximada; aumentar réplicas sólo reduce el error de Monte Carlo, no crea nuevas semillas ni garantiza la cobertura.

No se mira el final progresivamente ni se añaden semillas hasta que el intervalo cambie de signo. Una adaptación después de un final observado requiere otro conjunto sin observar y consume el siguiente presupuesto. Si se quisiera parar en cualquier momento con garantías explícitas, haría falta construir e-processes o secuencias de confianza bajo supuestos demostrados para estas variables. Un intervalo bootstrap fijo no se transforma en una secuencia de confianza por repetirlo. Las fuentes primarias sobre estas distinciones son Howard et al. y Ramdas et al. [S1–S2].

## NULL y el sesgo de fills OHLC

Hay dos paradas diferentes: la salida causal de una posición y la decisión estadística de continuar investigando. Bajo una trayectoria martingala, una estrategia predecible y autofinanciada con horizonte acotado no obtiene valor esperado positivo por mover únicamente su hora de salida; las fricciones y el coste fijo empeoran la cuenta. Esta observación requiere que los precios de ejecución pertenezcan al proceso modelado y que la posición se elija antes de la innovación que la remunera.

El motor conserva sólo OHLC de ocho subpasos. Cuando un mínimo cruza un stop paga el umbral, salvo gap de apertura; cuando un máximo cruza un target paga ese umbral. Priorizar stop cuando ambos se tocan es conservador respecto de una ambigüedad concreta, pero no demuestra ausencia de sesgo del modelo completo. Pagar el stop en lugar del primer subpaso observado por debajo puede omitir overshoot; omitir cruces que se revirtieron entre observaciones tampoco equivale a una orden real. HOLD evita targets y parciales, pero mantiene esta aproximación del stop.

Se conservan los bloqueos de NULL tanto absolutos como frente a CASH con el mismo coste. Un límite inferior positivo en cualquiera invalida la inferencia. Que ambos límites sean no positivos no demuestra que el simulador sea insesgado: también puede existir potencia insuficiente para detectar una desviación pequeña.

La prueba de falsación apropiada es auditar la misma trayectoria mediante primeros cruces observables o una política de decisión al cierre recibido y ejecución en la apertura siguiente. No se deben entregar los subpasos futuros a la estrategia ni recalibrar la ley, los costes o el orden intrabar a favor del ganador. Cualquier ejecución alternativa se versiona como prueba de robustez y no sustituye silenciosamente al resultado registrado.

## Viabilidad del objetivo y criterio de suspensión

El régimen WEAK usa un drift de 0.000025 por barra y sólo dos activos long-only. El techo que concedería conocer los estados positivos es más exigente que obtener un mejor score que el ORB. Una cota con exposición continuamente limitada al 12% no es, por sí sola, una cota del motor heredado: aquí el 12% limita la admisión/reserva y puede haber exceso posterior por precios. Tampoco una prueba para ejecuciones causales exactas certifica automáticamente fills OHLC interpolados.

Si una cota superior demostrada para **la semántica realmente admitida** queda por debajo del hurdle neto de WEAK, la búsqueda de ese contrato debe suspenderse. No sería correcto continuar hasta obtener una fluctuación favorable ni cambiar el umbral manteniendo la misma etiqueta. Si la cota sólo cubre una versión más estricta, se informa esa condición y la incertidumbre restante; no se anuncia una imposibilidad universal.

Esta ronda puede diagnosticar si entradas más persistentes mejoran las cuentas dentro del mismo banco. No promete llegar a 9. Las carencias de ejecución calibrada y de integración completa de la matriz virtual siguen siendo gates operativas falsas, predeclaradas, incluso si alguna política pasara los requisitos económicos.

## Contratos de ingeniería antes de la medición

- El código de MODULATION9, su registro y sus resultados deben conservar sus hashes. El analizador 10 reutiliza sólo funciones puras; no reasigna globals del analizador 9.
- Cambiar un dato con `availableAt` posterior a la decisión no puede cambiar la señal, su score, el ATR ni el tamaño de entrada anterior.
- La selección se reconstruye sólo desde desarrollo, incluyendo roles, hurdles y la totalidad de mundos, semillas y costes.
- Semillas duplicadas, controles ausentes, costes intercambiados, contextos sobrescritos, calendarios distintos o curvas que no concilian deben rechazarse aunque se recalculen checksums.
- Ningún dato faltante, resultado no finito, pérdida de riesgo, profit de una sola campaña o selección sin score positivo puede habilitar el final.
- Los fixtures de ingeniería son pequeños y explícitos. No se generan rendimientos de estrategias antes del registro.

## Fuentes primarias metodológicas

[S1] Howard, Ramdas, McAuliffe y Sekhon, *Time-uniform, nonparametric, nonasymptotic confidence sequences*, Annals of Statistics 49(2), 2021. https://arxiv.org/abs/1810.08240 — garantías uniformes en el tiempo bajo condiciones explícitas.

[S2] Ramdas, Grünwald, Vovk y Shafer, *Game-theoretic statistics and safe anytime-valid inference*, 2023. https://arxiv.org/abs/2210.01948 — e-processes, secuencias de confianza y continuación/parada opcionales.
