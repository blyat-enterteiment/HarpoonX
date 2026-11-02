# Gate económico neto y pareado de HarpoonX

Este módulo convierte curvas **C0, Ridge y SVR** en un dictamen reproducible de investigación. Verifica el protocolo previo, reconstruye los retornos netos desde patrimonio continuo, comprueba costes, flujos, inventario y riesgo, y calcula incertidumbre pareada por bloques de sesiones. No entrena modelos, no busca parámetros, no incrementa el contador histórico y no envía órdenes.

El ejemplo entregado es **enteramente sintético** y tiene fechas ficticias. Sus números positivos sólo ejercitan las ramas del programa. Su resultado correcto es `VENTAJA_NO_DEMOSTRADA`, aunque pase el cálculo estadístico. No reproduce ni sustituye la simulación histórica negativa ni representa una cuenta real.

## Funciones reales

| Función | Entrada y acción | Resultado |
|---|---|---|
| `seal_protocol(protocol)` | JSON sin hash; produce una copia con SHA-256 canónico | Integridad local; no equivale a preregistro |
| `register_protocol(protocol, journal_path, registered_at=None)` | Valida el protocolo, usa reloj local y añade una entrada con hash del registro anterior | Recibo local persistido; nunca modifica `optimizer.sqlite3` |
| `artifact_reference(path, root)` | Calcula hash de bytes de un archivo dentro de una raíz | `{path, sha256}` |
| `evaluate_gate(protocol, evidence, artifact_root=...)` | Valida artefactos y curvas; calcula el contraste registrado | Informe `HARPOON_ECONOMIC_GATE_1` con causas de bloqueo/rechazo |
| `paired_block_bootstrap(log_returns, protocol)` | Remuestrea conjuntamente sesiones de las tres carteras | Estimaciones y límites inferiores aproximados o `INCONCLUSIVE` |
| `verify_gate_report(report, protocol, evidence, artifact_root=...)` | Repite la evaluación de los mismos datos y exige igualdad exacta | Verificación local reproducible; permisos externos siempre falsos |

La API de registro sólo permite fijar un reloj ficticio si `data_scope` es `SYNTHETIC_ENGINEERING_ONLY`. En cualquier otro caso usa el reloj de sistema. Eso evita una opción trivial para retroceder la fecha desde la API; no autentica el reloj del sistema ni a su administrador. El registro tiene un bloqueo de escritor y escritura con `fsync`; una caída puede dejar un `.lock` visible que requiere comprobar el estado antes de recuperarlo.

## Ejecución del ejemplo

Desde el directorio `quant`, con las dependencias del proyecto instaladas:

```bash
python -m harpoon_quant.economic_gate \
  --protocol examples/economic_gate/synthetic_fixture/protocol.json \
  --input examples/economic_gate/synthetic_fixture/input.json \
  --output examples/economic_gate/synthetic_fixture/report.json \
  --artifact-root examples/economic_gate/synthetic_fixture

python -m unittest tests.test_economic_gate -v
```

Para crear otro fixture de ingeniería en un directorio nuevo:

```bash
python -m examples.economic_gate.make_fixture --output /tmp/harpoon_gate_fixture
python -m harpoon_quant.economic_gate \
  --protocol /tmp/harpoon_gate_fixture/protocol.json \
  --input /tmp/harpoon_gate_fixture/input.json \
  --output /tmp/harpoon_gate_fixture/report.json \
  --artifact-root /tmp/harpoon_gate_fixture
```

El generador no sobrescribe un registro existente. No borrar un registro real para reusar el comando. La CLI devuelve 0 si pudo ejecutar los validadores de software y 2 si la entrada quedó bloqueada. **El código de salida 0 no significa ventaja financiera ni autorización de operación.** Leer `dictamen`, `financial_blockers`, `rejection_reasons` y `statistics.status`.

## Contrato del protocolo

El ejemplo `protocol.json` es el contrato completo y ejecutable. Registra, antes del acceso a la prueba final:

