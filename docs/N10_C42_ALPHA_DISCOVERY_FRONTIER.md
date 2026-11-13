# HARPOONX — N10, protocolo de descubrimiento de alfa y crecimiento compuesto

## Hallazgo que cambia la prioridad

La protección de compra/stop tiene una capa C38 reproducible,
pero NO está certificada como límite real de pérdida: un gap,
rechazo, suspensión o stop-limit cripto puede impedir el fill.

C41 probó una sola estrategia previamente congelada, momentum5 +
RVOL10 >= 1.25 + 5×5 + trailing −2, sobre **179 nuevas barras**
octubre–noviembre de Alpaca (555 incluyendo 376 de calentamiento):
**una operación modelada, −10.783784 USD netos modelados**,
**−0.12542665 pb/día log**, frente al N9-S congelado de +1 pb/día.
El comparador momentum sin RVOL perdió −52.499318 USD modelados.
La diferencia +41.715534 USD solo evita pérdidas modeladas,
no genera rentabilidad.

Por tanto, el problema N10 no es extender la protección: es **alfa
rentable que se repite a través de activos/regímenes, se captura
con costes/recibos alcanzables y hace crecer una cartera conjunta**.

## N10 debe ser una especificación más exigente, no rentabilidad prometida

N10 no puede acreditar GO si N9-S sigue NO_GO. No existe una
escala universal 1–10 para la rentabilidad financiera. PROPUESTA
de aceptación N10 nueva, a preregistrar antes de cualquier muestra nueva:

1. **N9 ya probado:** criterio original +1 pb/día de ventaja
   log neta, CASH y ORIGINAL, comparación múltiple corregida
   FWER=0.025, una cartera y procedencia causal con fills reales.
2. **Repetibilidad:** dos cohortes prospectivas independientes o
   secuenciales sin solapamiento, con parámetros congelados
   y el mismo estimando económico. No se cuentan backtests antiguos.
3. **Aporte de activos/estrategias:** contribución neta al log
   riqueza de cada libro y tasa de oportunidades/espera, sin atribuir
   ganancias simuladas a brazos no ejecutados.
4. **Concentración:** robustez adversarial al eliminar la mejor
   operación, subir costes, gaps, rechazos, fills parciales,
   liquidación tardía y shocks de correlación. Los umbrales
   cuantitativos para N10 han de registrarse PRIMERO, no derivarse
   del resultado que se va a juzgar.
5. **Capacidad y compounding:** dinero de una cartera física
   continuo, riesgo por entrada ≤0.25%, gross en admisión ≤12%,
   plazo ≤72h; beneficio acumulado aumenta el patrimonio, pero
   la base dura de admisiones permanece como máximo 20k USD
   bajo el contrato original.
6. **Integridad externa y control:** identificadores de fuente
   nativa, recibos de Alpaca, presupuesto económico de comisiones,
   factura de gastos y prueba independiente del tiempo/preregistro;
   no basta una firma propia GitHub o un precio OHLC.

## Matemática del núcleo ganador

Para activo i, estrategia k y duración h:

    alpha_net_ik =
        E[R_bruto_ik | features knownAt <= decision]
        - E[fee + spread + slippage + impact + missed fill + carry]
        - penalty_uncertainty

Más que maximizar el índice de aciertos, se persigue crecimiento
geométrico neto financiado:

    maximize min_{P in uncertainty_set}
        E_P[log(1 + sum_i w_i * net_R_i)]
        - lambda * CVaR_p(loss_of_funded_wealth)

sujeto a caja asentada, reserva IOC, 12% gross original en
admisión, 0.25% riesgo por entrada, vencimiento ≤72h y
salidas pendientes confirmadas; CASH es elección legítima.
Las colas, WEAK, estimaciones, slippage y costos de cancelación
exigen cotas auditables, no supuestos paramétricos alegres.

**El objetivo es diseñar una incubadora de predictibilidad
condicional y monetización.** Se separan cuatro experimentos:

- **A: entrada temprana:** señal de régimen/ruptura volumen
  antes de un salto favorable, con reloj causal y sin high futuro.
