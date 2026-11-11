# HARPOONX — FWN9 M11-C28: obligaciones pre-filtro, anclaje externo y comparación financiera prospectiva

**Veredicto: C28 aprobado en ingeniería de contratos y persistencia; FWN9/N9-S permanece NO_GO.** El código implementa las piezas preparatorias sin abrir las 3.200 cuentas finales M10, generar nuevas señales económicas, solicitar precios en otro mercado, ejecutar estrategias, enviar órdenes o desplegar servicios. No se ha realizado un nuevo ensayo prospectivo en una cuenta auténtica.

## 1. El problema de la oportunidad omitida y cómo lo cerramos dentro del universo registrado

C27 ya exige que cada candidato **recibido** tenga un resultado; eso no garantiza que se llamó al evaluador de cada activo/ventana. C28 usa un **calendario de obligaciones independiente de las señales**: para cada barra programada y cada instrumento registrado, calcula las dos variantes correspondientes a su clase de activo más la política ORIGINAL_BASELINE. Las ventanas de equity/ETF respetan el calendario de `runtime30/sessions.js`; cripto investiga UTC_00_08 y UTC_16_24 y requiere estado abierto del venue; opciones requieren habilitación expresa de la sesión del contrato y **nunca autorizan órdenes**.

Cada casilla exige uno de dos estados: `EVALUATED`, con una llamada a su función generadora antes de aplicar filtros (incluida una llamada cuyo resultado es el conjunto vacío), o `SKIPPED`, con la razón exacta de calendario/elegibilidad. Un evaluador no puede ser omitido porque su resultado sea cero. La llamada está encapsulada por `makeTap()` y sus IDs deben coincidir **exactamente** con los del frame C27, incluidos rechazos. Se rechazan candidatos originales ocultados, candidatos inventados después del filtro, activos no registrados, variantes nuevas escogidas retrospectivamente, evaluaciones duplicadas y `knownAt` posterior al sello prebarra.

**Alcance estricto de exhaustividad:** se prueba la cobertura de *las casillas registradas y llamadas realizadas* respecto de un registro de instrumentos y calendario aportado. La implementación no puede demostrar por sí sola que el universo de mercado incluya todos los activos posibles ni que la lógica dentro de un generador no omita sus propias señales. La autenticación independiente del origen del calendario, del registro de activos y del proceso evaluador sigue siendo un requisito real; las declaraciones `EVALUATED` de un archivo local no son un hecho bursátil verificado.

Archivos: `runtime30/fwn9_c28_source_obligations.cjs` y `tools/fwn9_c28_source_obligations_test.cjs`.

## 2. Persistencia verificable de las evaluaciones

`runtime30/fwn9_c28_source_tap_archive.cjs` enlaza las llamadas originales pre-filtro a cada frame ya sellado de C27. Crea un manifiesto con hash de registro de instrumentos, calendario, políticas congeladas y manifiesto C27. Por cada barra, escribe de forma exclusiva un archivo privado 0600, vinculado al SHA-256 del frame C27, al hash de la anterior casilla y a la lista de todos los evaluadores esperados. Una cadena ajena, una barra ausente, una casilla omitida, un expediente reescrito o un escritor concurrente invalidan la comprobación.

La recuperación recorre de nuevo **todos** los frames C27 y C28. Tanto el directorio como los archivos tienen permisos privados, `fsync` y candado de escritor; un bloqueo dejado por interrupción requiere revisión manual, sin reparación silenciosa. No se reescribe el motor original de órdenes.

Una **firma Ed25519 opcional** puede anclar las cabeceras completas de C27 y C28 a un tercero usando una clave pública cuyo fingerprint debe estar previamente fijado. `runtime30/fwn9_c28_external_anchor.cjs` verifica la firma y detecta alteraciones de cabeceras, claves o registro posterior. **Una firma no convierte al firmante en el broker**, ni certifica un sello de tiempo externo solo por incluir una fecha firmada. La confianza en la entidad firmante, sus controles y la hora del anclaje requieren validación independiente. En particular, la firma de una cadena manipulada por un emisor comprometido no prueba nada sobre el contenido económico original.

## 3. Interfaz de auditoría local sin conexión al broker

Con Node.js 22, una carpeta C27 existente, un registro de instrumentos y un calendario guardados en archivos JSON privados (0600):

```bash
node tools/fwn9_c28_readonly_cli.cjs --init /privado/c28-taps --c27 /privado/c27-journal --registry /privado/registro.json --calendar /privado/calendario.json
node tools/fwn9_c28_readonly_cli.cjs --append /privado/c28-taps --c27 /privado/c27-journal --taps /privado/llamadas-fuente.json
node tools/fwn9_c28_readonly_cli.cjs --verify /privado/c28-taps --c27 /privado/c27-journal
```

