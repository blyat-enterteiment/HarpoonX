# HARPOONX FWN9 — Fase 9M-C13: acoplamiento de riqueza causal por ventanas de 72 horas

**Resultado de esta unidad:** se demuestra una identidad contable **exacta por trayectoria** en un libro autónomo de dos carteras con diferentes entradas, cantidades, activos y recibos, particionado en ventanas contiguas de hasta 72 horas. Se refuta una hipótesis precisa: **72 horas no proporciona un máximo determinista uniforme del rango de precios bajo la ley lognormal WEAK**. No se deriva una cota poblacional no vacua del rendimiento del replay; **N9-S sigue sin acreditación**.

## 1. Identidad económica sin emparejar operaciones

En un calendario común de precios publicados `S_{a,t}`, una cartera larga autofinanciada `j` con inventario `q^j_{a,t^-}`, cambios ejecutados `dq^j_{a,t}`, precio de fill `P^j_{a,t}`, comisiones `F^j_t` y cargos externos `C^j_t`, satisface:

```
dW_j = sum_a q_j_before[a] * dS[a]
     + sum_a dq_j[a] * (S[a]-P_j[a])
     - fees_j - external_j
```

Si `D_t=W_NATIVE,t-W_FIRST_CROSS,t`, entonces en cualquier ventana `[u,v)`:

```
D_v-D_u = sum_{[u,v)} (q_NATIVE-q_FIRST_CROSS) * dS
        + sum_{fills in [u,v)} [dq_NATIVE(S-P_NATIVE)-dq_FIRST_CROSS(S-P_FIRST_CROSS)]
        - (fees_NATIVE-fees_FIRST_CROSS)
        - (external_NATIVE-external_FIRST_CROSS)
```

Esta identidad **no requiere cantidades, decisiones ni órdenes comunes**. Su validez exige caja física, inventarios, fills y marcas coherentes y no legitima precios ejecutables inventados. Las marcas nuevas sólo entran al auditor en `availableAt`; los recibos tienen `at` económico y `knownAt` de conocimiento, conservados por separado. **La contabilidad económica retrospectiva no se entrega a la decisión de admisión.**

Para cada ventana se obtiene el límite determinista superior de diferencia de riqueza:

```
D_v <= D_u + suma_de_los_componentes_positivos_de_sus_eventos
```

El resultado se agrega a través de ventanas contiguas **sin reiniciar capital ni borrar posiciones abiertas en la frontera**. Este límite depende de la trayectoria observada; **no** es una cota de esperanza WEAK, ni se usa una probabilidad inventada de eventos.

## 2. Falsificación estructural del supuesto de rango local constante

La normal idiosincrática de WEAK tiene varianza estrictamente positiva. Condicionando los restantes factores a un evento de soporte positivo, para cualquier `M<infinito`, `P(S_v/S_u > M)>0` en un segmento con innovaciones normales no degeneradas. Por ello, incluso una ventana de 72 horas **no admite un techo fijo de razón de precios con probabilidad uno**. Una vía que sustituya el rango local por un `M` determinista, sólo por la duración de la ventana, queda refutada.

Esta prueba **NO** rechaza cotas estocásticas de momentos ni demuestra imposibilidad de N9-S; simplemente identifica qué premisa de la formulación ingenua es falsa. El rango global C10/C11 permanece descartado por su excesiva holgura y no se reactiva.

## 3. Fixture de ingeniería y conciliación independiente

Dos libros financiados de USD 20.000, símbolos SYNA/SYNB, comisiones nominales y cargos de calendario idénticos, negocian **distintos activos, tamaños y relojes** en tres ventanas hasta el terminal. La cartera nativa abre 8 SYNA, toma 2 parciales, liquida 6 tras cruzar la frontera de 72 h, y luego abre 4 SYNB. La contracartera abre 5 SYNB, luego 9 SYNA y registra otro IOC NO_FILL. Ninguna operación se copia de un libro al otro.

