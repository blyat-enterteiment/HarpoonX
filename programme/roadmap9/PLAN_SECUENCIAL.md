# Plan secuencial de mejoras y validación operacional de HARPOON

Fecha de referencia: 2 de noviembre de 2026, Ciudad de México. Baseline: `89602e263aeb7f4012a11f53c00c06a4a0058dba`. El objetivo es transformar las mejoras propuestas en una secuencia verificable que preserve capital, costes completos y trazabilidad. Cada fase termina con evidencia, rechazo o bloqueo explícito.

Alcance: swing hasta 72 horas, equity, ETF y cripto spot en USD. Las opciones aportan contexto mientras no exista otro contrato de valoración y lifecycle. La gestión de órdenes por eventos no convierte la estrategia en HFT.

El [plan estructurado](plan.json) es el catálogo de fases y validadores. Esta entrega especifica trabajo y criterios: no implementa los validadores nuevos ni da por cerrada ninguna fase. Las referencias a tests existentes indican cobertura parcial previa, que debe ampliarse y repetirse sobre el cambio correspondiente.

## Punto de partida y prioridades

El baseline contiene 649 tests aprobados en dos runners de GitHub y una verificación separada de 108 cuentas sintéticas. Conserva 16 retrasos CORE respecto al plazo planificado, costes de prueba supuestos, ausencia de fills live y ausencia de revisión externa. El timeout local del predictor legado sigue sin causa determinada. Estos hallazgos son entradas del plan, no excepciones borradas.

Primero se cierran costes, contabilidad, datos y ejecución. Después se congelan pronóstico y asignación comunes y se contrastan H1 horario, H2 gaps y H3 salidas. Las ramas rechazadas pueden cerrarse y dejar paso a la siguiente hipótesis; no pueden promocionarse. Si no queda ningún candidato viable al agotar el presupuesto, el programa termina sin pasar a un ensayo live.

## Secuencia y entregables

| Orden | Fase | Entregable | Responsable funcional |
| --- | --- | --- | --- |
| P00 | Baseline y registro de investigación | Baseline reconstruido, manifiesto de fuentes, registro global de ensayos y rúbrica económica. | Responsable de investigación y reproducibilidad |
| P01 | Costes y contratos económicos por activo | Esquema de costes, comisiones nativas, reservas y gasto común para el siguiente experimento. | Ingeniería de ejecución y contabilidad |
| P02 | Ejecución por eventos y recuperación | Máquina de estados de orden, reintentos acotados, recuperación y telemetría operacional. | Ingeniería de ejecución y operaciones |
| P03 | Datos temporales y universo elegible | Contrato point in time de datos, acciones corporativas, calendario, capacidad y universo. | Ingeniería de datos y control de mercado |
| P04 | Pronóstico condicional por horizonte | Pronósticos separados por tramo de sesión y horizonte, con incertidumbre y calibración temporal. | Investigación cuantitativa |
| P05 | Asignación de capital y congelación de recetas | Asignador común con incertidumbre, costes, correlación, bandas de no operar y recetas finales congeladas. | Construcción de cartera y riesgo |
| P06 | Hipótesis H1 continuación condicionada por horario | Ablación H1 con mismas fuentes, costes completos, controles y cuentas continuas. | Investigación de alpha |
| P07 | Hipótesis H2 gaps y aceptación del precio | Ablación H2 y, sólo con datos adecuados, variante con flujo de subasta auténtico. | Investigación de eventos y datos de mercado |
| P08 | Hipótesis H3 salida por valor de continuación | Control de continuación finito con deadline inmutable y comparación de salidas. | Control cuantitativo y ejecución |
| P09 | Integración adversarial y rendimiento | Matriz de fallos ampliada, recorrido completo, comprobación numérica separada y benchmark del perfil registrado. | Verificación y operaciones |
| P10 | Fills observados y validación prospectiva | A datos originales reconciliados y perfil de costes; B periodo futuro con candidato final y controles. | Operaciones, investigación y riesgo |
| P11 | Revisión externa y liberación controlada | Informe externo, resolución de hallazgos, autorización de versión y procedimiento de reversión. | Revisor externo, responsable de riesgo y titular autorizado |

La dependencia técnica es secuencial: cada fase utiliza los contratos y resultados registrados de la anterior. En P07, una rama que dependa de datos no disponibles se cierra como no evaluable; no se reemplaza por una proxy bajo la misma identidad. P10A recoge y calibra datos observados; sólo después de congelar esa calibración comienza P10B.

## Reglas de avance y parada

1. Una fase avanza por sus recibos y criterios, no por una fecha ni por sumar tests. FAIL, BLOCKED, NOT_RUN o un test crítico omitido impiden usar el cambio para promoción.
2. El resultado de una hipótesis puede ser RETAIN_FOR_FORWARD, REJECTED_CANDIDATE o NO_CONCLUSION. Un resultado negativo permanece visible; una combinación nueva de estrategias consume una receta.
3. El máximo de búsqueda nueva es tres hipótesis y seis recetas completas. Una receta incluye datos, targets, modelo, refit, asignación, entrada, salida, costes, riesgos y selección. Los seis manifiestos deben estar completos antes de medir; el periodo final no se usa para diseñarlos.
4. Ante fallo de datos, conciliación, autoridad o límites, se bloquean entradas. La gestión de posiciones conocidas continúa sólo conforme al estado conciliado y al runbook autorizado. Un halt puede impedir físicamente cerrar; se registra incumplimiento e inventario pendiente.
5. Las fuentes y acciones paper, live, históricas modeladas y sintéticas se conservan separadas. Detectar una infracción en una prueba no significa haber cumplido el límite en el escenario probado.
6. El presupuesto sigue siendo el de [programme.json](../frontier/programme.json): 5,000,000 USD de planificación y gasto reportado cero en el baseline. Los WP repetidos son referencias, no asignaciones adicionales. El horizonte de doce meses es orientativo desde un inicio autorizado y puede terminar sin aprobación si falta evidencia.

## Validadores por fase

### P00 Baseline y registro de investigación

Conservar resultados negativos y fijar el contrato de comparación antes de cambiar el motor. Entregable: Baseline reconstruido, manifiesto de fuentes, registro global de ensayos y rúbrica económica..

Paquetes presupuestarios: WP0. Cierre: Cerrar sólo con trazabilidad completa o registrar la incompletitud que bloquea inferencia económica y promoción.

