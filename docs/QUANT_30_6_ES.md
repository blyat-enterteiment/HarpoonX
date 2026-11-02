# HarpoonX 1.2 · métricas y calibración recursiva

Implementado en XXXUltimate 30.6.0. Las pruebas verifican contratos de software; no demuestran rentabilidad financiera. No se ha desplegado ni enviado órdenes. El ejemplo reproducible es enteramente sintético.

## Métricas comunes

`harpoon_quant.performance.report` recibe retornos netos ajustados por flujos, timestamps y frecuencia explícita, o NAV con flujos externos antes/después de cada periodo. Fórmula con NAV: `r=(NAV_final-flujo_después)/(NAV_previo+flujo_antes)-1`. El importe real ganado ajusta todos los flujos; se informa separado de TWR por capital inicial. Un depósito no cuenta como beneficio.

| Grupo | Cálculos |
|---|---|
| Rentabilidad | retorno compuesto, media geométrica, CAGR, P&L neto ajustado, costes |
| Riesgo | volatilidad, downside deviation, VaR y CVaR históricos 95%, ulcer index |
| Ratios | Sharpe, Sharpe HAC con autocorrelación, Sortino, Calmar, recovery factor, Omega |
| Pérdidas | drawdown máximo y actual, duración, pico, valle y recuperación |
| Operaciones | número, tasa de acierto, profit factor, expectativa neta |
| Benchmark alineado | beta, alfa por periodo, tracking error e information ratio |
| Diagnóstico estadístico | PSR; DSR solo con población declarada y completa de Sharpes de ensayos |

Sortino divide el exceso sobre MAR por la raíz de la media de desviaciones negativas **sobre todas las observaciones**. Denominadores nulos producen `null`, nunca infinito. Drawdown incluye el capital inicial. Recovery factor usa el mayor descenso en dólares. DSR/PSR son diagnósticos bajo supuestos; no equivalen a probabilidad de ganar y no deciden la promoción.

La versión común usa días UTC completos y 365 periodos/año para carteras mixtas; exige continuidad. La anualización se habilita con al menos 60 observaciones y 90 días efectivos. Los periodos insuficientes conservan métricas por periodo, sin ratios anualizados. Los antiguos informes de ResearchLab con 252 sesiones se conservan como históricos.

## Bucle conectado

El coordinador captura NAV cada 60 segundos y consulta el calibrador cada 15 minutos mientras la aplicación está en marcha. `GET /v1/quant/calibrator`, con la autenticación existente, expone métricas, estado y binding. La pausa de investigación pausa este bucle; las salidas mantienen su gestión independiente.

1. Esperar panel completo y conciliado. Verificar cuenta, código de ejecución, modelo, universo, configuración y límites.
2. Registrar estudio, configuración y ventana holdout antes de buscar. Reservar presupuesto en SQLite antes de cada evaluación.
3. Generar vecinos de la política, evaluar desarrollo temporal purgado y guardar el mejor. Repetir hasta convergencia o presupuesto.
4. Congelar finalista. Esperar la disponibilidad completa del holdout; evaluarlo una sola vez.
5. Aceptar para investigación o rechazar. Activar automáticamente exclusivamente en PAPER si la evidencia es observada y el registro antecede al holdout.

La búsqueda modifica **solo** `risk_scale` entre 0.25 y 1 y `quality_bps` entre 0 y 100. Los vecinos usan pasos de 0.125 y 5 bps. Reduce topes de cantidad y eleva el filtro mínimo de ventaja robusta; nunca aumenta límites originales. No reescribe código, no reentrena forecasts/SVM ni modifica salidas. Dos generaciones sin mejora o la convergencia terminan la búsqueda. Estado y cadena hash son durables, con transacciones, lease y reserva previa para evitar ensayos concurrentes duplicados. La integridad local no es una atestación independiente del proveedor.

## Evidencia y aceptación

Desarrollo mínimo: 180 días calendario; tres segmentos de evaluación temporal hacia adelante, purga de operaciones que cruzan cortes y embargo de 3 días. Holdout mínimo: 60 días. Por defecto: 24 ensayos/campaña, 128 ensayos acumulados, 3 generaciones, 5 segundos de CPU por lote. El presupuesto acumulado no se reinicia al cambiar `study_id`; conservar la base SQLite. Los intervalos holdout usados no se reutilizan para la misma cuenta y origen. El ResearchLab heredado mantiene su propio ledger y presupuesto; no se han fusionado ambos experimentos.

