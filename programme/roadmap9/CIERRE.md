# HARPOON: resultado y cierre del ciclo offline

**Se concluyó el ciclo autorizado de implementación e investigación. Las seis recetas quedaron rechazadas; no hay candidato para operativa real.** Se entregan código, pruebas ejecutadas, resultados negativos, reproducción y dictámenes para los 49 validadores. El plan original permanece intacto. El cierre no declara aprobadas las doce fases.

## Resultado económico

Periodo reutilizado: 404 sesiones, del 11 de marzo de 2025 al 16 de octubre de 2026; 20.000 USD por cuenta, sin reinicio. Los costes comunes modelados abarcan 585 días naturales: 585 USD nominal y 1.170 USD bajo estrés. Todas las cifras siguientes son de cuentas históricas modeladas.

| Receta | Neto nominal USD | Neto estrés USD | Campañas nominal/estrés | Decisión |
| --- | ---: | ---: | ---: | --- |
| H1 — horario 24 h | −535,50 | −1.170,00 | 1 / 0 | Rechazada |
| H1 — elección 24/48/72 h | −585,69 | −1.167,27 | 3 / 2 | Rechazada |
| H2 — aceptación del gap | −189,51 | −782,16 | 9 / 9 | Rechazada |
| H2 — gap y sector | −262,73 | −859,98 | 6 / 6 | Rechazada |
| H3 — salida total por valor | −407,08 | −1.062,23 | 52 / 52 | Rechazada |
| H3 — reducción parcial por valor | −463,41 | −1.102,39 | 46 / 46 | Rechazada |

El control de continuación original, reevaluado con gasto diario, queda en −54,42 USD nominal y −701,41 USD bajo estrés. El control de continuación causal común queda en −463,42/−1.086,06 USD. CASH representa la infraestructura sin posiciones, con su coste modelado: −585/−1.170 USD. No es el rendimiento de un depósito de efectivo.

H1 y H2 tienen soporte escaso; el error predictivo del modelo de horario supera la previsión cero en los tres horizontes. Ninguna de las 96 cotas inferiores pareadas supera cero. El pareado de 45 entradas fijas de H3 total mejora +86,81/+62,40 USD, pero la cuenta completa sigue perdiendo. La reducción parcial empeora −53,20/−67,45 USD en ese pareado. No se convierte un fragmento favorable en una séptima receta.

El estudio no acredita alpha a riesgo equivalente: los límites ex ante son comunes, la exposición realizada cambia y no hay referencia de mercado emparejada. El histórico ya se había inspeccionado y la historia global de búsqueda sigue incompleta.

## Implementación y verificación

Se añadieron contratos de coste en unidades nativas, reductor por eventos, recuperación, salidas con plazo original, previsiones causales, registro de recetas, asignador robusto discreto separado, admisión de observaciones, salud/degradación y cierre de evidencia. El asignador nuevo no está integrado en las seis recetas ni se le atribuye rentabilidad.

La reproducción conserva las entradas y primeros intentos de salida de 108 cuentas del banco sintético. Los retrasos CORE respecto al deadline planificado pasan de 16 a 0; en el control, de 57 a 0. El máximo original de 72 horas se mantiene. Son resultados dentro de un sobre sintético; no describen fills reales ni un SLA de broker.

Se reprodujeron los dos baselines archivados, las 108 cuentas sintéticas y exactamente las 20 cuentas del estudio. Los datos originales, el plan y los resultados anteriores no se alteraron. El benchmark de capacidad usa 288 contextos: 279 cálculos completos con 81 acciones y 9 rechazos de deriva esperados. **V040 falla el objetivo p95: 2,051 segundos frente a 2,000.** El p99 es 2,189 segundos frente al máximo 5,000; el máximo medido es 2,318. No se relajó el objetivo ni se repitió el experimento buscando un pase. Trabajo máximo 5.593.536 y antigüedad al terminar ≤ 2,3184 segundos permanecen dentro de sus topes.

La pasada final ejecutó **772 pruebas: 772 PASS, 0 fallos, 0 errores y 0 omisiones**, sin cambios de fuentes durante la ejecución.

