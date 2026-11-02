# HARPOON XXXUltimate 30.15.0

Integral actual: lee `LEEME_30_15_0.txt`, `docs/LEVEL7_OPERACION_30_15_0.txt` y `EVALUACION_ECONOMICA_HARPOONX_30_15_0.yaml`. Incluye validación de costes, procedencia de decisiones y evaluador económico de cartera. 230 pruebas aprobadas. El nivel 7 de rentabilidad real no está acreditado. Despliegue pendiente.

## Documentación heredada

# HARPOON XXXUltimate 30.14.0

Integral actual: lee `LEEME_30_14_0.txt` y `EVALUACION_ECONOMICA_HARPOONX_30_14_0.yaml`. Se corrigieron causalidad de señales, reservas compartidas y valoración inicial. El resultado histórico permanece en +91,28 USD; el nivel 7 de rentabilidad real no está acreditado. Reproducción: `node tools/verify_portfolio_validity_study.cjs`. Despliegue pendiente.

## Documentación heredada

# HARPOON XXXUltimate 30.13.0

## Core revisado antes de despliegue · Quant 1.8.1

La integral corrige cinco fallos reproducidos: disponibilidad temporal de etiquetas Ridge, reserva de efectivo coherente con la ejecución modelada, intersección de límites del core y la cuenta, estado terminal de protecciones OCO y cancelación del remanente de una entrada parcial tras el cierre de sesión.

Empieza por `LEEME_PRIMERO_30_13_0.txt`. Las pruebas nuevas están integradas en `tools/verify_remediation.py`; la reproducción actual está en `evidence/core5_30_13_0/reproduce.py`. La entrega conserva resultados históricos, interfaces y controles económicos. Preparación técnica no equivale a rendimiento real de 5/10.

Un modelo Ridge anterior no adquiere causalidad por cambiar el entrenador. Los modelos SVR anteriores deben conservar sus hashes; el cambio de fuentes puede invalidarlos por diseño. Sólo los ejemplos sintéticos de evaluación se reconstruyen como pruebas.

## Antecedente 30.12.2

## Medición observada y consistencia de evidencia · Quant 1.8.0

Esta aplicación integral incorpora un recolector autenticado de evidencia y corrige el vínculo entre la configuración observada y la comparación del nivel 4. La aceptación de un prefijo de observaciones debe ser la misma cualquiera que sea su división en páginas. El contrato de comparación conserva una configuración fija y admite únicamente acciones y ETF al contado, con multiplicador 1. El replay genérico dispone de un alcance distinto que también admite cripto; eso no amplía la comparación financiada del nivel 4.

`LEEME_PRIMERO_30_12_2.txt` es la guía actual. `EVALUACION_ECONOMICA_HARPOONX_30_12_2.yaml` distingue la evidencia económica, el resultado de acceso y las pruebas efectivamente ejecutadas. Las guías e informes anteriores conservan su fecha y alcance.

El nivel 4 existente significa medición observada integrada y puede coexistir con pérdidas. No es una calificación de rentabilidad real. Sin observaciones y cuenta conciliadas, la nota de evidencia permanece en 3 y la calificación de rendimiento real es desconocida. La revisión no modifica umbrales, modelos, capital, riesgo ni presupuesto para obtener una nota mayor.

El recolector realiza una única descarga por GET desde una instancia identificada. Conserva bytes originales, verifica páginas de observaciones y reconstruye el historial contable con los verificadores vigentes. Una revisión contable cambiante interrumpe la descarga y deja un resultado parcial no aceptado. No convierte un paquete íntegro en validación económica, no crea modelos ni recibos de costes, y no otorga autoridad para operar.

La instancia actual y su acceso siguen sin identificarse en los recursos comprobados. Los datos sintéticos de las pruebas están separados de la evidencia económica. Las fuentes nuevas y los recibos de esta revisión están en `evidence/nivel4_30_12_2/`.

## Antecedente integral 30.12.1


## Integral revisada del proyecto · 30.12.1 / Quant 1.8.0

Esta distribución contiene la aplicación completa. Se instala desde este árbol, sin aplicar un patch ni superponer otra entrega. `LEEME_PRIMERO_30_12_1.txt` es la guía de entrada. `REVISION_INTEGRAL_PROYECTO_30_12_1.yaml` identifica las ramas, sus fuentes, funciones, limitaciones y el resultado de la revisión.

