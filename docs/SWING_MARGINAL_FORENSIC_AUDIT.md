# Auditoría forense marginal: swing técnico cuantitativo y meta matriz local

Fecha: 7 de noviembre de 2026. HEAD examinado: `4325422cc104a8d75384ec852b8ae5cbde07f24e`, rama `codex/remediation-framework`. Auditoría interna de código y evidencia; no revisión independiente. No se encontró AGENTS.md local; se aplicaron las instrucciones del proyecto proporcionadas en la conversación.

**Veredicto: no promover ni acreditar nivel 9.** Sí hay una dirección de mejora concreta: estimar el resultado ejecutable del setup, coordinar exposición y proteger capital frente a gaps, usando volumen y volatilidad como contexto. La evidencia disponible no demuestra que añadir capas, elegir activos más volátiles o aumentar RVOL mejore el crecimiento compuesto. El objetivo económico sigue siendo crecimiento logarítmico neto con supervivencia, no una puntuación ni el porcentaje de aciertos.

## 1. Qué se hizo ahora y qué sigue siendo histórico

Se verificaron 117 archivos por SHA-256 y se ejecutó una nueva extracción descriptiva de los cuatro libros técnicos corregidos existentes. Se generaron **133 celdas locales**, correspondientes a 112 instantes de decisión, y se enlazaron 268 registros de campañas con 92 identificadores de candidato financiado distintos. Los escenarios y políticas comparten mercados: ni 268 ni 92 constituyen una estimación del tamaño muestral independiente.

Las celdas contienen únicamente precios y volúmenes disponibles al decidir. Los resultados futuros están en `labels.json.gz`, con fecha de maduración, separados de `shadow_cells.json.gz`. No se recalcularon carteras con reglas nuevas, no se entrenó un modelo y no se consumió otro ensayo económico de H1–H3. Las nuevas variables de volatilidad son descriptores de auditoría, no un indicador validado ni un criterio añadido a la estrategia.

Se mantiene la procedencia: histórico retenido de Alpaca/SIP, capturado retrospectivamente, ejecución OHLCV modelada y costes supuestos. No son fills LIVE ni PAPER observados. La extracción no convierte la historia reutilizada en holdout nuevo. Los informes horario/cripto y CURRENT/A/B se revisaron como evidencia archivada; no se volvieron a ejecutar aquí.

## 2. Economía antes de añadir filtros

Capital inicial de cada cuenta: 20,000 USD, continuo. Periodo técnico: 11/03/2025–16/10/2026, 585 días naturales de costes fijos. Estas cuentas son comparadores separados; no pueden sumarse como una cartera.

| Cuenta archivada | PnL de precios después de fricción modelada | Dividendos | Comisión explícita | Fijos | Neto USD |
|---|---:|---:|---:|---:|---:|
| SIMPLE nominal | 325.07 | 3.97 | 5.92 | 585.00 | -261.88 |
| CONFIRMED nominal | 593.09 | 0.00 | 3.21 | 585.00 | +4.88 |
| SIMPLE estrés | 156.75 | 3.97 | 11.34 | 1,170.00 | -1,020.62 |
| CONFIRMED estrés | 488.13 | 0.00 | 6.08 | 1,170.00 | -687.95 |

Identidad verificada: PnL de precios + dividendos − comisión explícita − fijos = PnL neto. Spread/deslizamiento ya están incorporados en los precios de ejecución modelados: restarlos de nuevo sería doble conteo. Los dividendos son contabilidad, no una señal fundamental.

**Hallazgo económico prioritario.** CONFIRMED produjo 589.88 USD después de costes variables, apenas 1.0083 veces sus 585 USD de fijos. Su capacidad retrospectiva de pagar fijos fue 1.0083 USD/día nominal y 0.8240 USD/día en estrés, frente a supuestos de 1 y 2 USD/día. Son puntos de equilibrio descriptivos, no estimaciones de ingresos futuros ni autorización para borrar costes.

Reducir 80% la comisión explícita nominal manteniendo exactamente los mismos fills ahorraría sólo **2.568 USD**. Es una cota contable aislada, no un resultado de ejecución optimizada. Una reducción de órdenes puede cambiar nominal, riesgo, spread, selección y operaciones perdidas; no equivale automáticamente a reducir 80% todos los costes.

