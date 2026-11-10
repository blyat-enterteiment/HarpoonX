# HARPOONX M11–C25: puente de recibos Alpaca, conciliación sin órdenes

**Estado: implementación funcional en rama aislada, exclusivamente lectura. N9-S NO_GO.** Esta fase no ha recuperado recibos reales en la sesión de ChatGPT y no ha abierto M10 (3.200 cuentas finales). La evidencia que no está disponible continúa como BLOCKED, sin sustituirla por resultados sintéticos.

## Alcance implementado

- **runtime30/fwn9_c25_broker_export_ingest.cjs**: valida exportación bruta de snapshots, posiciones, órdenes, actividades, fees y costes declarados. Reutiliza el normalizador original NetAccountLedger.snapshot y NetAccountLedger.activity, más un recálculo independiente con enteros decimales de ocho lugares. Reconcilia cash, NAV, posiciones, cantidad de cada fill parcial, precio promedio ponderado y orden correspondiente.
- **runtime30/fwn9_c25_alpaca_readonly_exporter.cjs**: lector local HTTPS del Alpaca Trading API con método GET exclusivamente y host permitido PAPER/LIVE. Endpoints limitados a account, positions, orders, account activities y metadata de activos. Credenciales tomadas solo del entorno local; sin envíos de órdenes ni acciones POST/PATCH/DELETE.
- **tools/fwn9_c25_capture_readonly_alpaca.cjs**: capturador de dos checkpoints (baseline y finish) y escritura local exclusiva de archivos privados modo 0600; no imprime cuentas, credenciales ni contenidos de la exportación.
- **tools/fwn9_c25_readonly_cli.cjs**: valida una exportación JSON ya obtenida, calcula SHA-256 de los bytes locales y devuelve un informe agregado sin mostrar la identidad de la cuenta. El hash local no constituye firma ni autenticación del broker.
- **tools/fwn9_c25_broker_export_ingest_test.cjs** y **tools/fwn9_c25_alpaca_readonly_exporter_test.cjs**: pruebas deterministas de software, sin mercado ni trading.

## Procedimiento local para un usuario con acceso autorizado a Alpaca Trading API

Node.js 22 requerido. Cargar APCA_API_KEY_ID y APCA_API_SECRET_KEY desde un gestor de secretos del entorno de ejecución. No subir claves, cuenta ni exportaciones a GitHub o al chat.

1. Inicio, solo si la cuenta no tiene órdenes abiertas: `node tools/fwn9_c25_capture_readonly_alpaca.cjs --stage baseline --mode PAPER --out /carpeta-privada/c25-inicio.json`
2. Corte posterior, una vez recibido el historial de órdenes y actividades: `node tools/fwn9_c25_capture_readonly_alpaca.cjs --stage finish --mode PAPER --baseline /carpeta-privada/c25-inicio.json --out /carpeta-privada/c25-final.json`
3. Validación desconectada (sin llamadas al broker): `node tools/fwn9_c25_readonly_cli.cjs --bundle /carpeta-privada/c25-final.json`

En la fase finish se acepta opcionalmente un documento local `--cost /carpeta-privada/costes.json` con categorías DATA, INFRASTRUCTURE, INFERENCE y OTHER, referencias, fechas, importes y marca de si ya están reflejados en NAV. Sus valores no se autentican por la simple declaración. Sin una cobertura acreditada, el PnL económico sigue incompleto.

Los archivos contienen información sensible; se crean con permisos 0600 y nunca se sobrescriben. C25 no se ejecutó contra las cuentas reales del usuario porque en este entorno no existe acceso conectado a los endpoints privados de Trading API. No se configura almacenamiento persistente de claves en HARPOONX.

## Contratos adversariales y límites de certificación

La fuente original de Alpaca usa un cursor page_token que representa el último ID de actividad. C25 exige páginas contiguas, sin duplicados, y última página inferior al máximo. La API documentada de lista de órdenes tiene máximo 500 sin page_token equivalente; ante un resultado de 500 órdenes C25 rechaza exhaustividad en vez de omitir filas. Una orden abierta antes de la línea base también bloquea la reconstrucción.

