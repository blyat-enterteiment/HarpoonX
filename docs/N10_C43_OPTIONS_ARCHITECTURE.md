# HARPOONX N10 — C43 Options Shadow Desk (calls, puts y verticales de débito)

## Estado y propósito

**Implementado en rama de investigación, no en el ejecutor.**
`N9-S = NO_GO`, `N10 = NO_GO`. No se crearon órdenes PAPER/LIVE,
posiciones, ejercicio, asignaciones, cambios a M9/C22/C29 ni entradas M10.
La matriz actual de C36 rechaza opciones en ejecución; esta capa
NO elimina ese veto. Su integración es de **información y simulación
económica**, no de órdenes.

C42 estudia oportunidades del **subyacente**. C43 traduce una
tesis con sentido direccional y reloj knownAt a una evaluación de
contratos, pero no convierte un movimiento del subyacente en alfa
de primas ni en una compra automática.

## Arquitectura implementada

```text
C42/C36: señal subyacente + RVOL + régimen + knownAt
     │
     ▼
C43: términos OCC, corporate actions, bid/ask, IV y griegas
     │  ↳ feed indicative ⇒ SOLO investigación
     │  ↳ OPRA tampoco prueba fill sin recibo broker
     ▼
Selector económico: long call / long put / debit call vertical /
                    debit put vertical
     │
     ├─ costo realista de entrada (ask largo, bid corto)
     ├─ spread de salida, fee entrada+salida, IV/Theta/Gamma
     ├─ estrés Monte Carlo / escenarios conjuntos suministrados
     ├─ pérdida máxima contractual de prima+fees
     ├─ 20k capital compartido, admisión ≤12%, riesgo ≤0,25%
     ├─ ejercicio/assignment americano y exposición en acciones
     └─ CASH obligatorio ante cualquier falta de evidencia
     │
     ▼
OPTIONS_SHADOW_ONLY → no orders, no fills, no N9/N10 GO
```

### Componentes de software

- `quant/harpoon_quant/options_shadow_desk.py`: símbolos OCC,
  vencimiento, strike/1000, dirección call/put, cantidad, multiplicador,
  quotes bid/ask, fechas, griegas, IV, cuatro estructuras con payoff
  de débito, coste total, caja y riesgo.
- `quant/harpoon_quant/options_shadow_portfolio.py`: múltiples
  estrategias comparten **una sola cartera** y un presupuesto de
  caja/riesgo; bloquea múltiples estrategias del mismo subyacente
  y escenarios desalineados.
- `research/n10_options/observed_indicative_SPY_2026-11-13.json`:
  **16 contratos SPY** indicativos (8 calls, 8 puts) al 18/dic/2026
  leídos del conector Alpaca, con sellos temporales, bid/ask, IV y
  griegas. No OPRA. El manifiesto `source_manifest.json` guarda
  SHA Git del archivo y documenta que el número de registros devueltos
  no equivale necesariamente al límite solicitado.
- `quant/tests/test_n10_options_shadow_desk.py` y
  `quant/tests/test_n10_options_shadow_portfolio.py`: pruebas
  adversariales de contratos, riesgo, causalidad, probabilidades,
  cartera, quiebra de caja y origen de datos.

## Reglas cuantitativas, sin fundamentales

Para cada ticker de subyacente que cumpla la señal causal,
una call larga se estudia ante dirección BULL y una put larga
ante dirección BEAR. También se estudian verticales de débito:
call spread larga de strike inferior y corta de strike superior;
put spread larga de strike superior y corta de strike inferior.
Mismo subyacente, vencimiento, tipo y multiplicador en cada vertical.
NO naked short, ratio spreads, credit verticals, iron condors, ni
ejecución de multi-leg. Una política put requiere señal bajista
independiente, no un supuesto de simetría de una señal alcista.

**Dinero real dentro del modelo de un contrato estándar:**

    entry_debit_usd = 100 × (long_ask - short_bid)
    fees_roundtrip = fees_open + fees_close + other_fees
    max_loss_contrato ≈ entry_debit + fees_roundtrip
    max_profit_spread_at_expiry =
         100 × (strike_width - debit_per_share) - fees_roundtrip

No se presume que `max_loss_contrato` incluya todos los efectos
operacionales de **asignación temprana**: una vertical short leg puede
convertirse en exposición de 100 acciones mientras la long leg no
se ha ejercido o cerrado. El módulo registra:

    required_share_delivery_cash =
        100 × max(strike de los contratos) × cantidad
        + buffer_operativo

Esto es una exigencia de liquidez de estrés, no necesariamente
la margin requirement real del broker. Una call larga ITM puede
ejercerse y requerir compra de 100 acciones; una put larga puede
requerir entrega de acciones y generar exposición corta.
No se adjudican fills ni se permite un GO con ejercicios sin
validar. En SPY strike 760, una entrega de 100 acciones puede
suponer del orden de 76.000 USD, por encima de una cartera de
20.000 USD.

La admisión en investigación replica el contrato congelado:

    base = min(equity_observado, USD 20000)
    gross_disponible = max(0, .12 × base − gross_existente)
    riesgo_disponible = max(0, .0025 × base − riesgo_reservado)
    cash_disponible = max(0, asentado − comprometido − no_asentado)

