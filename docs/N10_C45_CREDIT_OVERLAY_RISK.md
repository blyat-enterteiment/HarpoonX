# N10 C45 — Coberturas bajistas y primas de iron condors (investigación aislada)

**Estado:** N9-S NO_GO, N10 NO_GO; cero órdenes, despliegues, fusiones y acceso a las
3.200 cuentas finales M10. Rama de investigación independiente de la
congelación C44 para no contaminar el protocolo de mayo–agosto de 2025.

## Dos trabajos económicos diferentes

1. **Protección bajista:** put de débito o spread bajista de débito
   (C43, long put / bearish put vertical) pueden pagar cuando
   el subyacente cae. La prima y los derechos/obligaciones de
   acciones, el basis y el ratio de contratos deben estar
   financiados. No toda put es una cobertura eficiente o barata;
   puede vencer sin valor y consumir capital.
2. **Ingresos por volatilidad y lateralidad:** short iron condor,
   short iron butterfly. Se cobran primas y se asume el riesgo
   de movimientos extremos. **No son seguro de cartera contra
   caídas.** Ante un crash, equity largo e iron condor pueden
   sufrir pérdidas al mismo tiempo. Prima cobrada no es PnL
   realizado, y hasta el cierre la exposición continúa.

### Selector N10: régimen condicionado, no una orden

Indicadores del subyacente cerrados antes de la decisión:
`RVOL10`, momentum5, IV ATM, volatilidad realizada 20 barras.
Hipótesis C45 registrada antes de muestras nuevas:

- IV>=1,20*RV20; RVOL<=1,25 y |momentum5|<1%:
  evaluar **iron condor y butterfly** como hipótesis de venta
  de volatilidad, comparar contra CASH/ORIGINAL y spreads.
- Momentum5<=−1% con RVOL>=1,25:
  estudiar **put debit vertical** para protección; el mercado
  bajista no autoriza simultáneamente vender un condor.
- Otros regímenes: CASH/no abrir nuevas estrategias de primas.
- Ni IV>RV ni theta positivas acreditan P(TP antes de STOP).
  Es una heurística de research NO calibrada, refutable por datos.

Todos los precios deben tener reloj knownAt, cuatro quotes
sincronizados, mismo vencimiento, mismo subyacente, derechos
CALL/PUT, multiplicador y condiciones contractuales OCC.
C43 bloquea adaptaciones no estándar y cuotas vencidas.

## Payoff y financiación de un iron condor

Cuatro patas con `KpL < KpS < KcS < KcL`:

- Comprar put exterior `KpL`, vender put interior `KpS`.
- Vender call interior `KcS`, comprar call exterior `KcL`.
- Todas con mismo vencimiento y multiplicador 100.

`C = bid(Pshort)+bid(Cshort)-ask(Plong)-ask(Clong)` es el
crédito por acción según cotizaciones observadas; no se
sustituyen por midpoint ni por valores teóricos.

```
ganancia_max_al_vencimiento = 100*n*C - 8*n*fee_por_pata_y_lado - otros
pérdida_max_contractual_al_vencimiento =
    100*n*max(KpS-KpL,KcL-KcS) - 100*n*C + comisiones
BE_inferior = KpS - (C - comisiones/(100*n))
BE_superior = KcS + (C - comisiones/(100*n))
```

Para butterfly `KpS=KcS`. Es una estructura
más concentrada alrededor del centro, que usualmente
sacrifica amplitud de beneficio a cambio de más prima.
Estas fórmulas caracterizan el **payoff al vencimiento
contractual** bajo expiración/liquidación normal; NO una
cota garantizada del riesgo de ejercicio/asignación
de opciones americanas o de liquidación forzada.

**Ejemplo completamente sintético** con wings de 1 USD,
crédito 0,60 USD por acción y 5,20 USD de gastos
totales: ganancia tope al vencimiento = 54,80 USD y
pérdida máxima contractual al vencimiento = 45,20 USD.
Cabe en el presupuesto de riesgo original por entrada
50 USD sobre 20.000 USD, *pero* una pata corta SPY
con strike cercano a 760 puede crear exposición
intradía de ~76.000 USD a 100 acciones, sin
garantía de compensación instantánea de las demás patas.
No se autoriza la operación.

