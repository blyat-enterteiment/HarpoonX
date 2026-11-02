# HarpoonX · motor cuantitativo multi activo 1.8.1

Implementación de investigación y asignación, integrada en el coordinador XXXUltimate 30.13.0. El núcleo formula una decisión económica común para acciones, ETF, cripto y opciones; también valora futuros mediante entradas normalizadas. No acredita rentabilidad observada, participación en un campeonato ni una tecnología propietaria de Citadel o Jane Street.

## Correcciones del core · 1.8.1

Ridge purga las etiquetas por fin y disponibilidad antes de validación y prueba. `instrument()` usa la misma base de entrada y slippage que `pnl_lot()` al reservar efectivo. `runtime_config()` valida la configuración local y la general antes de intersectar cotas; mantiene el supuesto de slippage mayor y la antigüedad de cotización menor cuando existen límites explícitos.

Estas correcciones tienen contraejemplos y pruebas sintéticas en la integral 30.13.0. Los modelos anteriores conservan su procedencia. Modificar fuentes no corrige retrospectivamente el entrenamiento Ridge y puede invalidar la huella de implementación SVR. Las pruebas nuevas no demuestran rentabilidad y no activan ejecución.

## Puente económico y observaciones · 1.8.0

La ruta económica v2 distingue el control vigente NATIVE, Ridge, SVR y efectivo con costes. Reutiliza el contraste estadístico por bloques de sesiones y obtiene las curvas de la reejecución del coordinador del paquete integral. El contrato v1 mantiene su control C0 como efectivo. El nuevo contrato exige además riesgo durante el periodo, estrés fijado previamente, costes ligados a su calendario y procedencia de la prueba final y de los intentos anteriores.

Una afirmación de rentabilidad no puede surgir de una curva escrita a mano, una etiqueta OBSERVED o un contador reiniciado. La autenticidad externa y la integridad local se informan por separado. Los datos ausentes producen bloqueos y valores nulos. Las pruebas sintéticas conservan `financial_approval: false`, y ninguna ruta cambia el modo operativo.

La lectura de observaciones admite exportaciones fijadas y procesamiento acotado. Conserva las cotizaciones y fechas originales necesarias para contrastar las etiquetas, sin reinterpretar reconstrucciones retrospectivas como recepción en vivo. Los límites de bytes y la retención efectiva siguen siendo parte del contrato.

El ZIP del motor Python necesita el paquete integral para reejecutar el comparador Node y sus fuentes. El informe de la versión completa contiene el dictamen ejecutado; el incremento de versión a 1.8.0 no acredita una ventaja económica.

## Comparación fija y datos causales · 1.7.0

`causal_panel.py` reconstruye fuentes, verifica sus hashes y separa filas causales observadas de diagnósticos retrospectivos. Un timestamp de mercado no acredita el instante de recepción del motor. El adaptador `tools/build_causal_panel.py` del paquete integral genera y vuelve a verificar el informe sin entrenar modelos.

`fixed_predictor.py` ofrece inferencia reproducible con modelos previamente congelados. El comparador Node del paquete integral ejecuta C0, Ridge y SVR con el mismo coordinador, capital, salidas y costes; conserva los bytes originales del modelo para verificar su firma Python. Las curvas comparan resultados monetarios y mantienen posiciones abiertas, ejecuciones parciales y costes explícitos. No se afirma una ejecución observada cuando los fills son modelados.

`measurement_registration.py` verifica o reserva una medición fija en un journal existente; reserva tres plazas y limita a seis la familia completa. La reserva no acredita prerregistro externo ni autoriza órdenes. Los ejemplos sintéticos no consumen ese presupuesto y no pueden aprobar evidencia financiera. Este ZIP Python necesita el paquete integral para ejecutar el coordinador, su comparador y el verificador de nivel 4.

## Validación económica y procedencia · 1.6.0

`harpoon_quant.economic_gate` verifica curvas continuas C0/Ridge/SVR, protocolo previo, costes, flujos, posiciones abiertas, exposición y comparación pareada mediante bloques de sesiones. `verify_gate_report` repite el cálculo; un hash y un boolean de aprobación no bastan. El resultado sintético permanece `VENTAJA_NO_DEMOSTRADA`, incluso si pasa el cálculo estadístico. La verificación nunca activa PAPER ni LIVE.

La acción `python -m harpoon_quant observe` reutiliza las características del bridge sin abrir un archivo de calibración ni solicitar asignación. La acción `verify-gate` verifica un informe con sus entradas y artefactos. Ninguna habilita órdenes. El nuevo informe `HARPOON_PERFORMANCE_2` distingue costes desconocidos, alcance de los costes reportados y fecha inicial observada. El formato V1 se conserva exclusivamente para reconciliar recibos históricos diarios completos con su contrato original.

