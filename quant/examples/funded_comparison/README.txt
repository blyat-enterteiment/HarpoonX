COMPARACION FINANCIADA C0 / RIDGE / SVR
====================================

Esta herramienta reproduce las decisiones y el patrimonio de tres carteras
contrafactuales separadas sobre los mismos eventos. No tiene transporte hacia
un broker, no entrena modelos, no busca parámetros y no promueve estrategias.

El control C0 utiliza Plugins.evaluate y la selección/tamaño nativos del
coordinador actual. Ridge y SVR utilizan harpoon_quant.bridge.from_runtime y
el asignador existente con modelos JSON fijos proporcionados por el usuario.
Todos comparten universo, capital inicial, límites superiores de riesgo,
costes de ejecución, gestión, salidas, horizonte de evaluación y secuencia de
mercado. Comparar contra C0 mide el conjunto de selección/asignación de entrada;
no aísla exclusivamente el estimador. Ridge frente a SVR mantiene el asignador.

ESTADO DE LA EVIDENCIA
---------------------

Las pruebas incluidas son SYNTHETIC_ENGINEERING_ONLY. Los modelos constantes
del fixture son inventados para probar cálculo, guardias y contabilidad.
No son modelos entrenados, nueva evidencia OOS ni ensayos financieros.

Un cálculo reproducible tampoco autentica el entrenamiento de un modelo
aportado como OBSERVED. El informe lo declara por separado. Con faltantes de
datos, modelos, costes o registro, las curvas quedan null y se indican causas.
Ningún resultado de esta herramienta habilita PAPER o LIVE ni eleva por sí
solo la valoración económica del proyecto.

API NODE
--------

tools/funded_comparison.cjs exporta:

  comparisonReadiness(input)
  runFundedComparison(input)
  verifyFundedComparison(input, report)
  registrationBinding(input)
  comparisonSourceHashes()

Entrada HARPOON_FUNDED_COMPARISON_REQUEST_1:

  schema: HARPOON_FUNDED_COMPARISON_REQUEST_1
  purpose: SYNTHETIC_SOFTWARE_TEST | PREREGISTERED_FIXED_MODEL_MEASUREMENT
  account_scope: CASH_ONLY_COUNTERFACTUAL_NO_EXTERNAL_FLOWS
  common_request: HARPOON_COORDINATOR_REPLAY_REQUEST_1 sin predictor
  models: {RIDGE: objeto JSON fijo, SVR: objeto JSON fijo}
  model_json: {RIDGE: texto JSON original, SVR: texto JSON original}
  predictor_timeout_ms: 8000
  source_hashes: requerido para medición histórica
  registration: requerido para medición histórica

El transporte de inferencia solo admite el módulo local fijo
harpoon_quant.fixed_predictor. No acepta nombres de módulos, comandos ni
argumentos arbitrarios. El intérprete se selecciona con HARPOON_QUANT_PYTHON
(ruta absoluta a python) o python3. El proceso no hereda credenciales del
entorno, no usa shell, tiene límites de entrada/salida y timeout. Dentro del
replay siguen bloqueados red y creación de procesos; el único trabajador se
crea antes de entrar en ese aislamiento y se termina al acabar o fallar.

model_json es obligatorio para mediciones históricas. Conserva los bytes JSON
del modelo guardado por Python, incluidos números como 1.0 que Node podría
volver a escribir como 1. Su contenido debe coincidir con models. Nunca se
reescribe el artifact_hash interno del SVR para conseguir que pase una prueba.
model_hashes identifica esos bytes exactos; model_content_hashes identifica la
representación semántica canonical de Node. Son hashes con alcances distintos.

RECIBOS Y PARIDAD
-----------------

Cada decisión numérica conserva la solicitud efectiva del coordinador, sus
features normalizadas, el modelo, hashes de fuentes y la respuesta íntegra
del motor. Los bytes exactos enviados se incluyen como cadenas JSON y se
verifican con SHA-256 para evitar diferencias de serialización entre lenguajes.

El coordinador y la inferencia se ejecutan dos veces. El recibo compara
decisiones, acciones, fills, posiciones y patrimonio. La paridad del predictor
requiere al menos un pronóstico realmente calculable; reproducir únicamente
un rechazo no permite declararla completa. Los recibos PRECOMPUTED_OFFLINE
anteriores conservan predictor_parity_verified:false.

El SVR real sigue devolviendo SHADOW_RESEARCH_ONLY y execution_allowed:false.
Solo el adaptador del coordinador aislado permite simular las selecciones.
El informe externo siempre conserva execution_allowed:false,
liveApproved:false y financial_acceptance_allowed:false.

El informe HARPOON_FUNDED_COMPARISON_1 contiene reports de los tres candidatos,
curves, session_curves, diferencias pareadas sin intervalo estadístico,
parity y todos los límites del alcance. Los hashes solo acreditan consistencia
local; no son validación externa ni prueba de beneficio.

CONTABILIDAD
------------

