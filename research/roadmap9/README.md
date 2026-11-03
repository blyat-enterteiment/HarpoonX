# Roadmap 9: cierre del estudio histórico acotado

**Resultado: seis recetas rechazadas y ningún candidato retenido para validación futura.** Se implementaron y midieron las tres hipótesis y seis configuraciones completas registradas. Las doce cuentas candidatas terminaron con pérdida tanto nominal como bajo estrés. Este resultado cierra la búsqueda autorizada; no se eligió un ensamblado de los mejores fragmentos ni se relajaron límites.

Los resultados son históricos modelados sobre datos ya utilizados en investigaciones anteriores. No acreditan rentabilidad real, ejecución observada ni un nivel 9. El calendario de evaluación abarca **404 sesiones, del 11 de marzo de 2025 al 16 de octubre de 2026**, equivalentes a **585 días naturales** con el gasto operativo definido en este nuevo protocolo.

## Resultados de las seis recetas

Cada cuenta empieza con 20.000 USD y continúa sin reinicio entre los tramos históricos llamados VALIDATION y TEST. Esas etiquetas heredadas no convierten el periodo posterior en una muestra virgen. Los controles se calculan en cuentas separadas con el mismo capital y límites; no se suman sus resultados para fabricar una cartera.

| Receta | Neto nominal USD | Neto estrés USD | Campañas nominal / estrés | Decisión |
|---|---:|---:|---:|---|
| H1, horario a 24 horas | −535,50 | −1.170,00 | 1 / 0 | Rechazada |
| H1, selección fija entre 24/48/72 horas | −585,69 | −1.167,27 | 3 / 2 | Rechazada |
| H2, aceptación del gap | −189,51 | −782,16 | 9 / 9 | Rechazada |
| H2, gap y confirmación sectorial | −262,73 | −859,98 | 6 / 6 | Rechazada |
| H3, salida completa por valor de continuación | −407,08 | −1.062,23 | 52 / 52 | Rechazada |
| H3, reducción parcial por valor de continuación | −463,41 | −1.102,39 | 46 / 46 | Rechazada |

H1 y H2 tampoco alcanzan el mínimo registrado de 20 campañas por escenario. Los filtros redujeron fuertemente la exposición. Por eso una comparación de PnL aislada no identifica alpha incremental a riesgo equivalente.

| Control fijo | Neto nominal USD | Neto estrés USD | Campañas nominal / estrés |
|---|---:|---:|---:|
| Continuación residual con refit causal común | −463,42 | −1.086,06 | 45 / 45 |
| Referencia de precio/volatilidad a 24 horas | −585,00 | −1.170,00 | 0 / 0 |
| CASH con la misma infraestructura modelada | −585,00 | −1.170,00 | 0 / 0 |
| Continuación original con modelo histórico estático | −54,42 | −701,41 | 60 / 60 |

CASH es el programa sin posiciones y con su gasto operativo compartido. No representa el rendimiento de un depósito de efectivo. La continuidad original mantiene su identidad como comparador; el modelo residual actualizado de las seis recetas es una especificación distinta, fijada antes de medir.

La continuación original aporta 530,58 USD antes del gasto común en nominal. El nuevo gasto, 1 USD por día natural, suma 585 USD y deja −54,42 USD. Bajo estrés, el nuevo replay completo aporta 468,59 USD antes de 1.170 USD de gasto. Ese último aporte no debe confundirse con el resultado archivado bajo otra trayectoria de gastos: el gasto modifica patrimonio y lotes posteriores, de modo que hay que repetir toda la cuenta y no sólo restar una constante al resultado antiguo.

## Qué se implementó

El panel usa los 124.182 registros originales de cinco minutos de AAPL, MSFT y XLK reconstruidos desde 80 blobs Git verificados. El dataset reconstruido coincide exactamente con el SHA256 admitido:

`5546035f58a04255b35091191cd750bd3d86075380a8aed0c258edbff6cee530`

Se obtuvieron 6.162 filas de características. Los objetivos de precio a 24, 48 y 72 horas se descomponen en log retorno nocturno e intradiario; el residuo máximo de la identidad numérica fue cero. La apertura siguiente se usa como precio modelado de ejecución y etiqueta futura, nunca como dato conocido para la entrada o el tamaño.