| Validador | Ejercicio y ataque | Criterio de aceptación | Acción si falla |
| --- | --- | --- | --- |
| V001 Reproducción del baseline | Verificar los archivos archivados frontier/run_04 y synthetic9/run_01 con sus verificadores existentes en procesos separados. Ataque: Cambiar un precio, un modelo o un recibo, incluso recalculando una cadena de hashes. | Cero discrepancias de hashes; reconstrucción y tolerancias numéricas declaradas satisfechas; conservar la evidencia de los 649 tests de CI como evidencia previa, no como aprobación del plan. | Bloquear la fase y conservar incidente y baseline intacto. |
| V002 Presupuesto de búsqueda global | Inventariar todos los experimentos económicos previos y registrar como máximo tres hipótesis nuevas y seis recetas completas. Ataque: Presentar la séptima receta, cambiar semillas después del resultado o llamar observaciones nuevas a repeticiones de estrés. | Cada variante, cambio de asignación, salida y combinación tiene identidad y presupuesto antes de medirse; historia incompleta impide afirmar corrección global de selección. | Rechazar el ensayo adicional; una ampliación necesita protocolo nuevo antes de acceder a un periodo nuevo. |
| V003 Integridad del presupuesto de I D | Validar programme/frontier/programme.json y enlazar las fases con sus paquetes existentes. Ataque: Duplicar un paquete, añadir gasto negativo o contar una asignación dos veces. | Suma exacta de 5,000,000 USD, gasto reportado 0 USD en el baseline y ninguna duplicación de presupuesto por repetir un WP entre fases; no hay autorización automática de gasto. | Bloquear obligaciones y corregir la conciliación presupuestaria. |
| V004 Separación de evidencia y autoridad | Intentar promover evidencias sintéticas, paper y comprobaciones del mismo autor como fills de bolsa o revisión externa. Ataque: Cambiar real_fills_present, external_review_completed o execution_allowed a true en un expediente sintético. | Cada origen conserva su etiqueta; un hash, un test o la presencia de un documento no autoriza gasto, ejecución ni acredita nivel 9. | Rechazar el expediente y registrar el intento de reclasificación. |

Cobertura existente parcial: `quant/tests/test_frontier_core.py::FrontierTests.test_rehashed_numeric_tamper_rejected`; `quant/tests/test_synthetic9.py::AdversarialReviewTests.test_rehashed_invalid_fill_is_detected_by_semantics`; `quant/tests/test_frontier_programme.py::ProgrammeTests.test_budget_exact_and_no_expenditure`; `quant/tests/test_frontier_programme.py::ProgrammeTests.test_budget_overrun_and_duplicate_packages_rejected`; `quant/tests/test_synthetic9.py::AdversarialReviewTests.test_relabeling_as_real_or_external_is_rejected`; `quant/tests/test_frontier_programme.py::ProgrammeTests.test_hashes_do_not_authorize_spending_or_promotion`.

### P01 Costes y contratos económicos por activo

Sustituir supuestos de ejecución por contratos explícitos sin alterar el banco sintético ya congelado. Entregable: Esquema de costes, comisiones nativas, reservas y gasto común para el siguiente experimento..

Paquetes presupuestarios: WP4, WP2. Cierre: Todos los costes necesarios son conocidos o la entrada queda bloqueada; los costes sintéticos nunca se etiquetan como observados.

| Validador | Ejercicio y ataque | Criterio de aceptación | Acción si falla |
| --- | --- | --- | --- |
| V005 Tarifa y función de liquidez | Versionar comisiones por instrumento, venue, tipo de orden, rol maker o taker y volumen elegible; reconciliar con el contrato de la cuenta. Ataque: Asignar maker a toda orden límite o deducir el tramo de volumen a partir del saldo de 20,000 USD. | Una orden límite negociable no se clasifica automáticamente como maker; una tarifa desconocida bloquea entradas; los 2 bps del banco sintético no se heredan como tarifa real. | Bloquear el activo y corregir el perfil de costes. |
| V006 Comisiones en unidades nativas | Reproducir compras y ventas cripto con CFEE o FEE, fees tardíos, parciales y una corrección de comisión. Ataque: Cobrar el fijo en cada parcial, perder una comisión publicada al cierre o borrar una cantidad cripto pequeña. | La comisión afecta la moneda o activo realmente recibido; cantidades y mínimos se toman del contrato del instrumento; la conciliación no convierte una fee cripto en un débito USD ficticio. | Mantener la comisión como pendiente y bloquear calibración o nuevas entradas hasta reconciliar. |
| V007 Patrimonio y gasto común | Recalcular efectivo más posiciones más derechos pendientes menos obligaciones, en una cuenta continua sin aportaciones ni retiros en el experimento. Ataque: Reiniciar capital por ventana, sumar 20,000 USD por activo o repartir el gasto común varias veces en la misma cuenta. | El gasto común aparece una sola vez y también en CASH; el coste variable se atribuye a órdenes; evaluar ventaja incremental y viabilidad global por separado, sin eliminar gastos para fabricar beneficio. | Invalidar la comparación económica y reconstruir toda la cuenta. |
| V008 Disponibilidad de efectivo e inventario | Probar órdenes simultáneas, ventas propuestas, efectivo no disponible por liquidación y fills anunciados aún no recibidos. Ataque: Usar los ingresos de una venta no confirmada o vender dos veces la misma cantidad. | Compras financiadas sólo con poder de compra confirmado conforme al tipo de cuenta; reserva intacta para fills tardíos; no doble venta ni posiciones cortas implícitas. | Rechazar la orden y exigir conciliación del estado. |

Cobertura existente parcial: `quant/tests/test_synthetic9.py::ExecutionLedgerTests.test_fixed_order_fee_is_paid_once_on_two_fills`; `quant/tests/test_synthetic9.py::ExecutionLedgerTests.test_single_smallest_crypto_unit_is_not_erased`; `quant/tests/test_frontier_core.py::FrontierTests.test_shared_overhead_same_for_cash_and_enter`; `quant/tests/test_synthetic9.py::CausalBankTests.test_cash_pays_all_seven_days_and_no_capital_reset`; `quant/tests/test_frontier_core.py::FrontierTests.test_unconfirmed_sale_does_not_fund_buy`; `quant/tests/test_synthetic9.py::ExecutionLedgerTests.test_pending_sell_reserves_inventory`; `quant/tests/test_synthetic9.py::ExecutionLedgerTests.test_cancel_ack_keeps_reserve_for_announced_late_fill`.

### P02 Ejecución por eventos y recuperación

Resolver el reintento horario que produjo retrasos y mantener el plazo original de cada campaña. Entregable: Máquina de estados de orden, reintentos acotados, recuperación y telemetría operacional..

Paquetes presupuestarios: WP2, WP3. Cierre: Cerrar con cero infracciones evitables dentro del sobre de ejecución registrado; los halts y escenarios fuera del sobre permanecen como riesgo no resuelto, nunca como cierres ficticios.

