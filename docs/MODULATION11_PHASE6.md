# HARPOONX M11 — Fase 6: cota condicional en esperanza del crédito OHLC

**Veredicto:** un teorema para una barra WEAK, con inventario largo determinado antes de los movimientos de la barra, permite acotar la **esperanza condicional del crédito positivo nativo**. Sin embargo, la cota resulta ampliamente insuficiente para acreditar o descartar N9-S en campañas con admisiones y salidas endógenas. **NO_GO**; no hay señal nueva, ejecución real ni validación prospectiva.

## Fórmula y alcance

Sea `F_0` toda la información disponible en la apertura. Se fija en esa información la cantidad entera `Q≥0` (sin nuevas compras en esta barra), y el precio `S_0>0`. Se comparan los resultados al cierre de **una barra** de cinco minutos, con la **misma caja e inventario inicial**, de la ejecución retrospectiva OHLC y el primer cruce observable de sus ocho precios.

La ley congelada WEAK para cada activo es `S_k=S_0 exp(mu*k/8) M_k`, donde `M_k` es la exponencial del ruido gaussiano compensado y una martingala condicional al shock de volatilidad. El multiplicador de sigma por barra es 1 con probabilidad 0,996 y 4 con probabilidad 0,004. Se aplica el mayor módulo permitido de drift `mu`, el factor WEAK de 1,25, el máximo de actividad `exp(0.7)` y el máximo de escala final 1,20; estos extremos preservan el soporte del generador, no modifican sus parámetros.

Por Doob L² y Jensen para cada shock:

`E[max_k |M_k-1|] ≤ 2 sqrt(expm1(sigma²))`.

Se sigue `E[(H-L)/S_0] ≤ 2 A` y `E[H/S_0] ≤ 1+A`, con `A=0.996 d(sigma)+0.004 d(4sigma)` y `d(s)=2 exp(mu) sqrt(expm1(s²))+expm1(mu)`. La monotonía de los precios de venta netos, comisión por acción y tick lleva a:

`E[(W_OHLC-W_subpasos)^+ | F_0] ≤ Q S_0 [2A+f(1+A)] + Q[tick(1+1e-8)+comisión_de_venta]`.

Donde `f=(spread/2+slippage)/10000` corresponde al mismo escenario. Un coste fijo de calendario idéntico entre ambas cuentas se cancela **en el diferencial por barra**, no se elimina de la contabilidad de campañas. Esta afirmación es válida con señales causales que seleccionen `Q` antes de la barra: no requiere que `Q` sea independiente de los precios anteriores. Sí requiere que la mezcla de volatilidad nueva sea independiente de esa información. No exige independencia entre SYNA y SYNB: se suma mediante subaditividad.

## Magnitudes verificadas, no rentabilidades

Ejemplo fijo construido: Q=8 SYNA a 100 USD, Q=7 SYNB a 150 USD, ambos inventarios conocidos desde la apertura. Las cotas máximas analíticas del **crédito positivo esperado condicional de una sola barra** son:

| Parámetros | SYNA (USD) | SYNB (USD) | Suma (USD) |
|---|---:|---:|---:|
| Desarrollo NOMINAL | 6.5148 | 9.5683 | **16.0832** |
| Desarrollo STRESS | 6.7958 | 9.9197 | **16.7155** |
| Final NOMINAL (extremo del soporte, sin abrir semillas) | 7.7418 | 11.3928 | **19.1346** |
| Final STRESS (extremo del soporte, sin abrir semillas) | 8.0229 | 11.7444 | **19.7673** |

Un inventario meramente ilustrativo de 2.400 USD de SYNA (`Q=24` a 100 USD, sin afirmar exposición continua) tiene una cota de **23.2255 USD** en una barra nominal al extremo final. El margen restante entre la cota WEAK *idealizada* previa y el hurdle nominal registrado es **0,0948767530 pb/día**, equivalente linealizado a unos 0,18975 USD/día sobre 20.000 USD iniciales. Estos números **no son magnitudes directamente comparables**: el primero es un límite muy laxo de un pago positivo por barra y el segundo una diferencia de crecimiento logarítmico diario. Sí muestran que la vía de demostrar imposibilidad usando sólo este momento L² no es suficientemente precisa.

Un evento realizado puede superar la cota **en esperanza** sin contradecirla: la fixture de fase 5 tiene un diferencial realizado de 15,66 USD con ocho acciones, mientras que su cota condicional analítica es 7,7418 USD. Por ello ningún resultado usa el momento como límite por trayectoria.

## Qué se comprobó

GitHub Actions: **run `42419670499`, SUCCESS, 8/8 tests**, `tsc --checkJs` específico del módulo, `node --check`, conciliación independiente Python Decimal de 42 dígitos (`19.134593305192985...` USD), chequeos de hashes del origen congelado, microbenchmark de 3.000 invocaciones (**20,37214 ms**, medición indicativa de un runner).

Archivos: `runtime30/modulation11_conditional_credit_bound.cjs`, `tools/modulation11_phase6_test.cjs`, `tools/modulation11_phase6_accountant.py`, `research/modulation11/phase6_protocol.json`, `.github/workflows/modulation11_phase6.yml`, `evidence/modulation11/phase6_conditional_credit.json`. Checksums en el JSON. No se cambiaron código ni fuentes económicas previas. La revisión tipada aquí es focal, no toda la suite histórica.

## Bloqueo para N9-S

El modelo nativo decide reentradas, cantidades y salidas con dependencia de la trayectoria; las cuentas nativa y causal divergen después de una ejecución distinta. **No se puede sumar esta cota de una barra sustituyendo siempre Q S_0 por 12% de la equity:** el 12% controla admisión y reservas, no exposición continua. Falta una desigualdad global para `E sum_b Q_b S_{b,0}` condicionada a toda la historia y una conciliación universal de la cartera/eventos. Tampoco hay prueba de que un umbral OHLC interpolado sea una orden realmente ejecutable. La supuesta cota global de 0,9051232469572758 pb/día sigue condicionada a estas equivalencias.

Siguiente unidad: **M11_PHASE7_ENDOGENOUS_MULTI_BAR_INVENTORY**: probar o refutar un acoplamiento de inventario/caja autofinanciado en el replay completo, con distintos relojes IOC, cierres y reservas; si no existe, documentar un modelo de ejecución causal versionado y contrastarlo sin alterar resultados históricos. No se abre una nueva cuadrícula de señales mientras no exista contrato económico válido.

0 cuentas económicas nuevas; 0 alfa prospectivo; final M10 de 3.200 cuentas sin abrir. No hubo órdenes, despliegue ni fusión. La PR #7 queda en borrador; persisten las brechas operativas (entrada parcial, rechazo, interrupción, impacto y multicelda) y una discrepancia histórica SHA-256 de la suite general, independiente de la comprobación focal.
