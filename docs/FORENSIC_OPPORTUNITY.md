# Forense de oportunidad, pérdida y volumen relativo

Revisión del 7 de noviembre de 2026 sobre la rama `codex/remediation-framework`, padre `bab1746d5735158605feb96c58ee7102c5cb005a`. Veredicto: **diagnóstico reproducible; ninguna mejora de rentabilidad validada ni promoción**.

Se examinaron las cuentas técnicas SIMPLE/CONFIRMED nominales y de estrés, las cuentas horarias conjuntas nominal/estrés y el informe del walk-forward purgado de la matriz. No se suman carteras ni versiones como observaciones independientes. Son históricos archivados con fills OHLCV modelados, no operaciones de broker. El conjunto técnico se identifica como ALPACA_PROXY/SIP y declara que sus marcas de captura no son recibos originales del mercado; los tiempos de disponibilidad usados son los del modelo. La fixture multisectorial y los cinco casos sintéticos de matriz no se usan como evidencia económica.

## Hallazgos económicos

| Ensayo | Operaciones nominales | Resultado nominal USD | Estrés USD |
|---|---:|---:|---:|
| Horario conjunto, 2025 | 41 | -250.69 | -670.03 |
| Apertura SIMPLE, marzo 2025–octubre 2026 | 89 | -261.88 | -1,020.62 |
| Apertura CONFIRMED, mismo período | 47 | +4.88 | -687.95 |
| Matriz purgada CURRENT/A/B, 2025, cada cuenta | 0 | -365.00 | -730.00 |

La cartera horaria produjo 163.366783 USD brutos, pagó 49.055498 de costes variables supuestos y 365 de costes fijos supuestos: -250.688715 USD. Ganó en 27 de 41 operaciones y aun así perdió dinero. Su margen antes de fijos fue 114.311285 USD; equivale descriptivamente a 0.313182 USD/día de capacidad para cubrir fijos. No es el resultado de quitar costes y volver a simular, ni un presupuesto operativo validado.

CONFIRMED produjo 589.88 USD de trading, dividendos cero y soportó 585 USD de fijos. Su resultado cae a -175.06 USD al restar descriptivamente su mayor ganador. El beneficio residual de +4.88 USD no es evidencia suficiente de ventaja robusta. SIMPLE produjo 319.15 USD de trading más 3.97 USD de dividendos, menos 585 de fijos. En estrés cambian también cantidades y operaciones: no es sólo multiplicar comisiones sobre posiciones idénticas.

CURRENT/A/B: 316 celdas candidatas por cuenta, cero aprobaciones y cero compras; toda la pérdida procede del coste fijo supuesto. Las variantes no tuvieron exposición que permita identificar su efecto. El informe agregado no conserva resultados hipotéticos de cada rechazo: no permite afirmar cuántos ganadores perdió la matriz. Los casos siguientes pertenecen a los otros bancos.

## Casos trazables

Resultados por operación después de costes de trading modelados, antes de fijos. RVOL10: volumen de los últimos diez minutos dividido por la mediana del mismo intervalo en las veinte sesiones anteriores.

| Entrada, activo y ensayo | RVOL10 | Hito observado | Cierre USD | Lectura defendible |
|---|---:|---|---:|---|
| 2026-02-09, MSFT, CONFIRMED | 2.614 | Pico de valoración +65.60 USD | -46.00 | Beneficio transitorio devuelto; volumen alto no impidió la pérdida |
| 2025-04-02, AAPL, SIMPLE | 0.687 | Pico +10.70; salida siguiente sesión | -185.40 | Pérdida de -6.139R con riesgo inicial 30.20 USD; auditar gap, no asumir stop garantizado |
| 2026-04-13, MSFT, CONFIRMED | 1.188 | Parciales TP1/TP2 y salida temporal | +179.94 | El mayor ganador no necesitó RVOL extraordinario |
| 2025-08-05, AAPL, SIMPLE | 1.032 | No cumplía dos cierres de confirmación | +147.59 | Ganador excluido por ese requisito; no demuestra que relajar el filtro mejore la cartera |

El pico es valoración a cierre con provisión de comisión; no descuenta el spread/deslizamiento adicional de liquidar en ese instante ni los fijos. No es dinero que se hubiera podido capturar íntegramente. No se suman los picos como PnL alternativo.

En CONFIRMED nominal, **18 de 22 perdedoras** tuvieron una valoración positiva previa. Sólo **3** habían llegado a +1R de valoración. La conclusión no es vender toda ganancia pequeña: una regla así puede destruir la cola de ganadores. En SIMPLE, 45 operaciones incumplían confirmación: 28 pérdidas y 17 ganancias, con trading neto conjunto -175.94 USD. Ese subconjunto descriptivo no sustituye un replay con capital, reservas y oportunidades reasignadas.

Los grupos de RVOL tampoco justifican un umbral ganador. En SIMPLE, RVOL ≤1 suma -371.81 USD, 1–2 suma +787.82 y >2 suma -96.86, antes de fijos/dividendos. Son sólo 31, 46 y 12 operaciones seleccionadas. En CONFIRMED, >2 suma +36.20 nominal y -10.21 en estrés. Seleccionar ahora el intervalo 1–2 usando estos mismos resultados sería ajuste retrospectivo.

## Hitos de MSFT: oportunidad que terminó en pérdida

Horas UTC; los valores posteriores a entrar sólo estaban disponibles en sus propios instantes.

