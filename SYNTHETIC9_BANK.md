# Banco sintético de ejecución y economía secuencial

Implementación funcional de un banco de ingeniería para acercar HARPOON a la
verificación de ejecución, contabilidad, evaluación temporal y revisión por
terceros. Usa exclusivamente precios, liquidez y fills generados: todos los
artefactos declaran `SYNTHETIC_ENGINEERING_ONLY`. No utiliza credenciales ni
conecta con el broker.

## Alcance registrado

El [protocolo](research/synthetic9/protocol.json) congela tres mundos: sin
ventaja, tendencia con cambio de signo y choque de liquidez con gaps. Cuatro
semillas por mundo, 32 semanas de calentamiento y ocho de evaluación producen
96 ventanas futuras distintas. Tres escenarios de costes repiten esas ventanas;
no se cuentan como observaciones nuevas. CORE, CASH y FIXED_SAME_LOT_CAP forman
108 cuentas continuas de 20,000 USD y 288 decisiones del core.

La estrategia CORE invoca el motor frontier existente. Entrena sólo con labels
anteriores, crea la decisión sin los futuros de la ventana actual y después
procesa los eventos generados. Mantiene los parámetros del controlador; incorpora
cuantiles de slippage sintético como costes **supuestos**, nunca observados live.
Los otros controles son efectivo y entrada incondicional con los mismos topes
por lote. Este último no iguala la exposición de un core que se abstiene.

## Componentes ejecutables

| Módulo bajo `quant/harpoon_quant/synthetic9/` | Función |
| --- | --- |
| `market.py` | Trayectorias OHLC conjuntas y features derivadas de ventanas terminadas |
| `execution.py` | ACK, rechazo, parcial, cancelación, fill tardío, costes y calibración sintética enlazada |
| `ledger.py` | Reservas, efectivo, inventario en unidades nativas, fees y deadlines sin reinicio de campaña |
| `bank.py` | Cuenta continua, controlador real en shadow, continuación protectora y comparadores |
| `review.py` | Segunda reconstrucción Decimal que no importa simulador ni ledger primario |
| `events.py`, `storage.py` | Cadena de hashes, compresión determinista, escritura privada y lectura acotada |
| `faults.py`, `experiment.py` | Ataques ejecutados, matriz registrada, métricas y expediente reproducible |

El paquete queda fuera del directorio `frontier` para conservar la identidad de
código de los modelos y recibos históricos ya archivados. La ejecución del banco
no cambia el runtime operativo ni sus contratos.

## Convenciones y límites de la simulación

- AAPL, MSFT, BTC/USD y ETH/USD son nombres de las series sintéticas, no datos
  descargados de esos activos. No se generan dividendos ni splits.
- Calendario equity ficticio: días laborables, 14:00–21:00 UTC, sin festivos ni
  DST. Cripto continuo salvo las interrupciones inyectadas. No representa un
  calendario certificado de Nasdaq/NYSE ni una bolsa cripto concreta.
- Cada ventana dura 72 horas y comienza una semana después de la anterior.
  Los cuatro días fuera de la ventana acumulan gasto y mantienen las últimas
  marcas; un inventario sin cerrar se conserva y su valoración se señala como
  potencialmente obsoleta. No se transforma en efectivo ficticio.
- Comisiones supuestas: 2 bps y 0.01 USD por orden con fill, cobrada una sola
  vez aunque haya varios parciales. Spread base: 2 bps equity y 6 bps cripto.
  Doble coste duplica spread, fee, slippage, fijo y gasto común; el tercer caso
  añade 0.5% de gap adverso al precio de salida.
- El slippage depende de participación, retraso y ruido de un modelo declarado.
  La latencia mueve timestamps y coste; no se resuelve una trayectoria de precios
  intrahoraria. Las capacidades declaradas no son profundidad L2/L3 observada.
- Las compras usan límites negociables; no se presume fill de una orden pasiva
  por tocar su límite. No hay estimación de prioridad de cola.
- Las salidas reaccionan a barras ya completadas y precios actuales, con un
  margen temporal de una hora para intentar cerrar antes del deadline. Pueden
  ejecutar por debajo del stop. Una interrupción conserva el incumplimiento.
- Los 320 fills de calibración pertenecen a corridas aisladas de medición de
  costes, con órdenes y fills enlazados; no son 320 operaciones de una cartera
  ni recibos del broker. Sus quantiles no estiman impacto de mercado real.

