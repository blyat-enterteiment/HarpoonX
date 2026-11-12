# HARPOONX M11 C37 — Q3 2026 historical observed bars, no broker fills

**Dictamen:** validación de ingeniería reproducible con datos de mercado observados y precios de ejecución MODELADOS. **No es estudio prospectivo real ni acreditación N9-S. NO_GO.**

## 1. Recuperación

Se descargaron mediante el conector de datos de mercado de Alpaca cinco series
OHLCV diarias entre el 1 de julio y el 30 de septiembre de 2026:

| Activo | Fuente | Barras | Retorno cierre a cierre trimestre* |
| --- | --- | ---: | ---: |
| SPY | Alpaca IEX | 64 | +2,236% |
| QQQ | Alpaca IEX | 64 | +1,956% |
| NVDA | Alpaca IEX | 64 | +15,566% |
| BTC/USD | Alpaca Crypto US | 92 | +39,350% |
| ETH/USD | Alpaca Crypto US | 92 | +66,922% |
| **Total** | | **376** | |

*Retorno simple no ajustado por dividendos ni splits, entre primer y último
cierre suministrados, NO retorno de la estrategia ni índice total-return.

Los cinco CSV originales están en `research/observed_q3_2026/raw/`,
y la procedencia e integridad Git Blob SHA están congeladas en
`research/observed_q3_2026/source_manifest.json`.
La ejecución `evaluate.py` rechaza cambios de bytes, barras no
cronológicas, precios incoherentes y cobertura insuficiente. Salida:
`artifacts/replay_report.json`, resumen CSV, trades modelados CSV
y archivo comprimido de GitHub Actions.

**Límites críticos de fuente:**
- El feed libre IEX es de UNA bolsa; no representa la liquidez
  consolidada SIP/NBBO ni el volumen nacional de un activo.
- El feed cripto US de Alpaca puede publicar velas con precios
  medios de cotización cuando no existen trades. No todas esas
  aperturas/cierres son fills accesibles.
- No se observaron BBO de decisión, recibos de órdenes, fees reales,
  fracciones de fills, colas, impacto ni fuentes cripto adicionales.
- Las barras de acciones se pidieron sin ajuste corporativo
  adicional; no se incorporaron dividendos o splits.

Documentación primaria: 
https://docs.alpaca.markets/us/reference/stockbars
https://docs.alpaca.markets/us/reference/cryptobars-1
https://docs.alpaca.markets/us/docs/historical-crypto-data-1
https://docs.alpaca.markets/us/docs/crypto-fees

## 2. Diseño e integridad temporal

**Calibración histórica:** julio y agosto. Se estimaron únicamente
11 combinaciones activo–estrategia con alguna oportunidad; la matriz
completa incluía hasta 5 × 3 familias: ruptura de 10 barras,
momentum de 5 y reversión de 3. Se detectaron 54 señales de entrenamiento
y 26 señales de septiembre.

**Prueba retrospectivamente separada:** septiembre de 2026.
El corte se decidió en noviembre de 2026, DESPUÉS de ocurrir
septiembre. Por ello no existe prerregistro anterior al resultado,
ninguna significancia prospectiva y ninguna generalización
estadística N9-S. Es una validación pseudo-OOS temporal de software.

Cada señal usa el cierre del día i. Se impone un día completo
adicional por incertidumbre de publicación y se modela entrada
en el OPEN del día i+2, salida al siguiente OPEN del día i+3.
Se rechaza cualquier posición cuya duración real entre aperturas
sea mayor a 72 horas. Nunca se adquiere el mismo día del cierre
que generó la señal.

**Advertencia:** el OPEN del proveedor es un precio histórico,
NO una confirmación de fill IOC accesible. La simulación opera
sobre un libro continuo único de 20.000 USD, con admisiones
limitadas por 12% bruto conjunto, 0,25% de riesgo reservado
y máximo adicional de investigación de 4% nominal por candidato.
Una reserva calculada por 2×rango medio no es cota de pérdidas
ante gaps. La caída patrimonial se observa únicamente en marcas
de salida, por lo que subestima DD intraperiodo.

## 3. Hipótesis económicas (no recibos)

