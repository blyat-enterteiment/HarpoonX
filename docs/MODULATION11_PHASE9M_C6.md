# HARPOONX FWN9 — M11 9M-C6: presupuesto condicional de crédito con inventario endógeno

**Decisión:** PASS de ingeniería y lema de agregación condicional; **NO_GO N9-S**. La cota poblacional del patrimonio nativo sigue **NO DEMOSTRADA**. No se introdujeron señales ni se evaluaron caminos nuevos.

## Resultado matemático que sí se acredita

En una barra y activo `(b,a)`, sea `q[b,a]` la cantidad positiva de posiciones expuestas a stop y conocida **antes de la barra**. Sea `S[b,a]` el precio de apertura conocido antes de la innovación de los ocho subpasos, `B=0.0029457194636491983` la cota C5, `f` la fricción de salida original y `tick=0.01 USD`.

En el **acoplamiento de inventario/stop idéntico anterior a esa barra**, C5 demuestra:

```
E[D[b,a] | F_prebar] <= (1-f)*B*q[b,a]*S[b,a] + 0.01*q[b,a].
```

Para un conjunto FINITO de barras y los activos SYNA y SYNB, la linealidad y propiedad de torre implican:

```
E[sum D] <= (1-f)*B*E[sum q*S] + 0.01*E[sum q].
```

**No exige independencia entre activos, ni que los stop-outs sean predictibles**, pero exige que la cantidad de *posiciones potencialmente expuestas* sea previsible. No se permite multiplicar por una frecuencia de stops conocida sólo después de observar el futuro. El 12% es un límite de admisión y reserva, no de exposición continuada.

**Este lema no es una cota numérica sobre la cartera.** Los dos términos `E[sum q*S]` y `E[sum q]` siguen sin acotarse mediante un argumento aplicable a las reservas, 72h, recibos y riqueza endógena de M9. Una suma de primas por barra tampoco es una cota del cambio de riqueza final entre **políticas divergentes**: diferentes salidas pueden alterar las admisiones, el capital y los stops siguientes. Tampoco se convierte a log-patrimonio dividiendo por 20.000 USD sin justificar una cota inferior de riqueza.

## Fixture determinista: libro de exposición, NO mercado

Se incorporó `tools/fwn9_p9m_c6_budget_v2.py` (nuevo y aislado) y `tools/test_fwn9_p9m_c6_budget_v2.py`. El fixture contiene 2 activos, 2 barras y 3 pares lote/barra; SYNA 10 títulos a 100 USD, SYNA 7 a 102 USD después de una parcial y SYNB 4 a 50 USD. El total `sum q*S=1914 USD`, `sum q=21`.

Su **término derecho condicionado a ese libro hipotético** es 5.84641562130853817653614 USD nominal y 5.84472418919251080687228 USD estrés. **No es PnL, alpha, crédito esperado poblacional ni rendimiento de una política.** Se usan `Decimal` y los valores inalterados de fricción, tick y C5. La función nunca aplica un cap continuo de 12%; exige tiempos de decisión, fill y recepción anteriores a la barra y vencimiento inferior a 72 horas desde la señal. Rechaza duplicados, cantidades vacías, lotes recrecidos, recibos futuros y precios inválidos.

## Evidencia y fallas conservadas

El intento v1, [CI 42483189855](https://github.com/blyat-enterteiment/HarpoonX/actions/runs/42483189855), se conserva como FAIL: cuatro errores de tipos estrictos en acceso dinámico a TypedDict y construcción de fixtures. Se creó `v2` y un protocolo independiente sin sobrescribir v1; **no se repitió ningún experimento económico**.

La [CI v2 42483341875](https://github.com/blyat-enterteiment/HarpoonX/actions/runs/42483341875) concluyó **SUCCESS**: 8/8 pruebas, Ruff, mypy estricto en el nuevo módulo, sintaxis, SHA Git de fuentes, checksum del generador M9 y benchmark de 10.000 libros de tres exposiciones en 88,153 ms en ese runner. Las pruebas no son revisión externa ni validación contable de campañas.

La preregistración v2 se publicó **antes** de las pruebas CI en `4fd205e93677648f78b923c46bcd8f6e671fd589`, con presupuesto de 0 cuentas, 0 candidatos, 0 semillas, 0 alfa y 1 worker. La evidencia legible está en `evidence/modulation11/fwn9_phase9m_c6.json`.

La cuenta CASH, M9_BEST y el mejor candidato M10 siguen congelados como referencias, no se reevaluaron. Las 3.200 cuentas finales M10 permanecen intactas. El límite WEAK anterior de 0,9051232469572758 pb/día NO se ha transformado en una cota del nativo y no habilita declarar imposibilidad.

## Próxima frontera

Demostrar o refutar una **cota estocástica finita y cuantitativa** de exposición previa a cada barra y shares de stop, usando el reloj de admisión y el inventario financiado auténtico, y después construir un puente riguroso a log-riqueza con políticas endógenas. Hasta lograrlo, no buscar señales ni abrir holdouts. Siguen bloqueando N9-S la ejecución operativa integral y el coordinador multicelda.
