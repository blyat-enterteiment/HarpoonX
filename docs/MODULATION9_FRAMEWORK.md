# HARPOONX: framework de factibilidad sintética N9-S

## 1. Objetivo y contrato vinculante

Este documento define cómo buscar una combinación favorable de rentabilidad, riesgo y drawdown mediante modulaciones registradas. Describe el método; los resultados económicos pertenecen a un informe separado. La fuente vinculante es `research/modulation9/protocol.json`, esquema `HARPOON_MODULATION9_PROTOCOL_1`, fechado el 7 de noviembre de 2026. Su SHA256 registrado es `de694919b0908fc0ecf474c9612ff7d54fe04db635a385e12ffa0f81abc7780d`.

«9» significa aquí la etiqueta interna **`N9S_1_INTERNAL_CONDITIONAL_ONLY`**. Se concede **si y sólo si** todos los criterios económicos, estadísticos, contables y operativos predefinidos resultan verdaderos. Esta equivalencia pertenece al contrato del experimento: no demuestra que una estrategia ganará en el mercado ni constituye una puntuación industrial.

Se informan dos decisiones: `economic_model_feasibility`, relativa a la economía observada bajo el modelo, y `conditional_n9s_accepted`, que también requiere cerrar las brechas operativas. La versión registrada carece de cobertura completa de ejecución y de integración del coordinador virtual; por ello no puede otorgar la segunda etiqueta, incluso si aprobara la primera.

## 2. Cuenta, información y costes

Cada política mantiene una cuenta continua de **20.000 USD**, compartida entre SYNA y SYNB; SYNM funciona como referencia. No se reinicia capital entre operaciones ni se suman cuentas independientes como si fueran una cartera. Efectivo, inventario, reservas y costes pasan por el ledger nativo.

Los límites son 12% de exposición bruta y por activo, 0,25% de riesgo abierto, 2% de pérdida por sesión y 8% de drawdown observado. Los límites de exposición y riesgo son de admisión/reserva: apreciaciones, gaps o cambios del equity pueden causar excesos posteriores, que se informan separadamente. No se presupone rebalanceo continuo. El reloj de permanencia queda limitado a 72 horas; determinados perfiles lo acortan.

| Coste registrado | NOMINAL | STRESS |
|---|---:|---:|
| Spread completo | 2 pb | 4 pb |
| Slippage por lado | 2 pb | 4 pb |
| Comisión por acción y lado | 0,005 USD | 0,01 USD |
| Coste fijo por día de calendario | 1 USD | 2 USD |

El motor aplica medio spread y slippage por lado, conserva cantidades enteras y modela entradas IOC con límite causal de 30 pb. El volumen informa señales; no acredita profundidad ejecutable.

## 3. Modulaciones cerradas

Se cruzan **tres entradas, cuatro salidas y tres riesgos por campaña: 0,0625%, 0,125% y 0,25%**. Las 36 combinaciones permanecen fijas durante el estudio.

| Entrada | Regla causal |
|---|---|
| CONFIRMED | Dos cierres sobre el máximo inicial de 30 minutos, retorno relativo positivo y RVOL superior a uno. Decide a los 60 minutos más un segundo; entra en la siguiente apertura de cinco minutos. |
| QUALITY | CONFIRMED, RVOL máximo de tres, extensión máxima de 0,6 ATR previo de veinte días, retorno previo de treinta días positivo e histograma MACD(12,26,9) positivo. Las EMA se inicializan sobre exactamente cincuenta cierres diarios previos. |
| RETEST | Decide a los 90 minutos más un segundo. Exige ruptura entre los minutos 30–60, revisita posterior dentro de una banda simétrica de 0,15 ATR alrededor del máximo inicial, sin tocar el mínimo inicial, y dos cierres nuevamente superiores. Añade retorno relativo positivo, RVOL entre 0,8 y tres y tendencia previa de treinta días positiva. |

RVOL compara los últimos diez minutos con la mediana del mismo intervalo de las veinte sesiones anteriores completas. Se comprueba disponibilidad; la sesión actual no entra en los indicadores diarios.

| Salida | Regla registrada |
|---|---|
| NATIVE72 | Parciales nativos de 25% a 1,5R y 25% a 3R, trailing nativo y plazo máximo de 72 horas. |
| PROTECT48 | Conserva objetivos nativos. Desde un cierre que alcanza 1R, protege entrada ajustada por fricción de salida y dos comisiones, retiene 75% del beneficio máximo al cierre y usa trailing de 1R. Máximo: 48 horas. |
| RUNNER72 | Vende un cuarto entero a 2R; conserva el remanente con trailing de 2R activado a 2R. Máximo: 72 horas. |
| FAST24 | Objetivos nativos; después de seis horas, si el máximo beneficio al cierre no alcanza 0,5R y el cierre no supera la entrada, sale en la siguiente apertura. Máximo: 24 horas. |

