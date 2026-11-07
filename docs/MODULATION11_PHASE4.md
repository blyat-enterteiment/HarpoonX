# M11 Fase 4 — refutación estructural de la equivalencia causal OHLC

**Veredicto:** se refutó la equivalencia *para una clase específica*: ejecuciones nativas OHLC con prioridad stop-first frente a dos órdenes pasivas de stop/target precomprometidas, ejecutadas al primer precio observable que cruza el umbral en el mismo tape de ocho subpasos. **No se ha demostrado imposibilidad económica de N9-S**, ni equivalencia con cualquier mercado continuo adicional.

## Hipótesis, contratos y contraejemplo reproducible

El registro previo está en `research/modulation11/phase4_protocol.json` y precede los resultados. Se emplean `nativeBarExits` y `substepBarExits` de M11, coherentes con la lógica de stop-first analizada en fases anteriores; **esta fase no ejecuta una campaña económica completa del motor principal**.

Ambas trayectorias parten de apertura 100 USD, entrada previa 100,03, stop 99,03, distancia 1, target 101,53, cantidad 8, tick 0,01, fricción por lado 0,0003 y comisión por acción/lado 0,005. La primera pareja de subpasos es **100,20 y 101,80** en ambas; en el segundo punto el target es alcanzado. Posteriormente la rama ascendente permanece por encima de stop, y la rama adversa alcanza 95,50. El cierre vuelve a **100 USD en ambas**.

Si una orden objetivo de dos acciones estaba colocada y era ejecutable al primer cruce, **ambas ramas deben ejecutar dos acciones en el mismo instante antes de diferir**; cualquier decisión anterior depende de la misma historia. El comparador de ocho subpasos sí vende esos dos títulos en ambas. El nativo vende dos al target sólo en la rama sin stop y, en la rama adversa, **anula retrospectivamente ese target y vende las ocho acciones al stop**. La lógica utiliza el mínimo futuro de la barra para determinar un fill que no puede reproducirse con los órdenes pasivos precomprometidos del tape. Sus fills intra-bar se registran en `bar.end`, con `knownAt=bar.availableAt`. Los precios de stop/target de esta fixture no coinciden con las cotizaciones discretas disponibles ni con el cierre.

No se prohíbe una interpolación continua no especificada, pero para justificarla hay que definir su ley, sus clocks y el mecanismo causal de ejecución/recepción. **Un pago retrospectivo de una barra puede definirse como contrato sintético exótico**, pero no recibe automáticamente la propiedad martingala ni el lema de riqueza de una estrategia que opera las acciones discretas.

## Contabilidad independiente de dos trayectorias

Una segunda implementación independiente en Python `Decimal`, sin importar el motor JS, reconcilió los mismos cashflows y costes:

| Rama | Nativo OHLC, equity final | Primer cruce, equity final | Diferencia Nativo − Primer cruce |
|---|---:|---:|---:|
| Solo target | 20.002,69 USD | 20.003,23 USD | −0,54 USD |
| Target temprano y stop tardío | 19.991,68 USD | 19.976,02 USD | +15,66 USD |

La discrepancia **puede cambiar de signo**; no es válido corregir el nativo sólo con un sesgo constante o presumir que siempre es más conservador. Las cifras son **fixtures de ingeniería**, no resultados de rendimiento económico, Monte Carlo ni evidencia real.

## CI, alcance de validación y deuda histórica

- GitHub Actions `42413416181`: 7/7 pruebas aprobadas; sintaxis Node, chequeo TypeScript `checkJs` restringido al nuevo módulo, conciliación independiente `Decimal`, hashes M11 y microbenchmark ejecutados. Referencia: `https://github.com/blyat-enterteiment/HarpoonX/actions/runs/42413416181`.
- Benchmark informativo de 3.000 certificados: 54,183 ms en una ejecución GitHub Ubuntu/Node 22. No se utiliza como prueba de rendimiento de trading ni se comparó contra hardware equivalente.
- **El CI cuantitativo general no está verde**: `42413278022` falló por un hash histórico `profit8_replay.js`: esperado `26b7046...`, observado `303aa695...`. Esta unidad no reescribe ese hash ni la procedencia histórica; debe separarse el certificado antiguo de la evolución experimental sin falsear registro.
- M9/M10: cero cambios en generador, costes, capital, riesgo, límite de 72 h, criterio N9-S o datos finales. **Cero cuentas económicas**, **cero alfa prospectivo**, **3.200 cuentas finales M10 cerradas**; no se realizó despliegue, trading ni merge.

## Consecuencias de la refutación

La cota condicional WEAK de **0,9051232469572758 pb/día** no puede todavía acreditarse como límite del replay OHLC; el argumento de riqueza adaptada no se traslada a pagos retrospectivos de barrera sin una representación ejecutable. Tampoco se ha demostrado que N9-S sea alcanzable: el hallazgo es una **brecha estructural**, no un nuevo edge.

El requisito de reservas universales, los modelos de entrada parcial/rechazo/outage/impacto, la integración multicelda y la revisión contable externa siguen pendientes.

**Siguiente unidad elegible (sin búsqueda económica):** especificar un contrato ejecutable nuevo y versionado, o derivar una cota directamente para el payoff OHLC. Definir la filtración, times y orden de operaciones, reconciliar el hash heredado como deuda histórica y comprobar los anchors de reservas para todos los eventos. No modificar fuentes congeladas ni abrir finales para resolver esta brecha.
