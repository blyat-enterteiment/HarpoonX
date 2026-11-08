# HARPOONX N9-S — M11 Fase 9M-C10: riqueza endógena y cota por caja autofinanciada

**Veredicto: NO_GO N9-S.** Una unidad estructural de ingeniería y matemáticas; sin cuentas de mercado, nuevas recetas, semillas, holdout ni consumo de alfa. PR #7 permanece en borrador sobre #6. Hipótesis, catálogo finito y presupuesto registrados antes de las pruebas en `research/modulation11/fwn9_phase9m_c10_protocol.json` (commit `5e677020fbe0aa10c361814a2da684dd3b0c7c96`).

## Hallazgo: cota de riqueza por libro propio, sin suponer decisiones iguales

Para cada activo largo `a`, sea `m_a>0` el mínimo **ex post** de sus precios OHLC/ejecución y `M_a` el máximo, con `R=max_a(M_a/m_a)>=1`. Defínase el libro sombra `U_t=C_t+sum_a q_{a,t}m_a`, donde `C_t>=0` es caja física y `q_a>=0` inventario. Los costes fijos, fricción y comisiones, siempre no negativos, sólo reducen `U`.

Una compra al precio efectivo `p>=m_a` reduce `U` en `q(p-m_a)+fee`. Una venta efectiva con `p<=M_a` aumenta `U` como máximo en `q(M_a-m_a)`. Si `C>=0`, la cantidad `q m_a` no puede exceder `U` antes de vender, de donde `U_{después}<=R*U_{antes}`. Por inducción sobre `J` ventas, al valorar terminalmente a precios no mayores que `M_a`:

```
W_T <= R * U_T <= 20.000 USD * R^(J+1).
```

La desigualdad es **determinista y condicional a caja no negativa, inventario largo y precios de fill válidos**. Se verifica por separado para cada libro; no presume que dos estrategias con salidas OHLC/subpasos distintas admitan las mismas órdenes. El 12% no figura como exposición continua: sigue siendo exclusivamente un límite de admisión/reserva.

**Qué NO demuestra:** `R` utiliza extremos del camino completo y sólo es observable ex post para el auditor. La cota puede ser muy amplia; no prueba una desigualdad útil para el crecimiento neto diario ni una esperanza estocástica universal bajo WEAK. Para elevarla a momento del motor completo faltan un límite determinista de ventas, soporte numérico positivo de fills con tick y verificación de caja no negativa en *todas* las trayectorias operativas (no sólo fixtures). Tampoco se cerró un acoplamiento terminal ajustado a decisiones futuras ni la equivalencia OHLC/primer cruce entre ocho subpasos.

## Reproducción y validación

La auditoría R3 (`runtime30/fwn9_p9m_c10_wealth_envelope_r3.cjs`) lee eventos **nativos** de `replayFundedPortfolio`, inventario/caja/fills y costes originales, reconstruye el libro físico sin modificar el motor y compara terminal contra su curva. El contador Python Decimal-50 reconstruye por otra vía las cinco operaciones de recibo y tres salidas del fixture nominal. También se prueban coste STRESS, IOC `NO_FILL` de cada activo, guardas de caja no negativa, conocimiento temporal y comisiones.

| Verificación | Resultado |
| --- | --- |
| R3: pruebas focales nativas | **8/8 PASS** |
| Contabilidad independiente Decimal-50 | **PASS: 5 recibos, 3 salidas** |
| Sintaxis Node/Python | PASS |
| Hash de fuentes M9 registradas | PASS |
| Benchmark de 16 replays completos de ingeniería | **56,521 ms** |
| Ruff/mypy estrictos C10 | **No ejecutados; control residual** |
| Comparación poblacional OHLC/subpasos | **Pendiente** |
| Nuevas cuentas económicas / alfa | **0 / 0** |
| Finales M10 abiertas | **0/3.200** |

[GitHub Actions R3, aprobado](https://github.com/blyat-enterteiment/HarpoonX/actions/runs/42512536107).

Se conservan los intentos fallidos R1 [42512248407](https://github.com/blyat-enterteiment/HarpoonX/actions/runs/42512248407) y R2 [42512387707](https://github.com/blyat-enterteiment/HarpoonX/actions/runs/42512387707): R1 mezcló TAP con JSON; R2 exportó `v.h` inexistente, cuya falta detectó el contador Python. El módulo R3 separado corrige únicamente la serialización. **Tres intentos cargados**, sin reejecución adicional; las versiones fallidas permanecen en Git. Los SHA de los cuatro artefactos finales constan en `evidence/modulation11/fwn9_phase9m_c10.json`.

## Brecha concreta y siguiente unidad

La cota ex post de C10 es compatible con cambios en cantidades enteras posteriores, pero no mide ni restringe suficientemente ese efecto económico. La próxima hipótesis diferenciada (C11) debe comprobar bajo el motor WEAK original la aplicabilidad de caja no negativa, los fills redondeados, el máximo de ventas y la posibilidad de integrar la cota estocásticamente con una constante **no vacua**. Un contraejemplo nativo alcanzable refuta su aplicación; una cota amplia, aunque correcta, **no autoriza declarar N9-S imposible**.

Se mantiene la cota previa WEAK **0,905123 pb/día**, solamente condicional, frente al requisito original **1 pb/día**. Persisten los bloqueos operativos por parciales/rechazos/interrupciones/impacto y coordinación multicelda. Ninguna rentabilidad real queda acreditada. Sin brokers, órdenes, despliegues, fusiones ni contactos externos.
