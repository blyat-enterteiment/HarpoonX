# Actualización 1.2

La conexión recursiva y las métricas vigentes se documentan en [RECURSIVE_ES.md](RECURSIVE_ES.md). El modelo de retornos y los modelos de soporte siguen congelados durante la búsqueda. El texto siguiente describe las herramientas heredadas de 1.1.

# HarpoonX 1.1 · entorno de calibración y microestructura

Extensión funcional del motor 1.0, integrada en XXXUltimate 30.5.0. Los métodos se inspiran en literatura pública de microestructura y en prácticas documentadas de investigación y provisión de liquidez. No se afirma conocer ni replicar el core propietario de Jane Street, Citadel o Citadel Securities.

## Arranque reproducible

Python 3.11 o superior; entorno ejecutado: Python 3.12.14, NumPy 2.3.5, SciPy 1.17.0 y scikit-learn 1.8.0. Desde esta carpeta:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-tested.txt
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python reproduce_observed.py
.venv/bin/python -m harpoon_quant.lab micro --input observed/l1_AAPL.json --output micro_AAPL.json
.venv/bin/python -m harpoon_quant.lab curves --input observed/correlation_panel.json --output curve.json
```

El análisis observado recupera y mide el insumo incluido; no ejecuta operaciones ni entrena un modelo financiero con esta muestra breve. `evidence/observed_analysis.json` conserva los resultados y `evidence/observed_curves.sqlite3` las curvas registradas. Los datos de precios recibidos y sus hashes están en `observed/`.

## Qué cambió en el motor

- El coordinador conserva tamaños, condiciones y exchanges del BBO, incluidos mensajes de opciones MsgPack. Antes se descartaban los tamaños al entregar cotizaciones al callback.
- El colector toma la última observación por segundo y tipo, hasta cinco minutos y un máximo de 360 muestras por instrumento/tipo. Expone omisiones. Es una muestra L1 para swing trading; no contiene todos los trades ni todos los cambios de libro. Se descarta la caché del book que reconecta. No se inicia una segunda conexión de mercado.
- La nueva lane `quant-calibration-context` corre cada 15 minutos fuera del mutex, aunque no exista un modelo de retornos. Calcula diagnósticos, almacena superficies y busca episodios anteriores disponibles. Sus eventos distinguen `NOT_READY`, `UNCALIBRATED` y `STORED`; que el scheduler termine no certifica datos completos ni rentabilidad.
- El guard de entradas exige calentamiento y cobertura de microestructura cuando `required=true`. El ejemplo exige 20 muestras, 60 segundos de span, BBO reciente y al menos 50% de cobertura temporal de una ventana de 300 segundos; esto puede exigir alrededor de 150 segundos de captura continua. Una muestra sin tamaños no los inventa. Las salidas permanecen independientes.
- Un SVR de costes observado y aceptado puede añadir deslizamiento por lado. Nunca reduce el spread, las comisiones ni el deslizamiento base. Un One-Class SVM calibrado puede rechazar entradas fuera de su dominio. Una calibración sintética no se aplica operativamente.
- Las curvas y su SVM de regímenes se usan como diagnósticos; no se convierten automáticamente en alfa ni cambian los factores de cartera. Los modelos se congelan en JSON con hash, sin deserializar pickle y sin autoentrenamiento persistente.

## Medidas L1 y aproximaciones

| Medida | Cálculo / unidad | Límite |
|---|---|---|
| Spread temporal | 10,000 × (ask − bid) / midpoint, ponderado por duración válida | Del feed observado; IEX no equivale a NBBO consolidado |
| P95 de spread | Percentil por eventos válidos, en bps | No es un percentil temporal ni un precio garantizado |
| Imbalance | (bid size − ask size) / profundidad visible total | Solo mejor nivel; sin liquidez oculta |
| Midpoint ponderado | (ask × bid size + bid × ask size) / tamaño total | Proxy estático; no microprice entrenado |
| OFI normalizado | Cambios de precio/tamaño en mejor bid/ask, escalados por profundidad y número de intervalos válidos | Proxy sobre los eventos observados/muestreados, no cancelaciones ni cola completa |
| Flujo firmado | Trades comparados con BBO estrictamente anterior y tick rule en el midpoint | El agresor se infiere; el signo y el volumen total del mercado no se conocen |
| Spread efectivo | Distancia absoluta del trade al midpoint anterior, por tamaño | Requiere BBO suficientemente reciente |
| Volatilidad de midpoint | Raíz de suma de retornos logarítmicos cuadrados contiguos, en bps | No anualizada; contiene ruido microestructural |
| Cobertura | Duración de BBO válido / ventana solicitada | Se acota la duración de una cotización para no rellenar huecos |
| Markout futuro | Cambio firmado del midpoint posterior | Solo etiqueta de resultado; nunca variable disponible al decidir |

Alpaca documenta tamaños de acciones en acciones desde el 3 de noviembre de 2025 y en lotes antes de esa fecha. El normalizador convierte lotes a acciones para comparar profundidad. No aplica ese multiplicador a opciones o cripto. Se permite declarar `size_unit` explícitamente. Las condiciones no reconocidas, BBO bloqueados/cruzados y tamaños no positivos se excluyen y contabilizan.

El colector vivo utiliza `ALPACA_L1_LAST_PER_SECOND`. Un modelo entrenado con `FULL_EVENT_CAPTURE` no se admite como si hubiera recibido ese mismo muestreo. Las métricas del insumo histórico de dos segundos contienen eventos recuperados sin esa reducción adicional; no se mezclan con un modelo de captura por segundo.

## Capturar un periodo nuevo de Alpaca

El cliente es exclusivamente de datos y utiliza un único adaptador HTTP GET, host fijo y paginación acotada. Lee `APCA_API_KEY_ID` y `APCA_API_SECRET_KEY` del entorno, sin incluir claves en archivos, argumentos de CLI o informes. No contiene rutas para enviar órdenes.

```bash
python -m harpoon_quant.lab collect --symbols AAPL,NVDA --kind quotes --start 2026-10-28T14:00:00Z --end 2026-10-28T14:00:02Z --feed sip --output quotes.json
python -m harpoon_quant.lab collect --symbols AAPL,NVDA --kind trades --start 2026-10-28T14:00:00Z --end 2026-10-28T14:00:02Z --feed sip --output trades.json
```

Hay soporte REST de acciones/ETF y cripto. Opciones reutiliza el stream OPRA del coordinador. No se añadió un proveedor de microestructura de futuros a Alpaca. El feed es explícito; no se cambia SIP por IEX silenciosamente ni se compra una suscripción. Las cuotas y permisos siguen siendo los de la cuenta.

El límite de datos de Alpaca es global por página y el orden puede agotar un símbolo antes de llegar a los demás. El cliente continúa con `next_page_token`, rechaza tokens repetidos y marca `complete=false` si llega al presupuesto de páginas. El conector usado en esta ejecución no expuso tokens: se corrigió el muestreo inicial consultando cada símbolo por separado y las consultas finales no alcanzaron su límite. Eso no prueba que no existan correcciones o mensajes omitidos por el proveedor.

Cada descarga conserva `known_at` de recepción como backfill histórico. `LIVE_RECEIPT` exige disponibilidad real al decidir; `EVENT_TIME_REPLAY` permite estudiar tiempos de mercado reconstruidos y siempre se identifica como tal. No debe usarse la fecha del evento como prueba de que el sistema lo recibió en vivo.

## Superficies y memoria vectorial

`surface` calcula correlación de retornos de sesión en ventanas de 32, 64 y 128 observaciones y lags −6, −3, −1, 0, 1, 3 y 6. Solo empareja timestamps exactos; excluye saltos entre sesiones y no rellena precios. Un lag positivo significa corr(A_t, B_t−lag): asociación histórica, sin causalidad demostrada. Incluye beta, correlación condicionada a retornos negativos, coincidencia de cola inferior, cambios frente a una ventana previa no solapada, matriz regularizada PSD, concentración del primer autovalor y rango efectivo.

Los intervalos Fisher utilizan una aproximación de autocorrelación. Son descriptivos y no corrigen la búsqueda de toda la superficie. `DESCRIPTIVE_BREAK` significa que la diferencia supera un umbral configurado en el método; no es una prueba de cambio estructural ni un gatillo ganador. Las colas pueden contener muy pocas observaciones. Las curvas de sesión tampoco sustituyen la medición de riesgo overnight de una operación de 1–3 días.

El registro SQLite conserva vector, superficie completa, procedencia, feed, reloj, disponibilidad, esquema y hashes. Las búsquedas RMS o coseno separan datos observados/sintéticos, feeds, relojes, frecuencia y universo. Excluyen el presente, datos futuros y el embargo, por defecto un día. El índice es exacto dentro de un presupuesto de 5,000 filas y 32 MiB de payload por consulta; expone truncamiento. Una revisión posterior del mismo instante no se cuenta como otro episodio. No se borra automáticamente el historial. Para escalar más allá del presupuesto se requiere una evaluación de almacenamiento e indexación, no una afirmación de búsqueda global.

```bash
python -m harpoon_quant.lab curves --input observed/correlation_panel.json --db my_curves.sqlite3 --known-at 2026-10-30T00:00:00+00:00 --output curve.json
python -m harpoon_quant.lab neighbors --input curve.json --db my_curves.sqlite3 --available-at 2026-10-30T00:00:01+00:00 --output neighbors.json
python -m harpoon_quant.lab registry-get --db my_curves.sqlite3 --id ID_DEVUELTO_POR_EL_REGISTRO --output stored_curve.json
```

La fecha de `known-at` debe ser la disponibilidad real del archivo, posterior o igual a la decisión. El ID del último comando es un argumento requerido que devuelve el comando anterior, no una identidad predeterminada. Los hashes comprueban consistencia de archivos y registros; no autentican al proveedor ni convierten similitud en capacidad predictiva.

En producción el contexto reduce el cálculo a 12 símbolos como máximo por defecto, priorizando SPY e inventario, y declara los excluidos por presupuesto. Normaliza barras 5Min de valores a 15Min sin usar grupos incompletos para alinearlas con cripto. El motor offline admite hasta 48 símbolos. Si cambian el universo o el esquema, no se aplica el modelo de regímenes anterior de forma implícita.

## Calibrar soporte vectorial

Hay dos artefactos separados:

1. **Costes:** `support-fit` usa SVR RBF, tres valores de C y tres folds expansivos purgados. Reserva 20% para calibrar un margen superior de coste y 20% final para evaluación. Compara MSE con la media pasada y usa bootstrap por fecha con ajuste por los tres intentos. El One-Class SVM complementario revisa el dominio de las variables L1. Los indicadores de campos ausentes se incluyen; medianas y escalas se ajustan solo con entrenamiento.
2. **Regímenes:** `regime-fit` aprende la forma compacta de las curvas con One-Class SVM. Entrena 60%, calibra el umbral de novedad en 20% y describe la frecuencia de alertas en el 20% final. No predice rendimientos ni la siguiente correlación. La representación mantiene medias/dispersiones por ventana y lag y estadísticas espectrales. El modelo queda vinculado al esquema del universo.

Ambos exigen al menos 120 muestras y 100 fechas distintas, datos disponibles antes de la creación del artefacto y observaciones recientes. Reetiquetar un panel antiguo con una fecha de ajuste nueva no renueva su vigencia. Hay caducidad de 30 días desde el modelo y desde su última observación. La división del modelo de regímenes es cronológica por muestras; para evaluar cobertura estadística se debe además agrupar y controlar dependencia por sesión. Un ratio de alertas no es una probabilidad de pérdida.

La ruta `modelFile` acepta un modelo único o un bundle JSON `{"schema":"HARPOON_SUPPORT_BUNDLE_1","models":[modelo1,modelo2]}`. Cada artefacto interno conserva su hash. Se elige exactamente un modelo por feed, book, muestreo y alcance de símbolos; cero coincidencias se declara pendiente para ese dominio y varias coincidencias se rechazan. Un modelo SIP no se aplica a cripto ni OPRA.

El panel SVR requiere `origin`, `feed`, `sampling_schema`, `book_scope`, `symbol_scope` opcional, `horizon_hours`, `feature_names` y `rows`. Cada fila lleva `at`, `features_known_at`, `label_end`, `label_known_at`, `features` y `target_extra_bps`: coste adicional de ida y vuelta excluyendo spread, comisiones y deslizamiento ya modelados. Debe derivarse de fills observados y BBO de referencia, con definición estable de etiqueta. No se inventa esta etiqueta a partir de precios de cierre. La calibración requiere suficientes etiquetas fuera de muestra y no garantiza cobertura del margen de coste bajo drift.

El panel de regímenes lleva `origin`, `clock`, `feed`, `surface_schema_hash`, `feature_names` y `rows` con `at`, `known_at` y `features`. Puede construirse a partir de `regime_features(curve)`. Un backfill no puede declararse como recepción viva. La salida del modelo de regímenes solo es diagnóstica, incluso con origen observado.

Los ejemplos siguientes son fabricados para verificar la calibración y están separados de `observed/`:

```bash
python -m harpoon_quant.lab support-fit --input examples/lab/support_panel.synthetic.json --available-at 2026-09-01T15:00:00+00:00 --output support.synthetic.json
python -m harpoon_quant.lab support-eval --input examples/lab/support_evaluation.synthetic.json --model support.synthetic.json --output support_score.json
python -m harpoon_quant.lab regime-fit --input examples/lab/regime_panel.synthetic.json --available-at 2026-07-01T15:00:00+00:00 --output regime.synthetic.json
python -m harpoon_quant.lab regime-eval --input examples/lab/regime_evaluation.synthetic.json --model regime.synthetic.json --available-at 2026-07-02T15:00:00+00:00 --output regime_score.json
```

Las fechas corresponden a esos ejemplos. No instales esos modelos en la ruta operativa ni cambies su origen. La muestra observada incluida de ocho sesiones y dos segundos L1 es insuficiente para entrenar estos modelos con sus mínimos.

## Integración y límites pendientes

Configura `quant.microstructure` en el coordinador: `enabled`, `required`, `windowSeconds`, `minQuoteEvents`, `minCoverageSeconds`, `minWindowCoverageFraction`, `maxQuoteAgeSeconds`, `curveMaxSymbols`, `registryPath`, `modelFile` y `regimeModelFile`. El registro predeterminado es `/var/data/quant_curves.sqlite3`; requiere almacenamiento durable. El ejemplo conserva el feed de acciones configurado, IEX; el análisis observado incluido es SIP y permanece segregado. Seleccionar SIP en el despliegue requiere permisos disponibles, sin fallback silencioso.

Falta una captura prospectiva suficiente, etiquetas de ejecución para SVR, calibración observada de regímenes y beneficio incremental en PAPER/holdout nuevo. No se ejecutó un broker autenticado de órdenes, una imagen Docker ni un despliegue. El servicio separado de opciones 1.2 y el conector Ironbeam no se fusionan aquí. Las funciones existentes de salidas y límites siguen siendo las autoridades de ejecución.

## Fuentes primarias

- Alpaca quotes y unidades: https://docs.alpaca.markets/us/reference/stockquotesingle-1
- Alpaca IEX/SIP: https://docs.alpaca.markets/us/docs/market-data-faq
- Streams de acciones: https://docs.alpaca.markets/us/docs/real-time-stock-pricing-data
- Streams de opciones: https://docs.alpaca.markets/us/docs/real-time-option-data
- Cont, Kukanov y Stoikov, OFI: https://arxiv.org/abs/1011.6402
- scikit-learn OneClassSVM: https://scikit-learn.org/stable/modules/generated/sklearn.svm.OneClassSVM.html
- scikit-learn SVR: https://scikit-learn.org/stable/modules/generated/sklearn.svm.SVR.html
- Jane Street, enfoque público: https://www.janestreet.com/what-we-do/overview/
- Citadel Securities, spreads y liquidez: https://www.citadelsecurities.com/news-and-insights/market-lens-has-market-structure-evolution-made-equities-less-liquid/