| Validador | Ejercicio y ataque | Criterio de aceptación | Acción si falla |
| --- | --- | --- | --- |
| V009 Ciclo de orden idempotente | Entregar ACK, fill parcial, petición de cancelación, cancel ACK, fill tardío, rechazo y duplicados en órdenes temporalmente válidos y adversos. Ataque: Reordenar recepción y ejecución, ejecutar tras una cancelación efectiva o repetir un client_order_id con parámetros distintos. | Cada fill afecta caja e inventario una vez; un duplicado idéntico es idempotente; uno conflictivo se rechaza; no se libera reserva anunciada antes de resolver el fill tardío. | Suspender nuevas órdenes y reconciliar antes de reanudar. |
| V010 Deadline y reintentos acotados | Reproducir las 16 campañas CORE tardías y añadir rechazos y parciales cerca del deadline con reloj por eventos. Ataque: Reintentar cada hora, ampliar el deadline al reiniciar o enviar compras cuando ya no hay ventana admisible de salida. | La apertura y deadline originales no se reinician; última orden empieza con margen para ACK, fill y reintentos según cuantiles de demora registrados; cero retrasos evitables si existe mercado y capacidad dentro del sobre declarado. | Bloquear nuevas entradas y conservar exposición, incumplimiento y siguiente acción operativa visible. |
| V011 Halts y ausencia de liquidez | Inyectar halt o desconexión que atraviese el deadline y un caso de más de 72 horas sin capacidad de cerrar. Ataque: Cerrar contablemente una posición sin fill o suponer una reanudación sin timestamp conocido. | Cero fills inventados; posición pendiente, incumplimiento y causa quedan registrados; pasar la prueba de detección no certifica que se haya respetado el plazo. | Declarar estado no liquidado, bloquear promoción y aplicar el runbook autorizado. |
| V012 Reinicio y pulso real | Reiniciar procesos con órdenes pendientes, interrumpir almacenamiento, desconectar datos y provocar el timeout del predictor legado. Ataque: Mostrar alive por un temporizador de interfaz o subir el timeout para ocultar un proceso bloqueado. | Reconstrucción desde recibos y broker; campañas intactas; indicador alive vinculado a eventos recibidos y estado de conciliación; la falta de predictor impide entradas y conserva la gestión determinista de posiciones conocidas. | Marcar degradación, impedir nuevas entradas y recuperar el estado; la causa del timeout local debe investigarse, no borrarse. |

Cobertura existente parcial: `quant/tests/test_synthetic9.py::ExecutionLedgerTests.test_duplicate_delivery_is_idempotent_and_conflict_rejected`; `quant/tests/test_synthetic9.py::ExecutionLedgerTests.test_cancel_ack_keeps_reserve_for_announced_late_fill`; `quant/tests/test_frontier_core.py::FrontierTests.test_campaign_deadline_cannot_be_reset_between_decisions`; `quant/tests/test_synthetic9.py::ExecutionLedgerTests.test_increasing_position_cannot_reset_original_deadline`; `quant/tests/test_frontier_core.py::FrontierTests.test_expired_halted_position_not_fictionally_closed`; `quant/tests/test_frontier_programme.py::ProgrammeTests.test_unknown_halt_end_does_not_invent_resume`; `quant/tests/test_synthetic9.py::ExecutionLedgerTests.test_impossible_exit_is_recorded_without_erasing_inventory`; `quant/tests/test_frontier_core.py::FrontierTests.test_journal_idempotent_and_stale_input_rejected`; `quant/tests/test_frontier_core.py::FrontierTests.test_unreconciled_campaign_replacement_blocked`.

### P03 Datos temporales y universo elegible

Garantizar que cada precio, señal, sesión y activo existía y era negociable en la fecha de decisión. Entregable: Contrato point in time de datos, acciones corporativas, calendario, capacidad y universo..

Paquetes presupuestarios: WP4, WP0, WP1. Cierre: Excluir o bloquear datos sin cobertura suficiente; ampliar activos analizados sólo cuando cumplan el contrato.

| Validador | Ejercicio y ataque | Criterio de aceptación | Acción si falla |
| --- | --- | --- | --- |
| V013 Calendario y acciones corporativas | Reproducir splits, dividendos, festivos, cierres anticipados, DST y negociación cripto continua con interrupciones explícitas. Ataque: Mezclar precios ajustados y dividendos duplicados o asumir sesión por ser lunes a viernes. | UTC para tiempo transcurrido y zona de la bolsa para sesión; cantidades, precios y derechos consistentes; el calendario sintético UTC no se reutiliza como calendario NYSE o Nasdaq certificado. | Bloquear el activo o periodo no cubierto, manteniendo la evidencia original. |
| V014 Disponibilidad y caducidad | Modificar datos futuros, adelantar recepción, usar cotización de 15.001 segundos y reestampar un modelo con labels antiguos. Ataque: Usar un cierre de vela todavía no terminado, un suavizador que vea el futuro o una fecha nueva para ocultar datos viejos. | Datos conocidos al decidir; BBO y estado cumplen el máximo vigente de 15 segundos; modelo y últimas etiquetas cumplen 168 horas del contrato actual; labels y entrenamiento preceden a la consulta. | Rechazar la inferencia y registrar el motivo de abstención. |
| V015 Universo y concentración | Seleccionar el universo elegible con información de esa fecha, capacidad nativa y costes; contrastar factores de posiciones existentes y propuestas. Ataque: Añadir sólo ganadores actuales a toda la historia o declarar más tamaño ejecutable que el observado o supuesto con su etiqueta. | Sin supervivencia retrospectiva ni liquidez inferida de datos futuros; no aumentar exposición por ampliar símbolos; estado incluye toda la cartera y respeta caps de trabajo y factores. | Excluir el activo; bloquear la cuenta si queda inventario fuera del modelo. |
| V016 Procedencia y permisos de fuentes | Verificar origen, derechos de uso, granularidad, timestamps y cobertura de barras, BBO, subastas y opciones. Ataque: Fabricar NOII desde una vela o declarar licencia de datos por disponer de una página web. | Datos de subasta y opciones tienen recibos propios; OHLCV no se presenta como L2, L3, cola o desequilibrio real; fuente sintética nunca cambia a observada. | Bloquear ese componente o cerrar su rama como no evaluable; no sustituirlo con una proxy sin protocolo nuevo. |

Cobertura existente parcial: `quant/tests/test_frontier_programme.py::ProgrammeTests.test_early_close_normalized_without_weekday_guess`; `quant/tests/test_frontier_core.py::FrontierTests.test_calendar_support_is_not_fabricated`; `quant/tests/test_frontier_core.py::FrontierTests.test_stale_or_future_quotes_blocked`; `quant/tests/test_frontier_core.py::FrontierTests.test_new_fit_timestamp_cannot_hide_old_labels`; `quant/tests/test_synthetic9.py::CausalBankTests.test_future_current_window_cannot_change_first_decision`; `quant/tests/test_frontier_core.py::FrontierTests.test_incomplete_inventory_blocks`; `quant/tests/test_frontier_core.py::FrontierTests.test_quote_liquidity_not_invented`; `quant/tests/test_frontier_core.py::FrontierTests.test_grid_budget_blocks_without_partial_search`; `quant/tests/test_frontier_core.py::FrontierTests.test_synthetic_cannot_be_observed`; `quant/tests/test_synthetic9.py::AdversarialReviewTests.test_observed_fill_calibrator_refuses_synthetic_schema`.

### P04 Pronóstico condicional por horizonte