Se acepta una estructura como **investigación con prima financiable**
solo si el débito está dentro de cash, gross y 4% por candidato,
y la pérdida contractual más gastos está dentro de los 50 USD
de riesgo original sobre 20.000 USD. Se requiere además
financiación independiente para la posible entrega de acciones,
sin que eso autorice ejecución. La mayoría de calls/puts largas
con prima superior a 0,50 USD por acción no pueden superar
el límite original de riesgo de 50 USD para un solo contrato,
incluso sin considerar gastos.

### Escenarios y probabilidades

`scenario_economics()` usa una aproximación analítica **Black–Scholes
europea**, con dividendos y tipos explícitos, SOLO para explorar
sensibilidad a `S`, `sigma`, transcurso de hasta 72h y spread.
Las opciones estándar SPY son americanas: Black–Scholes
europeo **no valora correctamente el derecho de ejercicio
anticipado ni el evento de asignación**. El precio de liquidación
futuro no es observable ni se presume relleno.

Cada shock aporta un ID de escenario, probabilidad suministrada,
cambio del subyacente y variación absoluta IV; la suma de pesos
debe ser 1. Se reporta el PnL agregado bajo cash book único,
la peor pérdida de los escenarios y probabilidad positiva
`USER_ASSUMED`, **nunca** la probabilidad real de alcanzar
take profit antes que stop. Para calibrar
`P(TP antes de SL)` hacen falta trayectorias intradía de la propia
prima y del subyacente, con relojes y cotizaciones ejecutables;
no pueden obtenerse de una cadena aislada.

## Resultado de la muestra indicativa SPY, 13 de noviembre de 2026

Ejecuté el analizador de riesgo sobre las **16 cotizaciones indicativas
originales** (8 calls + 8 puts, 18/dic/2026) recibidas del conector
Alpaca. Bajo 1 contrato estándar de 100 acciones, gastos supuestos
de 0,50 USD por pata y lado más 1 USD extra, los **desembolsos de prima
más costes** de las calls/puts largas van de **994 a 1.803 USD**.
**Ninguna de las 16** respeta el máximo original de 50 USD
de riesgo por entrada ni tiene la obligación potencial de entrega
de acciones plenamente financiada por 20.000 USD.

Es una constatación de restricciones y fuentes **indicativas no
ejecutables**, no recomendación de compra/venta ni estimación de
alfa. Se mantiene abierta únicamente la posibilidad de analizar
verticales de débito de prima baja: aun así la asignación americana
de pata corta y la entrega pueden exceder la caja; por ello el
desk conserva autorización de órdenes FALSE.

## Datos y advertencias documentadas por los emisores

El feed de opciones indicativo de Alpaca es gratuito, pero las
cotizaciones son derivadas/modificadas y los trades están
retrasados; la referencia real consolidada OPRA necesita
derechos correspondientes. No debe tratarse el precio indicativo
como BBO alcanzable. Las opciones sobre acciones estándar de OCC
representan típicamente 100 acciones, pero las corporativas pueden
producir deliverables ajustados: por ello la arquitectura
descarta versiones no estándar o no comprobadas.

Fuentes primarias:
- Alpaca Option Chain:
  https://docs.alpaca.markets/us/reference/optionchain
- Alpaca Historical Option Data:
  https://docs.alpaca.markets/us/docs/historical-option-data
- OCC Equity Options Product Specifications:
  https://www.theocc.com/clearance-and-settlement/clearing/equity-options-product-specifications
- OCC Expiration Pricing Considerations:
  https://www.theocc.com/market-data/market-data-reports/series-and-trading-data/expiration-pricing-considerations
- OCC Characteristics and Risks of Standardized Options:
  https://www.theocc.com/company-information/documents-and-archives/options-disclosure-document

## Para conectar opciones realmente al N10

1. Verificar contrato/deliverable/corporate actions a partir de
   referencia oficial y contrato broker; no confiar solo en OCR
   del símbolo OCC.
2. Integrar OPRA (según entitlement) y reloj de quote/bid/ask
   conocido antes de decidir; una cadena indicative solo shadow.
3. Modelar american exercise/assignment, dividendos ex-date,
   liquidación en acciones, vencimiento y pin risk, incluyendo
   swaps de multiplicador o entregables no estándar.
4. Integrar C25/C26/C35 con recibos auténticos de órdenes multi-leg
   y de sus fill parciales; asignación de prima, fee, cash,
   cash/reservas y reinicio en un ledger único.
5. Estimar probabilidad `TP antes que SL` por trayectorias
   del mercado de opciones intradía, validación walk-forward
   purgada con embargo y sin optimizar sobre los casos finales M10.
6. Comparar el desk de opciones contra comprar el subyacente,
   CASH y ORIGINAL con same-book wealth y costes completos.
7. Registrar fuera de muestra un nuevo estudio independiente;
   recién después, revisión de N9 y posteriormente N10.

**No está implementada aún esa conexión con OPRA ni el ejecutor.
Opciones permanecen fuera de ejecución; no se concede GO.**
