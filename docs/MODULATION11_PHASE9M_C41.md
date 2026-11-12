# HARPOONX M11 C41 — UNA política candidata y puerta financiera N9

## Decisión definitiva

**El siguiente experimento no optimizará otra vez 1.250 variantes.**
Congelamos una única hipótesis de investigación (C41):

**MOMENTUM5 + RVOL10 ≥1,25 + grid con veto −2Δ + trailing
armado en +2Δ + sin límite superior de take-profit + 72 horas
máximo.**

C41 es una **NUEVA hipótesis prospectiva**, seleccionada DESPUÉS
de conocer el trimestre C40, NO una victoria histórica validada.
Se ensayará con una sola cartera y controles CASH y ORIGINAL.
No se añadirá como séptima variante a la distribución ORIGINAL
C29 ya congelada; requiere su propio protocolo independiente.
El experimento N9-S previo de ocho brazos sigue intacto.

El código `research/n9_c41/champion.py` es puro, determinista,
sin conexión a brokers, sin señales aprobadas para ejecución,
sin órdenes y sin habilitación para trading PAPER/LIVE.

## La cifra que impide anunciar GO hoy

El archivo C40 original (`c40_rvol_report.json`) identifica
**1.250 hipótesis exploratorias** durante julio-septiembre de 2026.
La combinación que destacó entre esos ensayos tuvo, solo en
septiembre retrospectivo:

- 4 operaciones históricas **MODELADAS**, 0 fills de Alpaca.
- PnL después de costes asumidos: **+13,282176 USD**.
- Costes de ida/vuelta modelados: **17,705223 USD**.
- Crecimiento log estimado: **+0,221296 pb por día**.

El objetivo congelado de N9-S es **>1 pb/día de crecimiento log
neto sobre los comparadores, con prueba poblacional corregida
(familywise α=0,025), no meramente una media positiva**.
En USD 20.000 y 30 días, 1 pb/día sostenido equivaldría a
20.000*(exp(30×0,0001)-1) ≈ **60,09 USD**. La muestra C40
no alcanza ni siquiera esa referencia aritmética y tampoco
tiene un comparador ORIGINAL auténtico.

El artículo *The Deflated Sharpe Ratio* de Bailey y López de Prado
explica por qué seleccionar la mejor estrategia de cientos/miles
de backtests sesga al alza su rendimiento:
https://doi.org/10.3905/jpm.2014.40.5.094

## Trigger exacto sin fuga temporal

Todas las fuentes son barras **cerradas** y cotizaciones
efectivamente conocidas antes de decidir:

    rvol10 = volumen_cierre_actual /
             media(volumen_10_barras_cerradas_previas)

    momentum5 = cierre_ahora / cierre_5_barras_atras - 1

    elegible =
        witness_prefiltro_nativo
        AND broker_caja_inventario_reservas_reconciliados
        AND quote_bidask_fresco
        AND pronóstico_inferior_calibrado_sin_mirar_resultado
        AND RVOL10 >= 1.25
        AND momentum5 > (1% equity/ETF; 2.5% crypto)
        AND importe_finado > 0
        AND contribución inferior a cartera supera
            [1 pb/día × horizonte + 0,25 pb buffer]

Las fuentes IEX y Crypto US NO constituyen NBBO universal.
Un objetivo debe superar comisión, spread, impacto, slippage
y coste de oportunidad medido. Maker no se presume ejecutable.
La tabla crypto oficial muestra 25 pb taker por lado
en el primer tramo: https://docs.alpaca.markets/us/docs/crypto-fees

## Take-profit sin liquidar prematuramente

Precio de referencia a partir de un **fill de entrada confirmado**;
no se reancla por cotizaciones subsecuentes. El precio de
parada inicial es entrada−2Δ, con Δ fijo desde los datos
preentrada: tick, ATR cerrado/4, 2×spread y coste completo.
Se protege desde el inicio y se mantienen las salidas nativas.

Al alcanzar el BID entrada+2Δ, se arma trailing y se
eleva el stop a `max(stop_viejo, máximo_BID_conocido−2Δ)`.
El stop puede superar el precio de entrada más las comisiones
solamente si el mercado ha recorrido lo suficiente; un
break-even económico no se presume garantizado antes.
Las subidas +3Δ, +4Δ o +5Δ **NO disparan por sí mismas**
ventas parciales: mantienen el trailing sin tope superior.
La posición requiere intención de salida protectora ante
cruce de stop o plazo absoluto de 72h, pero **ese estado
NO prueba un fill**, sobre todo en stop-limit cripto.

Se mantienen los límites históricos de capital: base
`min(NAV_real_observado, USD 20.000)`, admisión 12% gross,
0,25% de riesgo, hasta 4% por candidato solo en investigación.
No se altera el límite duro al capital mediante compound;
el NAV acumulado sí persiste en un libro continuo y no se
reinicia en cada operación. Cambiar el límite de admisión
para multiplicar el capital requeriría otro protocolo.

## Puerta financiera (no confundirse con CI)

**C41 no puede autoemitir N9-S GO** incluso con campos
de metadatos configurados en `true`. El dictamen requiere:

1. **Prerregistro externo** de una política nueva, con
   hash de fuente, datos y contrato, antes del primer evento
   futuro; sin abrir holdout M10.
2. Productor y universo C32/C27/C28 de oportunidades
   prefiltradas con recepción `knownAt` verificable.
3. Recibos de cuenta C25 y WebSocket C35 de PAPER
   efectivamente observados, horarios causales y
   reconciliación total de fills/fees/órdenes parciales/
   inventario/efectivo.
4. Una sola riqueza financiada continua. Prueba futura
   contra CASH y ORIGINAL, intervalos de hasta 72h,
   bloques sin contaminación, costes completos.
5. **Cota inferior sobre el exceso log neto > 1 pb/día**
   frente a ambos comparadores, multiplicidad corregida
   al α=0,025 congelado y certificación de una auditoría
   independiente. La cantidad de datos debe aportar
   potencia suficiente; cuatro operaciones no bastan.
6. Solo después: nueva revisión de política y una
   autorización humana **por separado** para pasar de
   observación a órdenes PAPER. Una aprobación de inversión
   REAL sigue siendo un escalón distinto, no implícito.

C41 no interpreta booleanos autodeclarados como pruebas
de registro independiente o autenticidad del broker.
Su función de lectura `evidence_gate` puede señalar
`externally_reviewable` pero devuelve siempre
`financial_GO=false` y `N9S=NO_GO` hasta corroboración
externa; jamás envía órdenes.

## Falsación y coste de oportunidad

El valor de C41 debe medirse frente al mismo CASH y ORIGINAL.
Si el stop −2Δ evita pérdidas pequeñas pero destruye la
cola de grandes ganadores, la hipótesis pierde. Si RVOL1,25
filtra operaciones rentables más de lo que ahorra en
fricciones, pierde. Si el coste de la liquidación forzosa
stop-limit supera el margen de alfa, pierde.

**Sin más optimización retroactiva sobre julio-septiembre 2026.**
No hay GO financiero observado. No se exponen credenciales,
no se ejecutan órdenes, no se altera main ni la reserva de
3.200 cuentas finales M10.
