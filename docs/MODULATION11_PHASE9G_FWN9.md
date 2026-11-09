# FWN9 — M11 Fase 9G: cota inferior condicional a la última admisión

**Veredicto: NO_GO N9-S.** Se obtiene una cota determinista POSITIVA de patrimonio causal **si y sólo si** se verifican las hipótesis de caja real, valoración del inventario, IOC y coste a la última admisión. Las verificaciones de alcance universal en el motor M9 **no se han realizado**. No es un certificado de imposibilidad del replay nativo. La demostración es exacta bajo sus premisas; los ejemplos de ingeniería no son cuentas económicas M9.

## I. Teorema condicional en el contrato de admisión

Sea τ el instante de la **última admisión aceptada** y Eτ la equity causal observada; Hτ la cota superior observada de equity. El source `runtime30/profit8_replay.js`, función `replayFundedPortfolio`, evalúa el gate de drawdown en líneas 1092–1105, con `peakEquity` inicializado al capital (líneas 935 y 1013–1027): para una admisión aceptada se necesita **Eτ > (1−0,08) Hτ ≥ 18.400 USD**.

Sea Cτ la **caja económica realmente libre** (capital menos compras pagadas y comisiones ya cargadas, más ventas cobradas), Vτ el valor íntegro de posiciones todavía abiertas, marcado con información estrictamente causal, y Bτ la obligación de compra máxima de órdenes IOC pendientes ya reservadas. Supóngase, adicionalmente:

1. Libro contable autofinanciado y reconciliado: `Eτ ≤ Cτ + Vτ`, con el **mismo reloj knownAt** para Vτ y equity (sin beneficio de marca futura, venta parcial o doble contabilización).
2. `Vτ + Bτ ≤ 0,12 Eτ`. La reserva del IOC y las posiciones marcadas deben estar completas, incluyendo posiciones originales sin liberación parcial. Esto es **cap de admisión/reserva en τ**, no un cap continuo.
3. Coste total futuro de las entradas pendientes, ventas y comisiones `Fτ ≤ 0,0025 Eτ`. Requiere que cada recibo tenga cobertura en las reservas de riesgo (el riesgo contiene ambas comisiones), no una afirmación sin auditoría.
4. Ninguna admisión posterior a τ; posiciones largas, sin préstamos ni obligaciones futuras ocultas; precios de salida no negativos; toda compra IOC paga como máximo el importe reservado.
5. Los costes externos restantes son `Kτ ≤ 176 USD` en NOMINAL y `Kτ ≤ 352 USD` en STRESS. El horizonte total son 176 días calendario.

Entonces, sin utilizar precios futuros:

```
W_T^C >= Cτ − Bτ − Fτ − Kτ
      >= Eτ − Vτ − Bτ − Fτ − Kτ
      >= (1 − 0.12 − 0.0025) Eτ − Kτ
       > (1 − 0.12 − 0.0025)(1 − 0.08) · 20_000 − K_max
```

**Por tanto, condicional a todas esas hipótesis y a su cumplimiento casi seguro:**

| Escenario | Límite inferior estricto W_T^C |
| --- | ---: |
| NOMINAL, 1 USD/día | **> 15.970 USD** |
| STRESS, 2 USD/día | **> 15.794 USD** |

Si no hubo ninguna admisión, CASH deja al menos `20.000−K_max`. Esta cota no sustituye los modelos de ejecución ni convierte un ledger falso en verdadero. Para la distribución M9 sólo serviría tras probar el cumplimiento de las hipótesis para **todas las trayectorias válidas**, incluyendo IOC `NO_FILL`, parciales, gaps y trailing, o bajo una condición probabilística formal explícita.

En ese caso `E[(W_T^C)^{-2}] ≤ (1/15.970)^2` NOMINAL y `E[D_T^+/W_T^C] ≤ E[D_T^+]/15.970`. Tomando el margen de Fase 9E `0,00166983085355194592`, bastaría además `E[D_T^+] < 26,6671987312245763424 USD` **NOMINAL** (y aplicabilidad de la cota causal WEAK) para refutar el hurdle en el nativo. **No está estimado ni demostrado ese segundo momento monetario.** Los 26,667 USD no son una pérdida observada ni un límite demostrado del motor.

## II. Lo que se verificó y lo que sigue faltando

Contratos inspeccionados en los archivos originales congelados:

