# Universo ampliado, cartera equity/cripto y costes observados

**Resultado: no se acredita 8. La nueva regla intradía se rechaza.**
Se resolvió la descarga y la comparación contable multiactivo; no se resolvió
la falta de ventaja neta, de universo point-in-time ni de fills live verificables.
El runtime, sus estrategias vigentes y el broker no fueron modificados por este estudio.

## Entregado y medido

- Panel horario 2025: **34,551 barras** válidas dentro del intervalo, nueve
  acciones/ETF (SPY, QQQ, IWM, XLF, XLE, XLV, XLK, AAPL, MSFT), BTC/USD y ETH/USD.
  Respuestas originales comprimidas, solicitudes, feeds, conteos y hashes incluidos.
- Descarga diaria adicional 2024–2026 archivada como contexto, **no utilizada**
  para seleccionar parámetros ni como validación nueva.
- Una sola regla congelada: continuación positiva sobre 20 barras, volatilidad
  de 60 retornos; tres nombres como máximo, ponderación inversa a volatilidad.
  Capital inicial **20,000 USD por alternativa**, continuo y sin duplicarlo entre libros.
- Entrada 10:00 y salida 12:00 de Nueva York, incluidas transiciones DST.
  **Es una prueba intradía de dos horas, no validación del swing de 1–3 días**.
  El horizonte corto permite evitar inventar dividendos, financiación o cobertura
  nocturna con estos datos; su resultado no se extrapola al motor swing.
- Límites conjuntos: 60% bruto, 20% por nombre y 20% cripto; lotes finales,
  caja y capacidad limitada al 1% de la mediana de volumen monetario anterior.
  El exceso de capacidad deja efectivo sin invertir; no se redistribuye tras caps.
- Comparadores: asignación conjunta, subcarteras 40% equity/20% cripto y efectivo.
  Sizing, capital y comisiones se recalculan por alternativa y escenario.
- Costes **supuestos, no calibrados**: 5 bp equity / 35 bp cripto por lado,
  más 1 USD por día calendario de infraestructura compartida. Estrés duplica ambos.
  Esta es una nueva prueba; no altera los costes del estudio residual sellado.

| Alternativa | Neto nominal USD | Neto estrés USD |
| --- | ---: | ---: |
| Conjunta | -1,867.39 | -3,781.73 |
| Subcarteras | -2,037.30 | -3,739.43 |
| Efectivo, pagando el mismo fijo | -365.00 | -730.00 |

HECHO DEL MODELO: conjunta nominal produce **245.60 USD brutos**, insuficientes
para 1,747.99 USD de costes variables y 365 USD fijos. La ventaja descriptiva
frente a subcarteras tampoco tiene límite inferior HAC positivo. Las cifras de
estrés no son simplemente el nominal menos costes extra: cambia la cantidad
financiada por la trayectoria de capital, como exige una cuenta continua.

La capacidad observada restringe la exposición cripto conjunta a un máximo
aproximado de **1.03% del capital** en las entradas. No puede afirmarse que este
ensayo pruebe una cartera con 20% cripto. El volumen IEX es de ese feed, no
volumen consolidado; tampoco se interpreta el volumen cripto retornado como
liquidez ejecutable total. Esta restricción es un supuesto conservador, no un
modelo calibrado de impacto de mercado.

## Datos: límites que permanecen

- Universo fijo elegido actualmente, no composición point-in-time ni universo
  que incluya valores desaparecidos. La ampliación no elimina survivorship bias.
- Feeds explícitos: IEX equity y US crypto. Quotes, profundidad, fills y precios
  realmente ejecutables no se infieren de OHLCV. Disponibilidad de barras:
  fin de hora más 60 segundos **supuestos**, no first_received observado.
- La respuesta cripto incluye un hueco horario por símbolo: se conserva y no se
  imputa. Hay 215 barras BTC y 618 ETH con volumen cero. Los ceros permanecen.
  El extremo 2026-01-01 recibido se excluye de la medición 2025.
- Saltos logarítmicos absolutos superiores a 0.20 suspenden la señal durante
  su ventana. Ese control no sustituye un catálogo completo de corporate actions.
- Historial ya visto; ninguna descarga convierte 2025 en holdout virgen.
  No hay selección de umbrales, fitting, walk-forward entrenado ni promoción.
  HAC con suelo IID es descriptivo; no corrige todo el historial de búsqueda.
- Drawdown únicamente en la cuadrícula de cierre; riesgo intrabar, liquidación,
  restricciones reales de cuenta y liquidación de efectivo no certificados.

## Fills: implementación utilizable y bloqueo concreto

`tools/observed_fills8.py` ofrece dos comandos reales:

1. `collect`: consulta **sólo GET /v2/account/activities**, paginación acotada,
   detección de duplicados/loops y origen fijo PAPER o LIVE. Conserva todas las
   actividades, incluidas comisiones y flujos; nunca crea ni cancela órdenes.
2. `calibrate`: mide shortfall firmado respecto al midpoint de la decisión,
   **incluyendo la comisión explícita una sola vez**. No vuelve a sumar spread.
   Separa LIVE/PAPER, equity/cripto y compra/venta; cuenta órdenes y días distintos,
   para no tratar fills parciales de una orden como observaciones independientes.