| Libro | Ida y vuelta base | Estrés ida y vuelta |
| --- | ---: | ---: |
| Equity/ETF IEX | 13 pb | 26 pb |
| Crypto USD Alpaca US | 100 pb | 170 pb |

En cripto, SOLO 25 pb por cada lado (50 pb ida y vuelta) procede
del tarifario público del primer tramo taker Alpaca. Los otros 50 pb
base son supuestos acumulados de spread, slippage e impacto, no
importes reales facturados. La ejecución maker y su probabilidad
de fill no se modelaron.

En acciones, 0 comisión de broker es el supuesto base, pero 13 pb
de fricción ida-vuelta son hipótesis. No se demostraron descuentos,
ejecuciones preferenciales ni verificación de costes externos.

## 4. Resultado de septiembre, capital compartido 20.000 USD

| Política | Operaciones modeladas | PnL neto modelado | Crecimiento log pb/día |
| --- | ---: | ---: | ---: |
| CASH 0% | 0 | 0,00 USD | 0,0000 |
| Momentum ingenuo, NO original | 17 | −2,78 USD | −0,0464 |
| Incubadora flexible (media neta entrenamiento positiva) | 9 | −52,78 USD | −0,8809 |
| Incubadora conservadora (puntuación de incertidumbre positiva) | 0 | 0,00 USD | 0,0000 |
| Incubadora conservadora, costes estresados | 0 | 0,00 USD | 0,0000 |

El filtro flexible acumuló **34,97 USD** de costes modelados
de ida y vuelta y terminó en **19.947,22 USD**. El naive momentum
consumió 36,96 USD de costes modelados y acabó en 19.997,22 USD.

**Hallazgo adversarial:** en estas condiciones, seleccionar solo
por media positiva de entrenamiento hizo perder más. Los
11 pares calibrados tuvieron un score de incertidumbre pesimista
no positivo, por lo que el filtro conservador no operó.
El resultado CASH es cero por hipótesis y no incluye intereses.
Un filtro que evita pérdidas observadas ex post no es prueba
de alfa futuro. La elevada subida de algunos activos en el
trimestre tampoco implica que las estrategias con holds ≤72h
puedan capturarla a precios de ejecución creíbles.

No se implementó paridad semántica con las seis estrategias
originales C22; `naive_momentum_reference_NOT_ORIGINAL` es
un comparador de ingeniería, nunca ORIGINAL_BASELINE de C29.

## 5. Evidencia y reproducción

Ruta principal: `research/observed_q3_2026/`.

    python -m unittest discover -s research/observed_q3_2026 -p test_evaluate.py -v
    python research/observed_q3_2026/emit_artifacts.py

La descarga ZIP de CI es autoejecutable desde su carpeta extraída:

    python -m unittest discover -s . -p test_evaluate.py -v
    python emit_artifacts.py

Este artefacto contiene 5 CSV, `source_manifest.json`, código,
20 pruebas, `artifacts/replay_report.json`,
`economic_comparison.csv` y `MODELED_TRADES_NOT_BROKER.csv`.
Verificar su hash a partir del manifiesto evita sustituir
silenciosamente un precio después de la evaluación.

## 6. Requisitos antes del experimento prospectivo de verdad

- Congelar externamente las reglas y endpoints de captura **antes**
  de observar futuros resultados (C34 RFC3161 con custodia vetada).
- Confirmar identidad nativa y matriz C32/C27/C28 de oportunidades.
- Recibir cotizaciones BBO conocidas al decidir y recibos ORDER/FILL
  contemporáneos del broker C25/C26/C35, con horarios causales.
- Reconciliar comisiones cripto que Alpaca publica posteriormente,
  compras/ventas, cash, inventario, reservas, reinicios y atrasos.
- Excluir opciones o certificar íntegramente multiplicador, ejercicio,
  liquidación, comisiones, vencimientos y fills.
- Comparar C36, ORIGINAL y CASH en una sola cartera prospectiva,
  bloques no contaminados, control de selección múltiple, criterio
  N9-S congelado y revisión independiente.

**No se autorizó ninguna orden, despliegue, apertura M10,
fusión a main ni reinicio de optimizador. Todas las 3.200
cuentas M10 permanecen selladas. N9-S NO_GO.**
