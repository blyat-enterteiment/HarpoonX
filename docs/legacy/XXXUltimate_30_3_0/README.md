# HARPOON XXXUltimate 30.3.0

Coordinador Alpaca PAPER con piloto automático, protección durable y laboratorio cuantitativo. El conector adicional Ironbeam utiliza exclusivamente la API de simulación del broker. El software no acredita rentabilidad ni participación en Championship.

## Arranque automático

```bash
npm ci --ignore-scripts
npm run build:xxx
npm run start:ultimate
```

Configura antes las variables de `.env.example` en el entorno del proceso. Node no carga ese archivo por sí solo. Node 24 y Python 3 son requisitos. Abre `http://127.0.0.1:10000` si usas el origen local predeterminado. Usuario del panel: `trader`; contraseña: `HARPOON_PANEL_PASSWORD`, mínimo 32 caracteres.

Con claves PAPER válidas, cuenta dedicada y journal conciliado, el servidor arranca la vigilancia y las entradas automáticamente. `HARPOON_START_PAPER` omitido equivale a `1`; `0` permite iniciar con entradas pausadas. Una pausa guardada por el usuario sobrevive al reinicio y no se elimina por el arranque automático. La primera vinculación exige una cuenta PAPER vacía. Las posiciones ya gestionadas se recuperan desde el SQLite original; no borres el journal para eludir una discrepancia.

El pulso de posiciones se programa cada segundo, cotizaciones cada tres segundos y conciliación cada cinco segundos. Además reacciona a eventos del stream. Estos intervalos son objetivos del planificador, no latencias garantizadas del broker. Cada ciclo evita solaparse consigo mismo. El cálculo nuevo utiliza un worker separado; una investigación pausada no pausa la protección. Un pulso de protección atrasado o con error bloquea nuevas asignaciones aunque la cuenta todavía esté conciliada.

El piloto utiliza los seis plugins seleccionados y todos sus controles de datos, permisos y riesgo. El catálogo conserva 61 plugins implementados. La selección adicional es opcional: algunos modelos necesitan datos y aceptación antes de generar entradas. Las salidas de posiciones existentes siguen activas al apagar un plugin o pausar entradas. La configuración admite modificaciones por el operador antes de vincular un journal; conserva el archivo original al actualizar una cuenta ya vinculada.

## Take profit

La base conserva parciales, runner, trailing que no retrocede, planes de salida persistidos, conciliación de fills parciales y prioridad del stop urgente. Las acciones y ETF admiten grupos OCO para parciales y stop independiente para el runner; `nativeProtection: "oco_trailing"` también permite trailing nativo independiente. Cripto y opciones usan la protección admitida por su broker y la guardia del servidor. Un stop no asegura precio ni ejecución durante gaps o suspensiones.

La política por defecto sigue siendo la referencia anterior. Ninguna candidata ha superado todos los criterios estadísticos y prospectivos. Cambiar manualmente a una política experimental requiere la acción explícita existente en el panel y afecta a nuevas campañas. El laboratorio no modifica estrategias ni límites del piloto automáticamente.

## Pantallas nuevas

- **Ultimate research:** prerregistro, importación validada, ejecución en worker, resultados, gates y exportación del protocolo y cadena de hashes. Muestra un estudio retrospectivo calculado sobre barras observadas SPY y XLK.
- **Futuros y campeonato:** estado medido de cuenta y datos, contratos fechados, márgenes, posiciones y órdenes observadas, y cálculo de riesgo de un bracket. Sin credenciales muestra `NOT_CONFIGURED`, nunca un resultado ficticio.

Los controles son opcionales para la operativa Alpaca preconfigurada. El panel es un cliente del servidor; abrir el HTML como archivo no crea un motor, no almacena claves del broker ni inicia trading.

## Laboratorio Ultimate

Tres hipótesis: ruptura tras apertura, continuación por canal de sesiones cerradas y reversión condicionada hacia VWAP. Tres salidas por hipótesis: base, parcial con runner y adaptación fijada por el régimen observado a la entrada. Las nueve combinaciones por activo consumen el presupuesto acumulado del registro; 72 ensayos por cuenta, con multiplicidad mínima fijada al presupuesto completo. Retocar después de importar exige un nuevo registro y consume nuevas plazas. No se permite repetir el mismo intento ni reemplazar el dataset bloqueado.

La validación usa entrenamiento rodante, selección solo con entrenamiento, ventanas externas cronológicas, purga de 72 horas, separación temporal y holdout. Los mínimos de 100 campañas OOS y 30 de holdout son diagnósticos; no garantizan suficiencia. DSR ajusta selección bajo supuestos; PBO es un diagnóstico complementario. Ninguno equivale a probabilidad de beneficios futuros. Bootstrap conserva bloques y utiliza una semilla determinista para poder repetir el cálculo.

Las comparaciones TP congelan oportunidades, entrada, tamaño, stop y costes. La curva unitaria puede contener campañas solapadas y **no es rentabilidad de cuenta**. El replay de cartera se calcula por separado, con capital compartido y cantidades enteras. El estrés duplica costes sobre el mismo conjunto completo de oportunidades. Una prueba sin operaciones no cuenta como éxito.

Los módulos de frecuencias calculan autocorrelación, dependencia de volatilidad, estacionalidad y espectro sobre entrenamiento. El espectro usa tiempo de negociación concatenado y es descriptivo; un pico no genera una orden. Incorporarlo a una señal exigiría otro protocolo.