- Identidad, moneda y unidades USD, capital inicial, universo, hashes de código, política, riesgo y costes.
- Horizonte de hasta 72 horas; límites de drawdown y exposición; tolerancia predefinida a exposición adicional frente a Ridge.
- Particiones temporales ordenadas, purga y embargo, lista exacta de sesiones con principio y final. Quitar una sesión de las tres curvas sigue siendo detectado aunque las curvas restantes estén perfectamente pareadas.
- Mejora mínima positiva en log crecimiento por sesión frente a Ridge, y comparación adicional contra C0. C0 representa no abrir posiciones con sus costes aplicables; no se elimina del informe por ser negativo.
- Número de intentos, conservación del piso histórico de **23**, longitudes de bloques, mínimo de sesiones y bloques completos, semilla, repeticiones, alfa familiar y resolución mínima de cola.

Los límites del fixture son ejemplos numéricos para regresión. No se han estimado para la cuenta, ETF o acciones reales. Un protocolo nuevo debe justificarlos con datos de desarrollo y recursos autorizados; cambiarlos tras mirar la prueba final la convierte en datos de selección.

El hash del protocolo, la entrada del registro, el hash de la cadena y la fecha de primer acceso deben coincidir. Se rechaza un protocolo posterior al primer acceso declarado, una prueba final ya utilizada, un contador reiniciado o un número de intentos distinto al historial. Estos controles prueban coherencia **local**. Reescribir de forma coherente archivos, anclas y fechas no puede detectarse sin un ancla externa confiable. No se afirma una evaluación ciega externa.

## Curvas y contabilidad

Cada una de las tres políticas tiene su propia curva, efectivo e inventario final. Todas usan el mismo universo, capital de partida, calendario, flujos externos, política de ejecución, límites y modelo de costes. La unidad de inferencia es **la cartera conjunta en una sesión**, no cada operación individual ni cada activo como una observación independiente.

Una fila incluye:

```text
session_id, start_at, end_at, data_available_at, source_hash
equity_start_usd, equity_pre_flow_usd, external_flow_usd, equity_end_usd
gross_marked_pnl_usd, fees_in_equity_usd, operating_costs_in_equity_usd
gross_exposure_fraction
return_net  # opcional: si se proporciona, tiene que coincidir con el cálculo
```

`equity_end_usd` es patrimonio **económico neto**, con todos los costes asignados ya descontados. Se comprueba:

```text
E_final - E_inicial - flujo = PnL_bruto_marcado - fees - costes_operativos
```

Los costes no se descuentan de nuevo al calcular el retorno. Valores nulos, negativos no permitidos o no finitos bloquean la entrada; no se convierten en cero. Cada comienzo debe coincidir con el final de la fila anterior. El patrimonio final incluye posiciones abiertas valoradas al bid, pasivos y costes pendientes; no basta el PnL realizado.

Para el alcance admitido de cero o un flujo por intervalo, con una marca observable inmediatamente anterior:

```text
1 + r_neto = (E_antes_del_flujo / E_inicio) * (E_final / (E_antes_del_flujo + flujo))
g = promedio(log(1 + r_neto))
PnL_neto = E_final - E_inicial - suma(flujos)
```

Un flujo exige su hora, hash de la marca y `flow_count: 1`. Múltiples flujos dentro de un intervalo necesitan un agregador con todas las marcas intermedias; este contrato inicial los bloquea. No se inventan marcas preflujo a partir de precios al cierre. Si el patrimonio llega a cero o menos, se registra insolvencia y no se recorta el retorno para hacer posible un logaritmo.

Alcance económico inicial: cuenta USD, posiciones largas de acciones/ETF sin apalancamiento, inventario inicial vacío y posiciones finales explícitas. Shorts, derivados, margen y un inventario inicial no vacío requieren extender y verificar la contabilidad antes de utilizar este gate. El rechazo de esos casos evita simular pasivos que no están modelados.