El contador independiente usa moneda USD y multiplicadores conocidos de equity/ETF o cripto spot, y rechaza operaciones en corto, opciones con contratos no resueltos, moneda desconocida, cash/posiciones inconciliables, cargos dobles y eventos futuros. Si Alpaca omite asset_class en un FILL, el catálogo de instrumentos aporta una vinculación explícita; nunca se infiere un multiplicador de opciones.

El reporte distingue la identidad contable de una prueba de origen. Puede acreditar que una exportación *declarada* se reconcilia, pero NO demuestra por sí misma que el usuario haya operado así, que la cuenta sea única y financieramente completa, ni que el sistema conociera cada fill antes de otra orden. Las actividades FEE con fecha solamente no prueban el reloj intradiario. Los costes de spread/impacto ya dentro del precio de fill no deben restarse por segunda vez.

Una exportación válida conserva siempre `sourceInputExternallyAuthenticated: false`, `receiptLevelPredecisionFiltrationCertified: false`, `familywiseOutsideSampleNetAlphaCertified: false`, `brokerAuthenticatedEconomicPnlUsd: null`, `orderAuthority: false`, `N9S: NO_GO`.

El contrato de orden/actividad puede verificarse con datos reales solo cuando el propio usuario ejecute la captura en un entorno autorizado; todas las pruebas CI actuales usan únicamente fixtures sintéticos de ingeniería, claramente separados de mercado real.

## Qué falta para FWN9

Acceso genuino al broker (sin exponer las claves aquí), precios y cantidades de fills verificables con recibos de origen, comisiones y costes, NAV/caja/posiciones en dos checkpoints, conjunto de oportunidades rechazadas, baseline original verdaderamente comparable y seis variantes congeladas evaluadas prospectivamente. La equivalencia OHLC STOP-FIRST frente al primer cruce está refutada en C21 y no se repara por una exportación contable.

**Prohibido promover esta fase a GO financiero.** No hay nuevos seeds, señales, cuentas económicas, órdenes PAPER/LIVE, merges, deploys ni reinicios de búsqueda recursiva. Las 3.200 cuentas finales M10 permanecen selladas.

## Verificación C25 R2 y documentación de origen

El cliente local sigue exclusivamente los endpoints oficiales de Alpaca Trading API: `GET /v2/account`, `GET /v2/positions`, `GET /v2/orders`, `GET /v2/account/activities` y la metadata GET por instrumento. Las órdenes GET se limitan a 500, por lo que una respuesta exactamente en ese límite se rechaza como evidencia de paginación no demostrada. En actividades se exige `page_token` del último ID y página final incompleta.

Documentación oficial usada al construir los contratos:

- https://docs.alpaca.markets/us/reference/getallorders-1
- https://docs.alpaca.markets/us/reference/getaccountactivities-2
- https://docs.alpaca.markets/us/v1.4.2/docs/account-activities

El capturador no ejecuta nada por sí solo: requiere claves en el entorno local y la invocación expresa de baseline y finish. No se han probado cuentas reales ni se autenticaron actividades privadas del usuario en ChatGPT. La CI utiliza mocks de transporte y recibos sintéticos marcados exclusivamente como casos de ingeniería.

Validación final esperada: **176 pruebas** en la integración C25 (24 de importador, 14 de exportación segura y 138 de regresión C16–C24) además de conciliación independiente Decimal-46. Esta cifra certifica contratos de software y matemáticas de alcance limitado, **no** 176 comprobaciones de rentabilidad ni una certificación económica.

Controles de seguridad añadidos: impedir que el modo de origen use propiedades heredadas del objeto y que la ruta de metadatos contenga `..` o sus variantes codificadas. Los precios fraccionarios cuya precisión supere ocho decimales se rechazan con error explícito, nunca se redondean de forma silenciosa.

El resultado del modelo WEAK original continúa N9-S `NO_GO`, con las 3.200 cuentas finales selladas. No se creó ninguna señal ni cuenta económica; el ejecutor histórico STOP-FIRST no se ha cambiado y permanece matemáticamente distinto del primer cruce de ocho subpasos.