Los fills, spread y slippage se modelan expresamente. No se fabrica NBBO ni cola. Los datos se validan por sesión, orden temporal, disponibilidad, OHLCV, acción corporativa y contrato. Las sesiones incompletas se excluyen: esa selección de cobertura es retrospectiva y puede introducir sesgo. Las rutas incompletas y los cruces de split se excluyen simétricamente. Los datos aportados por el usuario tienen checksums, pero no una certificación del proveedor.

Reproducir el estudio incluido:

```bash
npm run research:ultimate
```

El comando verifica las 149 fuentes retenidas, usa el registro SQLite persistente y conserva cada intento. Agotar su presupuesto detiene nuevos registros. No borres `evidence/ultimate/research.sqlite` para reutilizar el historial como si fueran pruebas independientes. El ZIP incluye la exportación inmutable del registro y el informe; los journals de ejecución se excluyen. El historial de 2024 a 2026 ya fue observado y no puede presentarse como holdout independiente después de rediseñar reglas.

## Futuros

La ficha contractual incluye MES, MNQ, MGC, MCL y M6E. MES y MNQ son el primer universo; los demás son etapas posteriores. Las opciones sobre futuros, crypto futures y otros brokers no tienen aquí ejecución autónoma añadida. La operativa Alpaca de acciones, ETF, cripto spot y opciones compradas se conserva.

Para conectar Ironbeam PAPER configura `IRONBEAM_USERNAME`, `IRONBEAM_PASSWORD` o `IRONBEAM_API_KEY`, `IRONBEAM_ACCOUNT_ID` y `HARPOON_FUTURES_CONTRACTS`. Este último es un array JSON de contratos reales con `root`, `symbol`, `lastTradeAt` en milisegundos UTC y `firstNoticeAt` cuando exista entrega física. Se valida símbolo, multiplicador, tick y plazo de seguridad; no se inventan fechas. Los secretos también admiten variables terminadas en `_FILE`.

El conector consulta cuenta, riesgo, posiciones, órdenes, quotes y margen por rutas oficiales. No utiliza el host LIVE. Sin acceso realtime o sin margen/quotes frescos bloquea el cálculo ejecutable. Puede presupuestar cero contratos: USD20000 y riesgo 0.25% son USD50; un MNQ con stop de 30 puntos ya excede USD60 antes de costes. Además se conservan exposición total 50% y por activo 12%, que pueden impedir cualquier micro. La inversión requerida por margen no es el riesgo de la operación.

La interfaz calcula un bracket sin enviarlo. El endpoint de envío PAPER exige `HARPOON_FUTURES_PAPER_ORDERS=1`, coste completo por lado en `IRONBEAM_COMMISSION_PER_SIDE_USD`, identidad de petición y confirmación literal `SEND_IRONBEAM_PAPER_BRACKET`. Su respuesta significa recepción pendiente, no fill. Guarda la intención antes de enviar; una respuesta incierta bloquea nuevos envíos y jamás se reintenta automáticamente. Solo permite una campaña de bracket en una cuenta dedicada sin inventario ajeno. No hay traslado automático de las hipótesis de investigación a esta cuenta.

La API documenta brackets fijos y no soporta trailing nativo. Por ello el conector no anuncia un trailing vacío. Los datos de simulación pueden llegar retrasados; las comprobaciones de timestamp impiden interpretarlos como realtime. El replay financiado de futuros necesita observaciones de margen histórico: sin ellas declara la carencia y no supone margen cero. Elegibilidad, contratos, automatización y costes del evento deben confirmarse con el broker y el organizador.

## Verificación

```bash
npm run typecheck:xxx
npm run build:xxx
npm run test:xxx
npm run test:ultimate
npm run test:xxx:browser
npm run test:ultimate:browser
npm run audit:xxx
npm run benchmark:xxx
```

Las pruebas usan dobles de broker y datos sintéticos identificados exclusivamente en `tools`. El runtime no los importa. La auditoría estática inventaría cuerpos de función, imports de pruebas y marcadores inconclusos; no es auditoría independiente ni certificación de producción. Consulta `AUDITORIA_XXXUltimate.txt`, el informe walk forward y los hashes de la entrega para los resultados efectivamente ejecutados.

El Dockerfile conserva compilación separada y dependencias de producción; los informes requeridos están permitidos explícitamente en `.dockerignore`. No se ha construido la imagen ni desplegado esta versión desde este entorno. El contenedor incluye el informe; reproducir toda la investigación requiere las fuentes del ZIP, no la imagen mínima.

Fuente anterior y contexto de integración: [README de 30.2](docs/legacy/README_XXX_30_2_0.md). Las limitaciones allí descritas corresponden a esa versión.

Referencias primarias: [API Ironbeam](https://docs.ironbeamapi.com/), [acceso a API](https://www.ironbeam.com/knowledge-base/ironbeam-api-access/), [reglas Championship 2026](https://robbinstrading.com/wp-content/uploads/2025/09/2026FuturesWorldCupEntryAgreement.pdf), [CME micros](https://www.cmegroup.com/articles/faqs/micro-e-mini-equity-index-futures-frequently-asked-questions.html), [DSR](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf) y [PBO](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf).
