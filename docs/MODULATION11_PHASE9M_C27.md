# HARPOONX / FWN9 — M11-C27: registro causal prebarra exhaustivo dentro de las entradas declaradas

**Estado de ingeniería:** C27 implementa un esquema, un validador fuente, adaptador de observaciones y diario privado persistente en un árbol separado de investigación. **Estado económico N9-S: NO_GO.** No se modificaron las rutas originales de órdenes ni se desplegó nada. Se mantienen selladas 3.200 cuentas finales M10.

## 1. Problema que resuelve la implementación

C20 y C21 demostraron que un archivo compacto de fills no permite reconstruir automáticamente todos los stops, targets, inventarios y rechazos **conocidos antes** de cada barra. No basta observar la razón del fill futuro para inferir que la barrera fue conocida causalmente antes. C27 registra explícitamente los campos originales por cada inicio de barra, la información de dónde provienen y un rechazo ante cobertura incompleta. El registro se toma del **estado fuente**, no del OHLC de la barra que todavía no ocurrió.

El registro C27 es una capacidad funcional, no una afirmación de que ya se haya capturado un periodo verdadero de mercados reales. Los tests usan tres barras y un libro `ultimate_reservations.js` exclusivamente sintéticos de ingeniería, sin llamar al generador M9 ni crear nuevas cuentas económicas.

## 2. Campos necesarios por barra

El esquema `HARPOON_FWN9_C27_PREBAR_INPUT_1` obliga a capturar:

- **Relojes:** `barStart`, `capturedAt`, `lastPublicKnownAt`, `barIndex`, identificación de la ejecución de investigación y SHA de la fuente M9. Nunca acepta `currentBar`, `currentOHLC`, secuencia de precios intrabar ni información de barras futuras. Rechaza también *campos no declarados*, en el objeto y en los estados anidados, para evitar introducir silenciosamente máximos/minimos de la barra.
- **Cartera financiada única:** `cashUsd`, `settledCashUsd`, `unsettledCashUsd`, compromisos externos, equity marcado, timestamps conocidos y caja libre calculada descontando reservas **PENDING**. Las reservas OPENED tienen inventario físico y no se descuentan por segunda vez como un gasto futuro. Se comprueba `equity = cash + sum(q * última marca conocida)` dentro de tolerancia de auditoría.
- **Posiciones:** ID de reserva y símbolo, acciones largas enteras, cantidad restante **idéntica a la fuente** `snapshotFundedReservations`, entrada/fecha, stop vigente, `knownAt`, precio de marca previo, plazo de liquidación máximo de 72 horas. Un trailing stop puede subir por encima de la entrada, y no puede aflojarse en una barra posterior.
- **Targets:** exactamente TP1 y TP2 con precio, cantidad, indicador de finalización y `knownAt`. Las cantidades no pueden superar el lote originalmente reservado. Los targets persistentes no pueden revertir del estado `done=true` al estado `done=false`.
- **Stops pendientes:** precio que endurece el stop y reloj conocido; si su aplicación es efectiva antes de la barra actual ya debe reflejarse en el stop vigente. No se usa un stop todavía desconocido.
- **Admisiones y reservas:** libro fuente `HARPOON_FUNDED_RESERVATIONS_1` completo, incluyendo decisiones, observaciones OPENED/CLOSED/NO_FILL y `knownAt`, enlazado con `runtime30/ultimate_reservations.js`. No se permite que una respuesta todavía desconocida libere capital o inventario.
- **Oportunidades:** enumeración de IDs solicitados por fuente, exactamente un resultado por ID (`RESERVED`, `REFUSED`, `NO_FILL`, `NO_SIGNAL`, `OBSERVED_ONLY`). Los rechazos requieren causa; una reserva admitida debe existir realmente en el libro fuente. `OBSERVED_ONLY` **no equivale a una orden**.

### Cierre temporal reforzado

Para `PROSPECTIVE_LOCAL_CAPTURE`, el corte de conocimiento es `capturedAt`, estampado por el proceso al guardar, **no** `barStart`, que puede encontrarse en el futuro. Se exigen `knownAt <= capturedAt` para reservas, stops, TP, decisiones, marcas y recibos. Este control bloquea un error sutil: un registro guardado antes de una barra no puede incluir datos que llegaron después del guardado pero antes de su inicio.

Para `ENGINEERING_REPLAY`, los fixtures históricos verifican `knownAt <= barStart` sin alegar una captura prospectiva. Ambas modalidades devuelven `sourceProviderTimestampCryptographicallyAuthenticated=false`: el reloj local y un hash de archivo no son firma de broker ni prueba de un sello de tiempo independiente.

## 3. Cobertura de todas las oportunidades de la fuente cuantitativa

El adaptador `runtime30/fwn9_c27_quant_observation_adapter.cjs` consume exactamente el contrato original `HARPOON_RUNTIME_OBSERVATION_1` de `runtime30/quant_observations.js`. Enfrenta los `plugin|symbol` solicitados con la unión de observaciones de características numéricas y razones de rechazo. Si falta un ID, si aparece dos veces o si se presenta un plugin fuera de las seis variantes registradas, **falla**.