R representa la distancia inicial de riesgo de precio. Los controles son CURRENT, SIMPLE y CASH, todos con los mismos costes fijos. `CONFIRMED_NATIVE72_R2500` replica exactamente CURRENT: se contabiliza, pero se excluye de selección como mejora.

### Hallazgo de recepción del trailing

La implementación heredada puede sobrescribir un stop pendiente antes de recibirlo: una barra disponible un segundo después de su cierre todavía no está disponible en la apertura siguiente. Una actualización posterior puede desplazar la anterior. NATIVE72 y FAST24 conservan esa semántica como control.

PROTECT48 y RUNNER72 preservan las actualizaciones mediante una cola y activan únicamente las recibidas. Por tanto, sus diferencias combinan parámetros de salida y reparación de recepción. No permiten atribuir toda mejora exclusivamente a parámetros; aislar ambos efectos requiere una futura ablación registrada.

## 4. Banco de pruebas y significado del nulo

Cada trayectoria contiene cincuenta sesiones de calentamiento, 126 de evaluación y seis de margen, con 78 barras por sesión y ocho subpasos por barra. El calendario comienza el 8 de enero de 2024 y utiliza lunes a viernes, 14:30–21:00 UTC; no incorpora feriados ni horario estacional.

| Mundo | Hipótesis sometida a contraste |
|---|---|
| TREND | Persistencia direccional con cambios de régimen. |
| WEAK | Ventaja más débil y volatilidad mayor. |
| FALSE | Rupturas iniciales y ráfagas de volumen seguidas de reversión. |
| NULL | Precios martingale compensados, sin drift explotable. |
| GAP | Tendencia con correlación elevada y gaps adversos. |

La estrategia recibe prefijos observables de precio y volumen, nunca el mundo, drift o régimen latente. En el final se desplazan parámetros dentro de rangos registrados: volatilidad 0,90–1,20, drift 0,75–1,10 y frecuencia de renovación 0,80–1,30, como multiplicadores.

En NULL, la compensación normal y los saltos simétricos preservan esperanza condicional del precio en los subpasos. Sin embargo, los fills a umbrales interpolados de OHLC constituyen otra aproximación. Un aparente beneficio puede revelar sesgo de ejecución, además de fuga, error contable o variación muestral. No se modifica el generador para producir un ganador.

## 5. Selección, Pareto y presupuesto

Desarrollo utiliza ocho semillas por mundo, de 730101 a 730108. Las 39 políticas contables, cinco mundos y dos costes producen **3.120 cuentas**. Se descartan candidatos que incumplen riesgo, plazo o conciliación.

Entre factibles, la frontera de Pareto compara crecimiento logarítmico nominal medio en TREND/WEAK y percentil 95 del drawdown de todos los mundos bajo costes STRESS. La elección maximiza el menor valor de «media menos 1,645 errores estándar» entre TREND/WEAK y ambos costes. Es un ranking exploratorio. Los desempates favorecen menor drawdown, menor riesgo y después identificador lexicográfico.

Se congela una receta antes del final. Sus 64 semillas por mundo, de 940201 a 940264, se evalúan junto con CURRENT, SIMPLE y CASH: **2.560 cuentas**. El techo conjunto es **5.680 ejecuciones**. Sin receta factible se detiene; si el mejor score no es positivo, el final permanece diagnóstico y no puede habilitar promoción.

El presupuesto histórico registra 151 frente a un techo de 128, sin conciliación. El suplemento actual añade 78 unidades política–coste —39 por dos— y un total provisional de 229 en esa unidad heredada. Las réplicas por mundo/semilla se cuentan además expresamente. La autorización actual no borra la deuda histórica.

## 6. Inferencia y regla de aceptación

La observación independiente es una trayectoria completa. Activos, políticas y costes permanecen emparejados. La métrica es `log(equity_final / equity_inicial)` dividida por los días de calendario inclusivos cobrados por el ledger.

El final usa 20.000 réplicas bootstrap de trayectorias, semilla 300710, y Bonferroni para **40 endpoints**: cinco mundos, dos costes y cuatro contrastes —absoluto, CURRENT, SIMPLE y CASH—. El error familiar nominal unilateral es 5%; cada cola emplea 0,00125. La cobertura bootstrap es aproximada. Se estima potencia objetivo de 80% desde desarrollo; una muestra insuficiente no autoriza cambiar umbrales o ampliar presupuesto retrospectivamente.

La factibilidad económica exige conjuntamente:

