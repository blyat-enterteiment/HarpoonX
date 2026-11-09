# HARPOONX — FWN9 / M11 C22: arbitraje por activo, sesión y crecimiento neto acumulado

**Estado: infraestructura de investigación aislada y probada; N9-S NO_GO.** Esta capa no genera estrategias, señales, semillas, cuentas económicas, órdenes ni conexiones con brokers. No activa automáticamente coordinador, optimizador ni políticas. Preserva los 3.200 M10 finales sellados y los fuentes económicos M9–C21.

## 1. Corrección estratégica

No hay un indicador único ni una hora universalmente "óptima". Las virtudes económicas de equity, ETF, cripto y opciones son distintas en disponibilidad, estructura de fricción, liquidez, riesgo y fuentes de PnL. Separa el calendario **en el que sería posible operar** de la validación estadística **de que realmente conviene operar**.

La política propuesta es **CASH por defecto**. Una evaluación observacional solo puede aparecer en el ranking cuando acredita procedencia OBSERVED, fills/fees documentados, relación de caja comparada, límites originales, fechas conocidas, evidencia fuera de muestra y control de multiplicidad. El ranking NUNCA genera una orden ni concede autoridad de ejecución: la procedencia declarada en un objeto de entrada sigue necesitando comprobación externa.

## 2. Matriz multicapa y las tres hipótesis prerregistradas (máximo seis variantes)

| Línea | Activos | Dos ventanas de contraste | Experimento falsable |
|---|---|---|---|
| H22_OPENING_CONFIRMATION | acciones/ETF | RTH_OPEN_30 y RTH_MORNING_30_120 | ¿La continuación de ruptura tras apertura y barra conocida gana a momentum estándar/CASH neto, sin mirar barras futuras? |
| H22_CRYPTO_UTC_LIQUIDITY | BTC/ETH elegibles | UTC_00_08 y UTC_16_24 | ¿Diferencia el net edge por bloque UTC, contrastado con UTC_08_16, fines de semana, costes de spreads e impacto? |
| H22_OPTION_ASYMMETRY_RESEARCH_ONLY | puts/calls elegibles | RTH_MORNING_30_120 y RTH_LAST_90 | ¿Tiene ventaja neta la asimetría put/call después de primas, greeks, spread, multiplier y cobertura subyacente? **Solo investigación**, ningún ejecutor de opciones admitido. |

No se prueban las seis variantes todavía. Este registro es un conjunto de **hipótesis de investigación** y sus reglas de refutación, no seis nuevas señales ni seis cuentas económicas. No hay optimización recursiva.

### Horarios reales y horarios candidatos

NYSE usa 9:30 a 16:00, horario local America/New_York; se exige calendario verificado para aperturas, cierres abreviados y feriados. No se hardcodea una diferencia fija UTC porque hay horario de verano. Cboe distingue RTH de 9:30–16:00 en opciones de acciones, algunos ETF hasta 16:15, y desde octubre de 2026 sesiones especiales GTH/Curb **solo para contratos designados**. El contrato debe aportar una comprobación explícita para su sesión, no heredar por defecto la elegibilidad de la acción subyacente. Alpaca documenta cripto 24/7; los tres bloques UTC en C22 son particiones de investigación, no horas empíricamente superiores.

Fuentes primarias: https://www.nyse.com/trade/trading-information ; https://www.cboe.com/about/hours/us-options ; https://www.cboe.com/notices/content/?id=62044 ; https://docs.alpaca.markets/us/docs/crypto-trading ; https://docs.alpaca.markets/us/docs/245-trading .

**La existencia de equity overnight 24/5 en un ATS no autoriza a C22 a negociar overnight**: disponibilidad depende de símbolo, venue, spreads, horario efectivo y órdenes elegibles.

## 3. Filtro económico adversarial y sesgos explícitos

Para un candidato observacional por clase/ventana:

    lower_net_bps =
      lower_oos_gross_alpha_bps
      - upper_round_trip_cost_bps
      - upper_market_impact_bps
      - uncertainty_buffer_bps

Solo se clasifica cuando lower_net_bps>0, límite inferior del resultado apareado contra CASH>0, ajuste familiar ya preregistrado con p<=0.025, al menos 20 días distintos y 30 trayectorias OOS, observación con knownAt<=asOf<=knownAt+5 minutos, drawdown <=8% y peor pérdida diaria <=2%. Esos mínimos son **controles de presentación de investigación**, no certificados de potencia estadística, independencia real de mercado ni valores óptimos. Fallar algún requisito => excluido y CASH.

Evitar explícitamente sesgos de look-ahead, cierre de barra visto antes de publicación, selección post-hoc de ventanas, sesgo por supervivencia, múltiples comparaciones no corregidas, inventar fills en OHLC, financiar entradas con proceeds desconocidos y comparar cripto/equity reiniciando USD20.000 por clase.

El ranking es determinista, ordenado por menor net edge demostrado y desempate de ID; no ajusta parámetros, crea hipótesis nuevas ni consume M10.

## 4. Interés compuesto: riqueza financiada neta de costes