El resultado CONFIRMED sin su mayor ganador sería -175.06 USD nominal y -866.63 USD estrés. Es sensibilidad por sustracción, no replay con reasignación. La ventaja nominal frente a SIMPLE (+266.76 USD) pertenece a comparaciones ya inspeccionadas y no identifica por separado el valor causal de RVOL, confirmación de dos barras o momentum relativo.

## 3. Atribución por activo y volumen: lo que contradice la intuición

| CONFIRMED nominal | Campañas | Ganadoras / perdedoras | PnL de trading antes de fijos | RVOL10 mediano ganadoras | RVOL10 mediano perdedoras |
|---|---:|---:|---:|---:|---:|
| AAPL | 29 | 17 / 12 | +350.32 USD | 1.5813 | 1.8714 |
| MSFT | 18 | 8 / 10 | +239.56 USD | 1.3344 | 1.6537 |
| Cuenta conjunta | 47 | 25 / 22 | +589.88 USD | 1.4945 | 1.7335 |

No hay faltantes de RVOL en estas campañas. Las medianas agrupadas por resultado usan etiquetas futuras; **no sirven para escoger retrospectivamente un umbral**. El resultado impide justificar la regla simplista «más RVOL implica más seguridad» en esta muestra. Tampoco prueba que un RVOL alto sea perjudicial: la selección previa, activo, fecha, volatilidad y pocas observaciones pueden explicar la diferencia.

AAPL y MSFT aportaron ambos PnL de trading positivo, pero comparten exposición tecnológica. Estos importes no prueban que funcionen como carteras aisladas ni que diversifiquen el riesgo. No se asignan 585 USD de fijos a cada activo para después sumarlos, ni se omiten de la cuenta común.

**Salidas:** 18 de las 22 pérdidas nominales estuvieron antes en positivo, pero sólo 3 llegaron a +1R. Una protección que se active en +1R no explica cómo rescatar las otras 15; además puede cortar ganadores. Los picos son marks de cierre, no precios garantizados de liquidación. SIMPLE conserva un peor resultado de -6.139R: el stop no acota un gap a 1R. En CONFIRMED, 15 pérdidas STOP quedaron por debajo de -1R; ese conteo incluye fricción y no debe presentarse como 15 gaps.

## 4. Hallazgos del código y mejoras marginales prioritarias

| Prioridad | Hallazgo verificable | Consecuencia | Cambio propuesto y estado |
|---|---|---|---|
| P0 | Fijos consumen casi todo el margen nominal | Un ahorro pequeño de comisión no convierte la estrategia en robusta | Medir costes operativos efectivos y eficiencia por unidad de riesgo/capital; sin suprimir retrospectivamente los fijos |
| P1 / H3 | `virtual_ab.py` entrega al gate 30 retornos genéricos de tres días, aunque opera señal, stop 2% y máximo 72h | El retorno usado para admitir una compra no representa el payoff de esa política | Etiquetas condicionadas al mismo setup y salida, sólo maduras; abstención por falta de evidencia. Hipótesis pendiente |
| P1 / H3 | `virtual_net.py` exige que todas las celdas de un símbolo pasen; corrige por el total original de celdas | Añadir «capas» como celdas independientes endurece el rechazo sin crear información | Una celda de decisión por activo/setup; las capas son características y controles, no votos independientes. Contrato propuesto |
| P1 / H3 | Bootstrap de 1,000 réplicas, `alpha=.05/N`; con más de 50 celdas marca resolución de cola insuficiente | La meta matriz puede quedar bloqueada por diseño; no se soluciona bajando confianza | Controlar familia real, dependencia y resolución antes de elegir método; no forzar compras |
| P1 / H2 | Tamaño depende del stop; el salto nocturno puede excederlo | La exposición económica no está completamente representada por R | Presupuesto de gap con historia anterior y estrés fijo, mismo capital y límites. Hipótesis pendiente |
| P2 / H1 | Muchas pérdidas tuvieron beneficio transitorio; la mayoría no llegó a +1R | «Vender cuando esté verde» no es una política causal suficiente | Una protección causal predefinida, próxima ejecución disponible, daño a ganadores y coste incluidos. Hipótesis pendiente |
| P2 | Parcial = `floor(cantidad_original × .25)` | Con menos de 4 acciones no hay parcial | 2/47 campañas CONFIRMED nominales y 1/45 estrés afectadas. Mostrar el plan entero real antes de entrar; cambio de política aún sin probar |
| P2 | `MOMENTUM_BASE` exige impulso previo ≥30%, contracción y patrón; declara `NO_EXIT_REPLAY` | Un candidato de ese módulo no equivale a estrategia swing validada | Mantenerlo en investigación; no relajar 30% ni activarlo para aumentar frecuencia sin prueba registrada |
| P2 | Matriz resta posiciones/pending por símbolo, reserva secuencial y carece de reserva atómica | Dos activos correlacionados o dos motores pueden competir por el mismo presupuesto | Coordinación única de caja, exposición por grupo y recibos idempotentes antes de cualquier envío |

