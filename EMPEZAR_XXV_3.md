# HARPOON XXV.3 R2 — Pulso propio y autogestión
La revisión **R2 / 25.3.2** añade un supervisor proactivo: pulso de cinco segundos, sesiones Alpaca, preparación COLD, selección de candidatas validadas y recuperación PAPER acotada. Lee **AUTOGESTION_R2.txt** para los parámetros y el alcance; **config/HARPOON_AUTOGESTION.json** es el perfil importable. El acceso principal es **Harpoon · Pulso y mesa → Pulso y autogestión**. Cerrar ese diálogo no detiene la supervisión; el HTML sigue necesitando una pestaña y equipo activos. El servicio cloud debe actualizarse para usar esta revisión 24/7.

Esta entrega añade al ejecutor XXV.2 un war room nativo y analítica de opciones de Alpaca. Conserva sus agentes, riesgo, conciliación, salidas, gateway GPT, persistencia, plugins heredados y despliegue cloud. La ejecución de esta edición sigue limitada a BTC/USD y ETH/USD spot. Acciones, ETF y contratos aparecen como oportunidades de investigación; esta capa no coloca órdenes sobre ellos.

## Uso

1. Abre **HARPOON_XXV_3.html**. En **API keys y conexión** usa la conexión Alpaca existente. El HTML requiere la pestaña y el equipo activos. Para ejecución persistente utiliza el paquete cloud y sus secretos de alojamiento; cerrar su panel no detiene el servidor.
2. Entra en **War room → Opciones y contexto cruzado**. Selecciona subyacentes, feed, coste estimado por contrato y ventana. **Consultar una ventana** hace lecturas de Alpaca y consume cero tokens GPT. **Lectura automática ON** habilita las siguientes ventanas y la profundidad cripto compartida.
3. **OPRA** requiere permiso de datos. La conexión consultada el 17 de octubre de 2026 lo rechazó por falta de suscripción. **INDICATIVE** tiene cotizaciones modificadas y trades retrasados; se mantiene explícitamente como exploración. No hay cambio de feed silencioso. Esta comprobación no identifica las credenciales instaladas en tu servidor.
4. En **Campaña y prueba**, fija once meses completos y el coste diario de datos e infraestructura. Se congela el riesgo vigente. Descarga el historial Alpaca o importa un dataset documentado. Las barras diarias sirven para diagnóstico, pero no acreditan ejecución intradía.
5. Evalúa las ocho variantes. Sólo si una pasa todas las puertas puede abrirse la reserva final. El informe agrega después los once meses con cartera continua. Un rechazo conserva la estrategia vigente.
6. La candidata aceptada puede asignarse a **PAPER** con la cuenta plana. Si habilitas **aplicar automáticamente** y **COLD**, el loop espera esa condición y realiza la asignación. LiftOff detiene nuevos estudios y promociones. Las salidas de posiciones siguen su política.

Los plugins experimentales aparecen LOADED para investigarlos. No pueden sustituir la estrategia vigente sin una campaña local validada. No se abre una operación por el mero hecho de que un motor figure ON: también debe existir señal, permiso, liquidez y presupuesto.

## Qué aporta cada fuente

| Fuente | Datos y uso | Límite |
|---|---|---|
| Cadena de opciones | Bid/ask, tamaños, IV y griegas; rango aproximado, skew y estructura temporal | Es L1, no profundidad L2; la IV no proporciona dirección |
| Catálogo de contratos | Vencimiento, strike, tipo, multiplicador real y open interest con fecha | OI es una observación retrasada; no identifica al comprador ni al dealer |
| Libro cripto de Alpaca | Niveles, tamaños y profundidad a 25 bps por lado | Sólo el venue Alpaca; vigencia máxima de cinco segundos |
| IBIT/BTC y ETHA/ETH | Correlación y beta descriptivas en intervalos de cierre de sesión iguales | Al menos 60 pares; no demuestra adelanto ni causalidad; fuera de sesión no hay contexto de opciones vigente |

La lista de contratos ordena fricción por exposición delta. Muestra prima estimada en riesgo, coste de ida y vuelta y equilibrio al vencimiento. **No es un ranking de rentabilidad esperada.** Las griegas e IV proceden del snapshot del broker; no incluyen una marca temporal independiente verificable para cada cálculo.

El contexto cruza tres tipos de hipótesis: compra del subyacente frente a prima, compra de prima condicionada al subyacente y señal cripto con proxy de ETF. Ninguna se incorpora retrospectivamente a los ocho experimentos ni altera sus órdenes. Para convertir un filtro nuevo en estrategia hace falta un ensayo separado y registrado.

## Variantes nativas

| ID | Cambio respecto al control |
|---|---|
| C0 | Tendencia canónica de la configuración vigente |
| C1 | Régimen BTC de cuatro horas |
| C2 | Filtro de ventaja económica causal, frente a costes estresados |
| C3 | Régimen y filtro económico |
| C4 | C3 y trailing adaptable que conserva recorrido abierto |
| C5 | C4 y un parcial del 20% al alcanzar 2.5R netos estimados |
| C6 | C3 y salida obligatoria a las 72 horas |
| C7 | C4 y límite paciente de 60 segundos; sólo tras cancelación conciliada sin fill puede prepararse un fallback IOC |

