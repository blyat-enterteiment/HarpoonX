# HARPOONX N9-S — M11 P9M-C9: inducción de reservas por eventos observables

**Dictamen: NO_GO N9-S.** Se cerró una sola unidad acotada de ingeniería sobre los eventos de reserva y recibos de la implementación M9, sin ejecutar cuentas económicas nuevas. Hipótesis prerregistrada en `research/modulation11/fwn9_phase9m_c9_protocol.json`; corrección del test registrada en un protocolo R2 separado. No se modificaron fuentes M9/M10, ley sintética, costes, tamaños, límites, capital ni umbrales.

## Hallazgo verificable: invariante determinista de la reserva conocida

Sea `q_0` la cantidad original registrada al reservar, `q_t` la cantidad larga remanente **conocida** por recibos válidos, `B_0` el techo nominal original y `p_t` el último cierre disponible causalmente. Para una reserva `OPENED` sin splits ni posiciones cortas, `0 <= q_t <= q_0` y `p_t>0`. Entonces, exactamente:

```
B*_t = max(B_0, q_0 * p_t) >= q_t * p_t.
```

Esta desigualdad se preserva ante una venta parcial conocida porque disminuye `q_t` sin cambiar `q_0`. En `PENDING`, el techo original se mantiene hasta conocer el `OPENED` o `NO_FILL`; en `CLOSED` o `NO_FILL`, la reserva deja de contarse únicamente cuando ambos tiempos (efectivo y conocido) son admisibles. Un rechazo de entrada no crea exposición. La nueva auditoría somete cada clase de transición a checkpoints de apertura, recibo, parcial y cierre; confronta los `state.notional` del motor con el ancla reconstruida y verifica la suma de riesgo y nocional para admisiones.

La cuenta de tamaño al IOC conserva el techo causal `quantity * priceCeiling` y la prueba de admisión `B*_t + nuevo techo <= 0.12 * E_t`, además del riesgo `<= 0.0025 * E_t`. Es una **condición en el instante de admisión**, no un techo continuo del nocional real, del valor de mercado ni del drawdown. Este argumento es algebraico para el dominio **conocido** y auditado, no una prueba de que todo camino operativo alcanzable satisfaga las premisas.

## Evidencia ejecutada

| Prueba | Resultado |
|---|---|
| Replay real M9 en fixture sintético y registro original | 14 checkpoints, 15 exposiciones OPENED, 4 PENDING, 7 observaciones con cantidad parcial; 2 admisiones contrastadas |
| Integridad de fuentes M9 SHA-256 | PASS |
| Conciliación terminal de caja e inventario por contabilidad independiente C8B | PASS |
| Corrupciones de admisión, estado y cantidad original | Rechazo comprobado |
| Sintaxis Node y pruebas focales R2 | **8/8 PASS** |
| Benchmark 10 replays locales en GitHub Actions | **68,294 ms** |
| Análisis estático específico y tipos estrictos del nuevo JS | **No ejecutados; pendientes** |
| Regresión cuantitativa completa | En curso al registrar esta evidencia, no declarada PASS |
| Cuentas económicas nuevas, semillas, finales abiertos, alfa | **0, 0, 0/3.200, 0** |

R1 ([Actions 42507381337](https://github.com/blyat-enterteiment/HarpoonX/actions/runs/42507381337)) aprobó 7/8 y falló una aserción que exigía incorrectamente un código de rechazo tardío; el libro nativo detectó antes la adulteración por `INVALID_RESERVATION_OBSERVATION`. Se preservó R1 y se publicó un test R2 separado que admite ambos puntos de rechazo sin permitir pasar la corrupción. R2 aprobó [8/8, Actions 42507464937](https://github.com/blyat-enterteiment/HarpoonX/actions/runs/42507464937). **Dos intentos de ingeniería, uno fallido**, conservados.

La máxima holgura de reserva frente a inventario conocido en estos fixtures fue **416 USD**; no es beneficio, alpha ni cota global. La referencia CASH y el mejor candidato M9 no se reevaluaron ni sustituyeron porque no existió nuevo experimento económico.

## Alcance que NO se demuestra

- La inducción sobre eventos **del libro observable** bajo supuestos de recepción y cantidad no certifica todos los estados operativos nativos ni el valor del inventario a precios intrabar todavía desconocidos.
- El motor nativo puede ejecutar stops/targets a umbrales OHLC interpolados diferentes de los ocho precios observados en la ley. No se probó equivalencia de trayectorias ni se hizo una corrección de precios.
- `max(B_0,q_0p_t)` no genera por sí solo cotas de momentos de `W_T`: cambios en ganancias, caja, fricción, tamaño entero y decisiones posteriores pueden invertir el signo de la ventaja, como muestra C7.
- La cota condicional WEAK previa de **0,905123 pb/día** sigue sin poder declararse certificado de imposibilidad del motor nativo. Tampoco hay base para afirmar rentabilidad real o aceptación condicional.
- Los dos requisitos operativos incompletos (modelo integral de parciales/rechazos/interrupciones/impacto y coordinador multicelda) permanecen cerrados a promoción.

## Próxima unidad diferenciada

C10 deberá acoplar patrimonios y admisiones posteriores **sobre las dos convenciones causales de ejecución**, obteniendo una desigualdad válida para las cantidades endógenas o un contraejemplo nativo alcanzable. Se prohíbe inferir `E[W_T]` desde los momentos de precio sin el acoplamiento y abrir una nueva cuadrícula de señales.

La PR [#7](https://github.com/blyat-enterteiment/HarpoonX/pull/7) permanece como borrador sobre #6. No se conectaron brokers, ejecutaron órdenes, desplegaron servicios, fusionaron cambios ni contactaron terceros. Datos brutos grandes: **ninguno nuevo**.