## Ejecución y asignación

Alpaca tiene soporte de opciones Level 3 y órdenes
multileg (estructura atómica) sujeto a autorización
de la cuenta. Tener una orden multileg no elimina
riesgo de asignación anticipada **después del fill**,
ni garantiza el precio de cierre. Para SPY americano
hay dividendos, ejercicio temprano, pin risk, evento
de asignación y entrega física. Se requiere un ledger
de 100 acciones por contrato, cuentas/reservas y
reconciliación de recibos y cargos.

Alternativa **XSP europeo y liquidado en efectivo**:
puede simplificar la exposición por asignación y
entrega física, pero exige contrato exacto, horarios
de cierre, OPRA y validación broker-specific.
No se hereda ese atributo por el símbolo, y no se
probará con la muestra SPY física.

## Interfaces implementadas (read-only)

- `quant/harpoon_quant/options_credit_hedge_overlay.py`
  - `select_research_structure(Regime)`: decide solo
    qué familias deben investigarse, nunca qué operar.
  - `credit_risk(CreditFourLeg, Book, Expenses)`: valida
    las cuatro patas, strike, bid/ask, griegas y reloj,
    crédito neto, riesgo de expiración, límites de
    20k/12%/0,25%/72h y colateral por asignación
    independiente. No acepta créditos ficticios.
  - `expiry_payoff(..., spot_at_expiry)`: PnL mecánico
    terminal bajo escenarios declarados, no fills.
  - `exit_72h_european_proxy(...)`: sensibilidad analítica
    BSM europea al spot, IV y theta ≤72h, con
    bid/ask estimados. No representa prima americana
    ejecutable ni probabilidad de first passage.
  - `cohort_identity(...)`: SHA-256 exacto de posiciones,
    presupuestos y costes para reproducibilidad.
- `quant/tests/test_n10_credit_hedge_overlay.py`:
  pruebas de max loss, ganancia, crash, butterfly,
  financiación compartida, falla de recibos y fuentes
  y casos de reloj/futuro.

Esta política no modifica C44 ni C43; C43 mantiene
las puts y verticales de débito como investigación,
C36 sigue bloqueando opciones en ejecución y
N9-S/N10 siguen NO_GO.

## Calibración necesaria para que un ingreso de prima sea alfa

Se requieren **cotizaciones históricas intradía
de las cuatro patas y subyacente**, IV/vega/theta
con timestamps, comisiones, faltas de fill,
asignación y dividendos. Un solo snapshot indicativo
es insuficiente para medir la probabilidad de que
`mark_to_market >= TP` antes de `loss <= stop` en
72 horas; tampoco identifica la probabilidad de
ejercicio inesperado. El ajuste del overlay exige
observación prospectiva comparada con CASH,
SPY subyacente, put debit spread, C22 ORIGINAL
y el simple RVOL momentum C41, de una sola
cartera física cuando corresponda.

Los 817.348 snapshots EOD de SPY Jan–Apr 2025
registrados en la investigación N10 previa
sirven para desarrollo, pero **no para
certificar first passage intradía**. Además,
su procedencia no está autenticada por bolsa.
Un estudio C44 tiene ya reglas congeladas:
C45 queda separado y no cambia ese test.

### Fuentes primarias

- [OIC / OCC — Short iron condor](https://www.optionseducation.org/strategies/all-strategies/short-condor)
- [Cboe — Strategy Guide](https://cdn.cboe.com/resources/options/Trading_Strategies.pdf)
- [Alpaca — Options Level 3](https://docs.alpaca.markets/us/v1.4.2/docs/options-level-3-trading)
- [Alpaca — Index options XSP/SPX](https://docs.alpaca.markets/us/docs/index-options)
- [Alpaca — Risks of Level 3](https://alpaca.markets/support/what-risks-should-you-consider-before-using-level-3-options-trading)
