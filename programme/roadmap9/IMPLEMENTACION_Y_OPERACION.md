# HARPOON: implementación offline y operación del contrato de evidencia

## Alcance de esta entrega

El plan original de 12 fases y 49 validadores se conserva en `plan.json` y `PLAN_SECUENCIAL.md`. Su estado propuesto no se sobrescribe. El cierre de este ciclo se entrega por separado en `closure.json` y `CIERRE.md`, con resultado, evidencia y trabajo pendiente para cada validador.

Los módulos nuevos residen en `quant/harpoon_quant/roadmap9`. Son componentes y ensayos offline. No contienen un transporte de órdenes al broker, no cambian el servicio desplegado y no conectan la nueva investigación a una cuenta real. Las firmas y hashes verifican relaciones concretas; no convierten una simulación en una observación ni acreditan por sí solos rentabilidad o independencia.

## Componentes y responsabilidades

| Componente | Función | Límite relevante |
| --- | --- | --- |
| `costs.py` | Comisiones por rol y activo, provisiones, postings tardíos, correcciones y gasto común con Decimal. | El contrato de una cuenta y sus tarifas deben confirmarse fuera del modelo. |
| `execution.py` | Reducir eventos de órdenes, reservar inventario, detectar ambigüedad, recuperar recibos y acotar reintentos. | No envía órdenes ni supone que un timeout equivale a un rechazo. |
| `execution_replay.py` | Reproducir las entradas y primeros intentos de salida del banco congelado con nuevos reintentos por eventos. | Los fills y tarifas de ese banco siguen siendo sintéticos. |
| `forecast.py` y `research.py` | Separar retornos nocturnos e intradiarios, construir etiquetas maduras y calcular señales causales de las seis recetas. | Histórico reutilizado; AAPL y MSFT con contexto sectorial XLK. |
| `registry.py` | Registrar tres hipótesis, seis recetas y doce mediciones mediante una cadena de hashes. | Conserva la incompletitud de la historia global de búsqueda. |
| `portfolio.py` | Evaluar asignaciones discretas con costes, incertidumbre y restricciones. | Componente de ingeniería independiente; no integrado ni evaluado económicamente en las seis recetas. |
| `forward.py` | Conciliar un paquete normalizado de cuenta, comprobar procedencia firmada y calcular diagnósticos pareados. | No obtiene actividades originales ni sustituye revisión externa, calibración o autorización. |
| `operations.py` | Derivar salud, bloqueo de entradas, gestión de reducción y un intento de reversión que preserva inventario. | Un indicador saludable no concede autoridad de ejecución. |
| `gates.py` | Vincular los 49 dictámenes a bytes de evidencia y generar el cierre legible. | Es un catálogo de evidencia, no un ejecutor automático de los ejercicios. |

## Instalación y comprobación

Usar Python 3.12 y Node 24. Las dependencias específicas están en `quant/requirements-roadmap9.txt`; incluyen las dependencias numéricas ya fijadas y la verificación de firmas Ed25519. `npm ci --ignore-scripts` instala las dependencias Node del repositorio sin ejecutar scripts de instalación.

Desde la raíz del repositorio:

```bash
python3 -m pip install -r quant/requirements-roadmap9.txt
npm ci --ignore-scripts
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONPATH=quant python3 -B tools/roadmap9_validate.py --output /tmp/harpoon-roadmap-validation
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONPATH=quant python3 -B -m unittest discover -s quant/tests
```

El primer comando de verificación registra cada prueba de los módulos nuevos y de los núcleos Frontier y Synthetic9. El segundo ejecuta toda la regresión Python. Los recibos incluyen las fuentes comprobadas; una prueba omitida o un cambio de fuente durante la comprobación no produce un pase global.

El workflow `.github/workflows/roadmap9.yml` ejecuta las comprobaciones offline. No dispone de credenciales de trading ni realiza despliegues. El rendimiento de una decisión local se informa por separado de la latencia de un broker. Dos scripts históricos congelados conservan nueve hallazgos de mypy: el workflow los informa en un paso diagnóstico que puede fallar, mientras que el tipado de los módulos y herramientas restantes sí actúa como requisito. Un workflow verde no equivale a declarar limpio el tipado de esos dos scripts; `research/roadmap9/README.md` detalla la limitación.

