# HARPOONX N10 P2 | Ingeniería inversa causal de opciones SPY

**Periodo:** 1 de enero a 30 de abril de 2025 (81 sesiones con datos, 120 días calendario). **Estado:** diagnóstico retrospectivo, NO_GO N10 / NO_GO N9-S. **Capital:** 20.000 USD. **Fecha del análisis:** 13 de noviembre de 2026.

## 1. Alcance reproducible

Se recuperaron los mismos registros históricos del estudio N10-P1, con identidad SHA-256 del Parquet de cuatro meses `01162014e951b32ceacb8064596a3341c7b6e848ae7a077460e76c01930b8acf`. El repositorio de origen es el espejo público `anahatsingh-ui/options-dataset-hist` en commit `37f6c456fe1a4775c875673fb8ef907d5cd2fd66`. El archivo fuente completo posee Git blob SHA-1 `133bf1d95c3479149bf4771bc8b3fd8b625064ce`. **No se verificó independientemente el productor original de las cotizaciones ni su ejecutabilidad.** Los registros incluyen fecha, pero no proporcionan un reloj intradiario autenticado de cada bid/ask; los fills simulados al cierre son aproximaciones.

El catálogo fue congelado en GitHub antes del examen de resultados en `57d4d4ecbfa66895bc9b1a09d6c773264238c05c`; su adaptación de lectura CSV y código fuente SHA-256 `7fecde1af82f6ac6b09ec38617d9134afae2c378ce10778a3f11b6713a30a231` quedaron registrados en el preflight `8d52ec244a6883f3da19a6592a57e244d02907bd`, también antes de la ejecución económica. Se procesó un solo estudio de cinco brazos sobre **36 fechas programadas idénticas** (de las 81 sesiones se excluyeron calentamiento, fecha sin horizonte, posiciones superpuestas y el calendario que excedía 72 horas). No son cinco holdouts nuevos: es el mismo periodo de desarrollo que ya se había inspeccionado.

El universo de cada fecha de decisión exigió DTE 7-35, bid ≥0,01, ask ≤0,45, spread ≤0,20 USD/acción, |delta| 0,01–0,30, volumen ≥1, OI ≥50 y tamaños bid/ask positivos. La elección queda congelada el día D; el intento de compra al cierre D+1 sólo entra al ask +0,01 USD/acción si no supera el IOC predeterminado. Se carga 0,65 USD por contrato y lado, capital compartido, riesgo inicial total ≤0,25% de patrimonio y reservas al admitir del 12%; salida al bid −0,01 y 0,65 USD de comisión el día D+2. Un recibo de salida sin cotización utilizable registra **recuperación cero** y no se descarta. CASH también paga 1 USD por día calendario. No se modelan la prioridad real de colas, contratos asignados anticipadamente, marca intradiaria o deslizamiento contingente en crisis.

## 2. La frontera ex post (sólo diagnóstico)

En las 36 fechas había 5.248 observaciones contractuales con parámetros admitidos al cierre D y 4.282 que pudieron superar los filtros posteriores del IOC y del riesgo. Sólo en **11 de 36 fechas** algún instrumento generó una ganancia neta positiva en este modelo. El oráculo retrospectivo, que elige el ganador tras ver D+1 y D+2, computa 433,70 USD de ganancias positivas y 313,70 USD tras descontar 120 USD de coste fijo. **No es una política causal: debe excluirse de cualquier selección, entrenamiento o promoción.** Las dos mejores oportunidades explican 314,40 USD (72,5%) de aquel total positivo.

| Decisión D | Instrumento ex post | Bid D | Ask D | Ask entrada D+1 | Bid salida D+2 | PnL neto USD |
|---|---|---:|---:|---:|---:|---:|
| 2025-02-19 | PUT SPY 595, vence 26 feb | consultable en CSV | 0,40 | 0,42 | 2,14 | **+168,70** |
| 2025-01-23 | PUT SPY 593, vence 30 ene | consultable en CSV | 0,43 | 0,29 | 1,78 | **+145,70** |
| 2025-03-31 | CALL SPY 583, vence 9 abr | consultable en CSV | 0,35 | 0,43 | 0,94 | +47,70 |
| 2025-02-25 | PUT SPY 560, vence 6 mar | consultable en CSV | 0,45 | 0,31 | 0,56 | +21,70 |
| 2025-01-07 | PUT SPY 565, vence 15 ene | consultable en CSV | 0,40 | 0,31 | 0,53 | +18,70 |

*No se deduce de estos máximos una rentabilidad alcanzable sin mirar el futuro. Hay selección entre miles de opciones y días; se usa como referencia de diagnóstico, no como benchmark de selección válido.*

## 3. Qué información existía antes

Las dos mayores ganancias ex post de puts ocurrieron después de una apreciación reciente del índice SPY, seguida de un retroceso en las sesiones siguientes:

| Fecha D | Retorno SPY de las 3 sesiones anteriores | Volatilidad realizada anual de 20 sesiones | IV PUT de la oportunidad | Retorno SPY D→D+2 | ¿Seguir momentum habría acertado dirección? |
|---|---:|---:|---:|---:|---|
| 2025-01-23 | +2,04% | 14,13% | 14,17% | −1,70% | **No**: preferiría CALL |
| 2025-02-19 | +0,52% | 10,26% | 15,15% | −2,12% | **No**: preferiría CALL |
| 2025-03-31 | −1,62% | 20,55% | 16,12% (CALL) | +0,92% | **No**: preferiría PUT |