Para una **sola cartera** con posición y caja auditadas, sin retiros ni depósitos:

    W_(t+1) = W_t + PnL_gross_t - fees_t - external_costs_t
    1 + R_compound_net = PRODUCT_t (W_(t+1) / W_t)
    LOG(1+R_compound_net) = SUM_t LOG(W_(t+1)/W_t)

La función compound exige identidad de patrimonio antes/después de cada intervalo, comisiones y costes no negativos, historial de recibos conocido antes de reutilizar caja, y ninguna transferencia externa. No suma resultados de backtests equity y cripto con capital inicial independiente. No reinicia el capital a 20.000 USD tras una pérdida.

**Fixture exclusivamente contable, NO rentabilidad de HARPOONX:** 20.000 → 21.000 (+5% neto después de gastos), después 21.000 → 20.790 (−1% neto). El patrimonio final es 20.790 USD, retorno compuesto neto = 3,95%, no 4%. Esta prueba no mide una estrategia.

La capacidad financiada requiere caja asentada, menos compromisos y saldos sin liquidar, descontando riesgo de posiciones existentes. El hard cap de N9-S sigue siendo 20.000 USD; riesgo de admisión ≤0,25% y exposición bruta de admisión ≤12%. **Una ganancia contable incrementa W pero no modifica el capital máximo permitido en el ensayo congelado.** Por tanto la implementación demuestra la mecánica del compound sin autorizar automáticamente más exposición.

La función size calcula exclusivamente cantidades hipotéticas. Las opciones permanecen bloqueadas para ejecución y ningún método envía órdenes.

## 5. Integración y evidencia

Código nuevo, sin alterar el coordinador, profit8_replay, capital inicial ni motor original:

- runtime30/fwn9_c22_session_compound.cjs — ventana DST NY, clasificación cripto 24/7 sujeta a venue, evaluación adversarial de costes, ranking, ledger compuesto y caja asentada.
- tools/fwn9_c22_session_compound_test.cjs — 19 pruebas deterministas de contratos, temporización y contabilidad; ninguna es una cuenta económica experimental.
- research/modulation11/fwn9_phase9m_c22_protocol.json — 3 hipótesis, máximo 6 variantes futuras; cero nuevas señales.
- .github/workflows/fwn9_p9m_c22.yml — pruebas y regresiones antiguas C21/C20/C16, incluida verificación Decimal-46.
- evidence/modulation11/fwn9_phase9m_c22_evidence.json — registro de resultados y límites.

La capa está aislada y NO conectada a la ruta de broker. Para futura integración se requiere cuenta conciliada y observaciones verificables con costes, fills y relojes realmente alcanzables. C21 refutó equivalencia exacta OHLC STOP-FIRST versus ocho primeros cruces; C22 no la modifica ni reinterpreta resultados anteriores.

## 6. Decisión

Horarios negociables acreditados, pero rentabilidad superior de cualquiera de estas ventanas NO demostrada. Sin prueba económica prospectiva, reparto de costes, distribución completa de estados stop/target, cota poblacional admisiones y ejecución alcanzable, no corresponde abrir el holdout ni reanudar la búsqueda automática.

**C22: verificador offline read-only aprobado. N9-S NO_GO; 3.200 cuentas finales M10 selladas; cero nuevas semillas, señales, cuentas económicas, órdenes, despliegues, fusiones o reinicios recursivos.**

Control de precisión C22: la cantidad cripto se redondea hacia abajo al incremento explícito permitido, y se comprueba que la cantidad multiplicada por precio y riesgo no exceda los límites de la capacidad financiada. Un contraejemplo de saldo de 0,0000999 USD frente a lote de notional mínimo 0,0001 USD produce cantidad cero, nunca una compra sobregirada. Este control adicional no autoriza órdenes.

## 7. C22 R2 — optimización de crecimiento geométrico prudente, no maximización del porcentaje de aciertos

Para una apuesta de pago binario *hipotética* con probabilidad inferior p, ganancia neta por USD comprometido g (cota inferior) y pérdida por USD comprometido l (cota superior), la utilidad esperada conservadora es

    G(f) = p * ln(1 + f*g) + (1-p) * ln(1-f*l)
    f_Kelly = max(0, [p*g-(1-p)*l] / [g*l])

Se restan los costes superiores de g y se añaden a l antes de resolver. La función geometricFraction aplica medio Kelly, limita por **el notional admitido <=12% de patrimonio congelado**, por la caja liquidada y por riesgo por operación <=0,25% de patrimonio. Una apuesta sin ventaja conservadora obtiene f=0 (CASH). No maximiza aciertos ni retorno bruto, sino log-crecimiento bajo las hipótesis explícitas.

Este cálculo **solo acepta como argumento** una cota de pérdida de cola y una verificación externa de ejecutabilidad: los stops OHLC originales NO son cotas de pérdida alcanzables, como acreditó C21. Esas banderas de entrada son afirmaciones del consumidor, no autenticaciones criptográficas realizadas por C22; el resultado jamás autoriza una orden. La dependencia conjunta entre múltiples activos no está demostrada, por lo que no se agregan múltiples Kelly como si sus riesgos fueran independientes.

La fórmula binaria es una sensibilidad conservadora del diseño, **no** un rendimiento futuro estimado de HARPOONX, y no equivale al óptimo universal en distribuciones de retornos no binarias o con riesgo de gaps no acotados.