Los ejemplos completos están en `examples/economic_gate/` y `examples/coordinator_replay/`. La integración Node que reejecuta el coordinador requiere el paquete completo XXXUltimate: el ZIP del motor Python, por sí solo, no contiene `../tools`, `../xxx` ni `../runtime30`. La evaluación sintética puramente Python sí es autónoma.

Se conserva la diferencia entre captura y trayectorias económicas ejecutables: muestras de cotización no aportan prioridad de cola ni volumen ejecutable. Tampoco son una prueba final no utilizada. El motor no convierte un recibo de paridad nativa C0 en paridad predictiva de Ridge/SVR.

```bash
python -m unittest discover -s tests -v
python -m harpoon_quant.economic_gate --protocol examples/economic_gate/synthetic_fixture/protocol.json --input examples/economic_gate/synthetic_fixture/input.json --output /tmp/economic-gate.json --artifact-root examples/economic_gate/synthetic_fixture
```

## Replay pareado y metadatos · 1.5.0

`harpoon_quant.paired_replay` incorpora C0/Ridge/SVR con cuentas separadas y patrimonio continuo. Usa el asignador numérico real y una política común de salida por tiempo o invalidez. Conserva el inventario terminal, marca a bid, descuenta comisiones una sola vez, incorpora slippage en el precio, limita fills a capacidad explícita y neutraliza aportaciones/retiros tras valorar las posiciones. Un reductor de eventos concilia de nuevo caja, comisiones e inventario. La financiación no modelada bloquea la medición; la insolvencia queda registrada aunque después se inyecte capital.

Su alcance inicial son acciones y ETF no apalancados en USD, lotes enteros y ejecución modelada. El discovery del coordinador sí conserva los metadatos de ETF apalancados y sus límites vigentes, pero este replay los rechaza mientras no tenga el adaptador de exposición correspondiente. No multiplica su PnL por el apalancamiento. La identidad Ridge/SVR se comprueba en la cabecera y en los modelos internos; dos versiones disponibles en el mismo instante se rechazan aunque sus timestamps tengan distinto formato.

```bash
python -m harpoon_quant.paired_replay --input examples/paired_replay/synthetic_request.json --output /tmp/paired-result.json
python -m harpoon_quant.paired_replay --input examples/paired_replay/synthetic_request.json --output /tmp/paired-readiness.json --check-only
python -m unittest discover -s tests -p test_paired_replay.py -v
```

El ejemplo es exclusivamente sintético. Los costes numéricos ausentes producen `MEDICION_BLOQUEADA`, no cero. Una cotización futura no entra en el predictor. No se permite declarar `policy_parity_verified=true`: este recurso aún no reproduce todos los plugins, trailing y parciales del coordinador. Tampoco implementa el gate estadístico de promoción; sus intervalos permanecen nulos hasta fijar y ejecutar ese protocolo. La documentación completa del esquema está en `examples/paired_replay/README.txt`.

Varias decisiones intradía reciben IDs distintos y se agregan por sesión sin multiplicar la muestra independiente. La calibración conserva una fila por activo/sesión y el horizonte por defecto de 24 horas; un cambio a varias filas por decisión exige un contrato nuevo de residuos. Los exportadores Ridge y SVR conservan clase, factor, referencia y unidades: la ausencia se representa por null, sin inventar factor a partir del ticker. No se ejecutó un nuevo ensayo financiero en esta entrega ni se reinició el contador histórico de 23 intentos.

## Regresión de salida escalar mediante SVR · 1.4.0

El estimador opcional `svr` aprende el retorno simple del subyacente para el horizonte configurado. Recibe las ocho variables existentes del motor y devuelve un escalar en fracción: `0.01` significa 1 %. El kernel RBF permite relaciones no lineales. El escalado de variables y del objetivo se ajusta sólo con las observaciones de entrenamiento, y la salida se devuelve a sus unidades originales. Las predicciones negativas se conservan.

La calibración compara tres valores de C con la media pasada y con tres configuraciones del modelo ridge. Usa separación temporal y purga por fin de etiqueta y por fecha de disponibilidad. Un menor error predictivo no acredita rentabilidad. El artefacto SVR está sellado como investigación: el asignador calcula escenarios y cantidades en sombra, pero `execution_allowed` permanece falso incluso si el origen declarado es observado. No se incluye un mecanismo de activación financiera de SVR en esta entrega. Los modelos ridge anteriores conservan su ruta; sin `--estimator`, `fit` sigue usando ridge.

