# HARPOON: programa de I+D cuantitativa, presupuesto de planificación USD 5 millones

Documento interno de diseño y ejecución de investigación. Fecha de referencia:
2 de noviembre de 2026. Se supone USD, con horizonte de planificación de doce
meses desde un eventual inicio aprobado. No existe encargo, financiación,
contratación, aval o relación institucional con DARPA, Citadel, MIT, Caltech,
Nasdaq, Cboe, NYSE ni el Premio Nobel. Las asignaciones son estimaciones internas,
no cotizaciones ni compromisos de gasto. El presupuesto registrado reporta gasto cero.

## Misión y producto concreto

Investigar y construir un controlador probabilístico de cartera para swing de
24–72 horas UTC. Debe usar únicamente información disponible en cada decisión,
valorar posiciones existentes y operaciones nuevas, pagar costes completos y
poder abstenerse. La meta económica es crecimiento geométrico neto reproducible
bajo riesgo y capacidad realistas, no maximizar acierto o un backtest seleccionado.

Producto implementado en esta entrega: núcleo Python ejecutable de investigación
con contratos, modelo de trayectorias conjuntas, controlador de acciones,
supervisor de estado, segunda valoración Decimal, diario privado, evaluación
temporal y programa presupuestario verificable. No sustituye ni activa el
runtime de trading. Es el punto de integración shadow para una promoción futura.

## Presupuesto y responsabilidad

| Paquete | Asignación USD | Entregable y criterio de parada |
| --- | ---: | --- |
| WP0: gobierno, contratos y reproducibilidad | 450,000 | Inventario de hipótesis, versiones, licencias, cronología y contabilidad de ensayos; detener si no se reconstruye el baseline |
| WP1: trayectorias, estados y calibración | 1,100,000 | Probabilidades y distribuciones comparadas con referencias simples; abandonar modelos sin mejora incremental bajo evaluación registrada |
| WP2: control y asignación de capital | 1,150,000 | Decisiones financiadas sobre inventario, costes y cola; rechazar mejoras que dependan de capital duplicado o exposición distinta no controlada |
| WP3: verificación y ataques adversos | 850,000 | Comprobaciones separadas, fallos de mercado/ejecución y revisión de código; bloquear ante incoherencias o certificaciones irreproducibles |
| WP4: datos, convenciones, fills y reconciliación | 650,000 | Procedencia y derechos documentados, corporate actions y calendario suficientes, recibos de decisión/BBO/fill/fee enlazados |
| WP5: prueba prospectiva y revisión externa | 500,000 | Protocolo congelado, cuenta reconciliada y revisión efectuada por un tercero distinto del desarrollador |
| Contingencia controlada | 300,000 | Uso sólo mediante una aprobación real separada; no financia búsquedas retrospectivas ilimitadas |
| **Total** | **5,000,000** | **Registro de gasto actual: 0 USD** |

Las partidas cubren el trabajo de sus equipos, cómputo, ensayos y suministros
correspondientes; no se añaden honorarios o infraestructura nuevamente fuera
del total. Se requiere un plan de compras y personal con ofertas reales antes
de convertir estas asignaciones en obligaciones. El software no efectúa pagos.

`programme.json` es la fuente ejecutable del presupuesto. `validate_programme`
comprueba dominios, suma exacta, gasto reportado y dependencias. `evidence_gate`
comprueba presencia e integridad de archivos; un hash no determina que un
resultado científico sea correcto, que un auditor sea independiente ni que
exista autorización de gasto. Por eso sus salidas no autorizan promoción ni pagos.

## Hitos y puertas de avance

| Puerta | Mes orientativo | Evidencia necesaria |
| --- | ---: | --- |
| G0 | 1 | Baseline sellado, reproducción, registro de ensayos e inventario de derechos sobre datos |
| G1 | 3 | Contratos causales, etiquetas ambiguas auditadas, evaluación temporal purgada y comparación predictiva sencilla |
| G2 | 5 | Inventario, lotes finales, caja, llenados parciales, invariantes y comparación del controlador con salidas fijas |
| G3 | 7 | Datos/convenciones con cobertura suficiente, fills y costes observados, reconciliación de cuenta, halts y reinicios |
| G4 | 10 | Protocolo prospectivo, crecimiento neto con incertidumbre frente a CASH y controles, estrés y registro global de búsqueda |
| G5 | 12 | Revisión externa realizada, resultados reproducibles y aprobación explícita de los límites operativos |