Definir targets, modelos y regularización antes de medir recetas económicas nuevas. Entregable: Pronósticos separados por tramo de sesión y horizonte, con incertidumbre y calibración temporal..

Paquetes presupuestarios: WP1. Cierre: Congelar modelo, variables, regla de refit y validación; no elegir especificaciones con el periodo final.

| Validador | Ejercicio y ataque | Criterio de aceptación | Acción si falla |
| --- | --- | --- | --- |
| V017 Descomposición nocturna e intradiaria | Reconstruir retornos close a open y open a close de equity con ajustes consistentes; comparar su suma en logaritmos con close a close. Ataque: Usar la apertura de mañana al decidir hoy o mezclar fechas locales con días UTC. | Identidad numérica satisfecha y features calculadas sólo con tramos terminados; cripto no recibe un gap bursátil ficticio. | Invalidar features y repetir ingeniería antes de cualquier medición económica. |
| V018 Distribución y etiquetas a 24 48 y 72 horas | Construir labels por horizonte y desenlaces de stop, objetivo y expiración manteniendo el orden intrabar no identificado. Ataque: Elegir target primero en toda vela ambigua o añadir duplicados como más soporte estadístico. | Ventanas maduradas y purgadas; límites de identificación conservados para OHLC ambiguo; réplicas sintéticas o bootstrap no cuentan como casos originales. | Rechazar el panel y conservar la incertidumbre no identificada. |
| V019 Calibración y modelo de referencia | Comparar un modelo condicional regularizado con referencia uniforme o simple, con el mismo panel y corte temporal. Ataque: Aceptar mejor score promedio ocultando falta de soporte por régimen o datos futuros. | Métrica y tolerancia de calibración registradas antes de medir; soporte efectivo insuficiente o deriva causa abstención; Brier de identificación no se interpreta como intervalo de confianza muestral. | Rechazar el modelo o mantener la referencia; no promover por complejidad. |
| V020 MACD y osciladores como contexto causal | Usar MACD12 30 9, RSI y estocástico existentes; evaluar información incremental frente a precio, volatilidad y horario. Ataque: Reutilizar la familia MACD ya negativa como descubrimiento nuevo o suavizar con valores futuros. | Calentamiento y disponibilidad válidos; transformaciones del mismo precio no se cuentan como confirmaciones independientes; una anticipación de histograma no se etiqueta como giro futuro conocido. | Retirar la variable si no aporta valor incremental; conservar registro de la familia cerrada. |

Cobertura existente parcial: `quant/tests/test_frontier_core.py::FrontierTests.test_barrier_collision_partially_identified`; `quant/tests/test_frontier_core.py::FrontierTests.test_bootstrap_replicates_not_new_original_cases`; `quant/tests/test_frontier_evaluation.py::EvaluationTests.test_evaluation_purges_unmatured_labels`; `quant/tests/test_frontier_core.py::FrontierTests.test_regime_drift_abstains`; `quant/tests/test_frontier_evaluation.py::EvaluationTests.test_identification_score_bounds`; `quant/tests/test_frontier_features.py::OscillatorContextTests.test_unknown_future_prices_do_not_change_context`; `quant/tests/test_frontier_features.py::OscillatorContextTests.test_existing_indicators_are_features_not_authority`.

### P05 Asignación de capital y congelación de recetas

Convertir pronósticos en posiciones costeadas sobre la cartera completa antes de comparar estrategias. Entregable: Asignador común con incertidumbre, costes, correlación, bandas de no operar y recetas finales congeladas..

Paquetes presupuestarios: WP2, WP1. Cierre: Ningún ensayo económico nuevo empieza hasta que las seis configuraciones completas y comparadores estén registrados.

| Validador | Ejercicio y ataque | Criterio de aceptación | Acción si falla |
| --- | --- | --- | --- |
| V021 Objetivo y unidades de la cartera | Revalorar la decisión con otra implementación a partir de efectivo, inventario, escenarios y costes. Ataque: Sumar bps y USD sin notional, confundir riesgo con error de la media o declarar óptimo global al enumerar una malla local. | Mismos dólares, cantidades nativas y base temporal; aproximación de log crecimiento identificada como tal; covarianza de retornos y de incertidumbre de la media diferenciadas; límites financieros satisfechos tras redondear. | Rechazar la propuesta y revisar el contrato matemático. |
| V022 Rotación y bandas de no operar | Comparar mantener, operar parcialmente, aumentar, reducir y cerrar con costes de cambio y decaimiento de la señal. Ataque: Operar por cambios diminutos del score o quitar costes fijos después de ver una pérdida. | La operación aporta valor incremental neto frente al estado actual dentro del margen de incertidumbre; gasto común y viabilidad global permanecen en la cuenta; esperar es una acción admisible. | Abstenerse o conservar inventario dentro de sus límites; el programa se detiene si su economía global no es viable. |
| V023 Lotes y financiación parcial | Redondear asignaciones a lotes nativos y probar subconjuntos adversos de fills. Ataque: Certificar una reducción completa cuando sólo llenó una pata o adoptar instrumentos no lineales sin valoración. | Ninguna compra depende de venta aún no confirmada; posiciones, caja, concentración y tamaño ejecutable vuelven a verificarse después del redondeo. | Bloquear el incremento de riesgo y conservar exposición real. |
| V024 Límites y escenarios sin señal | Probar mundo sin ventaja, señales contradictorias, choque de correlación, pérdidas diarias y drawdown. Ataque: Aumentar apalancamiento o límites para aprobar la rentabilidad o declarar que una reducción aún fuera de caps ya es segura. | Preservar límites del baseline: pérdida diaria 2%, drawdown 10%, bruto 60%, nombre 20%, factor 30%, cola 2% y estrés 5%, con sus bases explícitas; pausas impiden compras y permiten gestionar reducción de riesgo. | Bloquear entradas y activar gestión de riesgo conforme al estado conciliado. |

Cobertura existente parcial: `quant/tests/test_frontier_core.py::FrontierTests.test_separate_decimal_repricing_matches`; `quant/tests/test_frontier_core.py::FrontierTests.test_raw_dollar_paths_cannot_be_relative_returns`; `quant/tests/test_frontier_core.py::FrontierTests.test_all_costs_can_destroy_edge`; `quant/tests/test_frontier_core.py::FrontierTests.test_fixed_overhead_can_destroy_total_edge`; `quant/tests/test_frontier_core.py::FrontierTests.test_unconfirmed_sale_does_not_fund_buy`; `quant/tests/test_frontier_core.py::FrontierTests.test_noninteger_qty_and_nonlinear_instrument_rejected`; `quant/tests/test_frontier_core.py::FrontierTests.test_false_risk_reduction_exception_rejected`; `quant/tests/test_frontier_core.py::FrontierTests.test_risk_pause_forbids_new_buys_not_exits`; `quant/tests/test_frontier_core.py::FrontierTests.test_existing_exposure_can_be_reduced`.

### P06 Hipótesis H1 continuación condicionada por horario