Los gastos externos deben asignarse de forma consistente a una curva económica virtual y a su recibo contable; no se confunden con aportaciones. La reconciliación con la cuenta real y los costes externos debe preceder a la exportación. No hay cálculo fiscal: los resultados son antes de impuestos.

## Incertidumbre y comparación

Para cada sesión se conserva el vector:

```text
[log(1+r_SVR), log(1+r_SVR)-log(1+r_Ridge), log(1+r_SVR)-log(1+r_C0)]
```

Se toman bloques contiguos con envoltura circular. Los mismos índices se aplican a las tres métricas. Así no se destruyen los movimientos comunes de mercado al comparar SVR y Ridge. Longitudes y dependencia se fijan previamente y se evalúan todas las longitudes registradas.

La asignación de alfa es:

```text
alfa_por_extremo = alfa_familiar / (intentos_totales * numero_de_bloques_registrados * 3)
```

`numero_de_bloques_registrados` significa número de **longitudes alternativas**, no cuántos bloques se sortean en una réplica. Se usa Bonferroni porque no exige independencia entre las variantes; es conservador. No se aplica un supuesto DSR sin sus entradas. Esta asignación tampoco compensa intentos no declarados ni da cobertura finita exacta a un bootstrap aproximado.

Se exige que todos los límites inferiores superen simultáneamente cero para crecimiento absoluto, el mínimo económico para la mejora sobre Ridge y el mínimo registrado sobre C0. También deben ser positivos el PnL absoluto y el crecimiento puntual, y deben cumplirse los controles de riesgo y evidencia. Perder menos, cambiar el número de operaciones, incrementar exposición o pasar tests de software no basta.

El cálculo es inconcluso si faltan sesiones/bloques, si una métrica no tiene variación, o si `repeticiones * alfa_por_extremo` queda por debajo del mínimo registrado. El piso de 20 observaciones de cola es una decisión numérica de ingeniería; no es una garantía estadística. El número efectivo de observaciones independientes permanece `null`; no se presenta `n/bloque` como muestra independiente estimada.

La distribución debe ser razonablemente estacionaria y los bloques cubrir dependencia temporal material. La longitud óptima no se deduce automáticamente del horizonte de una posición. Pruebas de cambios de régimen y sensibilidad pueden refutar esa hipótesis. Si no puede defenderse, el cálculo es diagnóstico y el protocolo debe declarar la limitación.

Se limita el trabajo a 500.000 réplicas y 100 millones de vectores de sesión remuestreados; el uso de memoria se divide en lotes. Sobrepasar ese presupuesto deja el resultado inconcluso. No se eleva el presupuesto para forzar una aprobación. `verify_gate_report` vuelve a calcular sobre los mismos datos; usarlo al cargar/cambiar artefactos, no en cada tick ni en la ruta de orden.

## Paridad e integración operacional

`parity_receipt` requiere un archivo con hash, código fuente con hashes verificables y checks con valores esperados/observados. Un `policy_parity_verified: true` en la entrada no sirve como sustituto.

Si la entrada incluye `coordinator_input: {path, sha256}`, el gate ejecuta **el verificador local fijo** `tools/coordinator_replay.cjs` contra ese JSON y el recibo. El llamador no puede elegir otro ejecutable. El verificador vuelve a ejecutar el coordinador en modo offline, compara acciones, posiciones, costes y hashes. Tiene un timeout de 30 segundos. La canonicalización se realiza con Node para respetar exactamente la serialización numérica JS del recibo. Ninguna conexión a un broker está habilitada por esta acción.

El recibo debe conservar su alcance. La paridad del coordinador nativo C0 no prueba la paridad de predicciones Ridge/SVR. El replay actualmente entrega `financial_acceptance_allowed: false`; las predicciones precalculadas no tienen paridad predictiva certificada. Por tanto, **esta versión no transforma su recibo en un candidato financiero**, aunque su reejecución sea idéntica. Los vínculos de coste, riesgo, código y política con las curvas también deben verificarse.

