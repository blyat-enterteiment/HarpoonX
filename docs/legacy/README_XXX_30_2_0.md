# HARPOON XXX · 30.2.0

Coordinador de cartera Alpaca PAPER con motores asíncronos para acciones, ETF, cripto y opciones compradas. Sustituye el pulso de ejecución de XXV.3 R2: vigilar posiciones, refrescar opciones y tomar beneficios ya no depende del presupuesto ni de la disponibilidad del laboratorio.

**Entrega de código y pruebas locales. No desplegada, no publicada en GitHub y sin órdenes enviadas a Alpaca durante esta revisión. Rentabilidad no acreditada.**

## Cambios de take profit en 30.2

El plan de salida se guarda antes de cancelar la protección y sobrevive a un reinicio o a que desaparezca temporalmente el precio objetivo. Un stop urgente interrumpe un parcial pendiente, espera su cancelación confirmada y vende únicamente el remanente conciliado. La sincronización del stop usa el tick del instrumento; el panel distingue el piso calculado del confirmado por Alpaca.

En una instalación nueva, `nativeProtection: "oco"` coloca dos grupos OCO para los parciales de acciones/ETF y un stop independiente para el runner. `oco_trailing` permite un trailing nativo independiente; no se envía como pierna OCO. Un rechazo confirmado activa una protección simple real; una respuesta incierta bloquea nuevos envíos hasta conciliación. Cripto/opciones conservan sus tipos de orden admitidos y la guardia gestionada; no se les atribuye OCO. El modo de órdenes no modifica el presupuesto de riesgo.

WebSocket comparte cotizaciones, trades y libros con los plugins que los necesitan; evita conexiones duplicadas al mismo feed. Los eventos de órdenes despiertan conciliación y guardia sin esperar cinco segundos. OPRA usa MsgPack y su encabezado requerido; ante desconexión se invalida el calentamiento de flujo y REST mantiene su ciclo. La conexión/latencia/permisos externos aún requieren comprobación en la cuenta dedicada.

**Walk-forward previo a los cambios de ejecución: ningún candidato supera los criterios registrados.** Las salidas canónicas dejan sólo 7 operaciones comunes OOS y 5 de holdout; no hay una muestra que permita acreditar mejora. Las tres políticas pierden después de costes modelados. Se conserva la referencia por defecto, sin afirmar que sea rentable. Trend Runner y Regime Adaptive están implementadas pero requieren reconocer expresamente su uso experimental en PAPER; sólo afectan nuevas posiciones. No se instala un modelo ganador ficticio.

Informe: `evidence/tp32/WALKFORWARD_XXX_30_2.txt`; protocolo: `research/tp32/protocol.json`; fuentes y datos: `evidence/tp32/data`. La pantalla **Take profit lab** muestra resultados, planes, cobertura, comisiones estimadas/reportadas y latencias medidas. `docs/TAKE_PROFIT_32.md` describe método, límites y reproducción.

## Arranque de XXX

Requiere Node 24 y Python 3. Extrae el paquete en una carpeta privada y abre una terminal allí:

```bash
npm ci --ignore-scripts --no-audit --no-fund
npm run build:xxx
```

Copia `.env.example` como `.env`. Completa `APCA_API_KEY_ID`, `APCA_API_SECRET_KEY` y `HARPOON_PANEL_PASSWORD` —contraseña de al menos 32 caracteres—. Usa claves de una cuenta **PAPER dedicada**. En Windows, configura `PYTHON=python` si no existe `python3`.

Revisa `config/examples/xxx.json` antes del primer arranque. Luego ejecuta:

```bash
node --env-file=.env runtime30/server.js
```

Abre `http://127.0.0.1:10000`. Usuario: `trader`; contraseña: la indicada en `.env`. El proceso debe permanecer encendido; cerrar el navegador no lo detiene. `HARPOON_XXX.html` es una copia del panel: abrirlo como archivo no inicia el motor.

