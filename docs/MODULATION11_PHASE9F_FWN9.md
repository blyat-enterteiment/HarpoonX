# FWN9 — M11 Fase 9F: cola inversa del patrimonio causal

**Dictamen: NO_GO.** Se demuestra con aritmética exacta un lema de momentos y un contraejemplo a una inferencia insuficiente: controlar únicamente el crédito positivo en USD no controla el crédito relativo `E[(W_N-W_C)^+/W_C]`. **No se ha demostrado imposibilidad bajo la ley M9** ni tampoco crecimiento N9-S.

## A. Lema de crédito relativo para admisiones endógenas

Sean W_N>0 y W_C>0 los patrimonios terminales de las dos carteras, D^+=(W_N-W_C)^+, con una ley conjunta que representa el mismo mercado. Las cantidades, reservas y decisiones pueden ser diferentes. Si existen momentos de orden dos:

`E[D^+/W_C] <= sqrt(E[(D^+)^2] E[W_C^(-2)])`.

La desigualdad es Cauchy-Schwarz. **No afirma** que ambos factores estén finitos o acotados en el motor original. Con umbral fijo epsilon>0, un refinamiento exacto es:

`E[D^+/W_C] = E[D^+/W_C ; W_C>=epsilon] + E[D^+/W_C ; W_C<epsilon]`

`<= E[D^+ ; W_C>=epsilon]/epsilon + sqrt(E[(D^+)² ; W_C<epsilon] E[W_C^(-2) ; W_C<epsilon])`.

Si se prueba de manera independiente que W_C>=c>0 en todas las trayectorias del contrato, basta `E[D^+]/c`. Ninguna de estas premisas se presume ni se deriva incorrectamente del 12%: ese porcentaje regula admisión/reserva, no inventario continuo.

El crédito faltante de P9E es estrictamente inferior a **0,00166983085355194592** por campaña de 176 días para trasladar la cota previa condicional de WEAK de 0,9051232469572758 pb/día al hurdle original de 1 pb/día. Es una condición **suficiente si la cota causal original aplica**, no un certificado conseguido.

## B. Contraejemplo abstracto: primera esperanza insuficiente

Ley artificial de dos estados, no salida del generador M9:

- Con probabilidad 1/1024: W_C=0,50 USD; W_N=1,50 USD; D^+=1 USD.
- Con probabilidad 1023/1024: W_C=W_N=20.000 USD; D^+=0.

Por cálculo exacto, E[D^+]=**1/1024 USD = 0,0009765625 USD**, mientras `E[D^+/W_C]=1/512=0,001953125`, superior al umbral relativo **0,00166983085355194592**. Reemplazando únicamente W_C=0,50 por W_C=1,00 USD y W_N=1,50 por 2,00 USD, se conserva `E[D^+]` y el crédito relativo baja a 1/1024, por debajo del umbral. El comportamiento puede amplificarse cuando W_C tiende a cero.

**Este contraejemplo sólo refuta la deducción a partir de un primer momento; no demuestra que la ley artificial sea alcanzable por HARPOONX**, cuyas reservas, límites de admisión, reglas de riesgo y horizonte son más restrictivos. Una demostración de imposibilidad específica de M9 requiere acotar la cola inversa con el *motor verdadero*.

Se conserva también la fixture P8 nativo 20.112,16 USD y causal 19.973,20 USD sólo como ejemplo determinista de crédito relativo, nunca como esperanza poblacional. CASH y el candidato M10 anterior permanecen controles registrados sin nueva evaluación.

## C. Ejecución e integridad

- Código aditivo: `tools/fwn9_phase9f_tail_bounds.py` (tipos y fracciones exactas), pruebas `tools/test_fwn9_phase9f_tail_bounds.py`, contabilidad independiente `tools/fwn9_phase9f_independent.py`. No se alteró generador, código económico, fuentes o datos históricos.
- Protocolo preregistrado antes de CI en `research/modulation11/fwn9_phase9f_protocol.json`, commit **d11eb3c8bf21bb6c03716167efe9915bb927936d**, con SHA-1 Git de fuentes.
- [GitHub Actions 42441591963](https://github.com/blyat-enterteiment/HarpoonX/actions/runs/42441591963): **SUCCESS; 12/12 unitarias; Ruff y mypy --strict sin errores; Decimal independiente de 70 dígitos; sintaxis; hashes Git de fuentes y SHA-256 del generador M9 preservados**.
- Benchmark runner: 2.000 auditorías de dos estados en **79,1806 ms**; es medición puntual de la función algebraica, no latencia de replay.
- Integridad SHA-256 del código nuevo en `evidence/modulation11/fwn9_phase9f_moments.json`.
- No hay nuevos candidatos, semillas, cuentas económicas ni gasto alfa; **3.200 cuentas finales de M10 selladas**.
- Continúan la brecha de reloj P9B IOC `NO_FILL` y los dos requisitos operativos incompletos: cobertura de ejecución y coordinador multicelda. El 12% es reserva/admisión, nunca un cap continuo. Sin brokers, órdenes, despliegues, merge o cambio de PR.

## D. Siguiente paso delimitado

`M11_PHASE9G_NATIVE_INVERSE_WEALTH_BOUND`: demostrar con reglas reales de inventario, cantidad, costes, gap, `knownAt`, riesgo y máximo de 72 horas una **cota inferior de W_C** válida para todos los caminos o un límite de momentos negativos bajo WEAK. Paralelamente, registrar qué momento del diferencial de ejecución nativo/causal es necesario y si las cotas disponibles pueden satisfacer el margen. Si no puede derivarse, presentar un contraejemplo **alcanzable bajo M9** o el bloqueo exacto, sin abrir cuadrículas de señales o semillas finales. La ley artificial de 9F no basta para descartar N9-S.