| Hito | Hora | Valoración USD | RVOL10 |
|---|---|---:|---:|
| Decisión | 2026-02-09 15:30:01 | — | 2.614 |
| Primer cierre ≥+1R | 2026-02-10 14:55:01 | +46.70 | 1.372 |
| Máximo, identificado después | 2026-02-10 15:10:01 | +65.60 | 2.312 |
| Primer negativo después del máximo, identificado después | 2026-02-11 14:40:01 | -2.50 | 0.878 |
| Cierre conocido | 2026-02-11 17:05:01 | -46.00 | 1.559 |

Hipótesis: estudiar la protección después de avance suficiente y deterioro observable. Un caso no demuestra capacidad predictiva del descenso de RVOL; además el volumen volvió a subir antes de la salida perdedora. El máximo final y el primer negativo posterior a ese máximo son etiquetas retrospectivas, prohibidas como predictores de entrada o selección causal de salida.

## Defecto de cronología descubierto

El replay añade el mark de una barra en `availableAt = end + 1s`, y al procesar la siguiente apertura puede añadir la liquidación temporal en `t = end`. Así aparecen arrays con el mark anterior conocido un segundo después del cierre. Se observaron 44 inversiones en SIMPLE nominal, 27 en CONFIRMED nominal, 43 y 26 en estrés: **140 incidencias entre replays, no 140 operaciones independientes**.

El extractor conserva el contador y la valoración máxima archivada, pero excluye marks no terminales conocidos después de salir. Reconstruye la disponibilidad del recibo terminal desde `inventoryEvents.knownAt`. No modifica los libros originales ni corrige el replay; esa corrección y la medición de su efecto sobre reservas/valoraciones quedan pendientes. La conciliación de caja no demuestra cronología correcta. No se debe usar la secuencia antigua para entrenar una política de salidas sin resolver este punto.

## Representación escalar, vectorial, tensorial y por conjuntos

**Escalares calculados.** `net_r = netUsd/riskUsd`; `peak_close_r`, `trough_close_r`, `giveback_r`; RVOL y costes en unidades explícitas. Son descriptores o etiquetas, no probabilidades de ganar. `riskUsd` es el riesgo planificado, no una cota a pérdidas por gaps.

**Vector de entrada implementado**, cinco componentes conocidos al decidir:

`x = [retorno_log_relativo_sector, log(1+RVOL10), (precio-nivel)/distancia_stop, distancia_stop/precio, confirmación_dos_cierres]`.

**Tensor de entrada implementado:** `X[candidato, barra_previa, canal]`, dimensiones **133 × 12 × 7**. Canales: retorno log de la barra; retorno de barra relativo a XLK; log(1+RVOL de esa franja de cinco minutos); cuerpo/rango; posición del cierre en el rango; rango/precio; distancia al VWAP de sesión ponderado con `vw` de las barras. Cada fila tiene `available_at_ms` y máscara de observación. Cero volumen es distinto de dato faltante. Splits, historia insuficiente y denominadores nulos invalidan RVOL. No se mezclan RVOL5, RVOL10 y RVOL diario; no se comparan unidades de volumen entre mercados.

El tensor comprende todos los candidatos de ruptura presentes en `ranked`, no todo el universo de barras ni sólo ganadores. No se entrena un modelo de alta dimensión con 47 operaciones. Las 268 campañas de cuatro replays se guardan en otro archivo de etiquetas; muchas comparten el mismo evento de mercado. No son 268 muestras independientes.

**Estado dinámico propuesto, aún sin modelo ajustado:** `[PnL_t/R, máximo_observado_hasta_t/R, devolución_hasta_t/R, Δlog(1+RVOL_t), retorno_relativo_t, horas_restantes, cantidad_restante, coste_liquidación/R]`. El máximo es creciente sobre el prefijo observable; no usa el máximo final. Faltan cotizaciones ejecutables para calcular con fidelidad el último componente.

**Conjuntos descriptivos:** ganadores; pérdidas después de estar positivos; ganadores de SIMPLE rechazados por confirmación; pérdidas superiores al riesgo inicial. Se publican intersecciones y denominadores. Los conjuntos se superponen; no se suman como atribuciones independientes ni se convierten en reglas porque coincidan con estos ejemplos.

**Escalar de decisión propuesto, no estimado en esta entrega:** límite inferior del crecimiento logarítmico neto esperado condicionado al estado y a la acción, sujeto a capital/riesgo/coste. Debe superar también al efectivo y al control en prueba nueva. Añadir un tensor no crea una ventaja por sí mismo.

## Reproducir

```bash
PYTHONPATH=quant OPENBLAS_NUM_THREADS=1 python tools/run_forensic_opportunity.py --output-dir /tmp/harpoon_forensic_new
PYTHONPATH=quant python -m unittest quant.tests.test_forensic_features -v
```

El directorio de salida debe ser nuevo. Genera `report.json`, `entry_features.json.gz`, `outcome_labels.json.gz`, `compound_trades.json` y `sha256.json`. Los gzip tienen fecha interna fija para reproducibilidad. Reproduce las 404 decisiones técnicas y concilia eventos de las 268 campañas y dos cuentas horarias. No ejecuta un nuevo replay de políticas ni bootstrap de propuestas; reutiliza resultados archivados. Ver `evidence/forensic_opportunity/validation.json` para las comprobaciones de esta entrega.

El siguiente ensayo debe registrar una sola hipótesis económica por variante, presupuesto finito y datos no reutilizados. Las pruebas repetidas sobre la misma historia elevan el riesgo de falsos descubrimientos; la purga no borra la selección previa. Referencia primaria: Bailey, Borwein, López de Prado y Zhu, *The Probability of Backtest Overfitting* (2015), https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf. No se ha estimado aquí una PBO global: falta el registro completo de ensayos históricos.

El encargo reutilizable está en `docs/PROMPT_FORENSE_ECONOMICO.txt`.