La base activa sigue siendo el coordinador de 30.12 con Quant 1.8. Se incorpora de la rama 31.x la protección del transporte de almacenamiento: plazo por solicitud, límite de cola, estado de fallo retenido en esa instancia y reconocimiento de escritura incierta. Ese indicador no sustituye la reconciliación después de reiniciar el proceso. Un timeout no demuestra rollback; no se reenvían escrituras automáticamente. Al fallar la persistencia se bloquean las nuevas mutaciones que dependen de ella, incluidas las que requerirían persistir una protección o un cierre. Esto no revoca solicitudes previamente autorizadas o ya enviadas al broker. Las órdenes que el broker ya aceptó conservan su estado allí; se requiere reconciliación antes de reanudar.

Las ramas 31.6/TP-NET de opciones y Framework Aplicado Python 1.2 son implementaciones distintas y se conservan identificadas en la matriz. No se arrancan coordinadores paralelos ni se sustituyen los límites actuales por los de esos laboratorios. El número 31.x no prueba que una entrega incorpore las correcciones posteriores de 30.12.

La revisión amplía el historial conocido: el ledger de la rama 31.x conserva las 18 plazas Ultimate anteriores y añade otras 54, para 72 en esa familia. Otros estudios reutilizan datos, identidades y resultados; el total global deduplicado continúa desconocido. El catálogo nuevo complementa los recibos históricos originales y no convierte los antiguos contadores parciales en un inventario completo del proyecto.

El nivel económico verificable continúa en 3/10: faltan datos causales utilizables y una cuenta con patrimonio y gastos conciliados. El nivel 5 requiere una prueba temporal nueva de crecimiento neto positivo y mejora frente a Ridge y al motor vigente, con riesgo e incertidumbre aceptables. La versión de software no acredita ese resultado. No se realizó despliegue, no se enviaron órdenes y no se inició otro ensayo financiero.

Las secciones siguientes conservan el alcance histórico de las entregas anteriores. La evaluación actual está en `EVALUACION_ECONOMICA_HARPOONX_30_12_1.yaml` y `evidence/integral_30_12_1/`.

## Validación hacia el nivel 5 · 30.12.0 / Quant 1.8.0

Esta revisión conecta la comparación financiada con el evaluador económico y estabiliza la exportación de observaciones. Los controles tienen nombres explícitos: NATIVE es la estrategia vigente, RIDGE y SVR comparten el asignador y CASH conserva efectivo con los costes externos aplicables. El contrato económico anterior mantiene su significado de C0; no se cambia una etiqueta para fingir paridad.

El nivel 5 exige crecimiento neto positivo y una mejora relevante frente a Ridge y al control vigente en una prueba temporal nueva, con costes, riesgo, estrés, procedencia y búsqueda previa verificados. Las pruebas de software no conceden ese nivel. El informe ejecutado de esta entrega es `EVALUACION_ECONOMICA_HARPOONX_30_12_0.yaml`; los recibos y los comandos están en `evidence/level5_30_12_0/` y `LEEME_NIVEL5_30_12_0.txt`.

Los datos de la cuenta actual, sus costes originales y una muestra causal utilizable siguen pendientes. El repositorio privado recuperado contiene una versión antigua 24.3.1; no demuestra que 30.12.0 esté desplegada. El resultado económico permanece `VENTAJA_NO_DEMOSTRADA` y la nota de evidencia permanece en 3/10. La versión de software y la nota económica son valores distintos.

Las herramientas nuevas trabajan offline, mantienen los presupuestos y conservan la restricción de investigación de SVR. La captura, la gestión de posiciones y la inferencia existente conservan sus límites. El formato de snapshot evita mezclar páginas mientras llegan nuevas observaciones; el procesamiento acotado conserva los desconocidos y no garantiza una retención de cien sesiones.

Las secciones siguientes describen entregas anteriores y conservan su alcance histórico.

## Avance hacia el nivel 4 · 30.11.0 / Quant 1.7.0

Esta entrega incorpora archivo contable continuo con integridad y límites de memoria, lectura de recibos de costes, exportación autenticada de historia, reconstrucción de datos con procedencia causal y comparación reproducible C0/Ridge/SVR mediante los predictores numéricos y el coordinador. El verificador de nivel 4 vuelve a calcular sus entradas; las declaraciones de origen y los hashes locales no sustituyen la procedencia de las observaciones.