El CLI informa cantidad de barras/casillas y hashes de cabecera, sin imprimir posiciones ni identificadores privados de cuenta. El archivo `llamadas-fuente.json` debe provenir de `makeTap()` ejecutado en el punto causal *anterior* a los filtros, no de un resultado reconstruido después; **esta rama no está conectada a la instancia Render ni al productor real de eventos**. La lectura de un JSON introducido manualmente no acredita que la llamada se haya efectuado verdaderamente.

## 4. Ocho brazos y cartera única: qué comparación está implementada

`runtime30/fwn9_c28_one_book_prospective_comparator.cjs` preserva seis variantes C22 más ORIGINAL_BASELINE y CASH. Recibe bloques financieros cronológicos donde el brazo asignado se conoce antes de empezar, la cuenta física es la MISMA en todos los bloques, las posiciones están cerradas al comienzo y al terminar cada bloque y cada movimiento lleva su rastro de recibos. Exige patrimonio inicial de USD20.000, continuidad del patrimonio entre bloques, costes, comisiones y flujos externos reconciliados, fechas de `knownAt` y referencia CASH conocida antes del intervalo. Reutiliza el contrato `compound()` original de C22.

La métrica implementada es crecimiento logarítmico financiado:

    g = SUM_blocks log(W_end / W_start)
    g_cash = SUM_blocks log(1 + observed_cash_return_for_block)
    difference = g - g_cash

Los valores son **DESCRIPTIVOS**. No se atribuye rentabilidad contrafactual a una estrategia que no se ejecutó ni se mezclan ocho carteras ficticias con 20.000 USD independientes. La política ORIGINAL_BASELINE debe tener sus propios periodos ejecutados y verificados para figurar como observada. Los brazos no ejecutados permanecen sin medición real; una fila CSV/JSON con alta rentabilidad o una bandera `brokerSigned=true` no puede habilitar `financialGO`.

**Inferencia que todavía NO está acreditada:** asignación aleatoria/independencia de los bloques observada de forma externa, corrección familiar de las comparaciones contra CASH y original, dependencia entre días y posiciones que cruzan ventanas, rentabilidades de las seis variantes con recibos auténticos, y cotas de coste/cola alcanzables. C28 no fija falsamente un valor de alfa ni presenta un intervalo de confianza obtenido sobre datos inexistentes. La inferencia estadística rigurosa corresponde a la puerta C29, después de la recolección prospectiva.

## 5. Relación entre los recibos del broker y las obligaciones prebarra

C25 ya valida la identidad contable de una exportación de cuenta y C26 enlaza fills con quotes y recibos temporalmente conocidos. C28 ahora exige que el **universo de oportunidades** observado también sea completo respecto de los brazos/activos/barras previamente registrados. Ninguna de estas piezas convierte por sí sola archivos de procedencia autodeclarada en `FILL` firmados por el broker. La combinación C25+C26+C27+C28 aún no se ha observado operando en una cuenta real.

Para una validación realmente externa deben coexistir: registro completo de evaluaciones pre-filtro sellado prospectivamente, órdenes y actividades Alpaca auténticas, cotización y reloj de recepción predecisión, libro de caja/NAV/fees, rechazos y no-fills, identificación de órdenes por oportunidad y disponibilidad del calendario/contrato. La fuente Render autorizada previamente no entregó un ID de servicio para inspeccionar logs/disco; no hay prueba de que este sistema esté desplegado.

## 6. Validación técnica C28 y criterio de cierre

GitHub Actions C28 ejecuta pruebas adversariales de ocho brazos, activación/inactividad por horario, cero señales como resultado válido, candidatos omitidos/duplicados/falsos, integridad de hashes, reinicio y bloqueos de escritores; firmas Ed25519 con claves de prueba efímeras; privacidad del CLI; continuidad de una sola cartera, costas y benchmarks. Mantiene las 275 regresiones originales C16–C27, incluidas la contabilidad Decimal-46 y las pruebas matemáticas WEAK.

Las pruebas criptográficas usan claves generadas únicamente para los casos unitarios. No crean semillas de mercado, órdenes, estrategias ni cuentas económicas. Los controles de integridad no sustituyen una auditoría independiente del emisor o una fuente de tiempo fiable.

**Aceptación funcional de C28:** toda obligación registrada tiene evidencia de evaluación o motivo de exclusión; todas las señales resultantes están vinculadas a un resultado C27; el registro es repetible y resistente a fallos ordinarios de persistencia; el comparador no combina cuentas ni promueve alfa inexistente.

**Aceptación financiera FWN9/N9-S:** NO satisfecha. Es necesario observar prospectivamente el productor real y recuperar recibos auténticos y completos antes de cualquier prueba estadística o uso del holdout. El modelo OHLC STOP-FIRST original sigue sin equivalencia universal al primer cruce de ocho pasos (C21), y las cotas poblacionales E[A]/E[U] nativas continúan sin certificación económica.

**Veredicto: N9-S NO_GO; 3.200 cuentas M10 finales selladas; cero nuevas señales, semillas, cuentas económicas, órdenes, fusiones, despliegues ni reactivación del optimizador.**
