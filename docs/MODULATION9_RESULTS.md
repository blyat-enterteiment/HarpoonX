# HarpoonX: resultados forenses de Modulation9

## Decisión

**NO_GO.** No se acredita factibilidad económica bajo el contrato registrado ni la etiqueta interna N9-S. Ninguna de las 36 recetas tiene una media neta positiva en ninguna de las diez combinaciones mundo/coste durante desarrollo. La receta fijada también tiene medias netas negativas en las diez combinaciones finales. Esto rechaza estas configuraciones bajo este modelo; no prueba imposibilidad de cualquier otra estrategia.

El universo, los costes, las semillas y las reglas quedaron registrados antes de medir. El código económico se congeló en `d301fe53d1a57efe87b6fd91da5a599c6ba91d3d`; la selección se publicó en `489ba39e8aee3f78a751c50c569a45e8bec155a9` antes de abrir las semillas finales. Las correcciones estáticas previas quedaron registradas y no utilizaron resultados económicos.

## Alcance ejecutado

Se ejecutaron 3.120 cuentas de desarrollo y 2.560 finales: 5.680 en total. Cada cuenta comienza con 20.000 USD y conserva capital compartido entre dos activos sintéticos. Los beneficios de cuentas independientes no se suman como si constituyeran una cartera. Hay 126 sesiones de evaluación, equivalentes en este calendario a 176 días cobrados. Los símbolos, precios y volúmenes son sintéticos; no representan observaciones históricas de AAPL/MSFT ni prueban resultados con criptomonedas u opciones.

Se exploraron tres entradas, cuatro salidas y tres tamaños de riesgo; 36 configuraciones incluyen una réplica exacta del control CURRENT, excluida de selección como mejora. Hay ocho semillas de desarrollo por mundo y 64 finales, emparejadas entre políticas y costes. El final conserva una sola receta y tres controles. Las 5.680 cuentas no son 5.680 observaciones independientes de rentabilidad.

## Selección y frontera

La regla minimax fijó **QUALITY_RUNNER72_R0625**: filtro de calidad, salida runner hasta 72 horas y riesgo de 0,0625% del equity por campaña. Sobre el capital inicial, el presupuesto de riesgo planeado es 12,50 USD; gaps y fricción pueden causar una pérdida realizada mayor. Su score de desarrollo es −0,0001057174373 de log-crecimiento diario, aproximadamente −1,05717 pb/día. El score negativo ya impide promoción, independientemente del final.

Las 36 recetas satisfacen el filtro observado de riesgo del desarrollo; nueve pertenecen a la frontera de Pareto entre crecimiento nominal medio TREND/WEAK y percentil 95 de drawdown bajo estrés en los cinco mundos. Es una frontera relativa dentro de un catálogo finito y con resultados negativos. CASH con los mismos costes fijos supera el score minimax de la receta elegida, aunque no participa en el ranking de recetas. La referencia contable de efectivo sin plataforma e interés cero permanece separada de CASH.

## Prueba reservada: receta fijada

Medias de 64 trayectorias por mundo y escenario. Drawdown es el peor observado entre esas trayectorias, no una cota teórica.

| Mundo | Neto nominal USD | Retorno nominal | Peor DD nominal | Neto estrés USD | Retorno estrés | Peor DD estrés |
|---|---:|---:|---:|---:|---:|---:|
| TREND | -125.83 | -0.629% | 1.225% | -319.99 | -1.600% | 2.105% |
| WEAK | -182.21 | -0.911% | 1.335% | -362.02 | -1.810% | 2.196% |
| FALSE | -191.86 | -0.959% | 1.517% | -374.30 | -1.871% | 2.417% |
| NULL | -178.10 | -0.891% | 1.313% | -362.87 | -1.814% | 2.206% |
| GAP | -155.58 | -0.778% | 1.779% | -341.45 | -1.707% | 2.238% |

En TREND nominal, CURRENT pierde 124,99 USD y SIMPLE 72,05 USD: la receta no los supera económicamente. Su percentil 95 de drawdown es 1,0213%, frente a 1,5660% y 2,2645%, respectivamente. En WEAK estrés, la receta pierde 362,02 USD, frente a 416,36 USD de CURRENT y 466,24 USD de SIMPLE, con percentiles 95 de drawdown de 2,1069%, 3,0782% y 3,7224%. Las diferencias de drawdown son descriptivas; no se registró un contraste inferencial específico sobre ellas.

Los contrastes emparejados sí apoyan mejora relativa en WEAK estrés frente a CURRENT y SIMPLE, pero no rentabilidad absoluta ni superioridad frente a CASH en ese entorno. No hay mejora global confirmada sobre todos los controles.

## Costes: explicación del resultado

Nominal incluye spread completo de 2 pb, slippage de 2 pb por lado, comisión de 0,005 USD por acción/lado y 1 USD por día de calendario. Estrés duplica esos valores. Son supuestos del banco; no tarifas verificadas de un broker. Spread y slippage ya están incorporados en los fills y no se descuentan dos veces.

El coste fijo suma 176 USD nominales y 352 USD bajo estrés. En TREND nominal, las operaciones de la receta aportan 50,17 USD después de fricción y comisiones; la resta del coste fijo produce −125,83 USD. En WEAK nominal, las operaciones ya aportan −6,21 USD antes del coste fijo. Por tanto, el problema no se explica únicamente por infraestructura cara. Esta descomposición contable no resimula tamaños ni decisiones con otros costes.

