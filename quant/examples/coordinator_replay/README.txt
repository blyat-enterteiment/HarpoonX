HARPOONX: REPLAY OFFLINE CON COORDINADOR REAL
==========================================

Naturaleza y alcance
-------------------
Este ejemplo es SINTÉTICO. Las órdenes, confirmaciones, parciales, precios de
ejecución, liquidez, comisiones y calendario pertenecen a un escenario MODELED.
No se conecta a una cuenta, no entrena un modelo y no demuestra rentabilidad.

tools/coordinator_replay.cjs invoca los módulos reales compilados de Plugins,
Coordinator, policy y exits. No reimplementa las fórmulas de TP, trailing ni la
decisión de salida. Se conservan patrimonio e inventario entre eventos y
reinicios. Las posiciones abiertas siguen valoradas al bid disponible; se
declaran los símbolos con una valoración obsoleta. No se inventa un cierre final.

El alcance inicial admite posiciones largas de acciones, ETF y criptomonedas
al contado, multiplicador contractual 1 y protección de tipo stop. Un ETF
apalancado se contabiliza por sus participaciones y sus precios: no se vuelve a
multiplicar su PnL por el apalancamiento. La selección/tamaño usan la política
real y sus factores. Las opciones, posiciones cortas, OCO nativo, prioridad de
cola, liquidez oculta y concurrencia del scheduler están fuera de este contrato.

Las herramientas globales de red y de creación de procesos se bloquean durante
la ejecución aislada. El coordinador solo recibe SimulatedReplayBroker. No se
inicia el scheduler ni el trabajador numérico, ni se escriben los diarios de
experimentos históricos. Los parches temporales se restauran al terminar, también
ante una excepción. Solo se admite un replay a la vez en el mismo proceso Node.

Comandos desde la raíz de la distribución
---------------------------------------
node node_modules/typescript/bin/tsc -p tsconfig.xxx.json
node tools/coordinator_replay.cjs --input quant/examples/coordinator_replay/synthetic_request.json --output quant/examples/coordinator_replay/synthetic_report.json
node tools/coordinator_replay.cjs --input quant/examples/coordinator_replay/synthetic_request.json --output quant/examples/coordinator_replay/synthetic_verification.json --verify quant/examples/coordinator_replay/synthetic_report.json
node --test --test-isolation=none --test-reporter=tap --test-force-exit tools/quant_coordinator_replay_test.cjs

El CLI devuelve código 2 cuando una verificación reproducible no coincide; un
contrato inválido devuelve código 1. --output crea el archivo completo.

Funciones y validadores
----------------------
validateRequest(input)
  Exige origen, modo offline, cuenta OFFLINE-*, costes explícitos, liquidez
  cuantificada por evento y calendario. Rechaza datos futuros, barras sin cerrar,
  eventos fuera de orden, duración máxima superior a 72 horas, modo LIVE,
  streaming y habilitación del bridge de producción dentro del replay.

executeReplay(input)
  Realiza una pasada con el coordinador real. Un evento market solo incorpora
  barras conocidas al decidir y cotizaciones recibidas causalmente. Un fill
  requiere una cotización de mercado ESTRICTAMENTE posterior al envío. Las
  órdenes limitadas deben cruzarse en el escenario explícito de precios.
  No se afirma que esa cotización garantice ejecución en un mercado real.
  La cantidad ejecutable del evento se comparte entre las órdenes de ese símbolo.
  Una cotización repetida no crea un segundo presupuesto de liquidez.

  Una solicitud DELETE solo registra cancelación pendiente. El evento separado
  cancel_confirm es quien informa un estado terminal. Hasta entonces pueden
  llegar fills tardíos. reconcile usa el flujo de validación real de inventario.

runReplay(input)
  Ejecuta dos pasadas del mismo código real y compara decisiones, mutaciones de
  órdenes, posiciones, estados de salida, fills y contabilidad. Emite hashes de
  entrada, fuentes, alcance y artefacto, además de cada comparación.

verifyReport(input, report)
  Valida bindings y reproduce el trabajo. Cambiar salida, inventario o costes
  invalida el informe incluso si se recalcula su hash de integridad. Un hash solo
  aporta integridad, no prueba que la estrategia tenga ventaja.

compareReplays(inputs)
  Admite de dos a tres candidatos y comprueba que solo difieren id y predictor.
  Universo, riesgo, calendario, eventos, capital y costes deben ser idénticos.
  C0 usa el plugin real. Ridge/SVR pueden usar recibos de selección precomputados
  ligados al hash de la solicitud real, modelo y fecha de entrenamiento anterior
  al evento. Esos recibos no prueban por sí solos que el predictor se entrenó o
  calculó correctamente. predictor_parity_verified permanece false en ese modo.

  El adaptador de recibos solo existe en tools y en una ejecución aislada con
  SimulatedReplayBroker. No cambia los guardas SVR del bridge/worker ni concede
  permisos de ejecución externa. El permiso interno permite que entries recorra
  su política real en memoria; no es una autorización PAPER o LIVE.

