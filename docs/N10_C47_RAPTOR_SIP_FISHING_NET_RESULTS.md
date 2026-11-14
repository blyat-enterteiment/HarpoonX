# HARPOONX — C46/C47: red asimétrica de ruptura con trailing y prueba observada

**Resultado:** La matriz se implementó para investigación y se probó con
datos históricos reales de Alpaca IEX y SIP, pero **NO acreditó acercamiento
económico a N9**. N9-S NO_GO, N10 NO_GO.

## Motivación: capturar pocos ganadores extraordinarios

El usuario compartió dos imágenes de una lista Finviz "Raptor".
La configuración mostraba RVOL > 5 y cambio desde apertura +10%,
pero la lista de 16 símbolos visibles fue entregada después de
conocer los resultados. **Nunca se obtuvo el historial de pertenencia
al screener ni el RVOL>5 conocido en el momento exacto de señal.**
No se imputaron los tres activos ocultos de la cartera.

La hipótesis es convertir la matriz local 5×5 en:
- **Admisión positiva**: precio sube +3% o +4% respecto del cierre
  anterior observable; dos cierres consecutivos de 5min por encima;
  entrada SOLO al siguiente OPEN continuo, a precio no mayor de +75
  puntos básicos sobre trigger; no entrada después de 15h ET.
- **Protección negativa**: stop de 2 escalones bajo entrada congelada,
  stop-first en velas que toquen stop y máximo a la vez; detección
  de falsas rupturas, velas extremas y gaps de fuente.
- **Ganador sin techo fijo**: no take-profit rígido a +5 niveles.
  El trailing crece con máximos de barras plenamente CERRADAS
  y no puede disminuir; después de +6 escalones bloquea solo
  parte de la subida para dejar correr el resto.
- **Máximo 72h**, presupuesto de admisión original de 20k capital,
  ≤12% bruto, ≤0.25% riesgo, 4% por propuesta como límite adicional
  experimental. STOP tocado ≠ fill del broker.

Archivos de la arquitectura: `research/raptor46/local_fishing_net.py`
y `research/raptor46/replay_net.py`. Estas funciones NO
reciben llaves, NO colocan órdenes, NO cancelan stops remotos ni
reanuda un proceso tras perder fuente sin nueva conciliación.

## Dos fuentes: IEX vs SIP

La primera prueba **C46** descargó **808 barras IEX de 5 minutos**
para noviembre 12–13 de 2026 en los 16 símbolos visibles.
6 tocaron +3%, 5 tocaron +4%; ICMB tocó +4% y cerró por
debajo del último cierre IEX previo; TGEN tocó +3% y cerró rojo.
Como IEX no ofrece cobertura completa de la cinta, 10 símbolos
fueron detenidos por discontinuidad, 5 tuvieron insuficiente
historial y ENGN rebasó el límite de persecución del precio.
**Resultado C46: cero entradas modeladas**, cero PnL.

La conexión Alpaca permitió después consultar el feed **SIP**.
Para preservar la inferencia, C47 congeló los mismos parámetros
en el commit `f37f5a1266e2026d3ecb5b17818bfacc8a7223ff`,
**después de una comprobación previa de cobertura de cuatro
símbolos**, pero **antes de descargar el lote completo SIP**.
Este orden y la selección ex-post se registraron explícitamente.
El CSV SIP está firmado localmente por Git blob SHA-1
`20ab6f9cc4902d9c3b9135ef48011edb193e7cac`
y SHA-256
`74a1230b581a9654f27f47b624fac2f873add59a76046764e3d045304d6de3a4`.

| Cobertura | IEX C46 | SIP C47 |
| --- | ---: | ---: |
| Barras recibidas | 808 | 2.540 |
| Barras SIP en horario 09:30–16:00 NY | — | 1.867 |
| A +3% tocaron umbral | 6 | 8 |
| A +4% tocaron umbral | 5 | 6 |
| +3% estrictas, siguiente OPEN permitido | 0 | 0 |
| +4% estrictas, siguiente OPEN permitido | 0 | 1 |

Se descartaron las 673 barras SIP de fuera del horario regular,
que de otro modo habrían distorsionado el reloj de señales.