El nivel anterior es 3/10 y permanece en 3 mientras falten datos prospectivos utilizables, la historia observada de cuenta con todos sus costes y la comparación observada de las tres políticas. El resultado ejecutado se entrega en `EVALUACION_ECONOMICA_HARPOONX_30_11_0.yaml`; la ruta técnica está en `LEEME_NIVEL4_30_11_0.txt` y los artefactos en `evidence/level4_30_11_0/`. Un nivel 4 significa que existe una medición verificable; no significa rentabilidad positiva.

Los nuevos ejemplos son pruebas sintéticas de software, incluidas sus curvas de patrimonio y recibos. La ejecución histórica fija exige una reserva explícita en el journal existente, con tres plazas y un límite familiar de seis, sin reiniciar contadores. Esta revisión no consumió nuevos ensayos financieros. Los modelos observados y sus recibos originales deben existir antes de ejecutar esa medición; no hay búsqueda automática adicional ni activación de SVR en producción.

La verificación contable y la captura continúan con presupuestos acotados. Las estadísticas del historial archivado se reutilizan durante el intervalo configurado mientras sus fuentes sigan siendo válidas; los cambios de identidad, integridad, conciliación o costes invalidan esa reutilización. No se añaden servicios, llamadas al LLM ni sondeos nuevos al panel. El límite de posiciones, capital, riesgo y permanencia de 72 horas se conserva. La lectura y validación offline no envían órdenes.

Las secciones siguientes describen entregas anteriores y conservan su alcance histórico.

## Distribución integral · 30.10.1

Esta revisión integra la aplicación y Quant 1.6.0. Corrige la ruta de instalación para usar un único coordinador XXXUltimate, muestra los validadores y la contabilidad en el monitor, toma la versión del servidor e incluye las fuentes/verificadores necesarios para el gate económico en el diseño de la imagen. La guía `LEEME_INTEGRAL_30_10_1.txt` explica instalación, actualización y validación local. `EVALUACION_ECONOMICA_HARPOONX_30_10_1.yaml` contiene la valoración y sus fuentes.

La valoración de preparación económica es **3/10**, un hito ordinal de evidencia, no una probabilidad de beneficios. La revisión conserva la señal y los límites de riesgo; no realiza una nueva búsqueda financiera. El registro Quant conserva 23 intentos, y el informe Ultimate heredado declara otros 18 en su propio ámbito; no se afirma un total global deduplicado. Las cifras históricas con ejecución modelada y las pruebas sintéticas permanecen identificadas.

Las nuevas pruebas del monitor ejecutan sus funciones de render sobre un DOM mínimo. Las pruebas de distribución reconstruyen el contenido de los COPY finales y ejecutan el verificador desde esa disposición; no equivalen a construir o arrancar una imagen Docker. Consulta el informe de validación de esta entrega para los recorridos efectivamente ejecutados y los recursos no disponibles.

## Contabilidad y validadores operacionales · 30.10.0 / Quant 1.6.0

Esta entrega incorpora `NetAccountLedger`, captura prospectiva independiente del modelo, replay del coordinador real y un gate económico pareado contra Ridge. `docs/AUTONOMIA_30_10_ES.txt` describe funciones, contratos, comandos y límites. El informe ejecutado se entrega en `REMEDIACION_OPERACIONAL_HARPOONX_30_10_0.yaml`.

El rendimiento se alimenta del ledger interno. Una marca de patrimonio no acredita costes completos ni retorno comparable: se concilian caja, inventario, actividades, flujos y gastos declarados. Los recibos tardíos reconstruyen solamente el prefijo histórico cubierto y mantienen desconocido el resultado económico actual sin cobertura. `HARPOON_PERFORMANCE_2` añade procedencia de costes y fecha inicial real; el verificador histórico conserva explícitamente el formato V1 para sus recibos sellados, sin reescribirlos.

El journal recoge datos aunque falte calibración, conserva rechazos, conserva franjas de 90 minutos y archiva índices por segmentos con presupuesto explícito. El adaptador al replay conserva profundidad desconocida y no genera órdenes. Los trabajadores numéricos comparten un máximo de un proceso y ocho solicitudes pendientes; el plazo incluye espera. La gestión determinista de posiciones no usa esa cola.

`GET /v1/operational` y `GET /operational-readyz` requieren autenticación y separan proceso vivo, contabilidad, datos, planificación y evidencia económica. Pausa, parada, bloqueo del broker, problemas contables o persistencia inválida no producen disponibilidad operacional. El endpoint no autoriza órdenes por sí mismo.