Se exige un bundle `HARPOON_OBSERVED_FILLS_1` con `mode`, `available_at` y `fills`.
Cada fill necesita `fill_id`, `order_id`, `book`, `symbol`, `side`, `qty`, `price`,
`fee_usd`, `fee_receipt_id`, `bid`, `ask`, `quote_at`, `quote_received_at`,
`decision_at` y `filled_at`. Las fees faltantes no se convierten en cero; no se
fabrican quotes retrospectivos. Quote ≤ recepción ≤ decisión ≤ fill ≤ calibración,
y antigüedad del quote ≤5 segundos. Los importes de fee deben estar asignados
al fill, sin duplicar una factura global entre fills parciales.

El calibrador devuelve media ponderada, p95 empírico y rango de tamaños observado.
Exige al menos 30 fills, 20 órdenes y 10 días por grupo para marcar suficiencia
mínima; **esos números no establecen cobertura estadística ni ejecución fiable**.
P95 no es un límite de confianza. No extrapola a tamaños nuevos, no estima
coste de órdenes no llenadas ni markout sin quotes posteriores, y nunca acredita
rentabilidad ni autenticidad por sí mismo. El resultado conserva
`source_independently_authenticated=false`, `account_reconciled=false` y
`financial_acceptance_allowed=false`.

**No se recibieron fills live.** Las herramientas Alpaca conectadas en esta
sesión son de mercado; no exponen las actividades de la cuenta. El entorno local
tampoco tiene APCA_API_KEY_ID/APCA_API_SECRET_KEY configuradas. Por eso la
calibración queda preparada pero **no ejecutada con datos reales**. Una exportación
privada del broker y los recibos causales de decisión/fees son la entrada faltante.
No es necesario activar operaciones para leer ejecuciones ya existentes.

Las credenciales se toman del entorno, nunca del JSON ni de argumentos de línea.
La salida privada se crea con permiso 0600 y sin sobrescribir archivos existentes.
No se deben subir actividades de cuenta, claves ni recibos privados a GitHub.

```sh
# Leer actividades ya existentes, con credenciales configuradas localmente.
python3 tools/observed_fills8.py collect --mode PAPER \
  --start 2025-01-01T00:00:00Z --end 2026-01-01T00:00:00Z \
  --output /tmp/harpoon_private_activities.json
# Tras enlazar fills, quotes y fees en el contrato descrito:
python3 tools/observed_fills8.py calibrate --input /tmp/harpoon_linked_fills.json \
  --output /tmp/harpoon_private_cost_calibration.json
```

## Validación y reproducción

Protocolo publicado antes del replay: `3646af6b120c656ccbf443aa9de685f42ed4adb4`.
Implementación publicada antes de medir: `e4ae5dc7775b7e1008324b86d640bfa54c1bc8f3`.
El histórico ya había sido descargado; no es preregistro ciego ni independiente.
Los datos completos se archivan después de medir, con hashes de esta ejecución.
Se consumen cuatro mediciones de política/costes y dos controles CASH; el presupuesto
histórico global no se declara reconciliado. No se ensayaron más reglas tras el fallo.

- Suite quant completa ejecutada: **518 pruebas**, con 17 casos iniciales nuevos.
- Versión final del módulo: **19 pruebas específicas** aprobadas (incluye dos
  casos añadidos después), más **6 mutaciones de cuentas** en el verificador.
- Segunda ejecución: seis cuentas reproducidas; identidad/cantidad/precio de cada
  trade exactos y discrepancia monetaria permitida inferior a 0.0000001 USD.
- Verificación separada con Decimal: mayor error diario inferior a 2e-10 USD.
  Es otro verificador del mismo autor, **no validación externa independiente**.
- Compilación sintáctica Python ejecutada. Linter y verificador formal de tipos
  Python no ejecutados; no estaban instalados. No se equipara compilación a lint.
- Medición de una reproducción local: aproximadamente 2.08 s; sólo tiempo de
  cómputo, no mejora financiera. Workflow `multiasset8.yml` reproduce en GitHub.

```sh
python3 -m pip install -r quant/requirements-tested.txt
PYTHONPATH=quant python3 -B -m unittest discover -s quant/tests -p test_multiasset.py -v
python3 -B -m unittest discover -s tools -p test_multiasset8_verifier.py -v
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 -B tools/run_multiasset8.py \
  --output-dir /tmp/harpoon_multiasset8_new
python3 -B tools/verify_multiasset8.py /tmp/harpoon_multiasset8_new \
  --compare evidence/multiasset8/run_01
```

R4 y R5 fallan; R2, R6 y R8 siguen sin evidencia suficiente. R3 se verifica
únicamente en el modelo y R7 sólo como reproducción del mismo autor. La regla
queda rechazada, sin integración en runtime ni autorización de ejecución.

Referencias primarias para los contratos, no aval de HARPOON:
[Alpaca Account Activities](https://docs.alpaca.markets/us/reference/getaccountactivities-2),
[Alpaca Paper Trading](https://docs.alpaca.markets/us/docs/paper-trading).
La disciplina pertinente es contrastar señales netas, capacidad y capital conjunto;
no se atribuyen estrategias propietarias a Citadel, Jane Street o Two Sigma.