Ruff pasa; el tipado del paquete y de las herramientas no congeladas pasa. Se conservan nueve hallazgos de mypy en dos scripts históricos congelados, descritos en el README de investigación. No se anuncia un pase estático de todos los scripts. Los errores detectados por revisión adversarial se corrigieron antes de cerrar sus componentes y se volvieron a comprobar.

## Incidencias y requisitos que siguen abiertos

El journal de investigación presentó una discrepancia de resultados: el recibo indicaba 11 y una lectura posterior contenía 10, aunque existían 12 START y 12 resultados financieros. Su causa no está establecida. Se conservaron bytes y recibos, se añadieron sólo los dos RESULT faltantes y la reproducción exacta verificó la cadena reconciliada 12/12 sin modificar fuentes, recetas, PnL o presupuesto.

Faltan tarifas específicas de cuenta; universo/capacidad y fuentes point-in-time auténticas; feed de subasta y contexto Cboe; integración completa con el servicio y resolución demostrada del timeout legado; calibración de fills reales; observación prospectiva; revisión externa y autorización operativa de cuenta/version/límites. La asignación cripto con fee nativa está bloqueada en el nuevo optimizador aunque el ledger de comisiones esté probado.

No se ejecutó un despliegue ni se enviaron órdenes. Al no quedar candidatos viables, el resultado del protocolo es detener la promoción antes de un ensayo live. El código y la evidencia pueden revisarse sin abrir una nueva búsqueda económica.

## Documentación y recibos

- [Especificación, resultados y reproducción del estudio](../../research/roadmap9/README.md).
- [Implementación, comandos y contrato de evidencia](IMPLEMENTACION_Y_OPERACION.md).
- [Cierre verificable de los 49 contratos](closure.json) y [dictámenes con referencias SHA-256](claims.json).
- [Resultados económicos completos](../../evidence/roadmap9/research/results.json).
- [Pruebas individuales](../../evidence/roadmap9/validation/tests.json) y [benchmark registrado](../../evidence/roadmap9/validation/benchmark.json).


# Dictamen de las 12 fases y 49 validadores

Este recibo distingue implementación probada de aceptación económica y operativa.
Las fases con requisitos externos pendientes permanecen bloqueadas.

| Fase | Resultado | Contratos |
| --- | --- | --- |
| P00 — Baseline y registro de investigación | BLOCKED | PASS: 3, BLOCKED: 1 |
| P01 — Costes y contratos económicos por activo | BLOCKED | BLOCKED: 1, PASS: 3 |
| P02 — Ejecución por eventos y recuperación | BLOCKED | PASS: 3, BLOCKED: 1 |
| P03 — Datos temporales y universo elegible | BLOCKED | BLOCKED: 3, PASS: 1 |
| P04 — Pronóstico condicional por horizonte | BLOCKED | PASS: 3, BLOCKED: 1 |
| P05 — Asignación de capital y congelación de recetas | BLOCKED | PASS: 3, BLOCKED: 1 |
| P06 — Hipótesis H1 continuación condicionada por horario | BLOCKED | BLOCKED: 2, PASS: 2 |
| P07 — Hipótesis H2 gaps y aceptación del precio | BLOCKED | PASS: 1, BLOCKED: 3 |
| P08 — Hipótesis H3 salida por valor de continuación | REJECTED_CANDIDATE | PASS: 4 |
| P09 — Integración adversarial y rendimiento | BLOCKED | BLOCKED: 2, PASS: 1, FAIL: 1 |
| P10 — Fills observados y validación prospectiva | BLOCKED | BLOCKED: 5 |
| P11 — Revisión externa y liberación controlada | BLOCKED | BLOCKED: 2, PASS: 2 |

## Evidencia y trabajo restante