Esta SVR de retornos es distinta de `support.py`, que ya estima costes adicionales, y de la máquina de una clase usada para detectar novedad. Se mantiene un único worker Python. No se añaden servicios ni llamadas a modelos de lenguaje.

### Ejemplo reproducible de software

El panel de `examples/svr` es artificial y se generó para comprobar regresión no lineal, unidades y contratos; no contiene observaciones de mercado. Desde esta carpeta, tras instalar `requirements-tested.txt`:

```bash
python examples/svr/make_fixture.py
python -m harpoon_quant fit --estimator svr --input examples/svr/panel.synthetic.json --config examples/svr/config.synthetic.json --available-at 2026-10-14T15:00:00+00:00 --output examples/svr/model.synthetic.json
python -m harpoon_quant allocate --input examples/svr/request.synthetic.json --config examples/svr/config.synthetic.json --model examples/svr/model.synthetic.json --output examples/svr/receipt.synthetic.json
python -m unittest discover -s tests -p test_scalar_svr.py -v
```

`--estimator` se admite únicamente en `fit`; al inferir se utiliza el tipo sellado del artefacto. Los modelos SVR se vinculan al código del predictor: cambiarlo exige regenerar y revisar la calibración. Los hashes verifican consistencia local; no certifican autenticidad de las observaciones. Un modelo caducado, alterado, fuera de dominio o con habilidad predictiva insuficiente bloquea su uso para nuevas propuestas.

Los detalles ejecutados y sus limitaciones se conservan en `SVR_VALIDACION_1_4_0.yaml` y `evidence/svr/`. El estudio económico histórico y su journal se mantienen congelados.

## Auditoría adversarial 1.3.1

El journal detecta claves y reservas borradas; el analizador verifica sellos y conciliación antes de decidir y publica con estado recuperable. El replay incluye eventos EXIT, identifica posiciones, valida tiempos y conserva drawdown intradía. Los límites F nunca amplían una configuración más restrictiva, y el tamaño utiliza el patrimonio proyectado después del fill. El informe `AUDITORIA_HARPOONX_2026_10_31.yaml` detalla evidencia, limitaciones y comandos. `adversarial_verification/` conserva comparaciones fijas de ingeniería sobre datos sintéticos ya utilizados; no constituye validación independiente ni habilita operaciones. Los snapshots históricos de `economic_experiment` permanecen congelados.

## Investigación económica 1.3

[ECONOMIC_ES.md](ECONOMIC_ES.md) documenta el replay financiado, selección de vehículo, seis hipótesis y rechazo del finalista sintético. No se promueve ninguna política al runtime. Protocolo, código, journal y reproducción están en `economic_experiment/`.

## Métricas y calibración recursiva 1.2

Lee [RECURSIVE_ES.md](RECURSIVE_ES.md): Sortino, drawdown, Sharpe HAC, CVaR, Calmar, métricas netas y benchmark. El calibrador busca mejoras de selección y sizing con presupuesto persistente, holdout y promoción PAPER prospectiva condicionada. Sin P&L conciliado espera datos; no se acredita beneficio observado.

## Entorno de calibración 1.1

La guía vigente es [LAB_ES.md](LAB_ES.md): captura Alpaca L1, medidas de microestructura, superficies de correlación, registro vectorial SQLite, modelos SVR/One-Class SVM y separación de recepción viva y backfill. `python reproduce_observed.py` reproduce el análisis de la muestra observada incluida. Los ejemplos sintéticos están separados y no habilitan ejecución. `evidence/validation.json` identifica las pruebas de esta versión.

## Ejecutar el núcleo

