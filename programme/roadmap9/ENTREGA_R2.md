# HARPOON — conclusión R2 del plan offline

**Se completó y comprobó el recorrido de integración que faltaba. El cierre actualizado contiene 28 PASS, 20 BLOCKED y 1 FAIL. Las seis recetas económicas siguen rechazadas; no hay candidato aprobado para promoción.**

Esta revisión concluye los trabajos de integración offline del ciclo. V037 y V039 pasan dentro del alcance sintético de ingeniería que admite el plan original. V012 conserva el bloqueo por la causa no establecida del timeout histórico; V040 conserva el incumplimiento original de latencia. Los otros 45 dictámenes no cambian. El detalle verificable está en [closure_r2.json](closure_r2.json) y la matriz completa en [CIERRE_R2.md](CIERRE_R2.md).

La entrega permanece en el [PR #1 en borrador](https://github.com/blyat-enterteiment/HarpoonX/pull/1). La versión de fuentes R2 es `8c3cae0609b1353013023ef4bd29652d79260acf`; los archivos de evidencia se publican después de esa versión. Las fuentes científicas y las seis recetas conservan sus 29 bindings originales. No se enviaron órdenes ni se realizó un despliegue.

## 1. Qué se terminó en esta continuación

La nueva ruta **GET/POST `/v1/roadmap9/offline`** está integrada en el servidor HTTP existente. Compone datos sintéticos, el asignador real, intenciones simuladas, estados de orden, fills, FEE/CFEE, inventario neto y patrimonio. El cálculo usa los módulos Python existentes; la persistencia usa el `DurableStore` y el compare-and-swap de SQLite reales.

La ruta está deshabilitada por defecto. Mantiene la autenticación y las restricciones de origen del panel. El worker se ejecuta sin shell, con entorno acotado, sin heredar claves de broker o LLM, con límite de entrada/salida y timeout de ocho segundos. El reloj de recepción pertenece al servidor: el body no puede suministrar una instantánea, una hora de decisión ni una autoridad que sustituya la del servicio.

La salud de esta ruta deriva de los recibos, su antigüedad y la conciliación. Se comprueba de nuevo al terminar el worker y antes de confirmar una intención. La ausencia del predictor bloquea entradas y conserva la reducción determinista cuando los datos, la cuenta, el calendario y el plazo permiten reducir. `execution_allowed`, `orders_allowed`, `real_fills_present` y `financial_acceptance_allowed` permanecen en `false`.

El recorrido conserva el inventario y la deuda al fallar la persistencia. Si un fill se calcula pero su CAS falla, no se confirma la mutación. Un reinicio exige conciliación; el reintento de un recibo confirmado no vuelve a aplicarlo. Una comisión superior a su provisión puede dejar caja o patrimonio negativos, y ese resultado se conserva. Las correcciones de comisión aplican sólo su delta.

La contabilidad presenta por separado cantidad bruta de fills, comisión nativa contabilizada, saldo neto, comisión pendiente, cantidad disponible y reservas de venta. Las pruebas cripto usan inventario sintético inicial declarado para comprobar CFEE y reducciones; **la nueva asignación o compra cripto sigue bloqueada**. El pronóstico del fixture es un supuesto de ingeniería y no constituye una previsión con alpha medido.

Los contratos, límites y hashes de implementación se conservan en [implementation_receipt.json](../../evidence/roadmap9/integration_r2/implementation_receipt.json). La [vinculación de versión](../../evidence/roadmap9/integration_r2/version_binding.json) identifica el commit que contiene los bytes finales.

## 2. Defectos concretos corregidos

La revisión encontró y conservó reproducciones anteriores y posteriores. Las correcciones afectan disponibilidad, contabilidad y clasificación del cierre; no modifican las seis recetas.

| Caso | Comportamiento comprobado |
| --- | --- |
| Campaña vencida con inventario o intención pendiente | Expone el vencimiento, bloquea nuevas intenciones y publica `RECONCILE_ONLY`. Conserva inventario y deadline original. Puede incorporar recibos tardíos mientras exista capacidad. |
| Deadline cruzado durante el cálculo | Una evaluación en D−1 devuelta en D deja de estar vigente. PLAN y REDUCE preparados por Python se rechazan antes del CAS, sin cambiar la revisión o el inventario. |
| Modelo o etiquetas que superan 168 horas al terminar el worker | Desactiva entradas. Esa caducidad por sí sola conserva la reducción determinista; un PLAN rechazado por TTL no impone un bloqueo global a REDUCE. Exactamente 168 horas sigue permitido por el contrato actual. |
| Cambio de día tras ganancias anteriores | El ancla diaria usa el patrimonio reconstruido antes del primer recibo del nuevo día UTC. El primer gap cuenta como pérdida. GET y reinicio no restablecen el ancla ni el máximo histórico. |
| Calendario que cierra durante el cálculo | Los slots conservan el ancla inicial y la validez acaba antes de la siguiente frontera horaria. Una sesión cerrada no se reabre al refrescar cotizaciones. |
| Registro lleno | A 128 comandos, muestra `OFFLINE_JOURNAL_CAPACITY_EXHAUSTED`, `alive=false` y `RECONCILE_ONLY`. El comando 129 se rechaza; un duplicado no crea una revisión ni reinicia saldos. |
| Fase con fallo de ingeniería | El cierre la clasifica como `BLOCKED`. `REJECTED_CANDIDATE` requiere una decisión económica explícita; un fallo de latencia no inventa ese dictamen. |

El caso de riesgo diario es material: con patrimonio previo de **23.989,75 USD** y posterior de **23.391,25 USD**, la pérdida del día es **598,50 USD, un 2,4948%**. La cuenta aún conserva 3.391,25 USD de ganancia acumulada, pero las nuevas entradas quedan bloqueadas por el límite diario del 2%. El recibo está en [adversarial_daily_loss_after.json](../../evidence/roadmap9/integration_r2/adversarial_daily_loss_after.json). Son importes sintéticos usados para probar el control.

El ancla utiliza el último NAV defendible del journal del día anterior, no un cierre de mercado autenticado. Si falta una marca previa para inventario mantenido o el patrimonio no es positivo, se declara un bloqueo explícito. Una campaña ya vencida o un journal agotado conservan sus recibos y requieren un diseño de recuperación adicional; esta sesión limitada no pretende ser un servicio productivo indefinido.

## 3. Pruebas y alcance de la evidencia

| Comprobación | Resultado local sobre las fuentes finales |
| --- | --- |
| Regresión Python completa | **792/792 PASS**, 67,775 s; cero fallos, errores u omisiones. Incluye 19 casos nuevos de integración y una regresión nueva del cierre. |
| Recorrido HTTP, SQLite y Python | **10/10 PASS**, 56,364 s; cero fallos, cancelaciones u omisiones. El adaptador de broker instrumentado registra cero llamadas. |
| Integridad durante esas dos ejecuciones | Las 552 fuentes de cada snapshot permanecieron idénticas antes y después. |
| Vinculación del manifiesto al árbol Git | **567 archivos** de fuentes, configuración y contexto comprobados contra sus blobs versionados, sin diferencias. |
| TypeScript y sintaxis del bridge | PASS. Se compila el servidor existente y sólo se actualiza su artefacto `runtime30/server.js`. |
| Mypy del paquete y seis herramientas | PASS en 19 archivos de fuente. No incluye la deuda conocida de los dos scripts históricos congelados. |
| Guardia de Ruff | 28 archivos; coinciden exactamente las **20 observaciones revisadas**, cero observaciones nuevas y ninguna regla suprimida por la guardia. Esto no es ausencia universal de observaciones. |

La [regresión completa](../../evidence/roadmap9/integration_r2/final_validation/tests.json), la [verificación HTTP](../../evidence/roadmap9/integration_r2/integration_http_verification.json), su [salida original](../../evidence/roadmap9/integration_r2/integration_http.spec.log), el [análisis de tipos](../../evidence/roadmap9/integration_r2/mypy_checks.json) y el [resultado de Ruff](../../evidence/roadmap9/integration_r2/lint/lint_verdict.json) contienen el alcance y los hashes.

La captura HTTP local necesitó una corrección del lector de resultados: Node 24 eligió el reporter `spec`, mientras que el lector esperaba TAP. Node había terminado con código cero y diez pruebas correctas. Se conservó la salida original y el recibo del error de captura; se leyeron las diez pruebas de esa misma salida, sin fabricar TAP ni repetir la ejecución. La configuración de CI selecciona ahora `--test-reporter=tap` explícitamente. Ese ajuste posterior no cambió fuentes de aplicación o pruebas.

La revisión adversarial de otro agente del mismo equipo se documenta como **revisión interna**, con sus hashes y fechas reales. Su primera ejecución de tres ataques HTTP se conserva con la versión que probó; las comprobaciones focalizadas posteriores no se presentan como una nueva ejecución de esos tres ataques. El workflow añadido ejecuta esos tres casos completos en CI sobre la versión publicada. El [recibo del revisor](../../evidence/roadmap9/integration_r2/internal_adversarial_review.json) y los recibos de regresión final se complementan sin sustituir una revisión externa.

Las ejecuciones de CI de la versión publicada se identifican por commit y enlace en el PR. La CI archivada de `b48f38d` es evidencia de la versión anterior, no una prueba retrospectiva del código nuevo. En aquellos scripts congelados, la invocación de CI informó ocho diagnósticos de mypy y el análisis local anterior informó nueve; se preservan ambos alcances y no se atribuye esa diferencia a una reparación.

## 4. Dictámenes que cambian y bloqueos que permanecen

| Contrato | Dictamen R2 | Motivo |
| --- | --- | --- |
| V037 — ataques de integración | **PASS offline** | La API real compone los módulos y SQLite y cubre fallos combinados, comisiones tardías, persistencia, reinicio, concurrencia y límites. |
| V039 — pulso y autoridad | **PASS offline** | Recorrido completo de datos a patrimonio con orden simulada, reloj servidor, recibos y autoridad desactivada. |
| V012 — reinicio y timeout legado | **BLOCKED** | El test exacto pasó 1/1 en 29,709 s y el timeout sigue siendo 8.000 ms. No se estableció la causa del fallo histórico. El stall controlado del nuevo worker es otra evidencia. |
| V040 — perfil de latencia | **FAIL original conservado** | El p95 local registrado superó dos segundos. La medición posterior en otro runner se conserva separadamente. |

El plan original admite `SYNTHETIC_ENGINEERING_ONLY` para V037 y V039 y pide una orden simulada. Se corrige la interpretación anterior que condicionaba ambos pases a despliegue o broker real. Esto no cambia las exigencias observadas, prospectivas y externas de los contratos que sí las requieren. La fase P09 queda bloqueada por V040, aunque tres de sus cuatro contratos pasen.

| Perfil de capacidad registrado | p95 | p99 | Máximo | Interpretación |
| --- | ---: | ---: | ---: | --- |
| Local original, AMD EPYC 9V74 | 2,051 s | 2,189 s | 2,318 s | Incumple p95 ≤ 2 s. Conserva el dictamen V040. |
| CI de `b48f38d`, Intel Xeon Platinum 8573C | 1,951 s | 1,988 s | 2,065 s | Pasa en ese runner; no demuestra una aceleración del código ni reemplaza el resultado local. |

Ambos perfiles usan 288 contextos registrados: 279 cálculos completos y nueve rechazos esperados, sin fallos inesperados; el máximo de trabajo fue 5.593.536. El [archivo de CI anterior](../../evidence/roadmap9/ci_b48f38d/completion.json) conserva entorno, artefactos y comparación. Ninguna de estas mediciones es un SLA del broker.

## 5. Decisión económica preservada

Las cuentas históricas modeladas parten de 20.000 USD, continúan sin reinicios y cubren 404 sesiones y 585 días naturales, del 11 de marzo de 2025 al 16 de octubre de 2026. R2 no añade mediciones económicas ni cambia datos, horizonte, costes, recetas o resultados.

| Receta congelada | Neto nominal USD | Neto estrés USD |
| --- | ---: | ---: |
| H1 — continuación por horario a 24 h | −535,50 | −1.170,00 |
| H1 — selección entre 24, 48 y 72 h | −585,69 | −1.167,27 |
| H2 — aceptación del gap | −189,51 | −782,16 |
| H2 — gap y confirmación sectorial | −262,73 | −859,98 |
| H3 — salida total por valor | −407,08 | −1.062,23 |
| H3 — reducción parcial por valor | −463,41 | −1.102,39 |

El control de continuación original termina en −54,42 USD nominal y −701,41 USD bajo estrés al contabilizar 585 días de gasto común. Sus 530,58 USD nominales antes de ese gasto no cubren los 585 USD supuestos; el resultado anterior de +126,58 USD descontaba sólo 404 sesiones. Los costes fijos de 1/2 USD diarios son supuestos del experimento, no facturas verificadas.

La atribución H3 sobre las mismas 45 entradas mejora +86,81/+62,40 USD para la salida total, pero las cuentas completas siguen perdiendo. H1/H2 tienen soporte insuficiente y ninguna de las 96 cotas inferiores pareadas es positiva. El [estudio congelado](../../research/roadmap9/README.md) y sus [resultados](../../evidence/roadmap9/research/results.json) conservan esos límites. La mejora de fidelidad operativa de R2 no se contabiliza como rentabilidad.

## 6. Reproducción y límites operativos

Desde la raíz del repositorio, con las dependencias declaradas instaladas:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONPATH=quant python3 -B tools/roadmap9_validate.py --output /tmp/harpoon-r2-verify --full-suite
```

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 node --test --test-timeout=30000 --test-reporter=tap tools/roadmap9_integration_api_test.cjs
```

```bash
node tools/roadmap9_integration_adversarial.cjs /tmp/harpoon-r2-adversarial.json
```

```bash
PYTHONPATH=quant python3 -B tools/check_roadmap9_lint.py --output /tmp/harpoon-r2-lint
```

El harness HTTP levanta el servidor real mediante `server(..., {roadmap9Offline:true})`, con un Coordinator aislado y un adaptador que falla ante cualquier llamada al broker. Ésta es la forma comprobada de ejercitar la ruta sin credenciales. **El `main()` histórico conserva su arranque con broker**: `HARPOON_ROADMAP9_OFFLINE=1` habilita la ruta, pero por sí solo no crea un arranque completo del producto sin credenciales. Tampoco se ha probado aquí que el dashboard visual consuma el nuevo estado.

El POST exige la autenticación existente, `Content-Type: application/json`, `x-harpoon-action: 1` y un body con `origin: "SYNTHETIC_ENGINEERING_ONLY"` y `command`. El fixture compartido proporciona comandos sintéticos válidos. Una sesión tiene hasta cuatro activos y 128 comandos; no existe reset automático de capital ni extensión del deadline original de una campaña.

Los 20 bloqueos restantes están identificados individualmente en el cierre. Incluyen la procedencia y cobertura de datos, tarifas reales de cuenta, historial global de intentos, información auténtica de subastas y contexto de riesgo, asignación cripto pendiente, causa del timeout legado, ejecución observada, confirmación prospectiva y revisión externa. Al no existir candidato económico elegible, el ciclo termina con rechazo de las seis recetas y conservación de la infraestructura verificada.

## Documentos de cierre

- [CIERRE_R2.md](CIERRE_R2.md): doce fases y 49 dictámenes.
- [claims_r2.json](claims_r2.json) y [closure_r2.json](closure_r2.json): afirmaciones y resultado calculado.
- [source_manifest_r2.json](source_manifest_r2.json): 567 archivos vinculados a la versión de fuentes.
- [closure_verification.json](../../evidence/roadmap9/integration_r2/closure_verification.json): integridad del cierre y sólo dos cambios de dictamen.
- [ENTREGA_FINAL.md](ENTREGA_FINAL.md): cierre anterior conservado; R2 actualiza la integración, sus pruebas y los dictámenes indicados.