Comprobar si distinguir el tramo donde se genera retorno mejora la continuación ya estudiada. Entregable: Ablación H1 con mismas fuentes, costes completos, controles y cuentas continuas..

Paquetes presupuestarios: WP1, WP3. Cierre: Cerrar con candidato retenido o rechazado; el rechazo no se convierte en aprobación y permite estudiar la siguiente hipótesis registrada.

| Validador | Ejercicio y ataque | Criterio de aceptación | Acción si falla |
| --- | --- | --- | --- |
| V025 Congelación antes de medir H1 | Sellar código, entrenamiento, refit, reglas de entrada y salida, asignador, riesgos, costes y ventanas de H1. Ataque: Cambiar la hora de entrada, filtros o semillas después de conocer el PnL. | Identidad completa y registro anterior al acceso al periodo de evaluación; datos finales quedan separados del desarrollo. | Invalidar esa evaluación; cualquier propuesta distinta consume una receta y otro periodo nuevo. |
| V026 Ablación económica de horario | Comparar H1 con continuación original, CASH y referencia de mercado con exposición y riesgo emparejados. Ataque: Ganar sólo porque se duplicó el capital o se redujo a la mitad el riesgo frente al control. | Reportar PnL neto y log crecimiento de toda la cuenta, drawdown, rotación y contribuciones nocturnas e intradiarias; no atribuir mejora al predictor si cambió también la exposición. | Rechazar la atribución o la receta según la regla registrada. |
| V027 Incertidumbre y concentración de H1 | Evaluar dependencia temporal, sensibilidad a bloques registrados, regímenes y concentración de PnL. Ataque: Presentar barras correlacionadas como trades independientes o elegir sólo meses ganadores. | Se reporta soporte efectivo y selección global; quitar el mayor ganador es diagnóstico de concentración, no un filtro retrospectivo para borrar trades; no hay promoción por un promedio favorable aislado. | Mantener resultado no concluyente o rechazar el candidato. |
| V028 Decisión de conservar o descartar H1 | Aplicar los endpoints registrados a todas las variantes H1, incluyendo las negativas. Ataque: Reabrir un rechazo cambiando el nombre de la estrategia. | Veredicto RETAIN_FOR_FORWARD o REJECT registrado una sola vez; variantes rechazadas no entran a la cartera; no se declara ventaja real desde histórico reutilizado. | Cerrar la familia sin promoción y preservar resultados. |

Cobertura existente parcial: requiere implementación de validadores nuevos..

### P07 Hipótesis H2 gaps y aceptación del precio

Distinguir continuación informativa de rechazo del gap con información disponible al decidir. Entregable: Ablación H2 y, sólo con datos adecuados, variante con flujo de subasta auténtico..

Paquetes presupuestarios: WP1, WP4, WP3. Cierre: Si falta subasta auténtica, cerrar esa rama como no evaluable; continuar sólo con candidatos evaluables ya registrados sin presentar una proxy como la misma receta.

| Validador | Ejercicio y ataque | Criterio de aceptación | Acción si falla |
| --- | --- | --- | --- |
| V029 Gap y confirmación causal | Normalizar apertura respecto al cierre previo y volatilidad; evaluar aceptación o rechazo con barras ya cerradas y contexto sectorial. Ataque: Usar el high del día completo o confirmar con una vela aún abierta. | No se usa el máximo o cierre posterior de la ventana para confirmar una entrada; cripto conserva su propia definición de evento y no hereda un overnight equity. | Rechazar señal y panel afectado. |
| V030 Flujo auténtico de subasta | Enlazar snapshots NYSE o Nasdaq con símbolo, subasta, tiempo de mercado, recepción y derechos de uso. Ataque: Inferir NOII real desde volumen OHLC o usar información final de la subasta en una decisión anterior. | El dato existía antes de decidir y pertenece a la sesión e instrumento correctos; una señal de subasta no implica garantía de fill. | Bloquear la variante y registrar falta de evidencia. |
| V031 Contexto de volatilidad de Cboe | Versionar plazo, unidad, recepción y origen de volatilidad implícita y su estructura temporal. Ataque: Tratar VIX a 30 días como pronóstico direccional de 72 horas o confundir sigma anual con retorno diario. | Volatilidad implícita se usa como contexto de riesgo, no como probabilidad física de subida; datos caducados o inexistentes no se rellenan silenciosamente; opciones siguen sin ejecución en el motor spot. | Abstenerse del componente dependiente o rechazar el input. |
| V032 Valor incremental de H2 | Comparar la receta base registrada y su confirmación por flujo con mismas entradas elegibles y costes completos. Ataque: Descartar del denominador todos los gaps fallidos o añadir otro filtro tras ver sus pérdidas. | Atribución separada cuando cambian filtros, datos o exposición; registrar también rechazo de gaps y oportunidades perdidas; no promover por seleccionar retrospectivamente sólo gaps continuados. | Rechazar la interpretación o la receta y consumir el ensayo correspondiente. |

Cobertura existente parcial: `quant/tests/test_synthetic9.py::CausalBankTests.test_opening_quote_includes_current_known_gap`; `quant/tests/test_synthetic9.py::CausalBankTests.test_future_current_window_cannot_change_first_decision`; `quant/tests/test_frontier_programme.py::ProgrammeTests.test_derivatives_and_future_records_rejected`.

### P08 Hipótesis H3 salida por valor de continuación

Contrastar salida fija con una decisión de mantener, reducir o cerrar basada en información actual. Entregable: Control de continuación finito con deadline inmutable y comparación de salidas..

Paquetes presupuestarios: WP2, WP3. Cierre: La salida se conserva sólo si mejora el resultado bajo el control de riesgo registrado; ninguna nueva combinación fuera de las seis recetas queda autorizada por esta fase.

| Validador | Ejercicio y ataque | Criterio de aceptación | Acción si falla |
| --- | --- | --- | --- |
| V033 Continuación frente a liquidación | Comparar valor esperado neto de mantener con liquidación actual, riesgo de gap, coste de salida y tiempo restante. Ataque: Optimizar la salida leyendo el mejor precio posterior o renombrar un trailing arbitrario como óptimo. | Sólo datos conocidos; una llamada cambia la acción actual sin fingir Bellman global resuelto; el target aprendido no usa el máximo futuro de la posición. | Rechazar la política y conservar el control fijo. |
| V034 Protección y plazo original | Probar cambios de volatilidad, splits, parciales, reinicios y propuestas de aumentar una posición existente. Ataque: Reiniciar la apertura al reentrar sin reconciliar o alejar el stop sólo para evitar reconocer una pérdida. | No se amplía la campaña para esconder pérdidas; el límite de pérdida registrado y el deadline original se mantienen; se preserva el máximo de 72 horas transcurridas como restricción, con incumplimiento explícito si no se puede ejecutar. | Bloquear la propuesta y gestionar el inventario observado. |
| V035 Presupuesto temporal de la salida | Evaluar temporización de órdenes con cuantiles registrados de ACK, fill, cancelación y reintento, incluyendo costes de ejecución urgente. Ataque: Usar un p99 sintético como SLA observado o reintentar después del deadline sin registrar incumplimiento. | Cero retrasos evitables dentro del sobre; las colas no calibradas se declaran como incertidumbre; fuera del sobre se conserva la excepción y el riesgo, sin afirmar plazo garantizado. | Invalidar la certificación operacional y bloquear nuevas entradas. |
| V036 Ablación de salida H3 | Comparar salidas sobre el mismo flujo de entradas, cantidades iniciales y reglas de capital de la receta registrada. Ataque: Cambiar entrada y salida y adjudicar todo el PnL a la salida. | Costes, riesgo, reutilización de capital y reentradas explícitos; cualquier diferencia conjunta se atribuye a la política completa; no se incorpora un ensamblado adicional fuera del presupuesto. | Rechazar la atribución y evaluar la configuración completa como ensayo separado si queda presupuesto. |

