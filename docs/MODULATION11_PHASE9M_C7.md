# HARPOONX FWN9 — M11 9M-C7: límites de exposición y puente de patrimonio

**Decisión:** fixture causal-contable **PASS local**; el puente universal de M9 hacia una cota numérica de log-patrimonio **NO DEMOSTRADO**. El avance es una refutación acotada de dos sustituciones inválidas, no una refutación de la clase de estrategias ni una prueba de imposibilidad N9-S.

## Qué refuta C7 (alcance preciso)

El límite original de **12% es de admisión/reserva, no un cap continuo**. En un libro determinista con W=20.000 USD, 18 unidades existentes a 100 USD y 11 pendientes a 50,02 USD, el compromiso admisible es 2.350,22 USD (<2.400). Si la posición anterior pasa a 110 USD antes de conocerse el siguiente fill, el gross marcado sube a 2.530 USD y el patrimonio reconstruido a 20.179,725 USD: ratio **12,537336%**. No prueba una admisión incorrecta y no representa un evento observado de M9.

La cota C6 necesita E[Σ qS_apertura], no E[qS] de una sola reserva. Mantener 23 títulos a 100 USD durante dos barras de cinco minutos cumple 72h y el cap de admisión de 2.400 USD, pero la suma de nocionales prebarra es **4.600 USD**. Una reserva inicial no acota la **suma temporal** sin número de barras y excursiones de precios. Bajo un mismo ancla y razones de precio ≤M, la desigualdad válida es Σ qS ≤ n·B_ancla·M, no Σ qS ≤B_ancla. Ejemplo puramente condicional: n=2, M=1,10 y B_ancla≤2.400 producen una cota de 5.280 USD.

### Hallazgo estructural nuevo: retroalimentación por tamaño entero

Dos carteras contrafactuales con el **mismo próximo precio y señal**, un crédito local previo de +6,50 USD y las reglas nominales de riesgo y coste originales, pueden escoger cantidades enteras distintas sin violar la admisión: 24 títulos con W=20.006,50 frente a 23 con W=20.000. Entrada a 100,03 USD, stop a distancia 1, comisiones de 0,005 USD por acción y lado y fricción de 3 pb por lado; ambos riesgos iniciales son ≤0,25% de equity (25,680432 y 24,610414 USD). El gross inicial de 24 títulos equivale a 2.400,72 USD, por debajo de 2.400,78 del primer libro, pero por encima de los 2.400 del segundo.

Un gap sintético adverso **posible pero extremadamente improbable** hasta un open de 93 USD, con salida nativa gap-stop 92,97 USD tras fricción, da patrimonio terminal 19.836,82 USD contra 19.837,39 USD: el libro con **+6,50 USD local inicial termina 0,57 USD abajo**, o una diferencia de log-riqueza de **−0,00002873403150506176**. La pérdida por sesión queda por debajo del 2% y el drawdown por debajo del 8%. Es un contraejemplo algebraico de **la inferencia incorrecta «crédito local positivo ⇒ ventaja terminal positiva o igual crédito/20.000»**. No es un camino realizado, no fue ejecutado por el motor M9, ni demuestra frecuencia poblacional o que las señales nativas generen exactamente ese historial.

## Qué sí podría permitir una cota finita, pero NO se ha acreditado

Bajo condiciones explícitas, si en cada barra b el inventario stop-expuesto a precios de apertura satisface q_b S_b≤B_τ(b) M_τ,b y cada reserva satisface B_τ≤g W_τ, entonces

  E[Σ_b q_b S_b] ≤ g Σ_b E[W_τ(b) M_τ,b]
                 ≤ g Σ_b (E[W_τ(b)^2] E[M_τ,b^2])^(1/2).

La última desigualdad es Cauchy–Schwarz y **no necesita independencia**. Para el término de unidades se puede escribir q_b≤g W_τ M_τ,b / S_b y aplicar Hölder (4,4,2), condicionándolo a los momentos de W_τ, M y S_b^{-1}. La ley WEAK tiene volatilidad de actividad truncada y horizonte finito, por lo que hay una vía para analizar momentos de precios; **no se ha probado aquí** el momento de riqueza del motor endógeno, ni la desigualdad de ancla para todos sus relojes, ni el acoplamiento de acciones posteriores al cambio de fill.

No se puede sustituir E[W_τ M] por E[W_τ]E[M] sin independencia, ni usar 20.000 como piso de W_T. Una cota directa de E[W_T] permitiría aplicar Jensen a E[log W_T] para W_T>0, pero esa cota poblacional del motor nativo tampoco se ha obtenido. La esperanza local del crédito de C6 **no es** una diferencia de riqueza terminal entre políticas cuyas admisiones divergen.

## Alcance y evidencia

- Protocolo con lease CAS preregistrado: `research/modulation11/fwn9_phase9m_c7_protocol.json` (commit `a8d968293e6b730cedb6368fa8539d9a2c1182fa`).
- Módulo nuevo y aislado: `tools/fwn9_p9m_c7_bridge.py`; ocho pruebas de fixtures: `tools/test_fwn9_p9m_c7_bridge.py`.
- Local Python 3: 8/8 PASS, `py_compile` PASS, análisis AST PASS, cuenta Decimal independiente PASS; 10.000 iteraciones ≈213 ms en ese entorno. Ruff/mypy no se instalaron localmente por falta de red; `fwn9_p9m_c7.yml` los verifica en CI: **su estado debe consultarse** antes de declarar PASS de tipos/análisis estático.
- Semillas nuevas: 0; cuentas económicas nuevas: 0; alfa prospectiva consumida: 0; finales M10 abiertos: **0/3.200**. CASH y M9_BEST permanecen referencias congeladas; no se reejecutan datos económicos ni se recalculan PnL poblacionales.
- Los dos bloqueos operativos originales persisten: cobertura completa de parciales/rechazos/outages/impact y coordinación multicelda.
- No se modificaron generador, costes, capital, drift, umbrales, límites ni código de replay. Ninguna conectividad externa de ejecución.

**Próximo problema:** probar por inducción de eventos una desigualdad de ancla para cada prebarra nativa (incluidas reposiciones), acotar momentos/endogeneidad de W_τ y M, y contrastar el crédito frente a riqueza terminal mediante un acoplamiento causal no selectivo. No buscar más señales ni tocar holdouts. El veredicto sigue **NO_GO N9-S**, sin certificado poblacional de imposibilidad.