`HARPOON_START_PAPER=1` permite entradas al crear el primer diario, sujetas a los filtros. Con `0`, el primer arranque queda pausado. Los reinicios conservan la pausa persistida. **Pausar entradas** mantiene vigilancia y salidas. **Cerrar posiciones** solicita liquidar las posiciones identificadas por XXX según sesión, datos y conciliación.

En el primer arranque la cuenta debe estar sin posiciones ni órdenes. XXX no adopta inventario de R2 ni lo liquida para migrarlo. No ejecutes dos programas sobre la misma cuenta. Conserva `data/xxx/xxx.sqlite` y sus archivos WAL/SHM; no borres el diario para eludir un bloqueo. Una configuración distinta del diario exige reconciliar y preparar una migración; el programa la rechaza automáticamente.

## Cobertura

| Libro | Catálogo | Gestión y ejecución implementadas | Condiciones |
|---|---:|---|---|
| Acciones | 22 plugins | Compra, vigilancia, stops, TP parciales, trailing y cierre | Sesión regular, activo negociable, datos recientes y riesgo disponible |
| ETF | 22 plugins | Mismas funciones; exposición por factor y apalancamiento declarado | Incluye SPXL/SPXS; no compensa automáticamente exposiciones opuestas |
| Cripto | 14 plugins | Spot largo, vigilancia continua, TP, stop-limit y cierre | Precisión y tamaño del broker; sin margen ni cortos |
| Opciones | 3 plugins | Compra de call/put, cantidades enteras, protección, TP y cierre previo al vencimiento | OPRA, nivel de opciones >= 2, contrato estándar de 100, liquidez y vencimiento |

Se registran los 58 plugins identificados en el código recuperado y tres nuevas estrategias de opciones: ruptura alcista con call, ruptura bajista con put y recuperación con call. Inventario: `strategies/HARPOON_XXX_PLUGINS.json`. Se seleccionan en el panel. Integración significa cargar y evaluar las reglas; no demuestra que cada estrategia genere operaciones rentables.

Las variantes Ridge `equity-strategy-14` y `etf-strategy-14` conectan ahora registro, importación/captura de datos, entrenamiento real, validación temporal, instalación, persistencia, evaluación y revocación del modelo. Sin un modelo aceptado e instalado, permanecen en **ESPERA MODELO** aunque estén seleccionadas. No se incluyen pesos de muestra ni un modelo financieramente aceptado.

Por defecto se seleccionan seis plugins: los canónicos de acciones, ETF y cripto y los tres de opciones. Activar todos no elimina sus requisitos. ASTRA necesita flujo observado y el feed requerido; Shock Recovery necesita calentamiento y flujo real; los selectores y modelos económicos necesitan evidencia válida. Sin ella quedan en espera con un motivo visible.

Universo inicial: AAPL, MSFT, NVDA, SPY, SPXL, SPXS, BTC/USD y ETH/USD; opciones sobre SPY y AAPL. Se amplía en configuración antes del primer arranque, con factor, apalancamiento y precisión correctos. **Cuatro clases no significa escanear automáticamente todos los símbolos de Alpaca.** Los subyacentes de opciones también deben estar en el universo de acciones/ETF. No hay ejecutor de spreads, opciones vendidas, futuros ni forex.

## Take profit y riesgo común

Las salidas tienen prioridad sobre las entradas en la cola del coordinador. Vigilancia: intervalo objetivo de un segundo; cotizaciones: tres segundos; conciliación: cinco segundos. Son intervalos de planificación, no garantías de latencia del broker. Hay 21 ciclos independientes, sin solapamiento dentro de cada ciclo, y el laboratorio calcula en un worker separado.

La política base toma el 25% a 1,5R y otro 25% a 3R después de descontar costes estimados; el resto mantiene trailing. R es la distancia entre entrada y stop inicial. Acciones/ETF conservan los parámetros específicos de cada plugin. La política queda congelada al abrir la operación y el stop sólo se estrecha. Un contrato de opciones no se fracciona: se cierra entero al segundo objetivo o por la protección correspondiente.