La corrección causal anterior de marks y cierres TIME se conserva. Esta auditoría no modifica ese motor congelado. Tampoco cambia los límites de 12% de exposición de admisión, 0.25% de riesgo de entrada/abierto, 2% de pérdida diaria, 8% de drawdown ni 72 horas naturales.

## 5. Meta matriz propuesta: composición por activo y horizonte

Recomendación de arquitectura: **una intención local neta por activo y setup**, con varias capas auditables. Generar veinte señales del mismo movimiento no justifica veinte órdenes ni veinte muestras de evidencia. Ninguna capa genera órdenes de broker por sí sola.

| Capa | Qué calcula o verifica | Salida necesaria para avanzar |
|---|---|---|
| Datos y mercado | Feed, calendario, sesión, splits, disponibilidad y edad | Prefijo válido y máscaras de faltantes |
| Contexto técnico | Tendencia de precios, momentum relativo, dirección y volatilidad | Estado observable; no probabilidad de ganar inventada |
| Participación | RVOL de la misma franja y mismo feed; denominador de 20 sesiones | Volumen comparable; no mezclar diario, 5m y 10m |
| Setup y gestión | Ruptura confirmada existente, entrada ejecutable posterior, invalidación, parciales enteros y vencimiento | Plan completo de la campaña, antes de comprar |
| Economía | Payoff de ese setup y política neto de costes; incertidumbre y daño por abstenerse | Evidencia suficiente y margen neto, no sólo acierto |
| Cartera | Caja, reservas, riesgo por gap, grupos correlacionados, cantidad y límite agregado | Reserva atómica única y nominal incremental |
| Ejecución | Cotización vigente, liquidez, tick, latencia, duplicados, pendientes y recibos | Una intención elegible; reconciliación tras fill, parcial o rechazo |

El reloj de evaluación y la frecuencia de órdenes son conceptos diferentes. Puede observarse cada barra cerrada de cinco minutos manteniendo decisiones swing espaciadas y una campaña de hasta 72h. No se requiere HFT. El diseño objetivo puede separar contexto D1, decisión H1 y ejecución con observaciones de 5m; esa ampliación temporal todavía es una propuesta, no un resultado probado por estas celdas.

Las salidas protectoras, la pérdida máxima y el vencimiento no deben esperar unanimidad del gate de entradas. Mantener intenciones de compra en local reduce envíos innecesarios, pero no protege una posición durante una caída de conexión. Una futura conexión al broker debe definir protecciones compatibles con su API, caducidad y reconciliación; no se activó ninguna aquí.

### Adaptación por clase de activo

| Clase | Selección técnica a investigar | Tratamiento necesario | Cobertura de esta entrega |
|---|---|---|---|
| Acciones / ETF sin apalancamiento | Momentum relativo + ruptura/base + volumen comparable + volatilidad contextual | Calendario de bolsa, gaps, liquidez, riesgo sectorial | Celdas AAPL/MSFT; XLK referencia. Sin generalización a todo el universo |
| BTC / ETH spot | Momentum de precios y volatilidad en reloj UTC | RVOL horario por día de semana predefinido, feed consistente, costes cripto, concentración común | Sólo revisión del replay archivado; no celdas nuevas ni validación |
| ETF apalancados / inversos | Señal en subyacente y ejecución en instrumento | Factor de exposición, rebalanceo diario, trayectoria, gaps y spreads | Sin validación en este banco; no se infiere multiplicar el retorno del subyacente |
| Opciones | Requieren payoff y datos propios | Spread, griegas, vencimiento, asignación y liquidez | Fuera de esta auditoría de campañas cash-share; no trasladar reglas de acciones |

