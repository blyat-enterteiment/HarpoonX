# Veredicto económico y reparación de cronología

Trabajo sobre HEAD `8642b30adf281c1208e82bbf85229e2e2aed82a6`, rama `codex/remediation-framework`. La comprobación remota no encontró un AGENTS.md en raíz y no se encontró uno local; se aplicaron las instrucciones proporcionadas en la conversación. El análisis forense original se reprodujo con igualdad SHA-256 de sus cuatro artefactos de datos.

**Veredicto:** conservar la reparación de medición. **No promover la estrategia. H1, H2 y H3 no se ejecutaron por presupuesto global sin conciliar.** No se infiere que esas hipótesis sean falsas. La falta de una prueba nueva y de costes/fills observados sigue impidiendo acreditar rentabilidad.

## Resultado medido ahora

Se ejecutó el replay original congelado y el corregido con los mismos datos, señales, cantidades, costes y capital continuo. Se auditaron doce cuentas: seis controles y sus seis reproducciones corregidas. Los seis controles coincidieron íntegramente con los libros archivados. Los resultados siguientes son reproducciones de políticas existentes, no nuevos resultados de H1–H3.

| Cuenta técnica, USD | Control nominal | Corregido nominal | Control estrés | Corregido estrés |
|---|---:|---:|---:|---:|
| SIMPLE | -261.88 | -261.88 | -1,020.62 | -1,020.62 |
| CONFIRMED | +4.88 | +4.88 | -687.95 | -687.95 |
| Efectivo con plataforma | -585.00 | -585.00 | -1,170.00 | -1,170.00 |
| Efectivo sin plataforma, referencia determinista sin intereses | 0.00 | 0.00 | 0.00 | 0.00 |

| Hipótesis solicitada | Nominal | Estrés | Estado |
|---|---|---|---|
| H1, protección causal del beneficio | No medido | No medido | Bloqueada por presupuesto |
| H2, presupuesto de pérdida por gap | No medido | No medido | Bloqueada por presupuesto |
| H3, gate condicionado al setup | No medido | No medido | Bloqueada por presupuesto |

Se reprodujeron además las ocho cuentas horarias y las seis de matriz purgada: los informes coincidieron con los archivados. El horario conjunto conserva -250.688715 / -670.026733 USD. CURRENT/A/B conserva 316 celdas y cero compras por cuenta; -365 / -730 USD por coste fijo supuesto. Esto es reverificación, no una nueva prueba fuera de muestra. El script `economic_verdict.py` dejó de informar erróneamente que A/B no estaba implementado; distingue el informe purgado archivado de una ejecución de ese comando.

## Qué corrige el cambio

Antes, una valoración de la barra previa podía llegar en `end+1s` y quedar seguida por un cierre TIME conocido en `end`. El último mark del array no necesariamente tenía la última hora de disponibilidad; `profit8KnownAt` podía demorar un segundo la liberación de reservas por ese mark tardío.

La función `terminalTimeline` conserva los marks anteriores al recibo terminal y reemplaza los simultáneos/posteriores por la liquidación conocida. Rechaza desorden no explicado entre marks no terminales. Si el fill intrabar se conoce un segundo después de ejecutarse, conserva ese retraso; no adelanta el conocimiento del fill. No cambia precios, cantidades, fees, targets, stops ni órdenes. Se aplica a campañas trazadas PROFIT8 y mantiene el contrato legado sin opciones.

| Efecto | Resultado |
|---|---|
| Marks tardíos no terminales eliminados | 140 en cuatro replays; no son 140 sucesos independientes |
| Inversiones temporales restantes | 0 |
| Liberaciones de reserva corregidas | 140, un segundo antes que la disponibilidad artificial anterior |
| Cambios en ejecuciones e inventario de órdenes | 0 |
| Cambios en decisiones de entrada/cantidades | 0; sólo cambia `modeledCloseKnownAt` en los estados afectados |
| Diferencia de curvas de patrimonio y PnL | 0 |
| Máximos de valoración recalculados | 6 registros de campañas entre cuatro replays |