Estructura de la entrada
-----------------------
schema: HARPOON_COORDINATOR_REPLAY_REQUEST_1
mode: OFFLINE
execution_origin: MODELED
data_origin: SYNTHETIC o HISTORICAL (etiqueta declarada por la fuente)
start_at: epoch milisegundos
initial_cash_usd: capital inicial sin posiciones
config: configuración completa con quant.enabled=false
calendar: filas date/open/close en formato del calendario del broker
execution_model:
  origin: MODELED
  causal_fills: STRICTLY_LATER_QUOTE
  cancel_mode: EXPLICIT_CONFIRMATION
  mark_method: BID
  ack_latency_ms: 0 (supuesto explícito del alcance inicial)
  fees_bps_per_side: número >= 0, nunca null
  fee_per_fill_usd: número >= 0, nunca null
  slippage_bps: número >= 0, nunca null
  external_cost_usd: número >= 0, nunca null
  liquidity_assumption: descripción de la procedencia/supuesto
events:
  market: id, at, quotes y opcionalmente bars/minutes/daily por símbolo
    quote: symbol, market_at, bid, ask, executable_qty
    bar: t, o, h, l, c, v, vw opcional y known_at obligatorio
  evaluate/entries: id, at, book
  reconcile/manage/pulse/sessions/restart/llm_unavailable: id, at
  cancel_confirm: id, at, order {symbol, kind, ordinal opcional}

Toda fecha de conocimiento de una barra debe ser posterior a su cierre y no
posterior al evento. No se puede derivar resolución intrabar de OHLCV. Si un
frame prospectivo no aporta liquidez ni un supuesto explícito, no se fabrica:
executable_qty=0 permite estudiar señales sin afirmar fills ni rentabilidad.
El adaptador de un frame parcial debe conservar la cobertura parcial; este
replay no convierte un lote de símbolos en el universo total observado.

Pruebas concretas
-----------------
El archivo quant_coordinator_replay_test.cjs incluye señales reales de acciones
y ETF, ETF apalancado sin doble conteo, causalidad de barras/cotizaciones, bloqueo
de fills al decidir, costes desconocidos, liquidez repetida, cotizaciones
obsoletas, cancel ACK no terminal, parcial tardío, reinicio durable, plazo de
protección parcial, TP y trailing reales, límite de 72 horas, falla de LLM,
restauración del entorno, guardas de producción y rechazo de recibos alterados.

Interpretación del recibo
------------------------
policy_parity_verified significa equivalencia reproducida para el contrato y
los eventos adjuntos. Las dos pasadas comparten código y datos: no constituyen
una validación externa independiente ni paridad exhaustiva multiactivos.

financial_acceptance_allowed es SIEMPRE false en esta herramienta. El veredicto
es VENTAJA_NO_DEMOSTRADA. La aceptación económica necesita, además, datos
reconciliados, predictores reproducibles, costes empíricos, comparación temporal
fuera de muestra y un alcance de ejecución representativo. Este replay cierra
una brecha de política operativa y validación; no declara cerrado el problema
de ventaja financiera.

Integridad
----------
Los hashes son SHA-256. input_hash y artifact_hash usan JSON canónico de esta
herramienta (claves ordenadas, serialización numérica JSON de JavaScript).
artifact_hash excluye el propio campo artifact_hash. source_hashes incluye
fuentes TypeScript, JavaScript compilado, loader legacy, módulos de señales y
adaptadores usados. scope_hash vincula el alcance explícito.
Para evitar diferencias numéricas entre serializadores, consumir el CLI
--verify o la función exportada verifyReport en Node; no sustituirlas por un
boolean ni por un hash calculado con reglas de otro lenguaje.

Regenerar el informe después de recompilar/cambiar fuentes. La compilación debe
realizarse antes del replay. Un cambio detectado durante las dos pasadas bloquea
la emisión. Los resultados sintéticos del ejemplo no son un nuevo ensayo del
presupuesto de búsqueda económica.

Adaptación del journal prospectivo
---------------------------------
tools/observation_replay_input.cjs recibe HARPOON_OBSERVATION_EXPORT_1 y produce
una entrada del replay sin órdenes. Verifica source_frame_sha256 contra los
bytes JSON originales de cada frame y preserva qué símbolos y ventanas estaban
muestreados. La integridad local no autentica al proveedor de datos.

node tools/observation_replay_input.cjs --input exported_frames.json --assumptions quant/examples/coordinator_replay/observation_assumptions.example.json --output observation_replay.json
node tools/coordinator_replay.cjs --input observation_replay.json --output observation_report.json

observation_assumptions.example.json contiene SUPUESTOS SINTÉTICOS explícitos;
no son tarifas observadas ni límites nuevos para una cuenta. El adaptador exige
un archivo de supuestos para no convertir costes desconocidos en cero.

Todos los eventos adaptados tienen executable_qty=0: no existe información de
profundidad ejecutable. Solo se invocan evaluate y sessions; no se insertan
eventos entries. No se adoptan posiciones ni saldo del broker de origen. Se
registran los cambios necesarios para el contenedor offline y no se certifica
equivalencia de la ejecución con esa cuenta.

Las barras sin known_at conservan como disponibilidad su primer frame exportado
(una cota conservadora), nunca una recepción pasada inventada. Las barras sin
cerrar, cotizaciones obsoletas y recepciones no verificables quedan registradas
como descartadas. Una cotización repetida no obtiene un timestamp de mercado
nuevo ni un presupuesto nuevo de liquidez. Daily, minutos y proxies ausentes
permanecen ausentes; el plugin real puede no generar señal. La captura parcial
no se presenta como el universo completo ni como una trayectoria continua de
los 90 minutos de apertura/cierre.

El recibo scope.components enumera las entradas realmente invocadas. Un replay
de observaciones no afirma haber ejercitado Coordinator.entries ni salidas con
posiciones. financial_acceptance_allowed permanece false.
