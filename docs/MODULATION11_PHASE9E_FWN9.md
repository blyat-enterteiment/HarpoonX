# FWN9 — M11 fase 9E: puente global de log-riqueza y refutación de un certificado prematuro

**Dictamen: NO_GO.** Hay un teorema algebraico global para riqueza positiva y dos carteras endógenas comparables sobre la misma historia. No hay todavía cota de esperanza que transfiera el límite WEAK de 0,9051232469572758 pb/día al motor OHLC nativo. Ningún resultado nuevo es rentabilidad.

## 1. Teorema demostrable

Sean W^N_T y W^C_T los patrimonios **terminales después de todos los costes** de los libros nativo y causal, con el mismo capital W0=20.000 USD y ambos estrictamente positivos. No se necesita que las decisiones de admisión, inventarios o cantidades coincidan. Definiendo D_T=W^N_T-W^C_T, se tiene exactamente:

log(W^N_T/W0)=log(W^C_T/W0)+log(1+D_T/W^C_T).

De log(1+x)<=x para x>-1, se deduce la desigualdad **por trayectoria**:

log(W^N_T/W0) <= log(W^C_T/W0) + (D_T)^+/W^C_T.

Si ambas variables son integrables, tomando esperanza sobre un acoplamiento válido de la ley M9 y dividiendo por 176 fechas calendario:

g_N <= g_C + E[(D_T)^+/W^C_T]/176.

**Alcance:** la identidad y la desigualdad son verdaderas para cualesquiera dos patrimonios positivos; no prueban por sí solas autofinanciación, admisiones causales, ejecución alcanzable ni que la cota anterior de g_C sea válida para el libro de comparación. La divergencia endógena de inventarios se encuentra dentro de D_T, no se descarta.

## 2. Criterio suficiente, NO certificado obtenido

Hurdle original 1 pb/día. Cota original **condicional** de WEAK, 0,9051232469572758 pb/día. Separación: **0,0948767530427242 pb/día**.

Bajo las dos hipótesis aún no demostradas de (a) aplicabilidad del límite WEAK original al libro causal completo y (b) un límite poblacional verificable

E[(D_T)^+/W^C_T] < 0,00166983085355194592,

la desigualdad anterior bastaría para demostrar g_N < 1 pb/día y **refutar la factibilidad poblacional del hurdle en WEAK** para el contrato efectivamente acoplado. Esta cota del crédito no se ha demostrado ni estimado con una muestra apta. Si W^C_T puede acercarse a cero, hace falta además controlar integrabilidad y colas inversas; Jensen/Doob por barra no resuelve por sí solo el cociente terminal.

Se evita el error de sustituir cantidades endógenas por un supuesto 12% de exposición continua. El 12% sigue siendo sólo admisión/reserva.

## 3. Fixtures adversariales, no mercados nuevos

- Control base: 19.990 vs 19.990 USD: corrección positiva cero.
- Fixture P8 previamente documentada: patrimonio nativo 20.112,16 USD y causal 19.973,20 USD. D=+138,96 USD; `D^+/W_C=0,006957322812568842...`; crédito por 176 días **0,3953024325 pb/día**. La desigualdad pasa, pero el crédito observado excede el margen de 0,0948767530; **este único camino no es una esperanza ni refuta una ley poblacional**.
- Fixture P7 previamente documentada: 19.975,74 vs 19.977,06 USD, D<0 y crédito positivo cero; un diferencial nativo desfavorable no se fuerza artificialmente a positivo.
- Contraejemplo de exposición: una admisión de 2.400/20.000 USD=12% seguida de una apreciación de 10x deja inventario marcado de 24.000 y equity de 41.600 USD: exposición **57,6923%** sin ninguna nueva admisión. No hay cap continuo del 12%.
- Pruebas negativas: patrimonio terminal no positivo, neto post-costes adulterado, calendario alterado y admisión original >12% producen rechazo. Las banderas de prueba nunca permiten emitir un certificado matemático automático; devuelven una condición numérica **no verificada**.

Todos los importes son fixtures deterministas ya usadas para ingeniería, **no cuentas nuevas del generador**, ni prueba de ejecutabilidad de umbrales OHLC. El módulo registra explícitamente `nativeOHLCExecutable:false` y `stochasticPopulationBound:false`.

## 4. Código, evidencia y verificación

- Protocolo prepublicado en `research/modulation11/fwn9_phase9e_protocol.json`; commit de preregistro `c348f899892f540853c031f150bd45de29c998c3` con SHA-1 Git inmutables de código y tests, antes de CI.
- CI focal: [run 42438754541](https://github.com/blyat-enterteiment/HarpoonX/actions/runs/42438754541), **SUCCESS, 9/9 tests**, auditor Python Decimal 60, sintaxis Node/Python, SHA del generador congelado M9 y hashes Git de fuentes P9E.
- Benchmark en GitHub Actions de 3.000 puentes: **8,099976 ms**, una medición de runner, no latencia operacional.
- Comprobación de tipos focal local: `tsc --noEmit --allowJs --checkJs --skipLibCheck --target es2022 --module commonjs --typeRoots ...`, sin errores; esa comprobación de tipos **no** forma parte del workflow remoto.
- Auditor contable independiente: el nuevo verificador Decimal confirma la aritmética del ejemplo de dos patrimonios publicados; **no reaudita** todas las operaciones del simulador ni sus recibos. La deuda histórica de P9B por un evento de valoración IOC `NO_FILL` continúa abierta.
- Código nuevo aditivo, sin modificar el motor M9, parámetros, costes, señales ni fuentes históricas. **0 cuentas económicas, 0 semillas nuevas, 0 alfa gastado y 3.200 finales M10 sin abrir**. CASH y candidato previo se preservan sin reejecución. N9-S sigue NO_GO y los gates de ejecución y multicelda siguen incompletos.

## 5. Siguiente unidad propuesta (no iniciada)

`M11_PHASE9F_POSITIVE_CREDIT_WEAK_POPULATION_BOUNDS`: definir una cota **poblacional** del crédito terminal positivo en la ley M9 con las dos admisiones endógenas, usando inventarios previsibles, reservas y saldo autofinanciado; aislar la discrepancia de precios OHLC no alcanzables, controlar colas de `1/W_C` y demostrar qué condiciones son verificables. Si se demuestra que no hay tal acoplamiento sin cambiar el replay nativo, documentar la refutación; no abrir señales ni el final.
