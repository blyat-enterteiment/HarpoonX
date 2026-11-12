# HarpoonX M11 C38 — cinco niveles y veto persistente de compra en −2

**Rama aislada basada en C36 seguro para M9. No altera el ejecutor
operativo, no instala ninguna estrategia, no genera órdenes ni llena
posiciones.** N9-S NO_GO, 3.200 cuentas finales M10 selladas.

## Hallazgo forense

El módulo histórico `quant/harpoon_quant/virtual_net.py` representa
*celdas alternativas de intención de compra* y las consolida por símbolo.
Tiene comprobaciones de coste y riesgo pero NO materializa una malla
persistente con cinco precios superiores y cinco inferiores alrededor
de un precio de referencia de Alpaca.

C36 es un filtro multiactivo por señal, tampoco una malla física de
stop. C38 implementa esa capa faltante sin reescribir el código
nativo M9 (archivo `runtime30/plugins.js` permanece congelado).

## Definición exacta — dos pasos, no dos dólares

Para un precio de referencia recibido P0, ATR de barras cerradas,
spread observado, tarifa, fricción hipotética y tick:

    Delta = tick * ceil(max(
      tick,
      ATR_cerrado / 4,
      2 * (ask - bid),
      P0 * costo_ida_vuelta_bps / 10000
    ) / tick)

Los once niveles virtuales son P0 + k × Delta, con k = -5, -4,
-3, -2, -1, 0, +1, +2, +3, +4, +5. El nivel −2 bloquea
toda compra si el **BID conocido** se encuentra en o por debajo
del umbral. No importa que un pronóstico estadístico sea favorable.

- **Sin posición:** veto de nueva entrada en k≤−2.
- **Orden de compra pendiente:** exigir cancelación/reconciliación y
  conservar su reserva hasta ACK; nunca afirmar que se canceló.
- **Posición existente:** su nivel protector se calcula sobre el
  **precio efectivamente ejecutado**, no sobre un nuevo P0 arbitrario:
  stop_virtual = precio_entrada_confirmado − 2 × Delta_congelado.
  Si el bid cruza el umbral, se marca salida urgente requerida, **no fill**.
- **Rebote inmediato:** el veto está enclavado; no se desbloquea
  porque el precio haya recuperado 1–2 niveles.
- **Rearme:** exige nuevo grid/generación, dos barras cerradas
  posteriores al incidente con cierre por encima de la referencia
  anterior, nuevo pronóstico independiente, libro sin posiciones ni
  pendientes y órdenes reconciliadas. Se abre un nuevo diario.
- **Datos vencidos:** bloquear compras y conservar todas las
  protecciones existentes; no cancelar stops ante pérdida de conexión.

`Delta` usa parámetros de investigación y **no está optimizada
ni calibrada prospectivamente**. Los precios de IEX y las barras
de Alpaca Crypto US no demuestran fill ni bid/ask alcanzable.
Los cruces de barras OHLC no reemplazan los recibos C25/C35.

## Especificidad de órdenes Alpaca

La documentación actual distingue:
- Equity/ETF: stop market soportado, pero el precio ejecutado puede
  ser peor que el de disparo.
- Cripto: se admite stop-limit, pero NO stop market en la API.
  Ante gap el stop-limit puede quedar sin fill.
- Un stop de 2 niveles es umbral de detección, no cota dura de pérdida.
  El motor de riesgo debe preservar trailing/targets, plazo ≤72h,
  cantidad financiada, cancelaciones y fills tardíos.

Fuentes primarias:
https://docs.alpaca.markets/us/docs/orders-at-alpaca
https://docs.alpaca.markets/us/docs/crypto-orders

## Riesgo y financiación

El valor máximo modelado para investigación es:

    base = min(patrimonio_observado, USD 20000)
    new_gross_room = max(0, 0.12 × base − exposición_bruta)
    new_risk_room = max(0, 0.0025 × base − riesgo_reservado)
    loss_per_nominal = (2 Delta / precio_entrada)
                        + costo_ida_vuelta / 10000
                        + buffer_gap / 10000

    notional <= min(caja_asentada_disponible,
                    new_gross_room,
                    0.04 × base,  # límite conservador solo C36
                    new_risk_room / loss_per_nominal)

El buffer por gap y el stop modelado son hipótesis;
la pérdida máxima **no queda garantizada**. No se habilita una
liquidación 12% continua ni se altera capital de nuevas admisiones.
Las salidas protectoras existentes nunca se subordinan al filtro
de entradas.

## Persistencia y pruebas

- `quant/harpoon_quant/five_level_guard.py`: 11 niveles, stop,
  veto enclavado, reloj causal, rearmado y techo de capital.
- `quant/harpoon_quant/five_level_journal.py`: diario local privado,
  directorio 0700, archivo 0600, SHA-256 encadenado, fsync,
  único escritor; una interrupción exige revisión humana.
- `quant/tests/test_m11_five_level_guard.py`: 30 pruebas.
- `quant/tests/test_m11_five_level_journal.py`: 14 pruebas.
- `.github/workflows/fwn9_p9m_c38.yml`: Ruff, mypy estricto,
  pruebas C38 y regresiones C36/M9.

Esta implementación no está activada en Render ni conectada a la
cartera del broker. La condición `existing_native_protection_present`
se declara por el llamador: no autentica un stop remoto. Al integrar
con C25/C26/C35 deberá verificarse el estado real de órdenes y posiciones.

**Criterio económico refutable:** comparar contra la política sin
veto, ambos con la misma inversión de capital, precio alcanzable,
recepciones originales, costes y frecuencia de gaps. Un veto que
evite pérdidas históricas pero impida recuperaciones rentables puede
reducir el crecimiento logarítmico. No se otorga N9 GO por
menos operaciones ni por reducción modelada de drawdown.
