# HarpoonX C30 — factibilidad estructural previa a la autenticación financiera

Estado: diagnóstico reproducible de lectura únicamente en rama aislada. N9-S NO_GO. No cierra la prueba económica C29, no autoriza órdenes.

## Resultado de inspeccionar el código original

C29 congela seis variantes C22, ORIGINAL_BASELINE y CASH. Su lector de QuantObservationJournal observa solo el plugin observation-only y selección rotativa; no demuestra seis llamadas originales antes del filtro.

El módulo fwn9_c22_session_compound.cjs devuelve executionAllowed=false desde rank y quantity. Dos de las variantes congeladas son estudios de opciones, y size rechaza OPTIONS_CONTRACT_EXECUTOR_NOT_CERTIFIED. Por su parte el exportador C25 instrumentCatalog rechaza asset.class=option, de modo que todavía no permite conciliar multiplicadores, primas, comisiones, ejercicio y liquidación de un brazo real de opciones.

Con estas restricciones, una permutación de ocho brazos y un hash de plan no producen ocho políticas ejecutables; afirmar lo contrario confundiría investigación con ejecución.

## Artefactos y ejecución

- runtime30/fwn9_c30_study_feasibility.cjs: prueba de interfaces originales C22/C25/C28/C29, con inyección local controlada solo para comprobar el rechazo de contratos de opciones.
- tools/fwn9_c30_study_feasibility_test.cjs: seis verificaciones adversariales sin conexiones de red, órdenes, datos de mercado, semillas ni nuevas cuentas.
- .github/workflows/fwn9_p9m_c30.yml: validación automática enfocada de la rama aislada.

Reproducir desde raíz con Node 22:

    node --check runtime30/fwn9_c30_study_feasibility.cjs
    node --test tools/fwn9_c30_study_feasibility_test.cjs

El alcance es factibilidad estructural, no certificación de origen ni una estimación de rentabilidad.

## Puertas que siguen abiertas y criterio de cierre

A. Productor original: instrumentar antes del filtrado cada evaluación exigida por la matriz C28 de activo, barra y variante, incluyendo llamadas que devuelvan cero señales. Enlazar con C27 y comprobar exhaustividad respecto del universo anclado. La enumeración no debe depender de oportunidades emitidas ni de OHLC futuro.

B. Broker: identificar servicio Render autorizado y recuperar por GET los snapshots, órdenes y actividades privadas de Alpaca PAPER en un entorno protegido. C25-C26 deben demostrar conciliación de caja, NAV, tarifas, órdenes, quotes predecisión, eventos tardíos y recibos. El conector de datos de mercado no sustituye Trading API privada.

C. Preregistro: congelar hash del código, universo, ocho brazos, calendario, bloqueos, capital, análisis estadístico y presupuesto de comparaciones en un registrador independiente con recepción temporal verificable ANTES de observar resultados. Una firma local o un hash de GitHub por sí solo no lo certifican.

D. Ejecutabilidad: mantener la versión C29 sin operar. Si se desea ejecutar los dos brazos de opciones, crear y validar el ejecutor y la contabilidad adecuados, y preregistrar una versión prospectiva nueva antes de observar resultados. Si permanecen como shadow, no asignarles fills ni rentabilidad verdadera.

E. Inferencia: 8 ciclos permiten algebraicamente el p mínimo 1/256, no garantizan potencia ni intercambiabilidad temporal en más de un año de bloques. Exigir independencia del mecanismo de asignación, estabilidad del universo, tratamiento de carryover, costes y riesgos; si falla, reportar diagnóstico, no GO.

No se modificaron M9, OHLC ni los seis brazos originales; no hubo operaciones, claves, merges, despliegues ni acceso a M10.

## Veredicto

C30 revela una incompatibilidad estructural previa a la autenticación financiera: el estudio C29 está diseñado, pero no es ejecutable con sus seis variantes congeladas. C30 es un bloqueo fail-closed y queda pendiente la evidencia externa operativa. N9-S NO_GO.
