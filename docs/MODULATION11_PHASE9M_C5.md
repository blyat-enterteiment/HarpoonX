# FWN9 — M11 fase 9M-C5: límite estocástico de crédito de stop por barra

**Resultado:** demostración analítica de una cota **condicional a una barra**, con ley WEAK original y mezcla de volatilidad, reproducida y verificada con cuadratura independiente; **no hay certificación de una cota total del patrimonio nativo ni de imposibilidad N9-S**.

## 1. Problema y contrato preciso

El motor nativo OHLC puede vender un stop al nivel de la barrera aunque el primer subpaso discreto esté por debajo. Bajo el mismo stop inicial `H`, las mismas `q` acciones largas (predecibles antes de empezar la barra), los mismos targets y los costes originales, se aísla el **crédito positivo de interpolación del stop** respecto de la venta al primer precio discreto que cruza. Esto no incluye cambios posteriores de posiciones ni elecciones endógenas divergentes, y una interpolación continua no acredita liquidez real.

Si el precio anterior `S_prev>H` y el siguiente subpaso `S_next<=H`, el sobrepago bruto por título del stop OHLC satisface:

`0 <= H-S_next <= (S_prev-S_next)_+`.

La prioridad stop-first del motor no puede convertir en un crédito positivo una venta parcial anterior a target (precio superior a H); a favor del nativo queda acotado por el sobrepaso adverso del stop sobre las acciones restantes. Con fricción de venta `f`, el redondeo al tick puede añadir estrictamente menos de **un tick por acción**. El caso de gap ya bajo el stop a la apertura no produce crédito interpolado: ambos modelos usan la apertura.

La suma de caídas observadas de los ocho subpasos domina trayectoria por trayectoria cualquier único exceso de pago de stop dentro de esa barra. Se comprobó sobre todas las **5.040 ordenaciones** de la fixture previa, independientemente del precio específico de la barrera.

## 2. Cálculo normal exacto

La ley registrada por subpaso es:

```text
log(S_next/S_prev) = (d - sigma_bar²/2)/8 + sigma_bar Z/sqrt(8)
Z ~ N(0,1)
```

Con `h=H/S_prev <=1`, `mu=(d-sigma_bar²/2)/8` y `s=sigma_bar/sqrt(8)`, el valor esperado condicional por unidad del precio anterior es el valor de un put lognormal de un paso:

```text
L(h,d,sigma) =
 h * Phi((ln(h)-mu)/s)
 - exp(d/8)*Phi((ln(h)-mu-s²)/s)
```

La función es creciente en `h`, así que `L(h,d,sigma) <= L(1,d,sigma)`. Para construir una cota uniforme favorable al crédito se usa `d_min = -0.000025*1.10` y sigma máximo WEAK sobre dos activos: `sigma0=0.00085*1.25*1.20*exp(0.7)`. La mezcla multiplicadora 4 afecta a cada barra y activo con probabilidad registrada `0.004`; es independiente de las innovaciones de precio de esa barra y del estado anterior, según la ley idealizada.

Por tanto, para cantidad `q` aprobada causalmente antes de la barra, y precio de apertura `S0`, la siguiente **desigualdad condicional por barra** es válida bajo esas premisas:

```text
E[credito_positivo_stop_barra | F_antes_de_barra]
<= q*S0*(1-f)*B + q*tick

B = sum(k=0..7) exp(k*dmax/8)
    *[0.996*L(1,-dmax,sigma0)
      + 0.004*L(1,-dmax,4*sigma0)]
```

No se necesita independencia entre los activos: se usan sus marginales normales. Para el capital conjunto sólo pueden agregarse estos límites si las cantidades son predecibles y se controla su exposición en cada barra; el 12% original es **admisión/reserva**, nunca límite continuo.

## 3. Valores analíticos verificados