El modelo es ridge con lambda 10, incertidumbre de la media mediante HAC por sesión y cinco retardos, y ventanas de hasta 126 sesiones ya maduradas. Un refit ocurre al primer instante de decisión que dista al menos 120 horas del anterior. El modelo y sus últimas etiquetas deben cumplir 168 horas. La calibración predictiva usa las últimas 20 sesiones de TRAIN, con purga de etiquetas y al menos 60 sesiones anteriores para ajustar; una MSE superior a 1,25 veces la referencia cero provoca abstención. La guardia no certifica cobertura frecuentista de los límites inferiores del ridge.

Las características incluyen retorno de apertura, retorno relativo al sector, gap dividido por volatilidad, volatilidad previa, tramo nocturno e intradiario anterior y fracción de sesión transcurrida. No se suman los retornos previstos a 24/48/72 horas como oportunidades independientes. Los modelos de componentes utilizan el mismo diseño; su suma coincide con el pronóstico total y se conserva la incertidumbre del total, sin suponer independencia entre componentes.

El asignador de estas seis recetas es el sizing causal nativo con reservas compartidas. Conserva riesgo por operación y abierto de 0,25%, máximo bruto y por nombre de 12%, límite diario de 2% y drawdown de 8%. **El nuevo optimizador robusto de cartera no está integrado en estas mediciones.** Su eventual implementación o prueba unitaria separada no acredita una contribución a estos resultados ni autoriza una séptima receta.

El fork aditivo del replay conserva el motor original. Introduce horizontes registrados, salida causal por valor y gasto por día natural. H3 sólo aplica el pronóstico de 24 horas cuando su vencimiento cabe dentro del plazo original de la campaña; en caso contrario conserva la protección nativa. No resuelve un problema de Bellman global. El auditor recalcula el plazo del calendario y comprueba el reloj original, los horizontes de 24/48/72 horas y el deadline de H3. La mayor duración observada desde la decisión fue 71,999722 horas.

## Qué dicen los diagnósticos

En los pronósticos emitidos del periodo evaluado, la MSE del modelo de horario fue superior a la referencia de retorno cero en los tres horizontes, aproximadamente 6,0%, 9,4% y 10,5%. Es una comparación descriptiva posterior sobre historia reutilizada, no un nuevo procedimiento de selección.

La evaluación de incertidumbre usa 20.000 remuestreos de sesiones compartidos entre cuentas, bloques registrados de 5 y 20 sesiones, semilla 319 y 120 endpoints descriptivos con ajuste local de multiplicidad. Ninguno de los 96 límites inferiores de diferencias pareadas frente a los cuatro controles fue positivo. Los remuestreos no crean observaciones originales y el historial global de investigación sigue incompleto; no se afirma corrección global suficiente para inferencia confirmatoria.

La atribución de H3 separa el efecto de salida de la política completa:

| Atribución sobre las mismas 45 entradas, cantidades y precios iniciales del control | Nominal USD | Estrés USD |
|---|---:|---:|
| Cambio de PnL al cerrar completamente por valor | +86,81 | +62,40 |
| Cambio de PnL con reducción parcial | −53,20 | −67,45 |

Este pareado no incluye reutilización de capital ni pretende ser otra rentabilidad de cartera. Las cuentas completas sí incluyen el efecto de cerrar antes, liberar reservas y aceptar otras entradas; por eso contienen 52 o 46 campañas y sus diferencias no se atribuyen íntegramente a la salida. La pequeña mejora pareada de H3 total no compensa la pérdida global ni permite promover la receta.

Se publican exposición media y máxima, rotación, sesiones con posiciones, contribuciones por activo, concentración y PnL por tramo. La contribución nocturna usa las acciones efectivamente mantenidas antes de cada apertura. El residuo intradiario incluye precios intradiarios y ejecución modelada; no se etiqueta como alpha intradiario puro. Se mantienen comisiones, dividendos y gasto común por separado para reconciliar el neto.

## Costes y límites de evidencia

Nominal aplica spread de 2 bps, deslizamiento de 2 bps por lado, 0,005 USD por acción y lado y gasto común de 1 USD por fecha UTC natural. Estrés duplica esas cantidades. Son supuestos registrados de este experimento de acciones. No son tarifas verificadas de una cuenta, BBO ejecutable, profundidad ni fills reales. Las fechas `availableAt = cierre de vela + 1 segundo` son modeladas, no recibos originales de mercado.

La muestra contiene dos acciones supervivientes y un ETF sectorial que las incluye. No se certifica un universo libre de sesgo de supervivencia, una referencia de mercado con exposición efectivamente emparejada ni capacidad real. Las ramas de subasta auténtica, contexto Cboe y cripto carecen aquí de los datos requeridos; no se inventaron desde OHLCV. Tampoco existen nuevas observaciones prospectivas, revisión externa o autorización de broker en este estudio.