La autonomía económica completa sigue sin verificarse. No se han entrenado modelos para producción ni ejecutado nuevas búsquedas financieras, cambiado límites de riesgo, enviado órdenes externas ni desplegado esta versión. SVR conserva su restricción de investigación. El presupuesto histórico mantiene 23 intentos. En la versión 30.10.0 la retención era finita sin archivo automático; 30.11.0 añade el archivo acotado descrito arriba.

La configuración de ejemplo incorpora los validadores para una instalación nueva. Una configuración ya vinculada a un journal debe conservar su identidad; no borrar ese journal para aceptar el ejemplo. Las fuentes de costes externos, datos y predictores observados son requisitos explícitos, no valores cero predeterminados.

## Remediaciones de sesiones, vigilancia y comparación neta · 30.9.0

Integra Quant 1.5.0. Corrige la contaminación de características regulares por premarket, incorpora clasificación ETF en el descubrimiento, limita la vigilancia a 40 instrumentos totales y rota únicamente candidatos gestionados sin exposición. Historial, catálogo y datos recientes se verifican antes de declarar un símbolo listo. Los snapshots de candidatos y las decisiones cuantitativas se conservan con identidad, configuración y huellas. Aclaración operacional de 30.12.1: una persistencia fallida bloquea nuevas entradas; la gestión puede seguir programada, pero las protecciones o cierres que exijan persistencia no pueden completar nuevas mutaciones hasta recuperar y reconciliar el estado.

Las franjas de apertura y precierre de 90 minutos se identifican por calendario. Las rachas son diagnósticos causales y no añaden variables al predictor. Se conserva el corte de entradas diez minutos antes del cierre. La etiqueta postcierre no habilita órdenes fuera de sesión.

El nuevo replay offline compara C0, Ridge y SVR con patrimonio continuo, flujos, costes, ejecuciones parciales y posiciones abiertas. Llama al asignador real y usa una política común de tiempo/invalidez; todavía no reproduce todas las salidas y plugins del coordinador. Es un recurso de diagnóstico, no una comparación económica ya aprobada del motor completo. La SVR conserva su autorización de investigación y no puede habilitar órdenes.

La matriz de correcciones, pruebas ejecutadas y recursos pendientes se entrega en `REMEDIACIONES_HARPOONX_30_9_0.yaml`. Comandos de reproducción:

```bash
npm ci
python3 -m venv .venv
.venv/bin/pip install -r quant/requirements-tested.txt -r quant/requirements-dev.txt
.venv/bin/python tools/verify_remediation.py --suite all --output /tmp/harpoon-remediation-qa
cd quant
../.venv/bin/python -m harpoon_quant.paired_replay --input examples/paired_replay/synthetic_request.json --output /tmp/harpoon-paired-synthetic.json
```

La regresión se verificó con Node 24 y Python 3.12. Los relojes anclados son exclusivos de las pruebas. El ejemplo de replay es sintético; su beneficio, si lo hay, no es una medición de mercado. Los modelos SVR están vinculados a la implementación: un artefacto de una versión anterior requiere recalibración y revisión, no un simple cambio de hash. Conserva la configuración vinculada al journal; no sustituyas límites de una instalación existente por el ejemplo de esta entrega.

Los informes históricos siguientes conservan el alcance y los resultados de su versión original.

Coordinador Alpaca PAPER con piloto automático, protección durable y laboratorio cuantitativo. El conector adicional Ironbeam utiliza exclusivamente la API de simulación del broker. El software no acredita rentabilidad ni participación en Championship.

## SVR de retorno escalar · 30.8.0

Integra el motor 1.4.0 con regresión de vectores de soporte para el retorno del subyacente. El predictor utiliza el worker numérico existente y alimenta los escenarios/asignación en modo sombra. Entrenamiento, inferencia y controles están implementados; esta entrega no activa órdenes a partir de la SVR. Los artefactos ridge anteriores mantienen su compatibilidad y el predictor de costes SVR existente conserva su función. Instrucciones reproducibles: `quant/README_ES.md`; resultados de verificación: `SVR_VALIDACION_1_4_0.yaml`. La prueba completa del nuevo recorrido Node → Python se ejecuta con `npm run test:svr`.

## Auditoría adversarial 30.7.1

Incluye el motor 1.3.1 con verificación de integridad del journal y del estudio, publicación recuperable del dictamen, ledger completo de efectivo/inventario y controles de exposición calculados después del fill. El coordinador registra la exposición de entradas parciales pendientes de protección y conserva su plazo entre reintentos. La telemetría no elimina por sí sola esa exposición. La reproducción conserva el resultado negativo del estudio; no se entrega una estrategia aprobada. Informe, comandos y límites: `AUDITORIA_HARPOONX_2026_10_31.yaml`. Los escenarios sintéticos del estudio ya fueron utilizados y no deben tratarse como un nuevo holdout.

