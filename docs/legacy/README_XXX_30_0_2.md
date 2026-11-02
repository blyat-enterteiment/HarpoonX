# HARPOON XXX · 30.0.2

Coordinador de cartera Alpaca PAPER con motores asíncronos para acciones, ETF, cripto y opciones compradas. Sustituye el pulso de ejecución de XXV.3 R2: vigilar posiciones, refrescar opciones y tomar beneficios ya no depende del presupuesto ni de la disponibilidad del laboratorio.

**Entrega de código y pruebas locales. No desplegada, no publicada en GitHub y sin órdenes enviadas a Alpaca durante esta revisión. Rentabilidad no acreditada.**

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

**Hallazgo de la revisión 30.0.1:** las variantes Ridge `equity-strategy-14` y `etf-strategy-14` tienen evaluador, pero XXX todavía no conecta entrenamiento e instalación del selector. Permanecen bloqueadas y el panel lo indica. No se certifican las 61 variantes como operativas de extremo a extremo.

Por defecto se seleccionan seis plugins: los canónicos de acciones, ETF y cripto y los tres de opciones. Activar todos no elimina sus requisitos. ASTRA necesita flujo observado y el feed requerido; Shock Recovery necesita calentamiento y flujo real; los selectores y modelos económicos necesitan evidencia válida. Sin ella quedan en espera con un motivo visible.

Universo inicial: AAPL, MSFT, NVDA, SPY, SPXL, SPXS, BTC/USD y ETH/USD; opciones sobre SPY y AAPL. Se amplía en configuración antes del primer arranque, con factor, apalancamiento y precisión correctos. **Cuatro clases no significa escanear automáticamente todos los símbolos de Alpaca.** Los subyacentes de opciones también deben estar en el universo de acciones/ETF. No hay ejecutor de spreads, opciones vendidas, futuros ni forex.

## Take profit y riesgo común

Las salidas tienen prioridad sobre las entradas en la cola del coordinador. Vigilancia: intervalo objetivo de un segundo; cotizaciones: tres segundos; conciliación: cinco segundos. Son intervalos de planificación, no garantías de latencia del broker. Hay 18 ciclos independientes, sin solapamiento dentro de cada ciclo, y el laboratorio calcula en un worker separado.

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

Prueba opcional de navegador: `node tools/xxx_browser.cjs`, con Playwright y Chromium instalados. Acepta `CHROMIUM_EXECUTABLE_PATH` y busca Playwright en el entorno de desarrollo o en `node_modules`. El microbenchmark mide sólo la decisión de salida con datos sintéticos, excluyendo red, SQLite y runtime completo.

## Límites y evidencia

- PAPER es el único destino del nuevo adaptador. No se verificaron conexión autenticada, feeds ni fills contra Alpaca durante esta entrega.
- Los stops aceptados pueden seguir en el broker si el proceso cae; TP y trailing necesitan el proceso. Opciones usa stop diario; cripto, stop-limit. Las órdenes pueden vencer, rechazarse o no llenarse. Hay un intervalo sin protección nativa entre cancelación confirmada y siguiente orden.
- El lease cubre procesos sobre el mismo SQLite, no otro equipo con otro diario. Una cuenta dedicada y una instancia; sin consenso distribuido.
- **Descargar estado y evidencia** incluye campañas cerradas e intentos con fills. Los eventos conservan una ventana limitada; no se archivan todos los ticks ni se auditan comisiones netas. El PnL de fills es bruto.
- No se configuraron backups externos, alertas externas ni restauración automática. Las afirmaciones históricas de otros instaladores no se trasladan a XXX.
- `install.sh`, `deploy/managed.cjs`, HTML XXIV/XXV y `render-legacy.yaml` son históricos. Para XXX usa el arranque de esta guía. Documentación anterior: `docs/legacy` y archivos con versión. Los hashes históricos describen entregas anteriores.

No existe evidencia para afirmar que XXX sea el trader más rentable de Alpaca en 2026. La aceptación operativa pendiente requiere build Docker, despliegue PAPER, reinicio con diario, conciliación y una muestra prospectiva de fills, costes, drawdown y comparación contra una referencia.

Referencias consultadas: [Alpaca Orders](https://docs.alpaca.markets/docs/orders-at-alpaca), [Options](https://docs.alpaca.markets/us/docs/options-trading), [Crypto](https://docs.alpaca.markets/us/docs/crypto-trading), [Render Blueprint](https://render.com/docs/blueprint-spec), [Render Disks](https://render.com/docs/disks).


## Revisión funcional 30.0.1

Se corrigieron parámetros ignorados de reentrada, estancamiento y trailing de volatilidad; se conectaron salidas nativas de canal cripto y evidencia ASTRA. Los datos sectoriales proceden ahora de barras del ETF sectorial correspondiente; sin evidencia permanecen ausentes. Las características de acciones/ETF requieren VWAP observado. El panel desconectado muestra estado sin verificar. El puente carga sólo declaraciones y funciones de señales, sin crear ejecutores antiguos.

La auditoría estática reproducible está en `tools/xxx_audit.cjs` y su inventario, en `evidence/xxx/function-audit.json`. Revisar funciones y aprobar pruebas locales no equivale a probarlas contra Alpaca. El broker PAPER también simula fills: [documentación oficial](https://docs.alpaca.markets/us/docs/paper-trading). Los dobles de prueba permanecen aislados en herramientas de QA. Las simulaciones históricas y bootstrap del laboratorio son cálculos identificados como estimaciones y no resultados operativos.

## Validación estricta 30.0.2

El criterio de "todas las funciones integradas" resulta **NO CONFORME** por las dos variantes Ridge pendientes. `npm run audit:xxx` ahora termina con código 2 mientras existan esas integraciones pendientes: un inventario estático limpio no produce una aprobación falsa. El panel muestra 61 estrategias registradas y dos bloqueadas, deshabilita sus casillas y el servidor rechaza su activación sin modificar la selección anterior. Las condiciones de datos/permisos de otras estrategias siguen aplicando.

Se ejecutaron 65 pruebas y 19 comprobaciones del navegador. Los logs y la salida no conforme de aceptación están en `evidence/xxx`. Esto confirma el comportamiento probado con datos controlados; no acredita conexión autenticada ni ejecución contra Alpaca.