- `runtime30/profit8_replay.js`: `pnlAt` (936–957) usa un mark conocido o referencia causal; `cashPoolAt` (960–961) devuelve fondos de campañas completamente cerradas, **no** caja económica libre, ya que no descuenta el principal abierto. No debe introducirse ese valor directamente como Cτ.
- `replayFundedPortfolio` 1092–1206: gate causal de drawdown y reservas de último inventario con cantidad original, IOC y capital registrado. Las desigualdades `Vτ+Bτ≤12%Eτ` precisan conciliación de esos relojes con la caja física y las parciales.
- `ultimate_reservations.js` 90–140: retiene reservas hasta `CLOSED` o `NO_FILL` conocido. El IOC `NO_FILL` se registra en `profit8_replay.js` 1216–1230; falta P9B sobre valoración de ese instante.
- `profit8_replay.js` 559–584: stops/targets desde OHLC no equivalentes de forma probada a los ocho subpasos ejecutables. P9G **no** soluciona la cota de `E[D_T^+]`.

La herramienta registrada `tools/fwn9_phase9g_last_admission_floor.py` aplica un verificador **fail-closed** con `Fraction`: rechaza gate no estricto, marcas y caja no conciliadas, IOC no reservado, importes mayores al 12%, riesgo/fee mayor a 0,25%, reloj regresivo, ventas no largas y admisiones posteriores. Sus flags son requisitos declarados del fixture: **no inspeccionan automáticamente las trayectorias M9** y nunca elevan resultados a certificación poblacional.

Fixture exacta: Eτ=20.000; Cτ=18.000; Vτ=2.000; IOC=400; comisiones futuras=50; costes posteriores nominales=176. La desigualdad local entrega **17.374 USD**, superior al mínimo teórico general 15.970. Es una comprobación algebraica, no una trayectoria ejecutada del mercado.

## III. Registro de intentos y comprobaciones

El código, los fixtures y las verificaciones matemáticas se preregistraron antes de ejecutar CI en el commit `f358e66dd6705f200abc1ca765e464b568e30522`. Todos los intentos se conservan:

1. CI `42443088337`: **FAIL** por Ruff F401 (importación no utilizada), aunque 18 pruebas y Decimal-70 pasaron.
2. CI `42443175975`: **FAIL** por Ruff E741 (variable ambigua en nueve tests), aunque 18 pruebas y Decimal-70 pasaron. Se conservó el código anterior y se abrió test aditivo R3.
3. Protocolo correctivo registrado en `research/modulation11/fwn9_phase9g_r3_protocol.json` (commit `ffec764c7f4dc7770dec56d7a632a29c7520268d`); CI `42443265351` **SUCCESS**: 18/18 pruebas, Ruff, mypy --strict, auditor Decimal-70, integridad Git y SHA-256 del generador M9 intactos. Benchmark de 2.500 chequeos exactos: **84,5294 ms** en runner. CI `42443265487` de fixtures económicos preexistentes también pasó.

Evidencia: `evidence/modulation11/fwn9_phase9g_last_admission.json`; hashes SHA-256 de fuente y pruebas allí incluidos. Los intentos CI fallidos no se borraron ni se reciclaron como nuevas cuentas económicas.

**Presupuesto económico:** 0 nuevas cuentas, 0 candidatos, 0 controles reevaluados, 0 semillas, 0 gasto alfa. Los 3.200 finales M10 permanecen cerrados; CASH y `QUALITY_NATIVE_QUEUE72_R0625` siguen registrados sin nueva ejecución. Ningún broker, orden, despliegue o fusión.

## IV. Decisión y siguiente unidad

**NO_GO**, pero con una vía de cierre de la cola inversa claramente cuantificada: hace falta demostrar que el **cash económico** conciliado con parciales y órdenes IOC coincide con la equity disponible y las reservas que usa el motor en el instante de su última admisión. La siguiente unidad es `M11_PHASE9H_RECONCILE_CASH_MARKS_KNOWNAT`: reconstruir libro de caja y posiciones con subpasos y knownAt en fixtures, contrastar exactamente con `cashPoolAt`, `pnlAt`, y resolver P9B `NO_FILL` antes de reclamar cumplimiento del lema en M9. En paralelo sigue sin resolverse la discrepancia OHLC y la cota del diferencial positivo monetario. No se autorizan señales nuevas.

Los requisitos operativos de cobertura de ejecución (parciales, rechazos, outage, impacto) y coordinador multicelda continúan pendientes.