## Resultado económico C47 de un solo día

**No es un backtest completo de 72h.** Los costes son supuestos,
no facturas ni recibos de Alpaca.

| Entrada | Propuestas modeladas | PnL 100 pb RT | PnL 300 pb RT | PnL 500 pb RT |
| --- | ---: | ---: | ---: | ---: |
| +3% y dos cierres 5m | 0 | 0 USD | 0 USD | 0 USD |
| +4% y dos cierres 5m | 1 | −24,736402 USD | −40,736402 USD | −56,736402 USD |

La única entrada fue **ENGN**, 13/nov/2026:
- **13:40 ET** (18:40 UTC): entrada hipotética al OPEN
  **2,39 USD**, nominal 800 USD;
- stop inicial/trailing modelado en **2,34 USD**;
- **13:55 ET** (18:55 UTC): LOW de una vela de 5min toca
  el stop, salida teórica a **2,34 USD**, SIN fill del broker;
- caída teórica del precio −2,09% y 1% de coste RT
  modelado: **−24,736402 USD**.
- Con 5% de coste modelado la pérdida teórica pasa a
  **−56,736402 USD**, incluso superior al riesgo inicial
  objetivo de 50 USD; esta es una limitación real de
  gaps, tasas y presupuestos, no una violación del
  código de investigación.

¿Por qué +3% produce cero y +4% una entrada? Porque el
límite de no perseguir la cotización queda definido en
`nivel × (1+0,0075)`: +3% puede haber sido rebasado antes
de que existan dos cierres y un siguiente open contiguo.
El +4% puede entrar posteriormente, a precios diferentes.
No es una comparación neutral de fills reales.

## Pruebas y dictamen económico

- C46 CI [#43538654612](https://github.com/blyat-enterteiment/HarpoonX/actions/runs/43538654612):
  19 pruebas nuevas + 30 originales C38, Ruff y mypy PASS.
- C47 CI [#43539316603](https://github.com/blyat-enterteiment/HarpoonX/actions/runs/43539316603):
  19 C46 +12 C47, Ruff, mypy, M9 SHA fuente PASS.
- C47 mantiene un solo libro hipotético financiado con patrimonio
  20k, costes 100/300/500pb, sin órdenes ni reinicio del
  optimizador. Todos los resultados son **retrospectivos**.

**Resultado N9:** el experimento no demuestra crecimiento neto
positivo; el candidato de +4% perdió, y +3% quedó en CASH.
El que una matriz pueda teóricamente dejar correr 30% se
verificó en un test sintético, no mediante un fill real de
TGHL: C46 vio solo dos barras IEX ese día, mientras que
C47 encontró mayor cobertura SIP pero no su entrada admisible
bajo la regla congelada.

## Siguiente experimento realmente decisivo

Antes de retocar umbrales con estas ganancias ya conocidas:
1. Congelar **ex ante** un universo vivo producido por el mismo
   screener y observar de forma completa los descartes, no solo
   los visibles ganadores/declinantes.
2. Capturar del **SIP más NBBO/quotes** el precio, timestamps,
   RVOL relativo por **la misma franja horaria** y liquidez
   antes de cada decisión; registrar cancelaciones y
   órdenes pendientes.
3. Validar antes de cada nueva admisión `risk ledger` persistente
   y trailing con eventos de ejecución real PAPER, gaps,
   órdenes limitadas que no se llenan, deslizamientos.
4. Completar al menos cada campaña hasta **72 horas**, con
   comparación contemporánea contra CASH y ORIGINAL
   bajo el mismo capital continuo; no seleccionar por alta
   rentabilidad a posteriori.
5. Publicar el crecimiento geométrico NET, la contribución del
   mejor ganador, cobertura de oportunidades, rechazo
   y control de comparaciones múltiples. Solo entonces reconsiderar
   N9-S y eventualmente N10, sin reetiquetar datos históricos
   como prospectivos.

**N9-S NO_GO; N10 NO_GO; M10 3.200 cuentas selladas.
No se han enviado órdenes, no hay despliegues ni fusiones.**