Aceptación exige: mejora neta superior a 5 USD frente a baseline; límite inferior positivo de diferencia diaria usando bootstrap circular por bloques de 5 días y ajuste por el presupuesto familiar completo; drawdown no peor que baseline ni límite; Sortino finito no negativo; al menos 20 cierres; retorno positivo con costes multiplicados por 1.5. Es una estimación con dependencia y no una garantía de generalización. No basta mejorar un ratio reduciendo el beneficio.

`RESEARCH_ACCEPTED` no altera entradas. `PAPER_ACCEPTED` requiere además origen observado, `autoPaper=true`, modo PAPER y registro prospectivo. Un histórico reetiquetado como observado no obtiene promoción prospectiva. Una política PAPER tampoco se aplica al cambiar a modo live. La política caduca a los 30 días como máximo; cambio de binding, caducidad o drawdown excesivo pausa nuevas entradas. Las posiciones existentes y sus salidas no se reescalan.

## Contrato de datos que falta completar con actividad real

`panelFile` contiene desarrollo y holdout con todas las oportunidades, incluidas las descartadas; tiempos de features y etiquetas; funding, exposición y riesgo por lote; factor, lotes, ventaja conocida en la decisión; costes y curva diaria completa de patrimonio por lote hasta cierre (máximo 72 horas). Opciones requieren capital, riesgo y exposición a nivel de campaña con sus multiplicadores. Se admiten acciones, ETF, cripto y opciones; futuros financiados necesitan otro adaptador.

Las curvas deben proceder de un replay validado con salidas congeladas, bid/ask, costes y marcas ejecutables. El replay incluido es un sustituto de selección y sizing con reserva completa de capital y MTM diario. **No reproduce todo el MILP de producción, impacto de mercado, fills ni el código nativo de salidas.** Sus resultados necesitan confirmación PAPER prospectiva antes de valorar un despliegue real. Los flags `net_costs_confirmed`, `cashflows_adjusted`, `complete_opportunity_universe` y `frozen_exit_replay_validated` son declaraciones del productor, no certificación del broker.

`performanceFile` exige `origin=OBSERVED`, `cashflows_confirmed=true`, `net_costs_confirmed=true`, `return_basis=NET_FLOW_ADJUSTED`. Con solo NAV capturado, el runtime devuelve `WAIT_RECONCILED_PERFORMANCE`: no confunde depósitos, comisiones pendientes o cambios de cartera con alfa. Sin panel devuelve `WAIT_DATA`. La muestra Alpaca heredada (8 sesiones de precios, 2 segundos de L1) no aporta P&L conciliado ni histórico suficiente para estas ventanas.

## Configuración y reproducción

Ver `config/examples/xxx.json` del paquete completo: `quant.optimizer` activa el bucle, con rutas persistentes `/var/data/quant_optimizer.sqlite3`, `/var/data/quant_opportunities.json`, `/var/data/quant_performance.json`. El despliegue debe proporcionar esos archivos; no se instala el fixture sintético como evidencia observada.

Desde esta carpeta, con dependencias instaladas:

```bash
python reproduce_recursive.py
python -m harpoon_quant.lab performance --input examples/recursive/performance.synthetic.json --output evidence/cli_performance.synthetic.json
python -m harpoon_quant.lab optimize --input examples/recursive/envelope.synthetic.json --output evidence/cli_optimizer.synthetic.json
```

La última orden avanza una generación; repetir hasta estado terminal. El ejemplo usa un journal nuevo `evidence/demo_optimizer.sqlite3`; ejecuciones posteriores son idempotentes. `reproduce_recursive.py` ejecuta tres ciclos aislados y conserva las transiciones en `evidence/recursive_demo.synthetic.json`, siempre sin política activa. Los tests incluyen aceptación de contrato observado con fixtures controlados, rechazo económico, fuga temporal, duplicación de holdout, presupuesto, concurrencia, caducidad y corrupción de journal. Ningún fixture representa operaciones reales.

## Referencias metodológicas

- CFA Institute, Kidd, *The Sortino Ratio*: https://rpc.cfainstitute.org/sites/default/files/-/media/documents/code/gips/the-sortino-ratio.pdf
- Bailey y López de Prado, *The Deflated Sharpe Ratio*: https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf

No se atribuyen a firmas privadas métodos internos no publicados. El objetivo operativo es una mejora neta medible y repetible; 20x o beneficios récord no están acreditados.