| Resultado de fixture determinista | USD |
| --- | ---: |
| Patrimonio final del libro nativo | **19.946,56** |
| Patrimonio final del libro contrafactual | **20.048,49** |
| Diferencia nativo menos contrafactual | **−101,93** |
| Límite superior por componentes positivos | **+29,50** |

La desigualdad `-101.93 <= +29.50` es exacta en su alcance, pero **demasiado holgada para certificar un rendimiento poblacional**. La identidad de incrementos por ventana se verifica con residual máximo de 0,000001 USD y por segunda implementación independiente Python Decimal de 46 dígitos sobre **23 eventos**. La última ventana vacía no revalúa retroactivamente ni reinicia riqueza: esa corrección fue motivada por la CI fallida.

Se realizó adicionalmente una prueba de integración usando **campañas generadas por el replay nativo** y una contracartera con propia admisión y salidas al primer cruce sobre fixture construida. Las cuentas terminales conciliaron; esto no demuestra correspondencia universal ni mercado observado.

## 4. Calidad, errores conservados y alcance

[CI final v4 42535658934](https://github.com/blyat-enterteiment/HarpoonX/actions/runs/42535658934): **9/9 tests Node PASS**; Ruff PASS; mypy estricto PASS; contabilidad Decimal46 independiente PASS; integridad Git de todas las fuentes C13 y SHA256 de tres fuentes M9 registradas PASS. Benchmark de 1.000 libros: **103,363 ms** en runner, sólo indicativo.

Se preservaron tres intentos fallidos y sus protocolos/fuentes versionadas:
- CI 42535258081: 5/9; cierre de ventana posterior al último evento omitido.
- CI 42535394982: 5/9; el diagnóstico localizó `window[1].closingDifferenceUsd=null`.
- CI 42535528683: 9/9 Node + Decimal PASS; verificador de fuentes confundía el protocolo de preregistro C13 con el contrato congelado M9.

Fuentes finales: `runtime30/fwn9_p9m_c13_local_coupling_v3.cjs`, `tools/fwn9_p9m_c13_test_v3.cjs`, `tools/fwn9_p9m_c13_decimal_accountant_v3.py`, `.github/workflows/fwn9_p9m_c13_v4.yml`, `evidence/modulation11/fwn9_phase9m_c13.json`. Protocolo previo a resultados: `research/modulation11/fwn9_phase9m_c13_protocol.json`. Los hashes verificados están en el JSON de evidencia.

No se alteraron ley WEAK, generación de precios, capital USD20.000, 12% de **admisión/reserva (no exposición continua)**, riesgo abierto del 0,25%, drawdown 8%, pérdida diaria 2%, costes, máximo 72 h, umbral 1 pb/día ni el holdout M10 (3.200 cuentas sin abrir). **Cero nuevas cuentas económicas, cero nuevas semillas, cero alpha prospectiva**. Sin brokers, órdenes, despliegues ni merge. La automatización queda pausada.

## 5. Conclusión científica y puerta siguiente

**La condición de refutación solicitada para C13 queda satisfecha únicamente para la hipótesis de cota determinista local uniforme derivada de la duración del hold.** Se obtiene una identidad financiera local verificable y un contraejemplo a su sustitución por una constante de rango. **No hay demostración estocástica WEAK no vacua del motor nativo** y sigue prohibida su promoción a N9-S.

El siguiente problema materialmente distinto sería derivar un *control de momentos condicional de inventario/riqueza* por ventanas <=72 horas, bajo precios de ejecución cuya alcanzabilidad esté especificada, y probar que la desigualdad de esperanza resultante es cuantitativamente más ajustada que 1 pb/día. Debería incluir el acoplamiento de admisiones independientes y los dos gates operativos pendientes (parciales/rechazos/outages/impacto y coordinador multicelda). No habilitar exploración económica sin protocolo y señal de factibilidad nueva.