Cobertura existente parcial: `quant/tests/test_frontier_core.py::FrontierTests.test_hold_on_positive_paths`; `quant/tests/test_frontier_core.py::FrontierTests.test_exit_on_losing_paths`; `quant/tests/test_frontier_core.py::FrontierTests.test_expired_position_exit_and_no_deadline_reset`; `quant/tests/test_frontier_core.py::FrontierTests.test_unreconciled_campaign_replacement_blocked`; `quant/tests/test_synthetic9.py::ExecutionLedgerTests.test_impossible_exit_is_recorded_without_erasing_inventory`.

### P09 Integración adversarial y rendimiento

Demostrar que datos, modelos, asignación y ejecución conservan los contratos al funcionar juntos. Entregable: Matriz de fallos ampliada, recorrido completo, comprobación numérica separada y benchmark del perfil registrado..

Paquetes presupuestarios: WP3. Cierre: Cero fallo crítico sin resolver; un test crítico omitido, un estado desconocido o una evidencia requerida ausente bloquean la siguiente fase.

| Validador | Ejercicio y ataque | Criterio de aceptación | Acción si falla |
| --- | --- | --- | --- |
| V037 Ataques de integración | Ampliar los 18 casos existentes con CFEE tardío, cambio de tarifa, calendario incorrecto, almacenamiento lleno, caída de proceso y adversidad combinada. Ataque: Combinar fill tardío con reinicio y comisión retrasada en vez de probarlos sólo de forma aislada. | Cada fallo produce el estado previsto; no duplicación, pérdidas de inventario, fill ficticio ni reanudación automática sin conciliación. | Conservar incidente y bloquear release; corregir y repetir sólo los controles afectados y la regresión necesaria. |
| V038 Comprobación separada y hashes | Reproducir caja, inventario, propuestas y agregados con implementaciones separadas y fuentes versionadas. Ataque: Recalcular hashes después de alterar PnL o reemplazar el autor por un nombre de auditor no verificado. | Tolerancia numérica declarada; para observaciones, saldos cuantizados en la unidad oficial y cero diferencia no explicada; hashes no sustituyen autenticidad del broker; revisión del mismo autor no cuenta como externa. | Rechazar expediente y conservar diferencias. |
| V039 Pulso y control de autoridad | Ejecutar recorrido API de datos a decisión a orden simulada a fill a fee a patrimonio, con LLM desconectado y credenciales ausentes. Ataque: Un texto del modelo cambia execution_allowed o la UI muestra verde con datos caducados. | Alive deriva de recibos y edades reales; sin autoridad de ejecución no se emiten órdenes; el LLM opcional usa una API central y no puede modificar límites, aprobarse ni detener la gestión determinista de riesgos. | Bloquear entradas, señalar degradación y revisar el control de permisos. |
| V040 Benchmark reproducible del perfil operativo | Medir al menos 200 decisiones del perfil fijado antes de medir: cuatro activos, hasta 40 análogos, hasta 81 acciones y hardware declarado. Ataque: Mostrar sólo la mejor latencia, usar dos snapshots como p99 robusto o ampliar límites tras un timeout sin registrar la modificación. | Objetivo de ingeniería propuesto: p95 de cálculo local <=2 segundos y p99 <=5 segundos; publicar máximo, memoria, fallos y entorno; el cálculo no rebasa 30,000,000 unidades de trabajo ni la vigencia del input. No es SLA del broker. | Reducir cómputo o corregir el cuello de botella y volver a registrar el perfil; nunca saltarse validaciones para acelerar. |

Cobertura existente parcial: `quant/tests/test_synthetic9.py::ExecutionLedgerTests.test_fault_matrix_checks_both_implementations`; `quant/tests/test_synthetic9.py::AdversarialReviewTests.test_forged_final_cash_is_detected`; `quant/tests/test_synthetic9.py::AdversarialReviewTests.test_reviewer_imports_neither_simulator_nor_ledger`; `quant/tests/test_frontier_core.py::FrontierTests.test_rehashed_numeric_tamper_rejected`.

### P10 Fills observados y validación prospectiva

Separar calibración de ejecución observada y evaluación económica futura con procedimiento congelado. Entregable: A datos originales reconciliados y perfil de costes; B periodo futuro con candidato final y controles..

Paquetes presupuestarios: WP4, WP5. Cierre: A precede a B; datos paper sólo acreditan lo que su simulación observa. Un microensayo live necesita autorización específica y límites, sin implicar producción ni nivel 9.

| Validador | Ejercicio y ataque | Criterio de aceptación | Acción si falla |
| --- | --- | --- | --- |
| V041 Trazabilidad de fills observados | P10A: enlazar decisión, BBO causal, orden, ACK, actividad FILL, CFEE o FEE y estado de cuenta original. Ataque: Presentar fill paper como ejecución de bolsa, omitir una página de actividades o usar una cotización posterior para medir shortfall. | IDs, cuenta, moneda, cantidades, timestamps y fees completos; separar paper de live; autenticar procedencia mediante acceso o contraste independiente apropiado, no sólo hashes. | Bloquear calibración observada y mantener la evidencia incompleta privada. |
| V042 Calibración sin reutilizar la validación | Estimar costes por activo, tipo de orden, liquidez y régimen en P10A; congelar el estimador antes de P10B. Ataque: Calibrar el q95 con los mismos fills que luego se presentan como validación nueva. | Reportar soporte, incertidumbre, fill ratio, latencia y shortfall; no sustituir fees aún no publicadas por cero; periodos insuficientes permanecen no concluyentes. | Extender calibración dentro del presupuesto o suspender; comenzar otro periodo de validación sólo después de congelar. |
| V043 Protocolo de evaluación futura | P10B: registrar candidato, coste, universo, reglas de refit, periodo, métricas y parada antes de la primera decisión futura. Ataque: Reutilizar 2025 o un periodo ya inspeccionado como holdout virgen, detener al primer beneficio o cambiar receta a mitad del periodo. | Cuenta continua con capital de referencia 20,000 USD; ledger prospectivo inmutable; reentrenamiento sólo conforme a regla causal registrada; no elegir ganadores mediante consultas intermedias al endpoint final. | Invalidar la confirmación y conservar los resultados como exploración. |
| V044 Aceptación económica y riesgo comparable | Calcular log crecimiento neto y diferencias pareadas contra CASH, baseline congelado y referencia de mercado con riesgo y exposición emparejados. Ataque: Aceptar por un backtest positivo, por ratio de acierto, por repetir seeds sintéticas o por reducir artificialmente el coste para superar el umbral. | Umbral propuesto: crecimiento neto positivo nominal y bajo estrés registrado; límite inferior al 95% de la ventaja sobre CASH y baseline >0 con dependencia y selección global tratadas según método congelado; riesgo dentro de caps. Periodo, soporte, método, bloques y costes deben estar fijados antes de evaluar o el resultado queda BLOCKED. | Rechazar o declarar no concluyente; ninguna nota 9 ni promoción se deriva de un FAIL o de falta de soporte. |
| V045 Riesgo operativo durante observación | Monitorizar conciliación, frescura, drawdown, pérdida diaria, rechazos, plazos, límites de riesgo y costes realizados durante todo el periodo. Ataque: Continuar una prueba live sin poder reconstruir inventario o esconder un incidente para conservar la curva. | Incumplimiento crítico suspende entradas; los cortes por riesgo se mantienen en el PnL y en la selección de muestra; no borrar días de caída ni inventar cierres en una interrupción. | Pasar al estado degradado autorizado, gestionar posiciones conocidas y conservar el incidente. |