Prueba ejecutable de esa conexión, tras compilar el runtime TypeScript y desde `quant`:

```bash
python -m examples.economic_gate.bind_coordinator_example \
  --output examples/economic_gate/coordinator_fixture
```

El comando vuelve a producir el recibo del coordinador real y lo verifica por reejecución. No entrena predictores ni modifica escenarios. Es una prueba sintética de integración cuyo dictamen financiero esperado sigue siendo negativo a la promoción. Los recibos se deben regenerar después de cambiar los archivos fuente que vinculan; que un recibo antiguo falle tras ese cambio es comportamiento correcto.

La exportación observacional exige precios realmente recibidos, disponibilidad temporal, archivos contables de las tres políticas y trazas de señales, órdenes, fills, cancelaciones y descartes. `HARPOON_ECONOMIC_ACCOUNT_RECEIPT_1` es el contrato normalizado que vincula `curve_hash`, `terminal_hash`, `cost_hash`, el ledger subyacente `HARPOON_NET_LEDGER_1` y su traza de ejecución. Los formatos por sí solos no autentican a un proveedor. Los hashes conservan trazabilidad e integridad local; el informe identifica esa limitación.

No hay exportación financiera completa observada en este ejemplo. La ausencia exacta de cada recibo se conserva en `financial_blockers`; no se rellenan los huecos con datos sintéticos. Antes de habilitar candidaturas futuras habrá que completar y verificar ese adaptador con datos reales y la paridad predictiva correspondiente.

## Dictámenes y permisos

| Situación | Dictamen |
|---|---|
| Datos incompletos, protocolo inconsistente, falta de incertidumbre suficiente, datos sintéticos o recibos no elegibles | `VENTAJA_NO_DEMOSTRADA` |
| Insolvencia, riesgo candidato excedido, PnL neto no positivo o efecto puntual por debajo del mínimo registrado | `RECHAZADO` |
| Todas las condiciones económicas, estadísticas y de artefactos completas y verificadas dentro del alcance | `CANDIDATO_PARA_VALIDACION_FORWARD` |

Incluso el último resultado mantiene `execution_allowed:false`, `liveApproved:false`, `financial_approval:false` y `financial_acceptance_allowed:false`. Ser candidato permite proponer una validación futura dentro de los modos y límites ya autorizados. No activa LIVE ni cambia el control SVR de sombra existente.

## Pruebas incluidas

Las regresiones cubren: hashes y cadena manipulados; protocolo posterior a observaciones; reloj ficticio usado fuera de un fixture; holdout consumido; reinicio de contador; unidades y universo diferentes; capital reiniciado; sesiones eliminadas; retornos declarados incorrectos; costes nulos o contados dos veces; inventario terminal omitido; insolvencia; controles con riesgo distinto; financiación fuera de alcance; aumento de exposición; falta de marcas preflujo; muestra, dependencia o precisión insuficientes; varianza degenerada; shocks comunes preservados por el bootstrap; presupuesto computacional; paridad autodeclarada, código alterado y entradas etiquetadas “observadas” sin observaciones.

## Base metodológica

- Politis y White, *Automatic Block-Length Selection for the Dependent Bootstrap*, 2004, sección 3.1: [artículo original alojado en Duke](https://public.econ.duke.edu/~ap172/Politis_White_2004.pdf). Sustenta el remuestreo circular y las condiciones de dependencia; no valida los parámetros del fixture.
- NIST/SEMATECH, [Bonferroni’s method](https://itl.nist.gov/div898/handbook/prc/section4/prc473.htm). Sustenta repartir el error familiar entre comparaciones; no certifica la cobertura de intervalos bootstrap mal especificados.
- SciPy, [documentación oficial de bootstrap](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.bootstrap.html). Explica remuestreo pareado, límites percentiles, memoria por lotes y problemas de distribuciones degeneradas. Aquí se implementan bloques explícitos; no se usa un remuestreo independiente de trades.