La conciliación independiente en Python verifica inventario, cantidades, comisiones, derechos a dividendos, reservas, caja, gasto, continuidad, crecimiento compuesto y plazos de las 20 cuentas. Los precios de fill y las marcas proceden del replay nativo modelado: no se presenta esta conciliación como observación ni revaloración independiente de cada fill.

## Registro, incidente y reproducción

Las seis recetas, sus dos escenarios y 29 bindings de código/datos/configuración/plan quedaron registrados antes de los nuevos resultados. El presupuesto documentado pasa de 53 a 65 mediciones reservadas de un límite de 128. Ese contador no convierte en completo el historial anterior.

Después de la ejecución se detectó una anomalía del archivo de registro: el recibo emitido indicaba 11 resultados, mientras que el archivo leído después tenía diez, faltando ambos resultados H3 parcial. Los doce START estaban presentes y los doce resultados financieros existían. **La causa no está establecida.** No se borró la discrepancia ni se modificaron código congelado, recetas, PnL o presupuesto. Se conservaron ambos estados y se añadieron únicamente los dos RESULT faltantes, ligados a los mismos archivos y hashes. El registro reconciliado contiene doce resultados; su cabeza permanece estable durante la reproducción independiente.

Los artefactos de este incidente están en `evidence/roadmap9/research_registry_incident/`. `registry_verification.json` conserva el recibo original de once; el estado reconciliado está en `registry_reconciled_verification.json`. La cadena local no constituye una atestación externa del tiempo de registro.

Se realizó **una reproducción exacta completa**: veinte cuentas con hashes gzip idénticos, mismos modelos y señales, mismas estadísticas y pares H3. No consumió nuevas recetas ni nuevas observaciones. El recibo está en `evidence/roadmap9/research/exact_reproduction.json`.

El comando soportado para verificar este paquete conservado es:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONPATH=quant python -B \
  tools/verify_roadmap9_research.py evidence/roadmap9/research \
  --output /tmp/harpoon_roadmap9_exact_reproduction.json
```

`tools/run_roadmap9_research.py` conserva exactamente el código registrado. No se debe usar para sobrescribir los recibos de este estudio: su escritura inmutable del antiguo `registry_verification.json` detectaría correctamente la diferencia entre once y doce después de la conciliación. El verificador anterior reproduce el estudio sin reescribir ese registro ni ocultar el incidente. Una repetición exacta no constituye un nuevo ensayo de una política distinta.

## Archivos principales

- Especificación: `research/roadmap9/protocol.json` y `recipes.json`.
- Resumen completo: `evidence/roadmap9/research/results.json`.
- Auditoría de libro: `evidence/roadmap9/research/accounting_audit.json`.
- Modelos: `evidence/roadmap9/research/models.json.gz`.
- Controles, candidatos y hashes: `evidence/roadmap9/research/reports.json` y los veinte archivos `.json.gz` referidos.
- Registro reconciliado: `evidence/roadmap9/research/registry.jsonl` y `registry_reconciled_verification.json`.
- Reproducción: `evidence/roadmap9/research/exact_reproduction.json`.
- Reconstrucción original: `evidence/roadmap9/data_reconstruction.json`.

El siguiente experimento económico no está abierto por este cierre. Las seis recetas quedan rechazadas para promoción; investigar otra especificación requeriría un protocolo y presupuesto explícitos y evidencia futura adecuada.

## QA y alcance del tipado

Los diez tests nuevos de investigación pasan, incluyendo mutaciones futuras, purga de etiquetas, calibración limitada a TRAIN, caducidad, splits, deadlines, equivalencia del fork sin extensiones y conciliación del gasto por día natural. Ruff pasa en los dos módulos de investigación, sus tests y los cuatro scripts nuevos. Mypy pasa en `forecast.py` y `research.py`.

La comprobación estática ampliada detecta nueve errores en dos scripts ya congelados: `audit_roadmap9_results.py` reutiliza un nombre de variable para una lista y luego valores numéricos en bucles distintos; `run_roadmap9_research.py` reutiliza un nombre primero para `Path` y después para cadenas, y su comprobación runtime de valores opcionales mediante `require` no sirve a mypy para estrechar el tipo. Esos mensajes no revelaron un error de ejecución en la conciliación y reproducción completa, pero **mypy de todos los scripts no pasa**. Se conserva ese límite de calidad estática y el código medido, sin alterar su identidad después de observar resultados. Un arreglo de tipos futuro deberá preservarse como revisión de ingeniería separada y no atribuirse retrospectivamente a este estudio.