- **B: duración del alfa:** momentum vol + RVOL como variables
  continuas calibradas, sin fijar umbrales en un periodo ya explorado.
- **C: continuación de los ganadores:** trailing2 vs salidas
  ajustadas a vida media del predictor, sin relajar el stop
  original hasta probar equivalencia de riesgo.
- **D: monetización:** impacto de fees/colas/límites maker,
  costo de espera, omisiones y exposición compartida.

Una corrida futura elegirá una sola política preregistrada.
Las familias A–D requieren multiplicidad corregida e informes
de todas las variantes descartadas: no solo conservar la ganadora.

## C42: medición del potencial perdido sin contaminación

`research/n10_frontier/diagnose.py` reconstruye la entrada
C41 EXACTA (no modifica señales). Luego mide un **techo oracular**
que mira el HIGH posterior en cada ventana de hasta 72h,
reportando potencial por activo y cuántos objetivos +1..+5
niveles se habrían tocado. Etiqueta explícitamente:
- `oracle_* = FUTURO`: solo diagnóstico, nunca señal ni fill;
- mismo bar tocando STOP y TARGET => orden causal desconocido;
- un modelo stop-first conserva prudencia, pero **sin** fill
  broker real no hay rentabilidad certificada;
- señales RVOL vs sin RVOL se comparan sin reoptimizar RVOL;
- cada insumo tiene hash Git SHA + salida SHA de auditoría.

El objetivo diagnóstico no es afirmar que un ATH era vendible:
es identificar si la mayor pérdida de alfa vino de **entrar tarde**,
**salir prematuramente**, **pagar fricciones** o **restringir capital**.
Una diferencia ORACLE menos PnL real NO es una ganancia capturable.

### Presupuesto económico objetivo sin falsos positivos

C41 termina ~19989.22 USD; llegar al objetivo teórico N9 de
~20086.19 USD al día 43 exige ~96.97 USD adicionales.
Si se pretendiera lograrlo en una sola posición de 800 USD,
se necesitaría ~1212 pb (12.12%) de rendimiento NETO adicional
sobre esa posición. NO se infiere que haya posibilidad real,
ni se cambia el límite 4% del estudio para crear una solución ficticia.

Para N10 necesitamos múltiples oportunidades con margen económico
efectivo, no una operación perfecta con 12% neto en 72 horas.

## Decisión de investigación y próximas puertas

**Fase N10-A**: mapa de MFE/MAE alcanzabilidad, por activo y trigger,
atribución de alpha-capture y costes, dos relojes knownAt, prueba
con OHLC etiquetado oracle/fill modeled.

**N10-B**: modelos cortos de probabilidad condicional del recorrido,
con validación walk-forward purgada y embargo hasta 72h, sin tocar
C29/M10. Baselines sencillos CASH, momentum, breakout, RVOL y original
nativo; no entrenar con "mayor futuro" de la validación.

**N10-C**: paridad real con recibos de Alpaca y cuenta continua,
incluidos no-fills, estrés fee y salida protectora; opciones
solo shadow hasta certificar ejercicio, liquidación y costes.

**N10-D**: preregistro independiente y prueba prospectiva
con bloques/estadístico familiar congelados. N9-S primero;
N10 solo si todas las puertas superiores pasan.

## Evidencia y estado

La muestra C41 es mercado observado pero histórico y sus entradas
son **fill modelados**. C42 no abre el holdout M10 ni cuenta alpha
económica nueva. Cambios exclusivamente en investigación, ninguna
orden, despliegue, promoción a N9/N10 o modificación del origen M9.

Fuentes matemáticas primarias:
- Gârleanu & Pedersen, *Dynamic Trading with Predictable Returns
  and Transaction Costs*, Journal of Finance (2013):
  https://www.nber.org/papers/w15205
- Bailey & López de Prado, *The Deflated Sharpe Ratio* (2014):
  https://doi.org/10.3905/jpm.2014.40.5.094
- Bailey et al., *Probability of Backtest Overfitting*:
  https://escholarship.org/uc/item/4w1110bb

**N9-S NO_GO. N10 NO_GO.**