Ejemplo: AAPL del 17/10/2025 tenía máximo nominal 69.265 USD; ahora 68.79 USD. La operación siguió ganando 68.79 USD. El caso SIMPLE del 05/08/2025 pasa de máximo 148.0919 a 147.59 USD y conserva ese mismo PnL. Son correcciones de extrema reportados, no operaciones rescatadas ni dañadas económicamente. No se seleccionó una salida usando esos máximos.

Se mantienen visibles los excesos de exposición por movimiento de mercado. Por ejemplo, CONFIRMED nominal alcanza exposición marcada aproximada 12.614%, frente a un límite de admisión 12%. El motor limita la entrada; no se afirma que rebalancee continuamente para impedir todo exceso posterior. No se elevaron límites ni apalancamiento.

## Conciliación y costes

CONFIRMED nominal: 593.09 USD de PnL de precios ya después del spread/deslizamiento y redondeo modelados, menos 3.21 USD de comisión explícita, más cero dividendos y menos 585 USD de fijos = **4.88 USD**. En estrés: 488.13 - 6.08 - 1,170 = **-687.95 USD**. Spread y deslizamiento están incorporados en los fills; restarlos otra vez duplicaría costes. No hay recibos que permitan presentarlos como costes realmente pagados al broker.

La auditoría Decimal con precisión 50 reconcilió caja, inventario, dividendos y reservas de las doce cuentas. Los controles técnicos conservan 20,000 USD iniciales, composición continua, cantidades enteras, reservas compartidas entre AAPL/MSFT, límite de 72 horas naturales desde la decisión y cuatro no-fills modelados en CONFIRMED nominal. Son fills OHLCV: no acreditan cola de ejecución, profundidad, ejecuciones parciales de entrada ni latencia real. Los parciales de salida sí están en el libro.

La fuente técnica declara ALPACA_PROXY/SIP con capturas retrospectivas, no recibos originales del mercado. Se validan los contratos de disponibilidad del modelo y el calendario suministrado; no se certifica que esos datos hubieran llegado con esa latencia en vivo. Las pruebas incluyen gaps, sesiones cortas, datos faltantes, límites, dividendos tras parciales, splits no modelados y rechazo de anticipación. El fichero forense original y las fixtures sintéticas siguen separados de esta evidencia histórica modelada.

## Estado observable y estadísticas

El tensor de entrada 133×12×7 y sus hashes originales permanecen reproducibles. Se añadió una exportación de **12,381 estados de 92 campañas CONFIRMED**, nominal y estrés. Son dos escenarios de los mismos mercados, no 92 observaciones independientes.

Cada estado incluye PnL de liquidación estimado/R con costes de salida modelados, máximo conocido hasta ese instante/R, devolución conocida/R, cambio de log(1+RVOL10), retorno relativo al precio sectorial conocido al decidir, tiempo hasta el deadline, cantidad conocida y coste de salida/R. RVOL conserva numerador, mediana de veinte franjas equivalentes y faltantes. Los ajustes sectoriales por split usan sólo eventos efectivos hasta la barra observada. La falta de cotización ejecutable aparece como null/false; no se fabrica un spread observado. Los costes fijos permanecen en la cuenta, sin atribución arbitraria a campañas.

Se ejecutaron 20,000 réplicas bootstrap emparejadas, semilla 319, bloques circulares de 5 y 20 sesiones bursátiles. Todas las políticas y costes comparten los mismos índices de muestreo. La curva diaria es por sesiones; los costes de fines de semana se acumulan en la siguiente valoración de cuenta. Se usan 24 endpoints registrados y nivel unilateral local 0.05/24. Es diagnóstico sobre historia ya reutilizada, no inferencia selectiva global ni validación nueva.

Los **16 límites inferiores relevantes de crecimiento absoluto y ventaja frente al efectivo con plataforma son negativos**. Los ocho endpoints de diferencia corregido-control son exactamente cero porque se verificó igualdad de las curvas; no prueban equivalencia general de estrategias.