Python 3.11 o superior; comprobado en 3.12.14. Desde la carpeta de este archivo:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-tested.txt
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m harpoon_quant allocate --input examples/request.synthetic.json --model examples/model.synthetic.json --output receipt.json
.venv/bin/python benchmark.py
```

El ejemplo tiene origen `SYNTHETIC_ENGINEERING_ONLY`, fechas fijas y pronósticos fabricados para comprobar ecuaciones y contratos. `execution_allowed` permanece falso. No cambies su origen para habilitar órdenes. Los datos sintéticos no representan cotizaciones OPRA, Yahoo Finance ni observaciones del mercado.

Para instalar como paquete: `pip install .`. El punto de entrada es `python -m harpoon_quant`. `allocate` recibe un request normalizado; `worker` acepta el snapshot del coordinador por stdin; `fit` genera el artefacto de calibración.

## Qué decide

1. Construye ocho variables reproducibles con barras cerradas y conocidas: momentum de 1, 3 y 12 barras, volatilidad de 12 intervalos contiguos de una sesión, RVOL, desviación de VWAP, fuerza relativa de 3 barras y spread relativo. RVOL compara el volumen acumulado al mismo horario con al menos 10 sesiones anteriores, hasta 20. El adaptador exige calendario real para acciones y SPY alineado como benchmark. Las barras cripto son de 15 minutos; las de acciones, de 5. Los coeficientes se calibran por subyacente.
2. Ajusta Ridge por defecto, o SVR al seleccionar `--estimator svr`. La variante SVR se describe arriba y permanece en sombra. La ruta Ridge usa partición cronológica 60/20/20 y purga etiquetas que cruzan fronteras. Elige entre tres penalizaciones con validación. El test compara MSE frente a la media histórica del tramo anterior con bootstrap de bloques de cinco sesiones y ajuste por familia. Superar esta prueba significa habilidad predictiva modelada; no significa beneficio económico.
3. Usa fechas comunes de residuos fuera de muestra para generar escenarios conjuntos. Los mismos índices conservan dependencia transversal. La covarianza con contracción diagonal y corrección PSD escala los escenarios extremos. Los extremos no reciben probabilidades inventadas dentro de la esperanza.
4. Revalora cada lote en USD al horizonte de 1–72 horas, por defecto 24. Incluye BBO, deslizamiento y comisiones declaradas de entrada y salida. Las opciones usan árbol americano de 128 pasos o Black–Scholes europeo y variaciones conjuntas de IV; el modelo se ancla al midpoint observado para no convertir una diferencia de precio teórico en alfa.
5. Resuelve una asignación entera con SciPy/HiGHS: efectivo, buying power, inventario, reservas pendientes, exposición bruta, factores, máximo de campañas, CVaR y pérdidas de estrés. Resta una penalización heurística de incertidumbre al beneficio medio; no es un intervalo de confianza formal. Puede elegir cero operaciones.
6. Las restricciones no consumen ganancias de otras entradas propuestas como cobertura: acotan el riesgo de cualquier subconjunto de fills nuevos. El coordinador invalida el plan si cambia la cuenta, inventario u órdenes durante el cálculo. La comprobación opera dentro del mutex; el cálculo numérico queda fuera para que las salidas conserven prioridad.

## Cobertura y requisitos

| Clase | Núcleo | Coordinador 30.4.0 | Condiciones |
|---|---|---|---|
| Acciones y ETF | Lotes enteros, escenarios de precio | Puerta cuantitativa de entradas | Calendario, BBO, histórico y modelo aceptado; SPY alineado |
| Cripto | Pasos fraccionarios | Puerta cuantitativa de entradas | USD, histórico de 25 días, pasos del catálogo y comisiones |
| Opciones call/put compradas | Precio no lineal, tiempo e IV | Integrado; bloquea metadatos incompletos | IV, delta, estilo, strike, vencimiento UTC, tasa, dividendo, revisión de ciclo de vida y muestra conjunta de IV |
| Futuros comprados | Multiplicador, margen y roll | Entrada normalizada; conector Ironbeam heredado separado | Margen verificado y revisión de roll; no se creó un broker de futuros en Alpaca |

Solo USD. No hay FX consolidado, financiación short, spreads multileg atómicos, renta fija, swaps ni opciones exóticas. Los ETF apalancados se modelan por su propio histórico y precio, sin fabricar réplicas. La valoración al horizonte no reproduce todas las rutas de TP, stop, trailing o piramidación del coordinador. El árbol americano usa rendimiento de dividendo continuo; no sustituye una agenda validada de dividendos discretos, eventos corporativos, ejercicio o asignación. Los futuros requieren precios positivos en este núcleo. No se modela profundidad de libro ni impacto en capacidad real.

## Red de pesca de acciones y ETF

La consulta cada 15 minutos durante sesión reúne SIP movers y most-actives. Admite acciones y ETF con clasificación, factor, referencia, unidades y modelo vigente admisibles; el catálogo verifica identidad y negociabilidad. La capacidad compartida es 40 instrumentos totales. Un valor heredado de 48 se limita explícitamente a 40, sin aumentar exposición ni número de posiciones.

La prioridad de cobertura es número de fuentes coincidentes descendente y símbolo ascendente. Es una regla reproducible, no un ranking de rentabilidad. Cada candidato conserva sus fuentes y motivo de exclusión. Sólo rotan instrumentos marcados como gestionados por discovery y sin posiciones, campañas, órdenes pendientes ni subyacentes protegidos. La conciliación se comprueba antes y después de las esperas. Los nombres estáticos se preservan.

La carga histórica se prepara antes de modificar el universo y se reintenta completa cuando falla; los símbolos existentes con historia incompleta también se reparan. Histórico suficiente no implica READY: hacen falta barras regulares recientes y cotización vigente. El registro persistido se restaura deshabilitado hasta verificar catálogo y datos actuales. Los snapshots se sellan y se conservan antes de publicar disponibilidad. Un error de persistencia mantiene el bloqueo de entradas; una exclusión de candidatos ya registrada no congela los otros libros. La investigación SVR conserva su guarda de cero consultas y cero modificaciones operativas.

Se necesitan permisos SIP para estos screeners. La presencia de un proceso o tarea viva se informa separada de la cobertura utilizable; estos controles no prueban acceso efectivo a una cuenta, ni la identidad de una versión desplegada.

## Calibrar con observaciones

El contrato completo está en `INPUTS_ES.md`. Es necesario suministrar un panel observado verificable: al menos 100 fechas distintas, un registro por subyacente y fecha, variables conocidas al decidir y retorno simple al horizonte exacto. El artefacto debe estar disponible después de conocerse todas las etiquetas. Las opciones requieren también `iv_change` alineada al mismo contrato/horizonte, y consistencia de universo y vencimientos gestionada por el productor de datos.

```bash
python -m harpoon_quant fit --input panel.observed.json --available-at 2026-10-29T12:00:00+00:00 --output quant_calibration.json
python -m harpoon_quant allocate --input request.observed.json --model quant_calibration.json --output plan.json
```

La fecha del ejemplo es ilustrativa: usa la disponibilidad real, nunca una fecha anterior a las etiquetas. El modelo caduca a los 30 días por defecto. Se exigen al menos 20 fechas de residuos comunes para cada decisión. El control de multiplicidad cubre los tres lambdas y los activos de esa ejecución; no controla campañas humanas ilimitadas de investigación ni reuso del test en futuras búsquedas. Se necesita un holdout prospectivo nuevo para validar economía.

`origin=OBSERVED` es una declaración del productor, no una autenticación del proveedor. `execution_allowed=true` expresa admisibilidad técnica del plan y solo puede ocurrir con ese origen; `liveApproved=false` sigue indicando ausencia de aprobación financiera independiente. No se entrega un modelo observado aceptado. El coordinador actual sigue limitado a Alpaca PAPER y conserva los controles de cuenta, riesgo y protección existentes. No se cambian los límites presupuestarios del servicio de opciones 1.2 independiente.

## Verificación reproducible

```bash
pip install -r requirements-dev.txt
python -m ruff check harpoon_quant tests benchmark.py
python -m mypy harpoon_quant
python -m unittest discover -s tests -v
```

`REMEDIACIONES_HARPOONX_30_9_0.yaml` documenta esta entrega. `SVR_VALIDACION_1_4_0.yaml` y `evidence/svr/release_validation.json` conservan la verificación histórica de 1.4.0. `evidence/validation.json` conserva la validación histórica del motor anterior. `evidence/benchmark.json` mide únicamente valoración CPU y MILP con 48 candidatos y 256 escenarios fabricados, tres repeticiones. No mide red, arranque del worker, liquidez ni latencia de fills. Los logs `diagnostics_initial/` conservan intentos fallidos de diagnóstico y no se suman a los resultados finales. El paquete completo contiene las pruebas del coordinador y del puente; este núcleo funciona de forma independiente.

## Qué falta para atribuir ventaja económica

Conservar panel y universo por fecha, ajustes y delistings; congelar hipótesis; evaluar fuera de muestra sin reutilizar holdout; reproducir BBO, disponibilidad y rutas de salida con costes y restricciones reales; medir P&L incremental frente a la misma cartera sin el motor, concentración del beneficio y sensibilidad a costes; continuar en sombra prospectiva y PAPER con conciliación de fills. Ninguna cantidad de tests sintéticos sustituye esa evidencia.

## Fuentes primarias de diseño

- scikit-learn 1.8, SVR: https://scikit-learn.org/1.8/modules/generated/sklearn.svm.SVR.html
- scikit-learn 1.8, prevención de fugas de información: https://scikit-learn.org/1.8/common_pitfalls.html
- SciPy `milp`: https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.milp.html
- Lobo, Fazel y Boyd, optimización de cartera con costes: https://stanford.edu/~boyd/papers/portfolio.html
- Alpaca clases de activos: https://docs.alpaca.markets/us/docs/about-alpaca
- Alpaca movers: https://docs.alpaca.markets/us/reference/movers-1
- Alpaca most-actives: https://docs.alpaca.markets/us/reference/mostactives-1

Estas fuentes motivan componentes documentados; no acreditan la rentabilidad de HarpoonX.