## Reproducción de ejecución

El banco congelado de 108 cuentas se conserva en `evidence/synthetic9/run_01`. No se cambian sus entradas, tarifas ni resultados originales. `research/roadmap9/execution_protocol.json` fija los reintentos y el sobre de ejecución usado por el experimento de ingeniería.

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONPATH=quant python3 -B tools/run_roadmap9_execution.py --output /tmp/harpoon-roadmap-execution.json --raw-output /tmp/harpoon-roadmap-execution-accounts
```

La salida y el directorio de cuentas deben ser nuevos. El runner rechaza sobrescribir un recibo. El cambio estudiado es el tratamiento por eventos de las salidas; no vuelve a optimizar las entradas. Una reducción de retrasos dentro del modelo sólo certifica ese sobre de ingeniería.

Las campañas conservan su apertura y deadline originales. Reiniciar el proceso, recibir un fill parcial o reemplazar una orden no abre otras 72 horas. Ante una interrupción que impida cerrar, el sistema conserva inventario pendiente e incumplimiento explícito. No inventa un fill en el deadline.

## Reproducción de las seis recetas

`research/roadmap9/protocol.json` y `recipes.json` fijan la investigación. El runner enlaza código, fuentes Node transitivas, dataset, costes y plan antes de medir. El dataset conservado debe tener SHA-256 `5546035f58a04255b35091191cd750bd3d86075380a8aed0c258edbff6cee530`.

El ejecutor original es `tools/run_roadmap9_research.py`. Para comprobar esta entrega debe utilizarse el verificador de reproducción `tools/verify_roadmap9_research.py` según las instrucciones en `research/roadmap9/README.md`: conserva las identidades y coteja los resultados originales. El recibo de registro inicial del runner documentaba once resultados; el recibo suplementario registra doce después de añadir dos anotaciones ausentes. Volver a pedir al ejecutor original que sobrescriba el recibo inicial produciría un rechazo de inmutabilidad. La incidencia y su causa no establecida se conservan en `evidence/roadmap9/research_registry_incident`.

Repetir exactamente una receta con las mismas entradas es reproducción, no una nueva observación independiente. Las incidencias del registro y los recibos suplementarios se conservan junto al estudio; no se borran para presentar un historial perfecto.

Las seis recetas usan el asignador nativo y los mismos límites ex ante: capital continuo de 20.000 USD, riesgo por posición de 0,25%, exposición bruta máxima de 12%, drawdown máximo de 8% y pérdida diaria máxima de 2%. Estos límites no prueban que la exposición realizada de todas las variantes sea igual. Los comparadores se informan como políticas completas; la atribución de H3 añade un ensayo pareado con entradas, cantidades y precios iniciales fijos.

El nuevo componente de asignación robusta es una entrega de ingeniería separada. No se combina después de ver los resultados con una receta ganadora ni se contabiliza como una séptima receta económica. Su integración futura requeriría una nueva identidad de investigación y presupuesto anterior a la medición.

El gasto fijo se acumula por días naturales en las cuentas y en CASH. Los resultados de este estudio no se comparan directamente con el neto archivado que cobraba sólo por sesión: primero se deben igualar reglas, precios, horizonte y costes. Los datos NOII/subasta, BBO observado y contexto Cboe ausentes no se reconstruyen desde OHLCV.

## Contrato de admisión de observaciones

El comando siguiente produce un bloqueo explícito cuando no se aporta evidencia:

```bash
PYTHONPATH=quant python3 -B -m harpoon_quant.roadmap9 admit-forward --now-ms 1793664000000 --output /tmp/harpoon-forward-empty.json
```

Para un paquete existente, se proporcionan `--packet`, `--protocol` y `--trust-store`; `--now-ms` debe ser el reloj UTC real en milisegundos al comprobarlo. No se debe copiar la fecha del ejemplo como reloj operativo. El resultado máximo de este comando es `ADMITTED_FOR_ANALYSIS`; la autorización financiera y de ejecución permanece en falso.

El formato `HARPOON_ROADMAP_FORWARD_PACKET_1` admite una cuenta spot larga, denominada en USD, sin margen, divisas ni aportaciones/retiros. Los importes monetarios y cantidades nativas se representan preferentemente como cadenas decimales. Un flujo externo, evento no soportado o diferencia no explicada bloquea la admisión.

| Bloque | Campos y requisitos principales |
| --- | --- |
| Protocolo | Registro anterior al inicio, calibración anterior a validación, fechas y observaciones completas, capital inicial de 20.000 USD, commit, receta, coste e instrumentos. |
| Identidad del paquete | Origen `OBSERVED_LIVE`, `OBSERVED_PAPER` o `SYNTHETIC_ENGINEERING_ONLY`; referencia privada de cuenta; hashes del protocolo, receta y coste. |
| Orden | IDs de broker y cliente, campaña, símbolo, lado, cantidad, apertura y deadline originales, decisión y envío, reloj de origen y disponibilidad de la cotización, disponibilidad del modelo y de su última etiqueta. |
| Fill | Evento y ejecución únicos, cantidad incremental —no el acumulado de la orden—, precio, moneda y provisión de comisión. |
| Comisión | Posting una sola vez ligado al fill, importe y moneda real. La provisión se retira al asentar la comisión; no se cobra dos veces. |
| Gasto común | Factura única y declaración de si se debitó de la cuenta. Un gasto pagado fuera reduce el patrimonio económico sin crear un débito ficticio en el broker. |
| Snapshot | Balances exactos, marcas USD, reloj de origen y disponibilidad de cada marca, patrimonio económico conciliado. |

Las cotizaciones y marcas no pueden tener más de 15 segundos de antigüedad en el contrato soportado. El modelo y sus etiquetas cumplen el máximo de 168 horas; una recepción reciente no rejuvenece un precio viejo. No se permiten etiquetas posteriores al ajuste o a la decisión. Los snapshots tienen cobertura registrada y una separación máxima de un día; esto no demuestra que el riesgo entre snapshots se haya mantenido dentro de límites.

El reconciliador reserva las comisiones pendientes en su moneda, impide financiar ventas con inventario de otra campaña y detecta posiciones que siguen abiertas después de su deadline aunque no haya un fill tardío. Los originales del broker, su paginación completa y el enlace ACK/BBO requieren un adaptador y comprobación de procedencia externos a este módulo. El normalizador no resuelve por sí solo todo V041.

La procedencia usa una firma Ed25519 de un verificador expresamente confiable. El almacén de claves públicas se aporta desde un canal autenticado; el módulo no genera ni instala una autoridad. Una firma válida sólo demuestra quién firmó esos bytes. La diligencia del firmante, su independencia y su acceso a los originales siguen siendo requisitos reales. Las claves de pruebas no acreditan observaciones ni revisión externa.

## Salud, degradación y recuperación

`evaluate_health` deriva `alive` del tiempo de origen de mercado, recepción, conciliación y ausencia de órdenes ambiguas. Un temporizador de interfaz no actualiza esos relojes. Las entradas se bloquean si faltan modelo, etiquetas recientes, autoridad, riesgo conocido o conciliación, o si se alcanza un límite registrado. La caída de un LLM no elimina las posiciones conocidas ni hace desaparecer el riesgo.

`rollback_plan` produce una intención de reversión y conserva campañas, inventario y órdenes pendientes. Exige conciliación y una versión destino con aceptación previamente establecida. No ejecuta el despliegue ni prueba por sí solo la autenticidad de esa aceptación; ambos son controles del sistema de liberación. Una política rechazada no se reactiva automáticamente.

## Cierre y límites de interpretación

`gates.close_plan` exige un dictamen para los 49 contratos originales, comprueba hashes y tipos de evidencia y conserva los bloqueos. No admite cerrar observación real, economía prospectiva, revisión externa o autoridad de cuenta mediante pruebas locales.

El cierre de este ciclo puede rechazar las tres hipótesis y terminar la búsqueda sin promocionar un candidato. No equivale a afirmar que las doce fases quedaron aprobadas. Los requisitos pendientes de tarifas de cuenta, datos auténticos, observación prospectiva, integración del servicio y revisión externa deben aparecer expresamente en `CIERRE.md`.