Las cantidades proceden de fills confirmados. Antes de sustituir una protección se pide cancelación y se espera su confirmación: la respuesta a DELETE no basta. Una orden incierta se reconcilia por `client_order_id` sin reenvío a ciegas. Toda posición llena debe tener protección antes de otra entrada.

Los cuatro libros comparten capital, reservas y riesgo. Parámetros iniciales: techo de USD 20.000, riesgo de entrada 0,25%, riesgo abierto 1,5%, exposición total 50%, por activo 12%, ocho posiciones, pérdida diaria 2% y drawdown 8%. Son límites de partida, no parámetros optimizados. En opciones se reserva **toda la prima** como pérdida potencial; muchos contratos no cabrán en el presupuesto y no se comprarán.

El plazo máximo objetivo es de 72 horas; se adelanta al último cierre ejecutable si acaba fuera de sesión. Opciones añade un límite previo al vencimiento. Pérdida diaria/drawdown bloquea entradas y solicita cierres. Horarios cerrados, huecos, suspensiones, fallos o falta de liquidez pueden impedir ejecutar a tiempo o al precio esperado.

## Investigación independiente

El panel carga solicitudes JSON del laboratorio WarRoom/optimizador existente. Formatos y protocolos: `src/warroom3.js`, `src/optimizer3.js` y sus pruebas. Presupuesto inicial: 16 ejecuciones por diario; un error consume la ejecución iniciada. Este runtime no llama a GPT de pago.

El holdout exige entrenamiento calculado por este servidor con idénticos protocolo y datos. La ventana consumida queda reservada en SQLite; no se puede volver a probar cambiando parámetros. Sólo se exponen modelos económicos aceptados internamente y no se activan plugins automáticamente. Los backtests heredados no certifican las nuevas salidas XXX: falta validación prospectiva en PAPER con costes observados.

## Render

`render.yaml` define el nuevo servicio `harpoon-xxx-paper`, Docker Node 24/Python 3 y disco persistente en `/var/data`. Usa `deploy/Dockerfile.xxx`, que arranca el coordinador común. El Blueprint se validó contra el esquema oficial. No se construyó la imagen aquí porque el entorno no tiene Docker, ni se creó servicio remoto.

El Blueprint solicita claves Alpaca como secretos y genera la contraseña del panel. La URL externa de Render define el origen permitido; en otro alojamiento configura `HARPOON_PUBLIC_ORIGIN` con HTTPS. El repositorio encontrado, `masivarecords-ship-it/HerpoonX`, estaba vacío y el acceso disponible no permitía push: se entrega el paquete preparado para publicar.

## Verificación reproducible

```bash
npm run audit:xxx
npm run typecheck:xxx
npm run build:xxx
npm run test:xxx
npm test
npm run benchmark:xxx
```

Las pruebas XXX usan un broker simulado. Cubren cuatro clases, fills parciales, protección, cancelación pendiente, órdenes inciertas, reinicio, SQLite/lease, riesgo, independencia del laboratorio, fechas, exportación e HTTP autenticado. Suites heredadas ejecutadas: `evidence/xxx/regression.json`. Resultado vigente: `AUDITORIA_XXX.txt`.

La comparación histórica se reproduce con `npm run walkforward:xxx` (Python 3 con NumPy; dependencia de investigación en `research/tp32/requirements.txt`). Los datos históricos se incluyen para uso privado de esta entrega, sujetos a los términos del proveedor.

Prueba opcional de navegador: `node tools/xxx_browser.cjs`, con Playwright y Chromium instalados. Acepta `CHROMIUM_EXECUTABLE_PATH` y busca Playwright en el entorno de desarrollo o en `node_modules`. El microbenchmark mide sólo la decisión de salida con datos sintéticos, excluyendo red, SQLite y runtime completo.

## Límites y evidencia