El código y las pruebas nuevas constituyen evidencia de ingeniería para partes
de G1/G2; no declaran aprobadas esas puertas completas. G3–G5 no se cumplen por
construir un modelo, aprobar tests o marcar una casilla. El objetivo interno
“nivel 9” permanece sin acreditar.

## Arquitectura implementada y límites matemáticos

1. **Contratos y cronología.** Un estado USD con inventario completo declarado,
   cuotas por lote, BBO y recepción, estado de mercado, capacidad disponible,
   costes explícitos y calendario de 72 horas. No hay conversión FX implícita.
2. **Modelo condicional conjunto.** Casos originales de OHLC por activo y hora,
   normalizados a la unidad de entrada; splits y dividendos se representan
   separadamente. Labels conocidos antes de calibrar; features conocidos antes
   del inicio; IDs y fechas originales únicos y ordenados. Distancia de
   Mahalanobis con covarianza regularizada, cuarenta vecinos como máximo y
   mínimo de veinte casos compatibles con el calendario. No es un modelo
   fundacional ni presume superioridad frente a una referencia uniforme.
3. **Estados y deriva.** Contexto con retornos, volatilidad y extensión de
   tendencia; abstención ante deriva o soporte efectivo insuficiente. La
   volatilidad rolling es una referencia inicial. GARCH, estados latentes o
   redes tensoriales sólo se justificarían por una mejora contrastada.
4. **Recorrido y primeros pasos.** Frecuencias condicionales de objetivo, stop,
   expiración y ambigüedad. Cuando una vela toca ambas barreras, el orden no
   se inventa: se conservan límites de identificación. Esos límites no son
   intervalos de confianza de probabilidad futura.
5. **Control de cartera.** Acciones discretas entrar, aumentar, mantener,
   reducir, cerrar o esperar. Se enumera una malla registrada, se valora la
   continuación protectora y se ejecuta conceptualmente sólo la acción actual.
   Una llamada posterior con un estado nuevo permite replantear la decisión.
   No se resuelve exactamente un Bellman global ni se afirma estabilidad
   financiera del sistema cerrado.
6. **Objetivo.** Peor escenario de crecimiento logarítmico de patrimonio bajo
   una penalización HAC de incertidumbre de la media, con financiación y cola.
   Al abrir desde efectivo se exige además que la media neta inferior modelada
   cubra la infraestructura común. No se interpreta la penalización como
   cobertura estadística certificada o corrección global por selección.
7. **Costes y riesgo.** BBO actual, fee, slippage y fijo por orden separados;
   coste compartido una sola vez en el horizonte común de 72 horas. No se
   financian compras con ventas propuestas sin confirmar. Se prueban coste
   nominal, doble coste y doble coste con gap adverso de 0.5%; ese conjunto es
   una hipótesis registrada, no una región de confianza calibrada.
8. **Supervisor.** Recalcula lotes, caja, financiación, concentración, estado
   del mercado y deadline. Permite solicitar reducción de un incumplimiento
   existente sin certificar falsamente que las patas no llenadas sean seguras.
   No promete que un stop evite pérdidas por gaps o falta de liquidez.
9. **Segunda valoración.** Un auditor escalar con Decimal vuelve a calcular
   pagos, cola, reservas y puertas de ventaja de la propuesta elegida sin
   llamar al rollout del optimizador. Es una implementación separada del
   mismo autor: no una auditoría externa ni prueba independiente de optimalidad
   de toda la malla o de autenticidad de la fuente.
10. **Persistencia.** Diario privado SQLite con versiones idempotentes,
    fingerprints de código/modelo/configuración y cadena de hashes. Una campaña
    observada no puede cambiar su apertura/deadline ni reemplazarse silenciosamente
    por otra sobre el mismo símbolo. La cadena es integridad local, no atestación
    externa de datos del broker.

## Fuente de las referencias y qué se adopta realmente

