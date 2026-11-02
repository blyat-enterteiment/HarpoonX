# Gateway de investigación y supervisión HARPOON XXI 21.0.0

Este componente conecta el HTML con OpenAI Responses API. No recibe claves de Alpaca, no posee un endpoint de órdenes y no ejecuta código generado por el modelo. El HTML funciona sin servidor local. **La conexión real a OpenAI requiere desplegar este servicio remoto; esta entrega no incluye un despliegue ni una clave activa.**

## Configuración y despliegue

1. Usa un proveedor que ejecute contenedores Python y ofrezca un volumen persistente. Construye la imagen con `service/` como contexto y el Dockerfile incluido. La configuración de TLS, dominio y volumen depende del proveedor; no se asume una cuenta de hosting existente.
2. Monta un volumen persistente en `/data`, escribible por UID 10001. Una sola instancia del servicio utiliza esta base SQLite. No compartas el archivo entre réplicas distribuidas. Perder la base elimina el historial de reservas, por lo que nunca debe usarse almacenamiento efímero para el presupuesto.
3. Define en el gestor de secretos del proveedor `OPENAI_API_KEY` y `HARPOON_SERVICE_TOKEN`. Genera este último con `python -c 'import secrets; print(secrets.token_urlsafe(32))'`. No incluyas secretos en el HTML, en Git ni en capturas.
4. Configura `OPENAI_MODEL` con un modelo disponible en tu proyecto que admita Responses API y salidas estructuradas estrictas. Define `OPENAI_INPUT_USD_PER_MILLION` y `OPENAI_OUTPUT_USD_PER_MILLION` con sus tarifas actuales. Configura también `OPENAI_CACHE_WRITE_USD_PER_MILLION` si ese modelo tiene una tarifa de escritura de caché distinta; la reserva usa la mayor entre entrada y escritura. Los valores cero de `.env.example` hacen fallar el arranque deliberadamente: no se adivinan precios. Consulta https://developers.openai.com/api/docs/pricing.
5. Configura `HARPOON_MONTHLY_CAP` (30 USD por defecto), `HARPOON_RUN_CAP` (10 USD por defecto) y `HARPOON_ALLOWED_ORIGINS`. El valor `null` permite el origen del archivo `file://`; no identifica de forma exclusiva ese archivo y requiere el token de servicio. Para un HTML alojado usa su origen HTTPS exacto. No se permite `*` como comodín.
6. Publica el puerto 8080 **detrás del TLS del proveedor**. La URL que admite el HTML tiene que empezar con HTTPS. El servidor Python no termina TLS y no debe publicarse directamente por HTTP. Configura límites de conexión y cuerpo en el proxy; el proceso acepta JSON de hasta 30 KB.
7. En HARPOON → Laboratorio, introduce la URL base y el token del servicio, selecciona OpenAI, define presupuesto e iteraciones y pulsa Guardar investigación. El token se guarda cifrado en IndexedDB. La clave OpenAI permanece en el contenedor.
8. Conecta Alpaca. Audita y ejecuta una iteración, o inicia el loop. La ausencia de datos produce «evidencia insuficiente», no una rentabilidad estimada. El modo local funciona sin este servicio y está identificado como «SIN OPENAI».

## Contrato de red

Todas las rutas requieren `Authorization: Bearer <HARPOON_SERVICE_TOKEN>`.

- `GET /v1/health`: modelo, tarifas, reserva máxima por consulta y techos. No devuelve claves.
- `POST /v1/jobs`: `id`, `run_id`, `budget_usd`, `max_iterations`, `context`. El contexto máximo es de 20 KB UTF-8. Devuelve el trabajo persistido. Un POST repetido con igual ID y contenido devuelve el mismo trabajo sin consultar otra vez a OpenAI. Igual ID con contenido distinto se rechaza.
- `GET /v1/jobs/<id>`: conciliación del estado persistido. Estados: `pending`, `completed`, `failed`, `unknown`.

El cliente conserva el ID antes del envío y vuelve a consultar el mismo trabajo. El servicio realiza **como máximo una llamada OpenAI por ID**, sin reintentos de proveedor. Si llega una respuesta válida cobra el uso a las tarifas configuradas. Si la respuesta es incompleta o incumple el esquema se registra el fallo y el coste conocido. Ante timeout o reinicio se retiene la reserva completa y el estado incierto, sin asumir que la llamada fue gratuita.

Una reserva considera 32.000 tokens de entrada y 4.096 de salida. Es un límite conservador para los bytes admitidos, esquema e instrucciones; la salida está limitada en la solicitud. Los tokens ordinarios, de lectura de caché y de escritura de caché se contabilizan por separado a sus tarifas configuradas; registra `OPENAI_CACHED_USD_PER_MILLION` y `OPENAI_CACHE_WRITE_USD_PER_MILLION` cuando corresponda. La reserva usa la tarifa máxima de entrada/escritura. **No es una conciliación de la factura de OpenAI.** Si los precios configurados son incorrectos, el presupuesto estimado no equivale al gasto facturado. El presupuesto tampoco incluye hosting ni datos de mercado. Usa también los controles de gasto disponibles en tu proyecto OpenAI.

La reserva, el límite por ejecución y el techo mensual se comprueban en una transacción SQLite `BEGIN IMMEDIATE`. Cambiar el `run_id` no evita el techo mensual. El mes es UTC. Un trabajo incierto permanece retenido para revisión administrativa con el registro del proveedor; no borres la base ni reutilices su ID para forzar un reenvío. Esta versión no implementa conciliación automática de facturas ni recuperación de una respuesta cuyo ID nunca llegó.