Cobertura existente parcial: requiere implementación de validadores nuevos..

### P11 Revisión externa y liberación controlada

Obtener revisión ajena al desarrollador y decidir sobre una versión y límites concretos. Entregable: Informe externo, resolución de hallazgos, autorización de versión y procedimiento de reversión..

Paquetes presupuestarios: WP5, WP0. Cierre: Sólo una autorización real, vigente y acotada puede cambiar la autoridad operacional; la documentación del plan no la crea.

| Validador | Ejercicio y ataque | Criterio de aceptación | Acción si falla |
| --- | --- | --- | --- |
| V046 Revisión externa auténtica | Entregar fuentes, manifiestos, protocolos, cuentas, fallos y datos privados por un canal autorizado al revisor independiente. Ataque: Firmar automáticamente una auditoría en nombre de un tercero o sustituirla por un workflow verde. | Identidad, independencia, alcance, commit, método y conclusiones verificables; hallazgos críticos resueltos; la reconstrucción Decimal del autor conserva su alcance de revisión propia. | Mantener G5 y la promoción bloqueados. |
| V047 Permiso de ejecución con alcance | Comprobar autorización para cuenta, entorno, instrumentos, versión, límites monetarios y vigencia concretos. Ataque: Usar una clave live donde se autorizó paper o promover porque existe un archivo llamado approved. | Permisos mínimos y autorización auténtica vigente; reutilizar autorización existente cuando cubra la operación; cambios fuera de su cuenta, entorno, versión o límites requieren resolver ese alcance antes de ejecutar; un microensayo no amplía por sí solo permiso de producción. | Rechazar ejecución y mantener el modo de investigación. |
| V048 Ensayo de reversión | Simular fallo después de una liberación controlada con posiciones y órdenes pendientes. Ataque: Hacer rollback borrando el diario o tratando la ausencia de señales como ausencia de posiciones. | Detener nuevas entradas y conservar gestión autorizada de posiciones; reconstrucción y reversión sin órdenes duplicadas ni reinicio de campaña; no activar una estrategia anterior económicamente rechazada. | Abortar liberación y recuperar con el estado real conciliado. |
| V049 Vigilancia de degradación | Comparar costes y resultados realizados, calibración y régimen con los límites de deriva y presupuesto registrados. Ataque: Prometer autoaprendizaje continuo o mantener activo un modelo caducado sin mecanismo comprobado. | Alertas medibles y decisiones de pausa; sólo refit causal autorizado, sin autoaprobación ni cambio persistente de reglas desde un LLM; el deterioro de alpha puede retirar la estrategia. | Pausar entradas y abrir investigación versionada; no reiniciar el periodo adverso. |

Cobertura existente parcial: `quant/tests/test_frontier_core.py::FrontierTests.test_journal_tamper_detected`; `quant/tests/test_frontier_core.py::FrontierTests.test_unreconciled_campaign_replacement_blocked`; `quant/tests/test_frontier_core.py::FrontierTests.test_regime_drift_abstains`; `quant/tests/test_frontier_core.py::FrontierTests.test_new_fit_timestamp_cannot_hide_old_labels`.

## Criterio económico de aceptación

La cuenta se evalúa con patrimonio neto completo y crecimiento compuesto: `g_t = log(E_t / E_(t-1))` cuando no existen flujos externos. Si aparecen, deben conciliarse por timestamp antes de atribuir rendimiento. El gasto común se registra una vez y se paga también en CASH; la ventaja incremental de operar y la viabilidad económica de toda la cuenta son preguntas distintas.

La aceptación propuesta exige crecimiento neto positivo nominal y bajo el estrés registrado, y un límite inferior al 95% positivo de la diferencia de log crecimiento frente a CASH y al baseline, con dependencia temporal y búsqueda global tratadas por el método congelado. La referencia de mercado requiere riesgo y exposición comparables. Duración, soporte mínimo, bloques, corrección de selección y regla de parada quedan fijados antes del periodo; si no están definidos o falta soporte, el resultado es no concluyente o bloqueado.

Los límites de riesgo actuales son parámetros de ingeniería: pérdida diaria 2%, drawdown 10%, bruto 60%, nombre 20%, factor 30%, cola 2% y estrés 5%. Sus bases y tiempos de referencia deben ser explícitos. No constituyen garantías de pérdida máxima ante gaps o halts. La cota de 72 horas se conserva como deadline transcurrido, sin reiniciar campañas.

## Contratos matemáticos de las mejoras

El asignador propuesto aproxima crecimiento logarítmico con media prevista, covarianza de retornos, coste de cambiar posiciones y penalización por incertidumbre de la media:

$$
\max_{w\in\mathcal W_t}\left[\hat\mu_t^\top w-\frac12w^\top\hat\Sigma_t w-C_t(w-w_{t-1})-\rho\sqrt{w^\top\Omega_{\mu,t}w}\right]
$$

Todos los términos tienen la misma base temporal y se expresan como fracción del patrimonio; el coste USD se divide entre ese patrimonio. El gasto común se paga una sola vez en la cuenta y se conserva en el criterio de viabilidad global. Los retornos previstos a 24, 48 y 72 horas no se suman como beneficios independientes porque las ventanas se solapan. La solución continua vuelve a verificarse tras redondear lotes y considerar parciales.

La salida reserva tiempo para el ciclo completo de ejecución:

$$
\tau_{send}\leq\min(\tau_{deadline},\tau_{opened}+72h)-Q_{0.99}(T_{ack}+T_{fill}+T_{retry}\mid\mathcal C)-\delta
$$