| Referencia primaria | Principio adoptado | Alcance que no se afirma |
| --- | --- | --- |
| [DARPA Assured Autonomy](https://www.darpa.mil/research/programs/assured-autonomy) | Aseguramiento en diseño y durante operación | Programa de referencia ya concluido; no encargo ni aprobación DARPA |
| [MIT: Robust and Stochastic Control](https://underactuated.mit.edu/robust.html) | Incertidumbre explícita y control robusto | No demostración Lyapunov ni garantía de comportamiento de mercados |
| [Caltech CDS110](https://www.cms.caltech.edu/academics/courses/cds-110) | Realimentación y control predictivo | No revisión ni participación de Caltech |
| [Premio de Economía 2003](https://www.kva.se/en/news/the-prize-in-economic-sciences-2003/) | Volatilidad variable y no estacionariedad | No calificación Nobel ni que una desviación de precio deba revertir |
| [Citadel EQR](https://www.citadel.com/careers/career-perspectives/inside-eqr-what-it-means-quantitative-researcher/) | Integración investigación, construcción y ejecución | No acceso a estrategias o sistemas propietarios |
| [Two Sigma](https://www.twosigma.com/businesses/investment-management/) | Hipótesis y decisiones con costes y riesgo | No metodología privada ni resultados comparables a esa firma |
| [Nasdaq calendarios](https://nasdaqtrader.com/Trader.aspx?id=Calendar) y [halts](https://www.nasdaqtrader.com/Trader.aspx?id=TradeHaltCodes) | Horas explícitas, cierre anticipado, halt/resume | No feed live Nasdaq ni licencia implícita |
| [NYSE horas/calendarios](https://www.nyse.com/trade/hours-calendars) | Sesión real, festivos y subastas diferenciadas | No simular una apertura/cierre como fill asegurado |
| [Cboe especificaciones](https://www.cboe.com/markets/us/options/support/technical/) y [datos](https://www.cboe.com/data/market-data-services/document-library) | Contratos de fuente e instrumentación de opciones | El motor nuevo spot no ejecuta opciones/futuros ni omite ejercicio/asignación |

La normalización de calendario y halts funciona sobre documentos suministrados
con timestamps y hashes. No inventa una conexión a esas bolsas. Una reanudación
sin hora conocida no se supone ocurrida. Las opciones/futuros se rechazan en
este motor mientras no exista valoración y lifecycle suficientes; las funciones
legacy previas no se eliminan. WP4 incluye ese trabajo como alcance condicionado,
no una funcionalidad anunciada como operativa.

## Validación del programa, no sólo del código

- Etiquetas: orden temporal, disponibilidad, madurez, purga de ventanas solapadas,
  OHLC ambiguo y corporate actions.
- Predicción: puntuación Brier con identificación parcial contra referencia
  uniforme sobre los mismos análogos; revisión por régimen, no sólo media global.
- Decisión: comparación con CASH, salidas fijas y riesgo/exposición emparejados;
  balance de costes y capital del patrimonio completo, sin sumar cuentas repetidas.
- Ejecución: decision→BBO→order→fill→fee→inventario→caja→patrimonio, incluyendo
  parciales, rechazos, cancelaciones, halts y correcciones. No hay sustitución de
  fills reales por OHLC para aprobar G3.
- Robustez: errores de reloj, datos incompletos, cambio de versión, input repetido,
  inventario no modelado, presión de costes, shocks y límite de cómputo.
- QA: checksum, análisis estático, tipos, pruebas proporcionales, reconstrucción
  de modelos/datos y benchmark con alcance y entorno declarados.
- Promoción: evidencia prospectiva no usada para elegir la propuesta, control de
  multiplicidad, incertidumbre, auditor distinto y aprobación humana registrada.

No se inicia otra búsqueda después de un resultado adverso sin registrar una
hipótesis nueva y su presupuesto. Se conserva el primer fallo de construcción
del laboratorio y su corrección de serialización; no se ocultan ni se cuentan
como éxitos. Las mejoras retrospectivas pequeñas no se venden como rentabilidad.

## Estado de entrega

El detalle ejecutado está en [README del núcleo](../../FRONTIER_CORE_RD.md) y
los artefactos bajo `evidence/frontier`. Las fuentes del histórico ya existían;
no se descargaron fills ni datasets nuevos. El presupuesto es un marco para
completar y revisar este trabajo, no la afirmación de haber consumido cinco
millones o de haber terminado un programa institucional de doce meses.