1. Score de desarrollo positivo y cobertura final completa, íntegra y emparejada.
2. En TREND y WEAK, límite inferior nominal superior a **0,0001 de log-crecimiento diario**, y límite inferior STRESS superior a cero.
3. Diferencia emparejada positiva frente a cada control, en ambos mundos y costes.
4. Equity positivo, conciliación, drawdown máximo observado de 8%, pérdida por sesión máxima de 2% y plazo máximo de 72 horas.
5. En NULL, FALSE y GAP, diferencia media de retorno terminal frente a CASH no inferior a **−0,5 puntos porcentuales**, por mundo y coste.
6. En NULL, ningún límite inferior positivo, absoluto o frente a CASH.
7. Beneficio agregado positivo después de restar la mejor campaña de cada cuenta, en TREND/WEAK por coste. Es una resta descriptiva; no resimula decisiones ni capital.

El hurdle diario es una preferencia del contrato, no una predicción. Ausencia observada de infracciones tampoco demuestra riesgo cero. Cualquier fallo conserva el resultado negativo; reutilizar el final para diseñar otra receta lo convierte en desarrollo.

## 7. Ruta para cerrar brechas

1. **Cerrar este experimento:** publicar todas las combinaciones, frontera factible, selección, intervalos, infracciones y hashes; conservar también los descartes.
2. **Separar reparación y estrategia:** registrar una ablación del trailing con idénticos parámetros y distinta recepción. No atribuir causalidad a una comparación confundida.
3. **Completar ejecución:** modelar entradas parciales, rechazos, cancelaciones, impacto y caídas del servicio; probar conciliación, reintentos idempotentes y cierre antes del plazo ante fines de semana y calendarios reales.
4. **Integrar la matriz virtual:** reservar efectivo y riesgo atómicamente, tratar celdas como exposiciones alternativas y evitar doble contabilización. Una salida protectora no debe esperar al neteo de entradas.
5. **Registrar una validación nueva:** congelar cambios y semillas nuevas, incluyendo pruebas de ejecución sobre NULL; un fracaso previo permanece documentado.
6. **Pasar a datos observados:** calibrar costes y disponibilidad con evidencia, incorporar acciones corporativas y realizar evaluación temporal purgada por maduración y horizonte. Después procede observación prospectiva sin órdenes. Este framework no habilita broker ni ejecución real.

Son hipótesis refutables: que filtrar volumen añade información, que proteger beneficios compensa ganancias truncadas y que el retest reduce falsas rupturas después de costes. Su rechazo no se subsana elevando apalancamiento o escogiendo sólo el mundo favorable.

## 8. Fundamentos y reproducción

[Busseti, Ryu y Boyd, *Risk-Constrained Kelly Gambling*](https://web.stanford.edu/~boyd/papers/kelly.html), fundamenta considerar crecimiento logarítmico junto con riesgo de drawdown. Este banco no implementa su programa convexo ni hereda su garantía matemática.

[Boyd y colaboradores, *Multi-Period Trading via Convex Optimization*](https://web.stanford.edu/~boyd/papers/cvx_portfolio.html), integra retorno, riesgo, costes de transacción y mantenimiento. Motiva evaluar la cuenta completa; no aporta por sí mismo pronósticos ni valida estos generadores.

[Bailey y colaboradores, *The Probability of Backtest Overfitting*](https://escholarship.org/uc/item/4w1110bb), estudia el sesgo de selección entre estrategias y propone PBO/CSCV. Aquí **no se midió PBO**: se utilizan catálogo cerrado, final independiente y ajuste explícito de multiplicidad.

Los comandos siguientes reproducen la especificación congelada en directorios nuevos. No regeneran el registro existente ni constituyen nuevas variantes. Requieren Python con NumPy/SciPy y Node; los benchmarks quedan separados de los resultados económicos.

```bash
cd /workspace/scratch/0a6c27f713ac/HarpoonX
export PYTHONPATH="$PWD/quant:$PWD/tools"
python -c 'from run_modulation9 import verify_registration; verify_registration(); print("REGISTERED_SOURCES_OK")'
python -m unittest discover -s quant/tests -p 'test_modulation9*.py' -v
node --test tools/modulation9_test.cjs

MOD9_REPRO_ROOT="$(mktemp -d /tmp/harpoon-mod9-reproduction.XXXXXX)"
python tools/run_modulation9.py --stage development \
  --output-dir "$MOD9_REPRO_ROOT/development" --workers 2
python tools/analyze_modulation9.py --stage development \
  --input-dir "$MOD9_REPRO_ROOT/development" \
  --output-dir "$MOD9_REPRO_ROOT/development_analysis"
python tools/run_modulation9.py --stage final \
  --selection "$MOD9_REPRO_ROOT/development_analysis/selection.json" \
  --output-dir "$MOD9_REPRO_ROOT/final" --workers 2
python tools/analyze_modulation9.py --stage final \
  --input-dir "$MOD9_REPRO_ROOT/final" \
  --selection "$MOD9_REPRO_ROOT/development_analysis/selection.json" \
  --output-dir "$MOD9_REPRO_ROOT/final_analysis"
```