| Cantidad | Resultado |
|---|---:|
| sigma máximo de barra, componente ordinario | 0.002567534702 |
| `L` un paso con sigma ordinaria | 0.0003638647923 |
| `L` un paso con sigma multiplicada por cuatro | 0.001450292445 |
| `L` integrado con mezcla 0.004 | 0.0003682105029 |
| **B**, crédito bruto máximo condicional de una barra / notional inicial | **0.002945719464** |
| Ejemplo hipotético: exposición del 12% al comienzo de una barra a precio 100, fricción y tick originales | **3.653803 pb del patrimonio por barra** |
| Holgura entre límite previo WEAK y hurdle nominal | **0.094876753 pb por día calendario** |

El ejemplo con 12% es meramente **ilustrativo de una barra**; no prueba que tal exposición persista durante el replay ni que esa prima se materialice. Los 3.65 pb/barra no se pueden sumar directamente a la cota de 0.905123 pb/día sin una demostración de frecuencia esperada de stops, inventario, precios de apertura, recibos, financiación, riesgos y agregación de log-riqueza. El límite es deliberadamente conservador. **El cálculo no basta para excluir ni acreditar N9-S.**

## 4. Código, pruebas y preservación de errores

- Código analítico: `tools/fwn9_p9m_c5_credit_bound_v2.py`; pruebas adversariales y cuadratura independiente: `tools/test_fwn9_p9m_c5_credit_bound_v2.py`. Generador M9, universo, costos y umbrales inalterados.
- Protocolos separados preregistrados: `research/modulation11/fwn9_phase9m_c5_protocol.json`, `fwn9_phase9m_c5_v2_protocol.json`, `fwn9_phase9m_c5_v3_protocol.json`. Cada intento conserva su fuente y workflow; no se sobrescriben resultados.
- Primer intento CI **42482339371**, FAIL de tipado estricto (contrato JSON y anotación de fixture). Segundo intento **42482488223**, FAIL en verificador de protocolo (`budget` vs `economic_budget`): cuadratura y seis pruebas matemáticas PASS. Se mantuvieron ambos cargos de ingeniería (0 cuentas económicas).
- [CI verificadora v3 42482593082](https://github.com/blyat-enterteiment/HarpoonX/actions/runs/42482593082): **6/6 pruebas unitarias**, Ruff PASS, mypy estricto PASS, cuadratura Simpson independiente PASS, 5.040 desigualdades por trayectoria PASS, SHA-256 y Git blob integridad PASS, hash generador M9 original PASS; benchmark **5.000 certificados en 31,73 ms**, informativo.
- SHA-256 concretos y resultados en `evidence/modulation11/fwn9_phase9m_c5.json`.

No se evaluaron caminos de mercado M9/M10 ni se tocaron las 3.200 cuentas finales M10. CASH y el mejor candidato previo permanecen como controles congelados, no reevaluados en esta fase. 0 candidatos nuevos; 0 alfa prospectiva; no brokers, órdenes, despliegues, merge ni terceros.

## 5. Siguiente unidad C6: convertir la cota local en presupuesto de crédito de cartera

`M11_PHASE9M_C6_ENDOGENOUS_EXPOSURE_CREDIT_BUDGET` deberá construir una cota sobre la suma de `q_t*S_open,t` de todas las barras con un stop potencial, con cantidades y riesgos endógenos, máximo 72 horas, recibos `knownAt` y fuentes de financiación separadas. Debe integrar el efecto de pagos OHLC/primer cruce, reentradas y cambios de política sobre el **logaritmo del patrimonio final**, conservando costes y controles. El número de barras potenciales no puede sustituir sin prueba al número esperado de stops y sus cantidades.

Si el crédito agregado demostrable unido a la cota de 0.905123 pb/día queda estrictamente por debajo de 1 pb/día con supuestos aplicables al nativo, la vía N9-S quedará matemáticamente bloqueada bajo el contrato original. Si no, conservar la restricción y continuar con una hipótesis estructural diferente. No fabricar resultados positivos.
