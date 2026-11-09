# FWN9 M11 Fase 9L — puente de recibos nativos, caja común y checkpoint incremental

**Dictamen: puente nativo de ingeniería focal PASS; N9-S NO_GO.** Se implementó una conexión de lectura entre el **resultado real del código `replayFundedPortfolio`** y la cuenta compartida `fwn9_p9k_fault_matrix_r2.cjs`. Se contrastaron los compromisos nativos, el reloj `knownAt`, los recibos de entrada/salida e IOC NO_FILL, caja terminal y comisiones. Las salidas siguen siendo precios **modelados OHLC**, no fills observados ni rentabilidad real.

## 1. Implementación fáctica sin placeholders

- `runtime30/fwn9_p9l_native_bridge.cjs`: obtiene el objeto de `replayFundedPortfolio`, examina **todas las señales proporcionadas** y distingue `REFUSED_BEFORE_ENTRY`, `MODELED_CAMPAIGN` y `MODELED_IOC_NO_FILL` sin inventar estados. Para cada reserva comprobada contra el libro nativo, reconstruye el compromiso original usando precio IOC, cantidad y riesgo. Los eventos `QUOTE`, `ADMIT`, `ENTRY_FILL`, `EXIT_FILL` y `ENTRY_NO_FILL` se ordenan por `knownAt`. Las cotizaciones se derivan de `causalPriceLookup` de la fuente original y exigen `sourceAvailableAt <= decisionAt`.
- El mismo adaptador ejecuta `FaultMatrix.apply()`, reutilizando el libro de reservas original de HarpoonX, verifica aceptación y cantidades, audita el libro nativo P9H en las decisiones admitidas y exige paridad con el reloj P9J. Verifica a nivel **terminal** equity, fees e inventario/reserva cero. Las diferencias de caja en decisiones intermedias se registran explícitamente, sin equiparar `cashPoolAt` del motor nativo con caja física autofinanciada.
- `tools/fwn9_p9l_checkpoint.cjs`: journal acotado y persistente de **evidencia offline**, cadena hash SHA-256, ID único, reintentos idénticos idempotentes, rechazo de evidencia conflictiva, escritura temporal `wx` + `fsync` + cambio de nombre atómico y lectura de verificación. Se probó la reapertura desde **otro proceso Node**, no sólo otra instancia de objeto. Sus hashes detectan corrupción casual, pero **no** prueban autenticación externa contra una reescritura íntegra maliciosa ni durabilidad de una instalación distribuida.
- `tools/fwn9_p9l_accountant.py`: aritmética **Decimal-60 independiente** del source trader, sumando compras, ventas, comisiones y costes calendario desde los recibos de ingeniería. No importa la implementación de la cuenta 9K para verificar el neto.
- El gate `holdoutGate` devuelve `WAIT_OBSERVED_COMPLETED_OPPORTUNITIES`, `execution_allowed:false` y `optimizerEligible:false` para todo replay `HISTORICAL_MODELED_OHLCV`. Esto es un **bloqueo funcional probado**, no un placeholder de optimización ni una afirmación de que el panel observado ya esté disponible.

## 2. Resultados y registros adversariales

| Evidencia | Resultado |
|---|---|
| [Primera CI 42453903221](https://github.com/blyat-enterteiment/HarpoonX/actions/runs/42453903221) | FAILED después de 12/12 tests: `cmp` comparó tiempos variables del log TAP en vez del JSON de auditoría |
| [R2 42454005934](https://github.com/blyat-enterteiment/HarpoonX/actions/runs/42454005934) | FAILED después de 12/12 tests, auditor Decimal-60, Ruff y mypy PASS: workflow buscó `git_blobs` en protocolo correctivo, no en el padre |
| [R3 42454100111](https://github.com/blyat-enterteiment/HarpoonX/actions/runs/42454100111) | **SUCCESS**: 12/12, comparación determinista de `P9L_AUDIT`, Decimal-60, Ruff, mypy estricto y 47 SHA-256 M9 |
| [CI general R4 42454216680](https://github.com/blyat-enterteiment/HarpoonX/actions/runs/42454216680) | **SUCCESS**: gate P9L obligatorio, gates P9I–P9K, 1.062 pruebas HEAD y 12 archivos históricos de tests reconstruidos por linaje |

La fixture nominal reutilizada (no muestra estadística nueva) registra **dos campañas modeladas**, **diez eventos ordenados** y **ocho fechas calendario**: patrimonio terminal **19.990,390 USD** desde los recibos y desde `replayFundedPortfolio`, neto **−9,610 USD** incluyendo 8 USD de coste fijo. El ajuste de `profit8` no se recalibró para conseguir un resultado favorable. Es conciliación económica, **no alpha**.

Pruebas negativas: alteración del riesgo o cantidad de reserva, pérdida de disposición de señal, alteración de cantidad de salida, cambio de fee o gross original, corrupción del journal, colisión de ID y reetiquetado `OBSERVED` de datos modelados. Cualquier fallo detiene el puente; no autoriza trading.

## 3. Alcance no acreditado; próximos gates

El valor técnico de 9L es conectar **rutas ejecutadas del código nativo** con el libro 9K para un catálogo pequeño, en vez de alimentar la matriz con un tape artificial propio. **No está demostrada la paridad universal de todas las trayectorias ni de las decisiones intermedias bajo M9**, ni la integridad/ejecutabilidad externa de los fills OHLC; no se abrió una nueva búsqueda económica.

Para convertir el loop recursivo en un circuito cerrado persistente faltan: (a) **puente de observaciones prospectivas a oportunidades completas y etiquetadas**, con `known_at`, `label_known_at` y sellado independiente; (b) integración con `recursive.tick` usando los criterios de mejora originales N9-S y capital/fees exactos; (c) recuperación del journal y políticas tras caída de proceso/host en la infraestructura objetivo; (d) prueba de coincidencia de caja, posiciones, riesgo diario, drawdown 8%, calendario y estados entre P9K y replay M9 **en todos los eventos y escenarios registrados**; (e) calibración de parcial/rechazo/outage/impact con recibos de ejecución observados antes de permitir operaciones.

`quant/harpoon_quant/recursive.py` ya contiene un motor real con SQLite, presupuesto y holdout, pero **no se ha conectado automáticamente** a los recibos modelados de P9L para promocionar políticas. Esa separación es una condición de seguridad y honestidad de la evidencia. La evolución registrada es M11 Fase 9M.

Se conservan las limitaciones matemáticas: condición de rentabilidad N9-S aún NO_GO, cota poblacional de riqueza/crédito positivo no demostrada, las 3.200 cuentas finales M10 selladas y la deuda histórica no conciliada. Tampoco hay revisión externa ni aceptación de broker.

## 4. Integridad y continuidad

Una sola unidad 9L publicada en `codex/continuous-n9-research`, PR #7 DRAFT. `research/continuous_n9/program.json` y `state.json` se alinean dentro del mismo commit de cierre para evitar que el programa apunte a 9H estando el estado en 9L. El nuevo checkpoint local **no** se declara almacenamiento productivo ni autoridad económica.

Cero cuentas económicas nuevas, cero candidatos, cero alfa prospectivo, cero finales M10 abiertos, cero órdenes, cero despliegues y ninguna fusión. El límite del 12% sigue siendo **de admisión/reserva**, no un cap continuo.