- PAPER es el único destino del nuevo adaptador. No se verificaron conexión autenticada, feeds ni fills contra Alpaca durante esta entrega.
- Los stops aceptados pueden seguir en el broker si el proceso cae; TP y trailing necesitan el proceso. Opciones usa stop diario; cripto, stop-limit. Las órdenes pueden vencer, rechazarse o no llenarse. Hay un intervalo sin protección nativa entre cancelación confirmada y siguiente orden.
- El lease cubre procesos sobre el mismo SQLite, no otro equipo con otro diario. Una cuenta dedicada y una instancia; sin consenso distribuido.
- **Descargar estado y evidencia** incluye campañas cerradas e intentos con fills. Los eventos conservan una ventana limitada; no se archivan todos los ticks ni se auditan comisiones netas. El PnL de fills es bruto.
- No se configuraron backups externos, alertas externas ni restauración automática. Las afirmaciones históricas de otros instaladores no se trasladan a XXX.
- `install.sh`, `deploy/managed.cjs`, HTML XXIV/XXV y `render-legacy.yaml` son históricos. Para XXX usa el arranque de esta guía. Documentación anterior: `docs/legacy` y archivos con versión. Los hashes históricos describen entregas anteriores.

No existe evidencia para afirmar que XXX sea el trader más rentable de Alpaca en 2026. La aceptación operativa pendiente requiere build Docker, despliegue PAPER, reinicio con diario, conciliación y una muestra prospectiva de fills, costes, drawdown y comparación contra una referencia.