Las tres carteras empiezan íntegramente en efectivo, sin adoptar posiciones
de una cuenta existente y sin flujos externos de capital. No hay reinicios
entre eventos/sesiones. Las posiciones abiertas se valoran al bid del modelo
y se conservan al final: no se simula un cierre ficticio.

Las comisiones por fill ya se descuentan del efectivo del broker simulado;
no se restan otra vez de los rendimientos. El coste operativo externo es un
importe explícito común, pagado fuera de esa cuenta y cargado una sola vez
al último evento para obtener patrimonio económico. El instante de ese cargo
es un supuesto declarado, no una reconstrucción de gastos reales. Un coste
desconocido bloquea la medición. No se recortan insolvencias a cero ni se
calcula crecimiento logarítmico cuando el patrimonio deja de ser positivo.

Los costes con que el asignador estima su ventaja proceden del bridge y de
la configuración originales; los costes efectivamente contabilizados en el
replay proceden de execution_model. Que ambas rutas estén documentadas no
prueba que sus supuestos sean empíricos ni equivalentes. La validación
económica debe contrastarlos con el canal real y los gastos observados.

REGISTRO DE UNA MEDICION HISTORICA
--------------------------------

RESERVA DE GASTOS EN LA VERSION 30.12.0

Para una comparación económica que financie gastos externos con el capital
inicial se admite execution_model.operating_cash_reserve:

  {"method":"FIXED_INITIAL_CASH_RESERVE","amount_usd":R,"known_at":T}

R debe ser un importe fijado antes de la prueba, entre cero y el capital
inicial, y cubrir los costes externos de todo el periodo. T es su fecha de
disponibilidad en milisegundos UTC, estrictamente anterior al comienzo. La
reserva forma parte de la solicitud sellada y de su registro; no puede elegirse
después de ver el resultado para conseguir aprobación.

El broker simulado conserva la identidad efectivo+posiciones=patrimonio.
La potencia de compra disponible es efectivo menos R y cada fill de compra
debe respetarla incluyendo comisiones. El coordinador y ambos predictores
consumen esa disponibilidad al decidir. R queda inmovilizado hasta el final:
no se libera automáticamente al observar resultados, no cuenta como gasto,
no es una aportación adicional y no aumenta el capital. El gate v2 carga los
gastos originales una sola vez en sus fechas y contrasta la reserva en las
tres rutas reejecutadas. Sin reserva suficiente, los gastos externos siguen
siendo un bloqueo de la validación de financiación.

Esta política es un supuesto contrafactual de financiación. No mueve dinero
de una cuenta real. Las salidas de protección siguen disponibles; si sus
costes dejan menos efectivo que el reservado, la prueba registra el déficit
y no acredita la financiación. Un known_at declarado y un hash local no son
por sí solos un prerregistro externo: el gate exige además su trazabilidad.

La ruta histórica es funcional, pero exige reserva verificada en un Journal
existente. No se ejecuta en las pruebas entregadas ni se modifica un journal
histórico al crear ejemplos. Se requiere propósito explícito, modelos de
origen declarado OBSERVED, request HISTORICAL, source_hashes actuales y una
reserva de tres slots. No basta aportar {verified:true}.

1. Preparar la entrada completa e incluir source_hashes obtenido con
   comparisonSourceHashes(). Datos/costes/modelos desconocidos siguen null.
2. Generar el binding exacto (excluye solamente registration):

   node tools/funded_comparison.cjs --registration-binding request.json --output binding.json

3. Usar tools/measurement_registration.py con una copia explícita y completa
   del Journal existente y su head esperado. Su contrato preserva el contador
   previo y limita la familia a seis slots; no crea ni reinicia presupuestos.
   Incorporar a request.json el recibo producido como registration.
4. Ejecutar solo la medición fija registrada:

   node tools/funded_comparison.cjs --input request.json --output comparison.json

El productor llama al verificador local fijo con --verify-stdin, que consulta
el Journal en lectura y verifica cadena, reserva, hashes y presupuesto.
Esto acredita integridad local de la reserva; no la convierte en preregistro
independiente anterior a observaciones ya conocidas.

VERIFICACION Y PRUEBAS
---------------------

Reproducir un informe conservado:

   node tools/funded_comparison.cjs --input request.json --verify comparison.json --output verification.json

verifyFundedComparison ejecuta otra vez los modelos y el coordinador y compara
el informe completo; no se limita a comprobar su hash interno. Las fuentes
deben permanecer quietas durante las dos pasadas. Una edición o compilación
concurrente provoca SOURCE_CHANGED_DURING_REPLAY y debe repetirse cuando la
versión esté congelada, sin cambiar los criterios.

Pruebas de software sintéticas, sin entrenamiento:

   node --test --test-isolation=none --test-reporter=tap --test-force-exit tools/funded_comparison_test.cjs
   cd quant
   python -m unittest tests.test_fixed_predictor -v

Las pruebas abarcan cálculo real, guardia SVR, binding de modelos y fuentes,
modelos/quotes futuros, costes desconocidos, patrimonio manipulado y pérdida
terminal. No constituyen pruebas de rentabilidad de mercado.
