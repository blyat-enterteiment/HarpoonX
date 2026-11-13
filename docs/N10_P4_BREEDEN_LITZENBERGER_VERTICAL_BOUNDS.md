# HARPOONX N10-P4 — Cotas de colas implícitas y selección causal

**Veredicto de alcance: ingeniería P4, no acreditación de N10, N9-S ni rentabilidad.** Una única unidad de investigación; cero cuentas económicas, cero semillas de mercado, ningún holdout abierto. La rama N9 que mantiene el lease C14 es independiente e intocable.

## Hipótesis materialmente distinta

En vez de ajustar las señales a las grandes PUTs ganadoras retrospectivas de enero–abril 2025, contrastar una medida robusta de la **distribución física P** calculada antes de decidir con un **intervalo identificable de la distribución neutral al riesgo Q** extraído de cotizaciones de opciones europeas en dos strikes. Si la banda implícita está demasiado ancha, o la expectativa inferior no paga bid/ask, fricción, riesgo y error de modelo, la salida obligatoria es `CASH`.

El motor no afirma poder extraer la densidad puntual q(K), porque sólo recibe dos strikes. Para calls europeas del mismo vencimiento:

\[
C(K_1)-C(K_2)=D_T\int_{K_1}^{K_2}\mathbb Q(S_T>k)\,dk.
\]

Por lo tanto, dividir el vertical entre \(D_T(K_2-K_1)\) identifica **la probabilidad de cola promediada por strikes**, no \(\mathbb Q(S_T>K_1)\) ni \(\mathbb Q(S_T>K_2)\) individualmente. Para puts, la relación simétrica utiliza la CDF promediada.

Las cotizaciones bid/ask (firmes, conocidas y con tamaño positivo) proporcionan una **banda**, no una probabilidad única. Una call spread larga paga como mínimo `ask(K1) - bid(K2)`; una posición opuesta cobra `bid(K1) - ask(K2)`. El motor calcula el intervalo y rechaza arbitrajes estáticos seguros. Un spread PUT utiliza comprar la put de strike alto y vender la put de strike bajo.

Cuando hay ambas, un vertical CALL y uno PUT con iguales strikes y vencimiento suman exactamente una constante: \(V_C+V_P=D_T(K_2-K_1)\). Se verifica la existencia de un valor dentro de las bandas ejecutables. Los intervalos adyacentes se verifican contra monotonía de la supervivencia/CDF (convexidad en strike).

## Capa robusta de probabilidades físicas

Si los escenarios conocidos en la decisión contienen \(s_i, p_i\), cada vertical produce el pago terminal normalizado \(f_i\in[0,1]\). La expectativa física robusta es

\[
\underline{\mu}_P = \inf_{q:\,D_{KL}(q\Vert p)\le\rho} \sum_i q_i f_i.
\]

Se resuelve con una inclinación exponencial y búsqueda por bisección de su multiplicador, sin aproximaciones normales. `rho=0.02` es una **prueba de sensibilidad**, no una región de confianza empírica calibrada. La selección no puede interpretarse como significación estadística sin demostrar cobertura prospectiva, y el modelo P puede estar mal especificado.

El comparador exige que la expectativa física inferior, después del descuento aplicado, exceda el extremo superior de Q y el total de fricciones, **además de** exigir crecimiento logarítmico robusto positivo. Es un filtro deliberadamente conservador. No se usan precios futuros en la selección, no hay reentrenamiento recursivo ni conexión a brokers.

## Contrato de riesgo y ejecución

* Sólo contratos XSP/SPX europeos con liquidación monetaria; las opciones SPY de ejercicio americano quedan explícitamente rechazadas para esta identidad. Multiplicador $100.
* Vencimiento dentro de 72 horas a partir de la decisión; se usa pago en expiración, no una supuesta cotización futura inventada. Los registros deben ser como máximo 120 segundos anteriores a la decisión.
* Una sola unidad del vertical, financiada, con riesgo contractual limitado a 0,25% del patrimonio disponible menos riesgos previamente comprometidos; compromiso al admitir inferior al 12% del patrimonio. El 12% **no** es límite continuo de exposición.
* Entrada long spread por ask de la pierna comprada y bid de la vendida; $0,01 de slippage por pierna más $0,65 por pierna y lado (conservador para la liquidación). La convención es **hipotética de ingeniería**; no acreditamos que esos costes coincidan con un mercado real de XSP, ni que se puedan cruzar ambas piernas simultáneamente.
* `CASH` si el motor no puede acreditar ventaja bajo el modelo, si falla un control o si el contrato entero no cabe en presupuesto. No se aumenta el capital, apalancamiento o límite de riesgo para forzar fills.

## Controles que faltan antes de cualquier evaluación financiera

1. Datos XSP/SPX originales y autorizados de bid/ask **sincronizados** con tamaños negociables, tasas, vencimientos exactos y timestamps; reconstrucción de paquetes de ejecución y liquidez simultánea. Los cuatro meses SPY ya inspeccionados no son holdout y no validan el modelo europeo.
2. Integrar forecasts P3 conocidos antes de cada decisión con pruebas de no-leakage; comparar con climatología, precio implícito Q, y `CASH`.
3. Calibración OOS del radio KL con bloques sin contaminación de posiciones hasta 72 horas; un menor Brier no implica una ventaja de trading.
4. Muestra prospectiva independiente y preregistro de horizonte, universo, variantes, cuotas, alpha, costes y riesgo. Si los datos están vistos, análisis sólo descriptivo.
5. Auditoría contable separada, matriz completa de fills parciales/rechazos/outages/impacto y coordinador de cartera virtual. Dos gates de N9-S siguen pendientes.

## Referencias primarias

* Breeden y Litzenberger, *Prices of State-Contingent Claims Implicit in Option Prices*, *Journal of Business*, 1978. https://doi.org/10.1086/296025
* Cboe, **XSP Options Product Specification**: https://www.cboe.com/tradable_products/sp_500/mini_spx_options/specifications
* Cboe, **Product Comparison**: https://www.cboe.com/tradable-products/product-comparison

## Reproducibilidad

```bash
PYTHONPATH=. python -m unittest discover -s tests -p 'test_n10_vertical_bounds.py' -v
PYTHONPATH=. python tools/n10_p4_verify.py
python -m compileall -q quant/harpoon_quant/n10_vertical_bounds.py
```

Las pruebas contienen fixtures **sintéticos y etiquetados**, no resultados de mercado. No hay artefactos de precios reales ni PnL N10 nuevo en P4.