## Investigación económica 30.7.0

Replay continuo de capital, seis hipótesis, presupuesto compartido con el journal cuantitativo y holdout sintético nuevo. El finalista se rechazó: menor pérdida no equivale a margen positivo. El módulo offline no activa políticas. [Guía](docs/QUANT_30_7_ES.md). Código y evidencia: `quant/economic_experiment/`.

## Métricas y optimización recursiva 30.6.0

Sortino, drawdown, Sharpe HAC, CVaR y métricas netas comparten un módulo común. El coordinador consulta un optimizador durable de selección/sizing, con búsqueda acotada, holdout y promoción PAPER prospectiva condicionada. Sin panel o P&L conciliado espera datos. [Guía vigente](docs/QUANT_30_6_ES.md). No se ha desplegado ni demostrado beneficio observado.

## Calibración y microestructura 30.5.0

El colector conserva tamaños del BBO, toma muestras por segundo y expone omisiones. El worker registra curvas y detecta regímenes como contexto, con independencia del modelo de retornos. Las entradas requieren la calidad L1 configurada; los modelos de costes y regímenes observados todavía deben calibrarse. Lee [la guía de la versión](docs/QUANT_30_5_ES.md) y [el entorno](quant/LAB_ES.md). No se ha desplegado.

## Motor cuantitativo común 30.4.0

La configuración de ejemplo activa `quant.enabled=true`. Las entradas requieren ahora un modelo observado vigente y una asignación económica admisible; sin calibración se bloquean las entradas y continúa la gestión de posiciones. No se entrega un modelo financiero aprobado. Lee [la guía de esta versión](docs/QUANT_30_4_ES.md) y [el motor](quant/README_ES.md) antes de arrancar. La verificación histórica del motor está en `quant/evidence/validation.json`; la de esta entrega 30.8.0 está en `SVR_VALIDACION_1_4_0.yaml` y `quant/evidence/svr/`.

## Arranque automático

```bash
npm ci --ignore-scripts
npm run build:xxx
python3 -m venv .quant-venv
.quant-venv/bin/pip install -r quant/requirements-tested.txt
export HARPOON_QUANT_PYTHON="$PWD/.quant-venv/bin/python3"
npm run start:ultimate
```

Configura antes las variables de `.env.example` en el entorno del proceso. Node no carga ese archivo por sí solo. Node 24 y Python 3 son requisitos. Abre `http://127.0.0.1:10000` si usas el origen local predeterminado. Usuario del panel: `trader`; contraseña: `HARPOON_PANEL_PASSWORD`, mínimo 32 caracteres.

Con claves PAPER válidas, cuenta dedicada y journal conciliado, el servidor arranca la vigilancia automáticamente; las entradas requieren además la calibración y la asignación cuantitativa admisibles. `HARPOON_START_PAPER` omitido equivale a `1`; `0` permite iniciar con entradas pausadas. Una pausa guardada por el usuario sobrevive al reinicio y no se elimina por el arranque automático. La primera vinculación exige una cuenta PAPER vacía. Las posiciones ya gestionadas se recuperan desde el SQLite original; no borres el journal para eludir una discrepancia.

El pulso de posiciones se programa cada segundo, cotizaciones cada tres segundos y conciliación cada cinco segundos. Además reacciona a eventos del stream. Estos intervalos son objetivos del planificador, no latencias garantizadas del broker. Cada ciclo evita solaparse consigo mismo. El cálculo nuevo utiliza un worker separado; una investigación pausada no pausa la protección. Un pulso de protección atrasado o con error bloquea nuevas asignaciones aunque la cuenta todavía esté conciliada.

El piloto utiliza los seis plugins seleccionados y todos sus controles de datos, permisos y riesgo. El catálogo conserva 61 plugins implementados. La selección adicional es opcional: algunos modelos necesitan datos y aceptación antes de generar entradas. Las salidas de posiciones existentes siguen activas al apagar un plugin o pausar entradas. La configuración admite modificaciones por el operador antes de vincular un journal; conserva el archivo original al actualizar una cuenta ya vinculada.

## Corrección operacional 30.3.1