CONFIRMED nominal: retorno +0.0244%, drawdown por eventos 1.7332%, media de la peor cola del 5% de sesiones -0.1650%. En estrés: retorno -3.43975%, drawdown 4.2350%, cola -0.1742%. Quitar descriptivamente el mayor ganador deja -175.06 y -866.63 USD. El informe JSON incluye turnover, exposición ponderada por tiempo, duración, contabilidad y referencias; no suma resultados de distintas carteras como si compartieran capital.

Para una futura prueba se fijó un efecto mínimo de 1% de crecimiento logarítmico anual y potencia objetivo 80%. No existe una estimación defendible de tamaño muestral para H1–H3 mientras sus diferencias pareadas no se hayan estimado en entrenamiento autorizado. Se declara esa limitación; no se inventa una potencia a partir de varianza cero de la reparación. No se reservó ni consumió un holdout nuevo. Los ensayos antiguos llamados TEST siguen siendo exploración reutilizada.

## Bloqueo del presupuesto

Se siguió la unidad del último protocolo: cuentas política/escenario, incluidos sus controles. No se aumentó el techo ni se liberaron reservas automáticamente.

| Concepto | Cuentas |
|---|---:|
| Última reserva declarada | 119 |
| Multiasset8 fuera de esa cadena de reservas | 6 |
| Swing8 fuera de esa cadena | 8 |
| MACD30 fuera de esa cadena | 6 |
| Matriz sin purga | 6 |
| Matriz purgada | 6 |
| Total provisional reservado/documentado | **151** |
| Reserva PROFIT8 documentada como no usada | 20 |
| Estimación incluso si se liberara esa reserva | **131** |
| Techo | **128** |

El 131 es un recuento provisional, no una certificación del historial global: sigue pendiente conciliar posibles controles equivalentes y la procedencia completa del saldo importado. Los protocolos ya declaran `global_history_complete=false`. No se cambió la regla de conteo después de ver resultados para abrir cupo. `new_measurements_allowed=false` bloquea H1–H3; sus resultados son null, no cero ni pérdidas inferidas.

Este bloqueo se deriva del techo y la comprobación previa exigidos por el encargo. Se completó el trabajo independiente autorizado: reparación, reproducción, conciliación, estado causal y veredicto sobre controles existentes.

## Archivos y reproducción

```bash
PYTHONPATH=quant:tools OPENBLAS_NUM_THREADS=1 python tools/run_causal_integrity.py --output-dir /tmp/harpoon_causal_new
PYTHONPATH=quant:tools:quant/tests OPENBLAS_NUM_THREADS=1 python -m unittest quant.tests.test_causal_integrity quant.tests.test_forensic_features quant.tests.test_technical_swing quant.tests.test_technical_swing_replay -v
node --test tools/replay_chronology_test.cjs tools/profit8_replay_test.cjs
```

Para reproducir además las referencias horarias y cripto archivadas:

```bash
PYTHONPATH=quant:tools OPENBLAS_NUM_THREADS=1 python tools/run_compound_swing.py --output-dir /tmp/harpoon_compound_new
PYTHONPATH=quant:tools OPENBLAS_NUM_THREADS=1 python tools/run_virtual_ab.py --purged --output-dir /tmp/harpoon_virtual_new
```

El directorio debe ser nuevo. El comando carga el original congelado por SHA-256, reproduce ambos motores en procesos separados y genera los libros, auditoría Decimal, comparación, curvas, estados, hashes y tiempos. La congelación está en `research/causal_integrity/protocol.json`; el original se conserva comprimido en la misma carpeta. Los artefactos finales están en `evidence/causal_integrity/`. No se sobrescribieron las evidencias originales.

Se ejecutaron 33 pruebas Node y 24 Python, Ruff, mypy y comprobación de tipos del nuevo normalizador JavaScript. El manifiesto y la validación registran dos reproducciones completas y tiempos del host. Esto es revisión propia y pruebas internas, no auditoría externa ni autorización de trading.