El hurdle propuesto de 1 pb diario logarítmico equivale a 1,7756% en 176 días, unos 355,12 USD netos sobre 20.000. Además de las fricciones variables, habría que absorber 176 USD fijos: aproximadamente 531,12 USD de contribución antes de ese coste fijo. Elevar el tamaño no crea una ventaja y cambia el riesgo y las restricciones; no se aprobó ese recurso.

## Riesgo e inferencia

La receta no registra infracciones de los gates observados: peor drawdown 2,41675%, peor retorno por sesión −0,696673%, permanencia máxima 71 horas 55 minutos y conciliación final válida. Los límites del contrato son 8%, 2% y 72 horas. La admisión de exposición/riesgo no es un rebalanceo continuo y no garantiza pérdidas máximas ante gaps. En 91 de las 640 cuentas finales del candidato hubo exposición marcada superior al 12% por movimientos de precio; el máximo fue 12,3535%. Esto no incumple el contrato de admisión registrado, pero impide afirmar que el 12% se respeta continuamente.

Cero infracciones en 64 trayectorias de un mundo/coste todavía permite una probabilidad superior unilateral del 95% de aproximadamente 4,573% para una infracción en una trayectoria comparable, bajo el mismo generador. No es una estimación de riesgo de mercado.

El bootstrap usa 20.000 remuestreos de trayectorias completas y 40 endpoints, con ajuste Bonferroni unilateral de 0,05/40. La cobertura finita es aproximada. Los límites inferiores absolutos en TREND y WEAK son negativos bajo ambos costes. El control NULL no presenta límite inferior positivo absoluto ni frente a CASH; esto no demuestra ausencia universal de sesgo. Los fills interpolados de OHLC siguen siendo una aproximación adicional a los precios martingale.

Fallan cinco criterios económicos: score positivo de desarrollo; límite nominal superior a 1 pb/día; límite bajo estrés positivo; mejora emparejada sobre todos los controles; y beneficio después de restar la mejor campaña de cada cuenta. Faltan además dos condiciones operativas ya declaradas antes de medir: ejecución completa con parciales de entrada/rechazos/caídas/impacto e integración completa del coordinador de la matriz virtual.

## Hallazgos del motor y procedencia

El trailing heredado puede sobrescribir una actualización pendiente antes de recibirla, dado que la barra se publica un segundo después de su cierre. PROTECT48 y RUNNER72 preservan actualizaciones en una cola; NATIVE72 y FAST24 conservan la semántica heredada como controles congelados. La comparación mezcla reparación del mecanismo y parámetros de salida; no identifica causalmente una mejora atribuible sólo a estrategia.

La reproducción del banco archivado conserva 127 artefactos económicos, 108 cuentas y 2.978 fills sin diferencias. Su perfil de riesgo y sus generadores son distintos del estudio actual; no deben combinarse como una misma muestra. Sus incumplimientos de determinados plazos planeados de 48 horas no deben presentarse como incumplimientos de 72 horas.

El CI específico pasa 60 pruebas Python, 68 pruebas Node, Ruff y mypy. El conjunto heredado mantiene bloqueos de procedencia: el control evidence_scope espera el hash anterior de `runtime30/profit8_replay.js`, mientras PROFIT8 ya tenía una divergencia entre su freeze retenido y el HEAD base. No se cambian hashes congelados para ocultar esas diferencias. Véase `evidence/modulation9/qa/legacy_ci_diagnosis.json`. La revisión separada de resultados reconstruyó caja con Decimal en las 5.680 cuentas, 93.850 campañas y 134.660 fills de salida, con error terminal máximo de 3,85e-12 USD. Recalculó el bootstrap mediante conteos de remuestreo y reprodujo el ranking y la frontera. Es una revisión interna con implementación separada, no una auditoría externa.

El desarrollo tardó 33,52 segundos y el final 106,28 segundos con cuatro workers en este entorno. Son tiempos del experimento sintético; no benchmarks de latencia de trading.

## Uso y siguiente criterio de decisión

`docs/MODULATION9_FRAMEWORK.md` contiene las reglas y comandos. `research/modulation9/protocol.json` y `registration.json` fijan el contrato y fuentes. Los informes completos por grupo y los 40 endpoints están en `evidence/modulation9/*_analysis/report.json`. El archivo descargable de trayectorias contiene los 360 gzip y sus SHA256; su índice y checksum están en `evidence/modulation9/raw_data_archive.json`.

La decisión es mantener esta receta como referencia diagnóstica de control de pérdidas, sin promoción. El orden técnico siguiente es separar la reparación del trailing, completar ejecución y procedencia, y sólo entonces registrar hipótesis nuevas y datos no reutilizados. El final ya leído no puede convertirse de nuevo en validación independiente. Esta entrega no programa trabajo posterior, no conecta un broker y no acredita producción ni rentabilidad real.


### Verificación independiente de la aritmética

Después de extraer las trayectorias en la raíz del repositorio, el auditor lee los archivos y conserva todas las evidencias:

```bash
python tools/audit_modulation9_results.py
```

Este programa fue escrito después de la medición para comprobar cantidades, caja, costes, ranking, frontera y bootstrap. Su código no forma parte de las estrategias registradas; no genera mercados ni vuelve a seleccionar parámetros. No reproduce independientemente toda la secuencia intrabar de valoraciones del motor.