En C7, cualquier fill parcial impide completar la compra con un segundo intento; se cancela el remanente y se protege el inventario real. Los permisos de los agentes vinculan el símbolo, plugin, señal, cantidad y plan exactos. Una respuesta ambigua no se reenvía.

El límite de 72 horas es propio de C6. Las otras variantes respetan `hold_hours`; cero permite continuar la tendencia. El tamaño compuesto conserva los límites del core y, bajo la política correspondiente, sólo incorpora beneficio realizado estimado. El compuesto amplifica resultados favorables y desfavorables; no crea la ventaja.

## Evidencia y presupuesto

La prueba utiliza entrenamiento previo de 365 días, purga de etiquetas no maduras, embargo mínimo de 72 horas, ocho meses de validación y tres meses finales congelados. No liquida posiciones al cambiar de mes ni reinicia el capital. El calentamiento exige historial adicional anterior al entrenamiento.

Las puertas por defecto requieren beneficio después de costes, mejora emparejada con bootstrap por bloques, Sharpe HAC ≥1.5, Sortino ≥2, profit factor ≥1.4, drawdown máximo ≤8%, muestra suficiente, estabilidad, estrés de costes 2× y DSR aproximado ≥0.95. No son objetivos garantizados. Los ensayos registrados del war room se acumulan; la memoria heredada de un periodo final ya observado bloquea su promoción. Investigaciones externas a estos registros pueden seguir siendo una fuente de selección retrospectiva.

La cobertura de quotes exige ≥99.5% y ningún hueco mayor de 90 segundos, junto con incrementos de catálogo válidos. Las colas, fills, slippage y comisiones de un replay siguen siendo estimaciones. El resultado no certifica un neto de cuenta.

Con una campaña activa, las revisiones GPT reservan coste **antes** de enviar. Esta mesa limita ocho IDs y USD20; además rigen los presupuestos diarios/mensuales y máximos de tokens del gateway. Un envío incierto conserva su reserva. Las respuestas son propuestas estructuradas sin autoridad para órdenes o ampliaciones de riesgo. Una caída de GPT no detiene las salidas.

La captura adicional es un archivo limitado a 100,000 eventos, con estado visible y exportación. Se detiene al alcanzar el límite o perder almacenamiento; no es un archivo histórico ilimitado. La instrumentación habitual de órdenes, decisiones y beneficio continúa por separado.

## Cloud y comprobación

La versión cloud incorpora el mismo control en su pestaña **War room · opciones y pruebas**. Reutiliza instalación, Render Blueprint, gateway, autenticación y secretos del paquete. El endpoint privado `/crypto/v1/warroom` queda detrás del control existente. Las nuevas dependencias de ejecución son módulos nativos del runtime.

Consulta **AUDITORIA_XXV_3.txt** y `evidence/` para las verificaciones. Se probaron código, worker, SQLite, HTTP y navegador con fixtures explícitos. El paquete no aporta una rentabilidad real demostrada ni una comparación acreditada con otros sistemas. Esta entrega de código no constituye una comprobación de despliegue o credenciales de tu servicio activo.

## XXV.3 R1 · optimizar parámetros en el loop

1. En **War room → Campaña y prueba**, sella una campaña nueva e importa los datos. Las campañas creadas desde esta UI esperan que elijas evaluar las ocho recetas o iniciar optimización; COLD no consume una de esas opciones por adelantado.
2. En **Optimización recursiva**, deja **16 ensayos / 60 segundos** y pulsa **Iniciar búsqueda · COLD ON**. El sistema explora y refina entrada, salida y ATR en lotes de cuatro. Es presupuesto de cálculo; no promete una ganancia ni completar todo dataset dentro de ese tiempo. La mesa debe tener al menos seis iteraciones disponibles para este perfil.
3. Observa estado, valores, neto estimado, ratios, drawdown y rechazos. **Pausar búsqueda** conserva el avance; **LiftOff** bloquea nuevos lotes y promociones. **Calcular un lote** permite una solicitud puntual. Los cálculos no consumen tokens GPT.
4. Una candidata debe superar sus puertas antes de abrir la única reserva final. Los primeros ocho meses son selección; sólo los tres últimos permanecen sin observar hasta ese momento. La contabilidad y la validación prospectiva aún deben completarse para justificar capital real.
5. Si pasa la reserva y el agregado, la opción existente de aplicar automáticamente la lleva a PAPER con cuenta plana. Si es rechazada, se conserva el plugin vigente. Los parámetros elegidos quedan ligados a la campaña y se aplican en el adaptador; el riesgo y configuración base del core permanecen fijados.

La ejecución 24/7 requiere actualizar el paquete en el servicio cloud. Descargar o abrir el HTML no actualiza un servidor ya desplegado. Lee **DICTAMEN_RENTABILIDAD_R1.txt** para el estado real del producto y sus prioridades económicas.