La selección no debe maximizar volatilidad absoluta. Para estudiar crecimiento logarítmico tiene sentido estimar retorno neto por capital y su incertidumbre, con penalización de cola y covarianza entre posiciones. La aproximación `E[log(1+r)] ≈ E[r] − E[r²]/2` sólo vale para retornos pequeños; no reemplaza el replay ni modela adecuadamente por sí sola gaps extremos. No se ajustaron pesos ni se calcularon rankings de inversión con esta expresión.

## 6. Lo implementado: celdas locales, todavía sin validación económica

`quant/harpoon_quant/swing_meta_audit.py` calcula para cada candidato existente:

- RVOL10 con numerador, mediana de las mismas franjas de las veinte sesiones previas, máscaras y disponibilidad.
- Momentum direccional de 60 minutos y eficiencia del recorrido; conserva el momentum relativo a XLK de la regla existente.
- Volatilidad realizada de los primeros y últimos 30 minutos: raíz de suma de retornos logarítmicos al cuadrado, sin anualizar. El primer retorno de cada ventana parte de su apertura; los siguientes enlazan cierres. No incluye salto nocturno.
- Cada volatilidad se normaliza por su propia franja en veinte sesiones previas. El cociente «última media hora normalizada / primera media hora normalizada» describe expansión o contracción, sin confundir la estacionalidad de la apertura con un régimen nuevo.
- Referencias de entrada posterior, distancia al stop, targets existentes 1.5R/3R, parcial de 25% redondeado a entero y máximo 72h. Son referencias técnicas; precio y cantidad efectivos dependen del fill y del plan de calendario.

Las 133 celdas contienen observaciones completas bajo este contrato. No se eligió un umbral de expansión que rescate pérdidas conocidas ni se usó el descriptor para cambiar órdenes. El coste observado y el spread siguen desconocidos; no se rellenan con cero. La salida contiene `orders=[]`, `execution_allowed=false`, `entry_exit_profitability_validated=false` y `fundamental_inputs_used=false`. El estado de cartera es `NOT_RESERVED` y el grupo tecnológico es una referencia de concentración, no una covarianza estimada.

## 7. Literatura y costes externos: alcance real de la evidencia

Fuentes primarias revisadas el 07/11/2026:

1. [Alpaca: Crypto Spot Trading Fees](https://docs.alpaca.markets/us/docs/crypto-fees). El primer tramo publicado muestra 15 pb maker y 25 pb taker por lado. Una ida/vuelta taker ronda 50 pb de comisión antes de spread e impacto, con nominales comparables. Esto no determina la tarifa efectiva de una cuenta ni sustituye sus recibos. Swing reduce potencialmente rotación; no elimina el coste de cada ejecución.
2. [Moreira y Muir: Volatility Managed Portfolios](https://www.nber.org/papers/w22208). Documentan beneficios de reducir exposición cuando la volatilidad es alta en carteras de factores. Motiva investigar el tamaño ajustado por riesgo; no valida escoger los activos más volátiles ni estas entradas de 1–3 días.
3. [FINRA: Leveraged and Inverse Exchange-Traded Products](https://syndication.finra.org/content/lowdown-leveraged-and-inverse-exchange-traded-products). El objetivo diario de muchos productos no se conserva automáticamente durante varios días. La adaptación swing necesita modelar el instrumento y la trayectoria, no un multiplicador constante.
4. [Alpaca: Paper Trading](https://docs.alpaca.markets/us/docs/paper-trading). Su simulador declara omisiones como impacto, slippage por latencia y posición en cola. Una fase PAPER serviría para comprobar integración y recibos de simulación; no acredita economía LIVE.

No se atribuyen estrategias privadas a Citadel, Jane Street u otras firmas. La evidencia académica es contexto metodológico, no un certificado de estas reglas.

## 8. Ruta acotada para buscar una mejora real

No ampliar ahora el número de indicadores, activos apalancados ni combinaciones. Priorizar la conciliación del registro global y después el máximo de tres hipótesis ya definido: **H3, H2 y H1**, conservando los comparadores y presupuesto autorizados. H3 aborda primero la correspondencia entre la señal y su resultado ejecutable; H2 la supervivencia; H1 la devolución de beneficios y el coste de cortar ganadores.

La auditoría del presupuesto conserva 151 cuentas reservadas/documentadas provisionales frente al techo 128; aun liberando 20 reservas no usadas daría 131. La deduplicación no está certificada. Esta entrega no libera reservas ni ejecuta variantes nuevas. El margen para ensayos nuevos debe resolverse mediante conciliación verificable o una enmienda explícita, sin convertir ex post pruebas perdedoras en «no contadas».

Refutaciones que deben conservarse:

- H3: no mejora crecimiento logarítmico neto frente al gate vigente, o sigue sin evidencia suficiente; cero compras no demuestra equivalencia.
- H2: reducir cola por gaps cuesta demasiado retorno y empeora la utilidad neta con riesgo comparable.
- H1: las pérdidas evitadas no compensan ganadores cortados, costes, latencia y oportunidades perdidas.

Exigir cuenta continua de 20,000 USD, sin retiros ni resets, límites originales, coste fijo íntegro y nominal/estrés completos. Separar exploración reutilizada de una evaluación final realmente nueva. Mantener purga por maduración de etiquetas, margen registrado de 72h y bootstrap emparejado por días de cartera con 20,000 réplicas, bloques 5/20 si hay longitud suficiente y corrección por familia real. No se ejecutó otro bootstrap aquí: las nuevas variables no tienen una cartera de diferencias que validar.

Promover sólo a la siguiente validación si se superan conciliación/causalidad, crecimiento absoluto neto, ventaja frente al control y efectivo con límites inferiores ajustados, estrés, riesgo y sensibilidad al mayor ganador sobre datos nuevos. Hasta entonces «9» es una aspiración sin acreditación económica.

## 9. Reproducción y pruebas

```bash
PYTHONPATH=quant:tools OPENBLAS_NUM_THREADS=1 python tools/run_swing_marginal_audit.py --output-dir /tmp/harpoon_swing_audit_new
PYTHONPATH=quant:tools:quant/tests OPENBLAS_NUM_THREADS=1 python -m unittest quant.tests.test_swing_meta_audit quant.tests.test_evidence_scope quant.tests.test_forensic_features -v
python -m ruff check quant/harpoon_quant/swing_meta_audit.py tools/run_swing_marginal_audit.py quant/tests/test_swing_meta_audit.py
MYPYPATH=quant:tools python -m mypy --follow-imports=silent quant/harpoon_quant/swing_meta_audit.py tools/run_swing_marginal_audit.py
```

Dos extracciones finales: 0.33 y 0.45 segundos; cuatro archivos reproducibles idénticos por SHA-256. 32 pruebas aprobadas: 10 nuevas y 22 regresiones. Ruff en tres archivos y mypy en dos. Pruebas de prefijos ante mutación futura, datos tardíos, faltantes, splits, sesiones cortas, denominadores cero, dirección distinta de volatilidad, unión activo/instante y ausencia de órdenes incluso ante un setup positivo.

Protocolo: `research/swing_marginal_audit/protocol.json`. Evidencia: `evidence/swing_marginal_audit/{report.json,shadow_cells.json.gz,labels.json.gz,validation.json,sha256.json,delivery_sha256.json}`. El manifiesto de entrega excluye su propio archivo. No se ejecutó toda la suite del repositorio ni se probaron conexiones al broker.

**Limitación decisiva:** disponemos de una atribución reproducible y referencias técnicas locales, pero no de evidencia nueva que identifique el rendimiento de la meta matriz. Su valor económico sólo podrá medirse con el replay autorizado y posterior evaluación realmente nueva; esta auditoría no sustituye ninguno de los dos.
