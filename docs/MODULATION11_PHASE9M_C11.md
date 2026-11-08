# HarpoonX N9-S — M11 C11: cota de riqueza y precio cero por tick en stops nativos

**NO_GO N9-S.** Hipótesis y catálogo preregistrados en `research/modulation11/fwn9_phase9m_c11_protocol.json` antes de pruebas (commit `185174e7e87334370f37b501e9befb8e2022a9c2`). Una sola unidad estructural; ni cuentas económicas, ni semillas nuevas, ni apertura de los 3.200 finales M10, ni cambio de ley, cartera, capital, límites, señales, costes o horizonte.

## Hallazgo material: precio observado positivo, precio vendido exactamente cero

Se ejecutó `replayFundedPortfolio` nativo, no un emulador, con una compra anterior correctamente admitida para SYNA y un gap de ingeniería en la siguiente apertura (0,004 USD; todos los OHLC siguen estrictamente positivos, low=0,0035). El motor aplica su misma fricción y el `floor` vendedor a tick 0,01: `floor_tick(0.004*(1-f)) = 0`. El libro contiene **un recibo EXIT nativo con `filledPrice=0`**. El auditor C10 rechaza ese recibo porque exigía `filledPrice>0`; el auditor C11 permite ventas con `filledPrice>=0` y concilia inventario, caja física, comisiones y coste calendario.

Esta cinta es un **fixture determinista extremo**, no una muestra probabilística WEAK y no mide frecuencia ni daño económico poblacional. La ley ideal WEAK utiliza normales con soporte inferior no acotado para retornos logarítmicos, de modo que una caída bajo el tick tiene soporte matemático positivo; el generador concreto usa PRNG finito y aquí **no se ha demostrado una semilla que materialice el episodio**. La falta de demostración de alcance por semillas excluye el título de contraejemplo poblacional formal del programa, pero refuta la premisa de que `OHLC>0` implica `fill redondeado>0` en el modelo nativo.

## Reparación matemática sin tocar la ejecución

Para cada activo defínase `m_a>0` como el mínimo de precios OHLC **positivos** y precios de compras positivas ejecutadas (no incluir ventas de cero); `M_a` como máximo de precios OHLC y fills ejecutados no negativos, y `R=max_a(M_a/m_a)`. El libro sombra sigue siendo `U_t=C_t+sum_a(q_a*m_a)`. Para una venta de q acciones a `p>=0`, la variación es `q(p-m_a)-fee`, que puede ser negativa cuando p=0. Sigue siendo `<=q(M_a-m_a)` y, mientras `C>=0`, `q*m_a<=U`. Por tanto, se conserva la inducción `U_después<=R*U_antes` y la cota C10 `W_T<=20000*R^(J+1)` para el dominio **condicional** revisado.

La reparación evita que un precio de venta cero fuerce `m=0`, pero **no** verifica caja no negativa en todas las trayectorias, ni acota cuantitativamente momentos de riqueza bajo WEAK, ni corrige la diferencia OHLC/primer subpaso. No puede convertirse en la cota de 0,905123 pb/día del motor nativo ni en un certificado de imposibilidad/aceptación N9-S.

## Evidencia reproducible, alcance y bloqueos

| Control | Comprobación |
| --- | --- |
| Pruebas C11 nativas (baseline, gap, stress, IOC y adulteración) | **8/8 PASS** |
| Contabilidad externa Decimal-50 | **PASS; 1 venta nativa a tick cero** |
| Ruff/mypy `--strict` del contador Python | PASS |
| Sintaxis Node y Python | PASS |
| Git blob checksums, tres fuentes M9 congeladas y auditor C11 | PASS |
| Benchmark de 12 replays nativos | **54,016 ms** |
| Nuevas cuentas, nuevas recetas, alfa, finales abiertas | **0 / 0 / 0 / 0** |
| CI nativo | [42517313754](https://github.com/blyat-enterteiment/HarpoonX/actions/runs/42517313754): SUCCESS |
| CI estático separado | [42517434134](https://github.com/blyat-enterteiment/HarpoonX/actions/runs/42517434134): SUCCESS |

Fuentes reproducibles: `runtime30/fwn9_p9m_c11_tick_applicability.cjs`, `tools/fwn9_p9m_c11_tick_test.cjs`, `tools/fwn9_p9m_c11_decimal_accountant.py` y `evidence/modulation11/fwn9_phase9m_c11.json`. Ejecución manual: `node --test tools/fwn9_p9m_c11_tick_test.cjs`; para el revisor independiente ejecutar `node tools/fwn9_p9m_c11_tick_test.cjs --emit | grep '^{"schema":"FWN9_C11_TICK_SUPPORT_AUDIT_1"' | python tools/fwn9_p9m_c11_decimal_accountant.py`. Los demás workflows históricos pueden fallar por motivos propios: no se declara la PR integralmente verde.

Las referencias CASH/M9_BEST y contratos originales se mantienen, sin nueva búsqueda de candidatos. PR #7 en borrador apilada sobre #6; no broker, órdenes, despliegues, fusiones ni terceros.

**Próxima unidad estructural C12:** verificar si el ancla revisada es válida para todos los estados nativos alcanzables y obtener una cota efectiva sobre `J` y sobre momentos de `R` bajo el contrato de generación y su soporte numérico. Identificar si el resultado es ajustado para el hurdle de 1 pb/día; si no lo es, refutar la vía de certificación por esta envolvente sin buscar señales al azar. Persisten los gates de equivalencia de 8 subpasos, ejecución operativa completa y coordinador multicelda.