La documentación primaria de [Alpaca sobre paper trading](https://docs.alpaca.markets/us/docs/paper-trading)
también distingue simulación y ejecución real y enumera omisiones de sus modelos.
Este banco añade mecanismos explícitos para ensayarlas bajo supuestos; no afirma
haber calibrado esos mecanismos contra una bolsa.

## Reproducción y revisión

```sh
python3 -m pip install -r quant/requirements-tested.txt
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONPATH=quant \
  python3 -B tools/run_synthetic9.py --source-commit "$(git rev-parse HEAD)" \
  --output-dir /tmp/harpoon_synthetic9
PYTHONPATH=quant python3 -B tools/verify_synthetic9.py /tmp/harpoon_synthetic9 \
  --output /tmp/harpoon_synthetic9_verification.json
PYTHONPATH=quant python3 -B -m unittest discover -s quant/tests -p 'test_synthetic9*.py'
```

Ejecutar desde el repositorio clonado en el commit examinado. El campo se registra
como declaración, no como autenticación. La carpeta de salida debe ser nueva. Los
JSON/gzip se crean con permisos 0600 y no se sobrescriben. Una corrida que falla
conserva `incident.json` y los resultados parciales, sin promoción.

El verificador comprueba hashes de fuentes y artefactos, reconstruye modelos,
vuelve a calcular features causales y contrasta estados, propuestas, órdenes,+fills, patrimonio y agregados. Verifica la contabilidad con Decimal y las
propuestas con la segunda valoración del core. Es otra implementación del mismo
autor. La [guía para revisión externa](research/synthetic9/REVIEW_GUIDE.md) describe
qué puede reproducir un tercero y qué evidencia sigue faltando.

## Lectura correcta del resultado

Una ganancia en el mundo de tendencia es evidencia de comportamiento bajo un
generador diseñado con tendencia. Una pérdida o abstención se conserva. Cuatro
semillas permiten comparaciones descriptivas, sin acreditar significancia ni
generalización financiera. El banco nunca convierte esos resultados en fills
reales, validación prospectiva real, revisión externa o nivel 9.

## Resultado registrado y evidencia de QA

La corrida [run_01](evidence/synthetic9/run_01/summary.json) se ejecutó después de congelar las fuentes en `d73163c39527e534746d1a01800d8fa95040e8b7`. Terminó sin incidentes de construcción: 108 cuentas, 96 ventanas futuras sintéticas distintas, 288 decisiones CORE, 320 fills aislados de calibración y 2,978 fills en las cuentas contrafactuales.

Media del PnL neto por cuenta de 20,000 USD durante ocho semanas, cuatro semillas por celda; resultados exclusivamente sintéticos:

| Mundo | Coste | CORE USD | CASH USD | Entrada fija USD |
| --- | --- | ---: | ---: | ---: |
| NULL | NOMINAL | -56.00 | -56.00 | -80.20 |
| NULL | DOUBLE_COST | -112.00 | -112.00 | -165.93 |
| NULL | DOUBLE_COST_GAP | -112.00 | -112.00 | -259.00 |
| TREND_BREAK | NOMINAL | 51.34 | -56.00 | 155.73 |
| TREND_BREAK | DOUBLE_COST | -4.80 | -112.00 | -25.20 |
| TREND_BREAK | DOUBLE_COST_GAP | -111.90 | -112.00 | -407.28 |
| LIQUIDITY_SHOCK | NOMINAL | -56.00 | -56.00 | -691.78 |
| LIQUIDITY_SHOCK | DOUBLE_COST | -112.00 | -112.00 | -772.33 |
| LIQUIDITY_SHOCK | DOUBLE_COST_GAP | -112.00 | -112.00 | -845.96 |

Cinco de las 36 cuentas CORE tuvieron PnL positivo. El resultado nominal en tendencia no sobrevivió como ganancia media al doble coste con gap. En NULL y LIQUIDITY_SHOCK el CORE se abstuvo y pagó el gasto común; eso no constituye rentabilidad. No se cambiaron las semillas ni los umbrales después de medir.

Se conservaron 73 incumplimientos del plazo planificado: 16 CORE y 57 del control fijo. La demora máxima de la última venta fue de 3,601.677 segundos; la resolución horaria y los rechazos/parciales permiten perder el margen de reintento. Ninguna de las 108 cuentas registradas superó 72 horas; el caso adversarial separado de halt prolongado sí conserva una posición vencida sin inventar un fill. El [análisis de plazos](evidence/synthetic9/qa/deadline_forensics.json) permite revisar cada campaña. Una política con reintentos por evento y presupuesto temporal requeriría una hipótesis y prueba nuevas; aquí se registra el fallo, sin certificar el deadline.

La [verificación del paquete](evidence/synthetic9/qa/packet_verification.json) reconstruyó 108 cuentas, 36,396 marks y 288 modelos. Ruff y mypy aprobaron las fuentes nuevas; las 38 pruebas nuevas aprobaron localmente. La suite completa aprobó 649 tests en [dos ejecuciones](evidence/synthetic9/qa/github_ci.json) de GitHub, incluida la [corrida completa del banco](https://github.com/blyat-enterteiment/HarpoonX/actions/runs/41504044504). Su resumen reproduce el local dentro de 1e-12. El benchmark local fue de 167.135 segundos para la carga completa, sin equivalencia con latencia live.

La primera regresión local detectó un timeout del predictor anterior y las repeticiones aisladas también fallaron en sus fixtures. Los logs se conservan en [QA](evidence/synthetic9/qa/qa.json); no se modificaron el predictor ni su timeout. Ese fallo no se reprodujo en los dos runners de GitHub. La causa local permanece sin determinar.

El [estado de preparación](evidence/synthetic9/run_01/readiness.json) mantiene pendientes las tres puertas reales. Los hashes y las pruebas no sustituyen ni autentican fills de bolsa, resultados prospectivos reales o la revisión de un tercero.