El coordinador observa todas las campañas antes de emitir una mutación del broker. Las salidas urgentes tienen prioridad global y los turnos dentro de cada prioridad rotan; una protección rechazada no reinicia siempre el recorrido por la primera posición. Un pulso admite hasta ocho rondas de mutación/conciliación. Las campañas adicionales conservan su turno en el siguiente pulso. Esto limita el trabajo por pulso, pero no garantiza una latencia de ejecución ante retrasos del broker o una cuenta sin conciliación.

Cada posición expone intento real, última evaluación completada, antigüedad, resultado, cotización y snapshot usados. El límite local de evaluación es cinco segundos; una cotización vencida, propiedad incierta, error o campaña no visitada no hereda la salud de otra. La lane de guardia valida cobertura efectiva. La falta de protección alineada, las salidas pendientes y los reintentos no resueltos bloquean nuevas entradas.

Los rechazos definitivos tienen una espera persistida por campaña y clase de orden: 2, 4, 8, 16, 32 y hasta 60 segundos entre intentos. La conciliación de un hermano OCO anterior no borra ese presupuesto. Un grupo nativo rechazado permite una única transición al stop simple previsto; si ese stop se rechaza, vuelve a esperar. Una respuesta incierta nunca autoriza otro envío a ciegas. Reiniciar o pulsar reanudar no elimina la espera ni recupera una salud antigua como si fuera actual.

Una sesión cerrada se muestra explícitamente como MARKET_CLOSED, sin inventar una evaluación de precio ni actualizar su fecha de finalización. Puede permitir entradas en otros mercados abiertos únicamente tras comprobar un reloj de sesión cerrado reciente, propiedad conciliada, protección nativa alineada y ausencia de órdenes de salida o reintentos pendientes. Al reabrir, o al vencer el reloj, se requiere una evaluación nueva. Una orden standalone en estado held no cuenta como protección confirmada; una pata held de OCO solo cuenta con su padre vivo y su identidad verificada.

El plan TP conserva su precio mínimo y no se convierte en una venta a mercado por faltar una cotización. Un cierre urgente amplía su objetivo solo por nuevos fills de compra confirmados mientras se cancela una entrada; antes de vender se concilian las cantidades. El validador de reservas evita que la cantidad de venta, sumada a órdenes pendientes, exceda el inventario y cuenta patas OCO vinculadas una sola vez.

Los registros de evaluación guardados sirven como diagnóstico. Tras reiniciar, las fechas del proceso anterior no acreditan cobertura del proceso nuevo. Se conservan la pausa manual, la independencia del laboratorio y las puertas PAPER. Las hipótesis, límites y política BASELINE_30_1 no se han promovido ni cambiado.

Verificación de esta corrección: AUDITORIA_XXXUltimate.txt y evidence/operational-30.3.1/. Los resultados previos permanecen como evidencia histórica; no son una afirmación de que se repitieron todas esas pruebas. La documentación de 30.3.0 se conserva en docs/legacy/XXXUltimate_30_3_0/.

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
npm run test:operational
npm run test:xxx:browser
npm run test:ultimate:browser
npm run audit:xxx
npm run benchmark:xxx
```

Las pruebas usan dobles de broker y datos sintéticos identificados exclusivamente en `tools`. El runtime no los importa. La auditoría estática inventaría cuerpos de función, imports de pruebas y marcadores inconclusos; no es auditoría independiente ni certificación de producción. Consulta `AUDITORIA_XXXUltimate.txt`, el informe walk forward y los hashes de la entrega para los resultados efectivamente ejecutados.

El Dockerfile conserva compilación separada y dependencias de producción; los informes requeridos están permitidos explícitamente en `.dockerignore`. No se ha construido la imagen ni desplegado esta versión desde este entorno. El contenedor incluye el informe; reproducir toda la investigación requiere las fuentes del ZIP, no la imagen mínima.

Fuente anterior y contexto de integración: [README de 30.2](docs/legacy/README_XXX_30_2_0.md). Las limitaciones allí descritas corresponden a esa versión.

Referencias primarias: [API Ironbeam](https://docs.ironbeamapi.com/), [acceso a API](https://www.ironbeam.com/knowledge-base/ironbeam-api-access/), [reglas Championship 2026](https://robbinstrading.com/wp-content/uploads/2025/09/2026FuturesWorldCupEntryAgreement.pdf), [CME micros](https://www.cmegroup.com/articles/faqs/micro-e-mini-equity-index-futures-frequently-asked-questions.html), [DSR](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf) y [PBO](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf).