## Alcance de la revisión IA

Se transmiten un resumen de hallazgos, la referencia congelada, recetas anteriores con métricas/gates y extractos relevantes del código con hash SHA-256 sólo para operativa. La tarea económica recibe la revisión/hash y omite ese código repetido. No se transmiten credenciales de Alpaca, cuenta completa, series de holdout ni el diario entero. La revisión del código es parcial y no sustituye una auditoría integral de seguridad. La respuesta sólo admite una receta declarativa acotada y hallazgos de texto. El navegador valida nuevamente la receta y calcula las métricas por su cuenta.

El servicio funciona independientemente de la ejecución. Su caída no llama a `engine.stop`, no cancela salidas ni modifica órdenes existentes. La gestión local y las órdenes nativas conservan sus reglas vigentes. En modo HTML continúan dependiendo de la pestaña; el ejecutor de `runtime/` permite alojarlos en un servicio remoto independiente.

## Verificación

`python3 service/test_server.py` desde la raíz del paquete ejecuta diecisiete pruebas: contrato, costes, idempotencia, timeout, límites concurrentes, techo mensual, iteraciones, reinicio, autenticación/CORS, separación de contexto externo, alcance de prompts y rechazo de tareas desconocidas. Usa proveedor simulado y HTTP de prueba en loopback; **no llama a OpenAI**. El Dockerfile se entrega para despliegue; no se construyó una imagen ni se desplegó un contenedor en esta sesión.

Documentación oficial de referencia:
- https://developers.openai.com/api/docs/guides/structured-outputs
- https://developers.openai.com/api/reference/overview

## Prompts por tarea · harpoon-prompts-5

`context.task` admite `operations`, `profitability` o `sandbox`. Las plantillas confiables viven en `prompts.py`; el contexto externo se transmite como mensaje de usuario. Operativa conserva toda la receta; rentabilidad conserva familia, RVOL mínimo, impulso y reentrada; sandbox sólo propone las cinco familias declarativas implementadas. El servicio y el HTML verifican el alcance. No se habilitan herramientas de órdenes, shell, navegación ni ejecución de código del modelo.

La auditoría operativa puede ejecutarse sin esperar meses de datos; registra evidencia insuficiente cuando corresponde. El loop evita volver a consultar operativa si no cambió su resumen de evidencia. Las propuestas económicas automáticas sí esperan la cobertura requerida. Una respuesta rechazada puede haber consumido tokens y su coste se conserva. Las defensas reducen el riesgo de prompt injection, sin garantizar inmunidad.

XII amplía el contrato con `selection_filter` (none/ridge_lcb), `trailing_mode` (entry_atr/realized_vol), `stagnation_minutes` y `progress_r`. Rentabilidad conserva el selector y la lógica de entrada; sandbox puede proponer el filtro. Los pesos se entrenan localmente con datos anteriores a cada ventana, nunca desde la respuesta GPT. El contexto incorpora atribución agregada cuando está disponible.

XIII incorpora `exit_layout` (two_targets/single_target), atribución agregada por motor y contexto de pérdidas coincidentes. Una propuesta sin cambio material o equivalente a un ensayo anterior no consume otro holdout. La biblioteca tensorial y supervivencia se calculan localmente; no se envían tensores completos a GPT ni se delega dimensionamiento de órdenes.


## Supervisión XXI

El Dockerfile incluye `supervision.py`. Mantén una sola instancia del gateway con un volumen SQLite durable. Las migraciones crean tablas adicionales; conservan jobs, IDs, costes y reservas anteriores.

En Take profit · GPT, configura modo/intervalo/techos y habilita la supervisión. El gateway usa la misma clave, modelo y tarifas del laboratorio. La política diaria/mensual es global y se aplica a ambos, aunque pauses nuevas revisiones. Una cuota mensual solicitada superior a HARPOON_MONTHLY_CAP se rechaza; ajusta el hosting o reduce el formulario.

- POST /v1/review-policy: guarda la política validada; requiere el mismo bearer de administrador.
- POST /v1/reviews: reserva, persiste y devuelve 202. Campos id, policy_revision, material_hash, context. Snapshot <=12 KB, 20 evidencias, vigencia 120 segundos. No hay herramientas de trading.
- GET /v1/reviews/ID: consulta el mismo trabajo. Nunca repite la llamada al proveedor.
- GET /v1/health: incorpora policy, policy_revision, gasto/reservas y límites de supervisión, sin claves.

La salida de revisión tiene 256–2.000 tokens configurables (1.200 por defecto); conserva una reserva de hasta 32.000 tokens de entrada. La reserva es capacidad presupuestaria bloqueada, no tokens enviados. Los contextos ordinarios son menores y se liquida el uso devuelto por OpenAI. El presupuesto global usa días/meses UTC.

Una respuesta unknown mantiene su coste máximo reservado. Tras 120 segundos deja de ocupar el cupo en vuelo, pero no se reenvía su ID ni se devuelve presupuesto como si fuera gratis. El cliente archiva su evidencia. La conciliación de esa reserva con una factura sigue siendo administrativa; no borres la base para liberar presupuesto. Las revisiones rechazadas por esquema/incompletas conservan el uso conocido.

Pruebas: python3 service/test_supervision.py además de test_server.py. El proveedor está simulado; los tests cubren coste, presupuesto entre cuentas/laboratorio, idempotencia, incertidumbre, reinicio, TTL, inyección y contrato HTTP 202. No equivalen a probar permisos o disponibilidad de OpenAI en tu proyecto.