Las observaciones con ocho características finitas quedan como `OBSERVED_ONLY`, mientras que las rechazadas tienen un motivo. Los resultados se integran directamente en la verificación de una barra. **Esta comprobación solo es exhaustiva respecto de los IDs solicitados que la fuente proporcionó**: no demuestra que el generador original haya enumerado todas las oportunidades concebibles del mercado. El campo `sourceEnumeratorExhaustiveOfAllPossibleMarketOpportunities` permanece falso y está prohibido usar los datos como tasa de admisión poblacional hasta instrumentar el generador y sus omisiones.

## 4. Diario realmente persistente y recuperación entre reinicios

El módulo `runtime30/fwn9_c27_prebar_journal.cjs` contiene una implementación de archivos privados append-only. Crea un manifiesto SHA-256 para `runId`, seis políticas C22 más CASH y política original, hash del generador M9 fijo, modo de captura y **lista completa de inicios de barra esperados**.

Para cada barra, valida su estado **antes de escribir**, lo sella en un archivo numerado y content-addressed SHA-256 creado exclusivamente con permisos 0600, hace `fsync` del archivo y del directorio, y mantiene una cadena de `previous` hashes. Un candado de escritura exclusivo en archivo adyacente impide dos procesos escritores concurrentes. Si el proceso muere y deja el candado, la recuperación se detiene y requiere intervención manual: no se modifica automáticamente un diario cuya procedencia no está clara.

Al reiniciar, `verifyJournal()` revalida TODO el historial, secuencia, SHA, archivos, permisos, reloj, snapshots de las reservas y continuidad de posiciones/TP/stop. Una página truncada, un archivo ajeno, una barra ausente, una reserva alterada o un recibo antiguo sustituido invalidan la prueba. `checkScheduleComplete()` devuelve la lista precisa de barras no capturadas y jamás acepta una malla parcial como completa.

`originalM9Grid()` deriva 78 inicios de 5 minutos por sesión del calendario original registrado sin muestrear precios ni abrir cuentas finales. En un uso real bursátil debe utilizarse un calendario contrastado con feriados y DST y conservar su procedencia; no puede inventarse una jornada ordinaria en medio cierre o festivo.

El hash local **no es antimanipulación frente a un adversario que controla todos los archivos** y puede reescribir toda la cadena y el manifiesto. Para un certificado financiero independiente haría falta anclar periódicamente el hash de cabecera a un registrador externo o a evidencia de fuente firmada, además de recibos auténticos del broker. La implementación no sostiene esa propiedad hoy.

## 5. Interfaz utilizable desde un entorno privado

Se requiere Node.js 22 y un directorio privado. El manifiesto debe incluir `runId`, `mode`, `expectedBars` y el `generatorHash` original; el JSON de la barra debe respetar el contrato exacto y no contener datos futuros. Para el ensayo congelado el hash del generador se verifica contra el registro M9. No debe cargar el ZIP final M10 ni incluir claves API.

```bash
node tools/fwn9_c27_prebar_cli.cjs --init /carpeta-privada/c27-journal --manifest /carpeta-privada/grid.json
node tools/fwn9_c27_prebar_cli.cjs --append /carpeta-privada/c27-journal --input /carpeta-privada/prebar.json
node tools/fwn9_c27_prebar_cli.cjs --verify /carpeta-privada/c27-journal
```

El comando solo imprime número de barras capturadas, barra total esperada, SHA de cabecera y puertas de seguridad; nunca imprime la cartera privada. La captura `PROSPECTIVE_LOCAL_CAPTURE` toma el tiempo de sello del proceso y exige que no haya ocurrido aún la barra, ni información conocida después de ese momento.

**No está cableado a la ruta de órdenes o al servicio Render.** El usuario no autorizó una reactivación y el workspace conectado no devolvió un identificador de servicio. Su ejecución con fuentes reales requiere instalar primero el observador en el punto causal inmediatamente anterior a la barra y comprobar que puede recuperar todo su estado de reservas y de oportunidades sin ver OHLC futuro.

## 6. Comprobaciones y límites de aceptación

Se mantienen los verificadores C16–C26 (203 regresiones). C27 añade pruebas de origen `ultimate_reservations.js`, TP, trailing/pending, caja y máximo de 72h; adaptación original de observaciones, nanosegundos C26, errores por valores futuros, nombres de campos extra, corrupción de archivo, reinicio, doble escritor y calendario completo. Todos son ensayos de software con datos inequívocamente sintéticos.

**Las seis variantes originales de C22 permanecen registradas pero no ejecutadas**. Solo después de un tramo prospectivo nuevo con registros de oportunidades completas, recibos auténticos de fill y quote, tarifas, caja, NAV y política original comparable será apropiado contrastar el crecimiento geométrico neto en una sola cartera financiada. C27 no se convierte en una estimación poblacional universal E[A]/E[U] por pasar unit tests, ni repara la contradicción C21 de OHLC stop-first.

**Veredicto:** C27 implementa la capacidad verificable de registro causal prebarra; no hay certificado de captura real universal ni rentabilidad N9. N9-S `NO_GO`, 3.200 cuentas finales M10 selladas, cero nuevas señales, semillas, cuentas económicas, órdenes PAPER/LIVE, deploys, fusiones o reactivación recursiva.