El cuantil corresponde a la demora total bajo condiciones registradas, no a una suma automática de cuantiles marginales. El margen y el sobre de condiciones se fijan antes de medir. Sin observaciones suficientes, la demora sigue siendo un supuesto; en un halt no se garantiza cierre. La comisión cripto se descuenta del activo o moneda recibido y su publicación tardía debe conciliarse sin duplicar el cobro.

## Evidencia que debe producir cada fase

Cada recibo enlaza fase, hash de este plan, commit, manifiesto de datos, modelo cuando corresponda, configuración, universo, costes, origen y tiempos de mercado y recepción. Incluye valores observados de cada validador, umbrales, entorno, hardware del benchmark, incidentes, exclusiones y ubicación de evidencia. Para aprobación externa o ejecución se añade identidad y alcance verificables. Un campo requerido ausente bloquea el recibo.

Caja e inventario se recalculan con aritmética separada. Para datos observados se cuantiza con la unidad oficial del activo o moneda y toda diferencia debe quedar explicada por fills, fees o derechos pendientes. Las tolerancias de coma flotante del simulador no autorizan pérdidas de unidades ni saldos sin conciliar.

Las actividades, credenciales y estados de cuenta originales permanecen privados. En GitHub se guardan código, protocolos, métricas no sensibles y manifiestos adecuados. Un hash demuestra integridad local; no autentica por sí solo un proveedor, reloj, titular o auditor.

## Modos operacionales y permisos

| Modo | Alcance y condición |
| --- | --- |
| RESEARCH_OFFLINE | Código, simulación, histórico y replay sin órdenes de broker. |
| OBSERVED_READ_ONLY | Actividades y estados existentes, con permisos adecuados; leer no envía órdenes. |
| PAPER_EXPERIMENT | Sólo tras configuración y autorización del ensayo concreto; sus fills siguen siendo simulados. |
| LIVE_CALIBRATION_EXPERIMENT | Si faltan fills live existentes, ensayo pequeño sólo con autorización específica, presupuesto de pérdida, límites y runbook; no requiere fingir aprobación de producción. |
| LIVE_PRODUCTION | Sólo después de revisión externa, aceptación económica y autorización de cuenta, versión y límites. |

P10 evita una dependencia circular: puede usar fills live existentes mediante lectura; si no existen suficientes, un microensayo de calibración necesita autorización específica y límites de pérdida, antes de afirmar validación económica real. Ese permiso experimental no equivale a producción. Después se congelan costes y procedimiento y comienza un periodo distinto de evaluación futura.

Las decisiones de autorización, gasto, revisión externa y nivel 9 permanecen pendientes. No se programan tareas, despliegues, órdenes ni pagos por generar este plan.

Una autorización ya otorgada se conserva cuando sigue vigente y cubre la acción, cuenta, entorno y límites concretos. Se resuelve únicamente el alcance material no cubierto, sin pedir confirmaciones redundantes.

## Correspondencia con los hitos del programa

| Hito existente | Fases que aportan evidencia |
| --- | --- |
| G0 | P00, P01, P03 |
| G1 | P03, P04 |
| G2 | P02, P05, P08, P09 |
| G3 | P01, P02, P03, P09, P10A |
| G4 | P06, P07, P08, P10B |
| G5 | P11 |

Las fases aportan partes de la evidencia de cada hito. El comando `audit-gate` existente verifica presencia e integridad de archivos; no autentica aprobaciones de dependencias ni aprueba ciencia, presupuesto o ejecución. Un hito completo necesita revisar además sus requisitos originales en programme.json.

## Comandos existentes que pueden reutilizarse

Desde el repositorio clonado, con las dependencias de `quant/requirements-tested.txt` instaladas. Las rutas de salida deben ser nuevas; una salida existente se rechaza. Estos comandos verifican el baseline y no implementan las fases propuestas.

C01 Validar presupuesto sin autorizar gasto.

```sh
PYTHONPATH=quant python3 -B -m harpoon_quant.frontier_core validate-programme --programme programme/frontier/programme.json --output /tmp/harpoon_plan_budget_check.json
```

C02 Regresión del núcleo frontier.

```sh
PYTHONPATH=quant python3 -B -m unittest discover -s quant/tests -p 'test_frontier*.py'
```

C03 Regresión del banco sintético.

```sh
PYTHONPATH=quant python3 -B -m unittest discover -s quant/tests -p 'test_synthetic9*.py'
```

C04 Verificar artefactos frontier archivados.

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONPATH=quant python3 -B tools/frontier_verify.py evidence/frontier/run_04 --repeats 3 --output /tmp/harpoon_plan_frontier_check.json
```

C05 Verificar el paquete sintético con proceso separado.

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONPATH=quant python3 -B tools/verify_synthetic9.py evidence/synthetic9/run_01 --output /tmp/harpoon_plan_synthetic_check.json
```

C06 Suite completa antes de cambios de código relevantes.

```sh
PYTHONPATH=quant python3 -B -m unittest discover -s quant/tests
```

C06 corresponde a regresión de código. En esta entrega documental no se reejecuta como si hubiera un motor nuevo: la evidencia previa de 649 tests sigue identificada por su commit. Los datos reales de cuenta no se recogen con estos comandos. El colector read only existente requiere credenciales y permisos adecuados y no entrega por sí solo BBO causal ni calibración completa.

## Fuentes y documentos base

- [Framework de I D de 5 millones](../frontier/FRAMEWORK_RD_5M.md).
- [Banco sintético y sus resultados](../../SYNTHETIC9_BANK.md).
- [QA previa y timeout local conservado](../../evidence/synthetic9/qa/qa.json).
- [Preparación actual y puertas pendientes](../../evidence/synthetic9/run_01/readiness.json).
- [Familia de continuación y reversión ya evaluada](../../RESULTADO_RESEARCH9.md).
- [Familia MACD ya evaluada](../../MACD30_RESULTADO.md).
- [Tarifas cripto y unidades de comisión](https://docs.alpaca.markets/us/docs/crypto-fees).
- [Subastas NYSE](https://www.nyse.com/trade/auctions).
- [Cruces y NOII Nasdaq](https://nasdaqtrader.com/Trader.aspx?id=OpenClose).
- [Estructura temporal de volatilidad Cboe](https://www.cboe.com/tradable-products/vix/term-structure).
- [Control de cartera multiperiodo](https://stanford.edu/~boyd/papers/cvx_portfolio.html).
- [Retornos nocturnos e intradiarios](https://personal.lse.ac.uk/polk/research/TugOfWar.pdf).
- [Selección y Sharpe deflactado](https://doi.org/10.3905/jpm.2014.40.5.094).

El tarifario público de Alpaca distingue rol de liquidez y volumen de los últimos 30 días, y las fees cripto afectan al activo o moneda recibido. El perfil particular de la cuenta debe verificarse en P01. La documentación de las bolsas y la literatura sustentan mecanismos y contratos de investigación, no el desempeño de HARPOON ni una afiliación institucional.