Las diferencias se conocen retrospectivamente; no constituyen un modelo capaz de prever eventos. El nivel de IV del PUT de febrero (15,15%) era *superior* a la RV20 (10,26%), de modo que no puede justificarse diciendo que la prima era inequívocamente barata con ese criterio. En el conjunto de 11 fechas con mejor oportunidad positiva, la dirección momentum acertaba 6, es decir 54,5% en una submuestra elegida por resultado; sobre las 36 fechas acertó 18 (50%). Estas frecuencias carecen de potencia y no acreditan capacidad predictiva.

La fuente primaria **Cboe Index Insights: April** (7 mayo 2025, https://www.cboe.com/insights/posts/index-insights-april/) documenta la expansión de la volatilidad y el VIX de abril tras los anuncios arancelarios. **St. Louis Fed** (https://www.stlouisfed.org/on-the-economy/2025/jun/financial-market-volatility-spring-2025) confirma la excepcionalidad histórica de los movimientos de esa primavera. Estos hechos describen el régimen *después* de las publicaciones y movimientos; no autorizan a emplearlos como etiquetas predecibles en enero o febrero. En particular, volatilidad alta no garantiza que una opción comprada a prima ya inflada gane dinero.

## 4. Pruebas causales sobre los mismos caminos y costes

| Regla congelada | Trades reales modelados | Neto USD | Ventaja sobre CASH | Máximo drawdown cierre | Mejor trade | Neto retirando mejor trade |
|---|---:|---:|---:|---:|---:|---:|
| CASH | 0 | **−120,00** | 0,00 | 0,60% | 0 | −120,00 |
| PUT a delta 0,08 (control P1) | 26 | **−5,15** | +114,85 | 0,940% | +168,70 | −173,85 |
| Momentum 3 sesiones | 26 | −368,85 | −248,85 | 1,844% | +21,70 | −390,55 |
| Volatilidad realizada 20d ≥1,2 × IV + momentum | 12 | −306,30 | −186,30 | 1,532% | −5,30 | −306,30 |
| Reversión después de |r3| ≥2% | 7 | −102,45 | +17,55 | 0,985% | +128,70 | −231,15 |

**Hallazgo negativo:** el filtro predefinido RV20/IV analizó 16 señales, efectuó 12 compras y ninguna de esas 12 produjo un resultado positivo en el diario. La reversión acertó una gran ganancia, pero su contribución queda más que anulada al retirarla. Por tanto, no hay mejora robusta en este cuatrimestre. El control PUT conserva la misma cifra terminal que N10-P1, −5,15 USD, una regresión económica útil.

**Concentración:** el resultado de PUT está dominado por la mejor campaña. El resultado de reversión también. Los meses marzo y abril fueron negativos para ambas. El supuesto de hallar repetidamente esas dos caídas con un simple umbral de momentum no supera los controles.

## 5. Auditabilidad y límites

Los balances terminales de **las cinco carteras** y los 120 asientos de cada una se reconstruyeron con un auditor independiente de aritmética Decimal a partir de cotizaciones de entrada y salida, costes y registros de cierre. Se conciliaron además **98 registros de máximos** asociados a las oportunidades diarias por tipo, contra el CSV de cotizaciones. 11 pruebas unitarias sintéticas para causalidad, ausencia de ejecución, recuperación cero, selección de fechas y conciliación fueron PASS. El código Python fue compilado. Esto **no** es una auditoría externa de los datos originales ni una validación de fills reales.

- Oráculo: conoce D+1/D+2 y no se ofrece a candidatos, selección o promoción.
- Predictor: sólo utiliza r3/RV20 de SPY hasta D y cotización del contrato en D. Sin etiquetas de mundo ni observaciones posteriores.
- Riesgo: un contrato largo, primas y comisiones financiadas, capital continuo, límites de admisión originales y 72 horas máximo. La liquidación efectiva/ejercicio americano no está modelada.
- No se abrió un periodo final, no se empleó bootstrap nominal como garantía ni se consumió presupuesto alfa prospectivo.
- N9-S / C14 y las 3.200 cuentas finales M10 permanecen fuera de este experimento. Ni broker ni órdenes ni despliegues.

## 6. Siguiente hipótesis estructural, todavía sin prueba

**H_TAIL_REVERSAL_P_Q:** estimar la probabilidad condicional de un movimiento bajista discontinuo tras avances recientes, utilizando variables disponibles antes de cada decisión (IV relativa por vencimiento, pendiente/skew de puts vs calls, tasas de cambio de volumen/interés abierto, volatilidad realizada y retorno previo). **No basta predecir la caída:** se debe cotizar el put a ask y su salida alcanzable a bid, y demostrar ventaja neta frente a CASH, el put permanente y el predictor sencillo. Un modelo de distribución física P vs precios implícitos Q debe refutarse si no supera controles fuera de muestra, con pruebas purgadas y corrección prospectiva por múltiples hipótesis.

La hipótesis está motivada por los eventos de enero/febrero **ya observados**; por tanto debe probarse en fechas distintas que no se hayan usado para ajustar decisiones. Mayo–agosto de 2025 podría servir *únicamente si ese periodo sigue sin inspeccionarse en el proceso*, con embargo por vencimiento y separación de 72 horas; queda pendiente verificar esa condición y registrar la evaluación antes de abrir resultados. No se cambia el contrato de N9-S.

**Veredicto:** `N10_P2_CAUSAL_EDGE_NOT_CERTIFIED`; oráculo positivo exclusivamente por conocimiento posterior y concentración de eventos; N10 sigue NO_GO.