| Validador | Resultado | Observado | Pendiente o límite del alcance |
| --- | --- | --- | --- |
| V001 — Reproducción del baseline | PASS | 151 archivos originales (10.850.720 bytes) verificados; recibos Frontier reproducidos; Synthetic9: 108 cuentas, 2.978 fills, 36.396 marcas y 288 modelos comprobados en procesos separados. | Pase de reproducción local; los 649 tests de CI previos conservan su fecha y alcance originales. |
| V002 — Presupuesto de búsqueda global | BLOCKED | Registro implementado y probado: 3 hipótesis, 6 recetas, 12 mediciones; 53 anteriores documentadas y 65 reservadas del límite 128. Cadena reconciliada 12/12; incidencia de 2 RESULT ausentes preservada. | Historia global incompleta y causa de incidencia no establecida. No se certifica corrección global de selección ni registro temporal independiente. |
| V003 — Integridad del presupuesto de I D | PASS | Validador del programa ejecutado: 5.000.000 USD de presupuesto de planificación, 0 USD reportados gastados en el baseline; sin autorización de gasto. | El gasto reportado del baseline no es una auditoría de facturas actuales. |
| V004 — Separación de evidencia y autoridad | PASS | Ataques de origen, autoridad, claves de prueba, firma del propio autor, manifiesto ausente y commit inválido se rechazan; todos los recibos nuevos mantienen execution_allowed=False. | Una firma válida verifica una afirmación de una clave confiable; no prueba por sí sola la verdad de la fuente. |
| V005 — Tarifa y función de liquidez | BLOCKED | Perfil tarifario versionado enlaza todos sus campos; maker/taker desconocido se rechaza y una orden límite no fuerza maker. Modos nativo cripto y USD por acción probados. | Falta contrato de cuenta, tramo por volumen, venue y tarifas observadas. Las tarifas públicas asumidas y los 2 bps archivados no se presentan como tarifa real. |
| V006 — Comisiones en unidades nativas | PASS | Comisiones nativas, parciales, provisiones, posting tardío, corrección delta y deduplicación comprobados con Decimal. El perfil completo permanece ligado a cada fill. | Fixtures sintéticos; no se ha reconciliado una actividad CFEE/FEE original de una cuenta. |
| V007 — Patrimonio y gasto común | PASS | Cuenta continua 20.000 USD; gasto común una vez, incluyendo CASH y fines de semana; 20 cuentas históricas conciliadas. 585/1.170 USD nominal/estrés en 585 días naturales. | Gasto diario modelado de 1/2 USD; las facturas reales y la viabilidad observada siguen pendientes. |
| V008 — Disponibilidad de efectivo e inventario | PASS | No se financian compras con ventas propuestas ni derechos no disponibles; se reservan fills anunciados y comisiones pendientes; se rechaza doble venta entre campañas. | El asignador nuevo bloquea órdenes pendientes hasta un adaptador de reconciliación; ningún recibo transmite órdenes. |
| V009 — Ciclo de orden idempotente | PASS | Máquina de órdenes probada con ACK, parciales, cancelación, reemplazo, rechazo, duplicados, fill antes de ACK y anuncios acumulados. 3 errores adversariales corregidos y reatacados. | Comprobación offline; la idempotencia del reductor no promete idempotencia de un envío al broker. |
| V010 — Deadline y reintentos acotados | PASS | 108 cuentas con entradas preservadas. Retrasos respecto al deadline planificado: CORE 16→0; control 57→0; cero inventario pendiente en el replay y duración ≤ 72 h. | Pase sólo dentro del sobre sintético registrado. Los 16 eran retrasos planificados; no eran 16 excedencias del máximo original de 72 h. |
| V011 — Halts y ausencia de liquidez | PASS | Halts, falta de ventana de salida y exposición vencida se detectan sin crear fills; se conserva inventario y la causa. También se bloquea inventario vencido sin un fill tardío. | La prueba de detección no demuestra cumplimiento de plazo cuando no existe mercado. |
| V012 — Reinicio y pulso real | BLOCKED | Reinicio de journal, fallo de escritura atómica, reserva de órdenes ambiguas y salud por recibos probados. Caída del predictor bloquea entradas y conserva gestión de reducción. | No se ha reproducido y corregido el timeout del predictor legado dentro del servicio desplegado ni probado su integración completa con broker/almacenamiento. |
| V013 — Calendario y acciones corporativas | BLOCKED | Probados DST, media sesión, deadline de fin de semana, calendario recibido, dividendos y rechazo de splits sin disponibilidad conocida; el estudio usa calendario y acciones corporativas archivados. | El conjunto completo multiasset con ajustes y recibos point-in-time originales no está certificado. No se transforma el calendario sintético en calendario bursátil observado. |
| V014 — Disponibilidad y caducidad | PASS | Precios futuros, recepción adelantada, cotizaciones caducadas, etiquetas posteriores al ajuste y reloj reestampado se bloquean. Topes 15 s y 168 h no se relajan mediante configuración. | En el histórico, disponibilidad es cierre de vela +1 s modelado, no recepción original; se conserva esa etiqueta. |
| V015 — Universo y concentración | BLOCKED | Control de inventario completo, concentración, cash y presupuesto de trabajo probado. Estudio limitado a AAPL/MSFT con contexto XLK. | Falta universo sin sesgo de supervivencia, capacidad observada y elegibilidad punto en el tiempo de un universo ampliado. |
| V016 — Procedencia y permisos de fuentes | BLOCKED | Dataset 124.182 barras reconstruido exactamente desde 80 blobs. Ninguna barra se etiqueta como cola, profundidad, BBO o desequilibrio de subasta observado. | Faltan autenticación independiente de fuente, permisos verificados y recibos temporales originales de BBO/subasta/opciones. |
| V017 — Descomposición nocturna e intradiaria | PASS | 6.162 filas; objetivos 24/48/72 h descompuestos en nocturno e intradiario con residuo máximo 0. Mutaciones futuras no cambian las features anteriores. | Identidad de precios de acciones; no acredita ventaja económica ni añade gap bursátil a cripto. |
| V018 — Distribución y etiquetas a 24 48 y 72 horas | PASS | Etiquetas maduras con purga 72 h, calibración sólo en TRAIN y deadline real de 24/48/72 h; pruebas de barrera ambigua y bootstrap sin nuevos casos originales pasan. | La cronología intrabar no identificada conserva sus límites; el replay sigue modelado. |
| V019 — Calibración y modelo de referencia | PASS | Comparación predictiva y guardas ejecutadas. MSE del modelo supera la referencia cero aproximadamente 6,0%, 9,4% y 10,5%; 2.448 abstenciones por fallo de referencia de calibración. | Pase del ejercicio de comparación, con resultado predictivo desfavorable. No se acredita calibración poblacional ni ventaja del modelo. |
| V020 — MACD y osciladores como contexto causal | BLOCKED | Tests causales existentes de MACD, RSI/estocástico y contexto de precio pasan; no se tratan como votos independientes. | Falta una ablación incremental aislada y registrada de esos osciladores frente a precio/volatilidad/horario. No se añadió una séptima receta después de ver resultados. |
| V021 — Objetivo y unidades de la cartera | PASS | Asignador robusto discreto nuevo para acciones/ETF USD, costes en Decimal, Σ de retornos y Ω de la media diferenciadas, una base de patrimonio/horizonte, repricing independiente y redondeo comprobados. | Proxy media-varianza de crecimiento logarítmico, no utilidad log exacta ni óptimo global. Componente no integrado ni medido económicamente en las 6 recetas. |
| V022 — Rotación y bandas de no operar | PASS | Malla incluye esperar/mantener, reducir, aumentar y cerrar; exige ventaja incremental frente al estado actual y control sin compras, coste global y banda registrada; decaimiento/cooldown probados. | Pronósticos, banda y decaimiento de este componente son supuestos de ingeniería sin calibración económica. |
| V023 — Lotes y financiación parcial | BLOCKED | En acciones/ETF USD se comprueban lotes, coste, caja y esquinas adversas de fills parciales; compras nunca dependen de ventas pendientes. | La adaptación de asignación a compras cripto con comisión en activo nativo y órdenes pendientes reales queda bloqueada. El ledger nativo ya está probado por separado. |
| V024 — Límites y escenarios sin señal | PASS | Sin señal, costes excesivos, shock de correlación, riesgo diario/drawdown y pausas probados; no se relajan caps originales. Las 6 recetas mantienen bruto 12%, DD8%, diaria 2% y riesgo 0,25%. | Los escenarios discretos no garantizan riesgo futuro. La propuesta de reducción fuera de caps no se certifica como segura. |
| V025 — Congelación antes de medir H1 | BLOCKED | Código, recetas, 29 bindings y doce START registrados antes de los nuevos cálculos. Reproducción exacta verificada; incidencia de registro conservada. | El periodo completo ya había sido inspeccionado. No cumple separación de un holdout virgen ni atestación independiente de preregistro. |
| V026 — Ablación económica de horario | BLOCKED | Dos H1, continuación causal, continuación archivada, CASH y precio 24 comparados; neto, crecimiento, drawdown, exposición, costes y atribución nocturna/intradiaria publicados. Ambas H1 negativas. | Los límites ex ante son comunes, pero exposición realizada y referencia de mercado no están emparejadas; no se identifica alpha aislado del filtro. |
| V027 — Incertidumbre y concentración de H1 | PASS | Diagnósticos de concentración y soporte, 20.000 remuestreos pareados, bloques 5/20 y 120 endpoints declarados. Ninguna de 96 cotas de diferencias pareadas supera 0; H1 sólo 1/3 campañas nominales. | Pase de reporte diagnóstico; no inferencia confirmatoria global. Remuestreos y periodos solapados no se cuentan como nuevos casos. |
| V028 — Decisión de conservar o descartar H1 | PASS | Las dos H1 registradas quedan REJECTED_CANDIDATE y retained_for_forward=False, sin reajuste posterior. | Cualquier hipótesis futura requerirá una nueva identidad y presupuesto antes de medir. |
| V029 — Gap y confirmación causal | PASS | Gap normalizado, aceptación con barras cerradas y contexto XLK implementados y probados causalmente. H2 ejecuta 9 y 6 campañas por escenario. | Resultado económico negativo y soporte inferior al mínimo 20; confirmación sectorial no es flujo de subasta auténtico. |
| V030 — Flujo auténtico de subasta | BLOCKED | La rama de subasta permanece ausente y explícitamente declarada como no soportada. | Se requieren snapshots auténticos NYSE/Nasdaq con símbolo, sesión, origen, recepción y derechos. No pueden reconstruirse desde OHLCV. |
| V031 — Contexto de volatilidad de Cboe | BLOCKED | No se añadió una serie Cboe inventada ni se habilitaron órdenes de opciones. | Faltan series y recibos originales de contexto implícito y sus plazos/unidades; se requieren antes de evaluar esa rama. |
| V032 — Valor incremental de H2 | BLOCKED | H2 gap −189,51/−782,16 USD y H2 sector −262,73/−859,98 USD nominal/estrés. Ambas rechazadas; filtros y exposición reportados por separado. | No hay rama con flujo de subasta observado ni riesgo/exposición realizados emparejados; no se puede completar la atribución prevista de flujo. |
| V033 — Continuación frente a liquidación | PASS | H3 compara continuación frente a salida con datos disponibles y sólo cuando 24 h caben en el deadline; la comisión de entrada gastada no se cobra otra vez. | Política de decisión actual basada en previsión; no resuelve Bellman ni garantiza el valor previsto. |
| V034 — Protección y plazo original | PASS | Campaña/deadline originales preservados en parciales, nuevas propuestas y recuperación; 20 cuentas históricas auditadas con duración máxima 71,999722 h y 108 replays sintéticos dentro 72 h. | Eventos corporativos sin disponibilidad suficiente bloquean el componente; no se garantiza salida física en halt. |
| V035 — Presupuesto temporal de la salida | PASS | Presupuesto de despacho, ventanas recibidas y 8 reintentos máximos a 250 ms fijados; 108 cuentas sin retrasos evitables en el sobre sintético. | Demora de broker y ejecución urgente no calibradas con fills reales; no se extrapola un SLA desde tiempos locales. |
| V036 — Ablación de salida H3 | PASS | Ablación sobre 45 entradas/cantidades/precios fijos: salida total +86,81/+62,40 USD; parcial −53,20/−67,45 USD. Cuentas completas separan reutilización/reentradas y siguen negativas. | Pase de la atribución ejecutada; las dos recetas H3 quedan rechazadas y no se crea un ensamblado adicional. |
| V037 — Ataques de integración | BLOCKED | Ataques locales de CFEE tardía, cambio de tarifa, cancelación ambigua, almacenamiento fallido, reloj y caducidad comprobados; hallazgos del equipo corregidos y repetidos. | No hay integración desplegada que cubra todos los fallos combinados. Incidencia del registro de causa no establecida y 9 hallazgos de tipado en 2 scripts congelados se conservan. |
| V038 — Comprobación separada y hashes | PASS | Verificadores separados reconstruyen baseline y 108 replays; auditor Python de 20 cuentas y reproducción exacta de hashes; matriz de pruebas preserva fuentes. | Repricing de fills históricos usa precios modelados del replay; la revisión por otro agente del mismo equipo no es externa ni autenticación del broker. |
| V039 — Pulso y control de autoridad | BLOCKED | CLI y componentes offline sin transporte ni credenciales; salud usa fuente/recepción/conciliación, LLM no es requisito de reducción y ningún recibo autoriza órdenes. | Falta el recorrido completo en la API/servicio del producto y su adaptador de datos/órdenes autenticados. No se afirma integración productiva a partir de tests de componentes. |
| V040 — Benchmark reproducible del perfil operativo | FAIL | Benchmark fijado antes de medir: 288 contextos, 279 cálculos completos con 81 acciones, 9 rechazos esperados, 0 fallos inesperados. p95=2,051 s > 2 s; p99=2,189 s ≤ 5 s; máximo 2,318 s. Trabajo 5.593.536 ≤ 30.000.000; fuente aún vigente. | Objetivo p95 incumplido; no se relajó ni se repitió buscando un pase. Perfil sintético local, no SLA del broker ni garantía para otro universo. |
| V041 — Trazabilidad de fills observados | BLOCKED | Reconciliador implementado y probado con paquetes sintéticos; admisión sin observaciones queda BLOCKED y no acepta autoatestación. | No se dispone de paquete original de cuenta con decisión/BBO/ACK/FILL/CFEE/FEE y cobertura autenticada. El normalizador no aporta los originales. |
| V042 — Calibración sin reutilizar la validación | BLOCKED | Se exige calibración anterior al periodo y fees conciliadas; las pendientes no se sustituyen por cero. | Faltan fills live y soporte de ejecución por activo/rol/liquidez/régimen; no se ha estimado un coste observado independiente. |
| V043 — Protocolo de evaluación futura | BLOCKED | Contrato de periodo futuro, cuenta 20.000 USD, fechas completas y bindings de receta/coste/código implementado. | Cero candidatos elegibles después de las 6 recetas rechazadas. No se abre un ensayo futuro ni se recicla 2025–2026 como holdout virgen. |
| V044 — Aceptación económica y riesgo comparable | BLOCKED | Diagnóstico pareado con soporte/bloques/multiplicidad local implementado; todas las 6 cuentas candidatas pierden nominal y estrés. | Falta evidencia prospectiva live, riesgo/exposición comparables, crecimiento neto positivo y control de selección global. No se acredita 9/10. |
| V045 — Riesgo operativo durante observación | BLOCKED | Monitores de conciliación, edad, pérdida diaria, drawdown, deterioro de alpha/costes y plazos implementados como decisiones locales. | No existió periodo de observación real de esta entrega; faltan riesgos, incidentes y costes realizados durante ese periodo. |
| V046 — Revisión externa auténtica | BLOCKED | Revisión adversarial interna entre agentes y verificación de firma/independencia implementadas; no se autogenera firma de un tercero. | Falta un revisor externo auténtico, su identidad/independencia verificadas, alcance y conclusión vinculada a versión y evidencia. |
| V047 — Permiso de ejecución con alcance | BLOCKED | Toda la entrega mantiene execution_allowed=False y carece de transporte al broker. | La autorización para código e investigación no es autorización para operar una cuenta. No hay candidato aprobado ni permiso operativo específico verificado. |
| V048 — Ensayo de reversión | PASS | Ensayo de intención de rollback conserva campañas, deadline, inventario y órdenes pendientes; rechaza destino rechazado y estado no conciliado. | No ejecuta un despliegue ni autentica la aprobación de destino; esa liberación permanece bloqueada. |
| V049 — Vigilancia de degradación | PASS | Pausa por deriva de alpha/costes, pérdida y caducidad probada; se preserva reducción determinista y ninguna regla se autoaprueba mediante LLM. | Estadísticas suministradas por el llamador y umbrales de ingeniería; falta calibración y monitorización observada en servicio. |

Ningún resultado de este documento habilita órdenes, acredita nivel 9 o sustituye revisión externa.