Referencias consultadas: [Alpaca Orders](https://docs.alpaca.markets/us/docs/orders-at-alpaca), [Options](https://docs.alpaca.markets/us/docs/options-trading), [Crypto](https://docs.alpaca.markets/us/docs/crypto-trading), [Render Blueprint](https://render.com/docs/blueprint-spec), [Render Disks](https://render.com/docs/disks).


## Revisión funcional 30.0.1

Se corrigieron parámetros ignorados de reentrada, estancamiento y trailing de volatilidad; se conectaron salidas nativas de canal cripto y evidencia ASTRA. Los datos sectoriales proceden ahora de barras del ETF sectorial correspondiente; sin evidencia permanecen ausentes. Las características de acciones/ETF requieren VWAP observado. El panel desconectado muestra estado sin verificar. El puente carga sólo declaraciones y funciones de señales, sin crear ejecutores antiguos.

La auditoría estática reproducible está en `tools/xxx_audit.cjs` y su inventario, en `evidence/xxx/function-audit.json`. Revisar funciones y aprobar pruebas locales no equivale a probarlas contra Alpaca. El broker PAPER también simula fills: [documentación oficial](https://docs.alpaca.markets/us/docs/paper-trading). Los dobles de prueba permanecen aislados en herramientas de QA. Las simulaciones históricas y bootstrap del laboratorio son cálculos identificados como estimaciones y no resultados operativos.

## Monitor y validadores 30.2.0

El panel tiene ocho espacios: mesa de ejecución, monitor, estrategias, señales/datos, capital/riesgo, investigación y bitácora. Es adaptable a escritorio y móvil. El patrimonio se dibuja sólo con snapshots de cuenta conciliados durante el proceso: no se rellena una curva histórica. Las marcas al bid vencidas dejan de presentarse como P&L vigente.

`/v1/health` y `/v1/state` entregan telemetría autenticada: CPU, memoria, event loop, uptime, solicitudes/errores/latencias del transporte, última escritura SQLite confirmada, ejecución y fallos de cada ciclo, cobertura y edad de cotizaciones, validadores y protección nativa. Ninguna sonda garantiza un fill. `/healthz` sólo comprueba que responde el proceso HTTP; `/readyz` comprueba conciliación y almacenamiento. No se confunden estos alcances.

| Estado | Evidencia |
|---|---|
| ALIVE | La función terminó y su muestra sigue dentro de su umbral |
| RUNNING | Una ejecución está en curso |
| STARTING / NOT_RUN | Todavía no hay una ejecución/validación terminada |
| WAITING / WAIT_DATA | Faltan datos o condiciones para evaluar |
| MARKET_CLOSED | El reloj del broker no permite sesión regular |
| STALE / STALLED | Muestra vencida / ejecución que excede su umbral |
| ERROR / DEGRADED | Fallo observado / salud agregada incompleta |
| DISCONNECTED | Lectura fallida o más de ocho segundos sin actualización del cliente |

El cliente consulta cada 2,5 segundos y aplica timeout de ocho segundos; al desconectar retira los indicadores verdes operativos y bloquea nuevas acciones. Los ciclos no se solapan y miden duración con reloj monotónico. El take profit conserva un ciclo de un segundo, con umbral de atraso de tres segundos. Los errores capturados por posición también se exponen. Una orden pendiente de cancelación o con cantidad insuficiente no acredita protección confirmada ni habilita otra entrada.

Los validadores están en `xxx/validators.ts`: configuración, diario, cuenta, reloj, inventario, órdenes/fills, intención ejecutable, señales/políticas de salida, cotizaciones, barras y modelos/datasets Ridge. Los contadores aumentan sólo al ejecutar el contrato; una escritura asíncrona no se marca aprobada antes del ACK de SQLite. NOT_RUN es ausencia de comprobación, no aprobación.

## Selector Ridge: flujo operativo

1. En Investigación elige Acciones o ETF, declara costes del estudio y registra el experimento. El servidor fija identidad, fecha, receta de catálogo y límites de riesgo; no acepta un modelo externo para instalarlo.
2. Importa una sola vez el histórico observado o empieza a recoger datos. El histórico queda inmutable por SHA-256. Sus muestras posteriores al registro no acreditan holdout. El servidor registra prospectivamente cotizaciones recibidas, características y cobertura de sesiones en SQLite.
3. **Validar modelo** ejecuta el cálculo existente en un worker separado: Ridge con calibración cronológica, purga, embargo, 12 folds y holdout final. Se requieren 384 sesiones completas, 1.000 trayectorias y 63 sesiones prospectivas posteriores al registro; además de las barreras de costes, riesgo y rendimiento del protocolo. Una ventana prospectiva completa se reserva al inspeccionarla, incluso mediante diagnóstico. No puede reutilizarse para ajustar la misma evaluación.
4. Sólo un informe interno aceptado, no sintético ni diagnóstico, permite instalar con la frase `INSTALAR SELECTOR PAPER`. Se verifican 25 barreras, el contrato del modelo y vigencia. La instalación no activa plugins ni entradas. La vigencia es de 30 días desde el cierre del holdout.
5. El modelo queda vinculado a cuenta, configuración, recetas y código de ejecución. Reiniciar conserva modelos válidos. Una corrupción, expiración o cambio de vínculo revoca el modelo opcional sin impedir conciliar y supervisar posiciones. Revocar/retirar queda persistido.

**Diagnóstico** puede ajustar y examinar evidencia histórica, pero sus resultados no autorizan instalación. Los imports no están acreditados por el broker. El replay heredado no certifica la ejecución ni las nuevas salidas XXX. Se necesita una evaluación prospectiva de operaciones y costes reales PAPER. El informe distingue código conectado de estrategia financieramente validada.

Contrato de importación: objeto con `samples`, `events`, `sessions` y `source`; ejemplo estructural y tipos en `docs/SELECTOR_DATA.md`. Exportar datos devuelve observaciones disponibles, nunca ticks generados para completar evidencia.

## Validación de esta entrega

La auditoría estática exige el ciclo Ridge conectado; termina con código 2 si detecta una integración pendiente. Con código conectado usa `STATIC_REVIEW_ONLY_EXTERNAL_VALIDATION_PENDING`: no equivale a certificar todos los casos operativos ni los resultados financieros. Revisa los archivos inventariados de las rutas actuales, detecta cuerpos vacíos inexplicados, dependencias de tests y marcadores de implementación pendiente. Se mantienen las fuentes antiguas identificadas como legado para trazabilidad y regresión; su documentación no configura XXX.

Las pruebas automatizadas y sus cifras actuales se encuentran en `AUDITORIA_XXX.txt` y `evidence/xxx`. Los dobles de broker, datasets sintéticos y un doble de aceptación interna para probar instalación están aislados en `tools/*test*`; no se importan al arranque. Esta prueba de instalación no es una aceptación financiera real. El microbenchmark sólo mide la decisión de salida en memoria.
