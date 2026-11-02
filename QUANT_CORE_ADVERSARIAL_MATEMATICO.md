# Qué falta para acertar y acreditar 8: confrontación matemática

No se necesitan más indicadores para formular mejor el problema. Tampoco puede
un optimizador crear esperanza positiva a partir de entradas netas negativas.
Esta entrega implementa y prueba una alternativa matemática acotada; no acredita
8, mayor precisión predictiva ni mejora económica histórica. No descarga datos,
no ensaya otra estrategia y no cambia el core sellado ni el runtime/broker.

## 1. Escalar: acierto no equivale a ventaja

Con W y L como ganancia y pérdida media por trade **después de variables**, p
como frecuencia de ganadores, n trades y F infraestructura compartida:

    PnL = n[p W - (1-p)L] - F
    p_equilibrio = (L + F/n)/(W+L)

En este banco no se imputan nuevamente variables porque ya están en W y L.
La relación es contabilidad descriptiva, no una estimación prospectiva de p.
Cambiar tamaños, frecuencia o entradas cambia W,L y la dependencia: no basta
subir p o multiplicar posiciones. La fórmula presupone trades no nulos y misma
mezcla de tamaños; el resultado no es una tasa objetivo ya validada.

| Regla nominal 2025 | Acierto observado | W USD | L USD | F/n USD | p equilibrio |
| --- | ---: | ---: | ---: | ---: | ---: |
| Gap confirmado |53.19%|23.79|14.14|7.77|57.74%|
| MACD anticipado |50.00%|28.33|23.13|22.81|89.29%|

Para gaps podría estudiarse mejorar selectividad o asimetría de pagos; para
MACD anticipado exigir89% de acierto manteniendo todo lo demás es una mala
base de diseño. La solución es evaluar ganancia/pérdida/tamaño/frecuencia netos,
no prometer esa tasa. Tampoco aumentar trades a costa de calidad para amortizar F.
En gaps, conservando53.19%de acierto y número de trades, el equilibrio exige
W≈27.04USD en lugar de23.79USD, o L≈10.45USD en lugar de14.14USD, cambiando
sólo uno de ellos. Son fronteras contrafactuales: no se ha demostrado poder
modificar esos pagos manteniendo todo lo demás.
Estos números están condicionados al coste fijo supuesto, no calibrado con facturas.

## 2. Vectorial: hallazgos del código existente

HECHO: `core.allocate` construye robust[i] restando incertidumbre por candidato
antes del MILP. Eso es una formulación conservadora separable: no es incertidumbre
conjunta de la media de la cartera. Su conveniencia depende del modelo de error.
No se demuestra que esa elección haya causado las pérdidas históricas.

HECHO: `robust_core.allocate` llama ese solver y luego certifica los lotes
finales. Si falla el certificado, bloquea todo. No reoptimiza otra combinación
que pueda ser factible; no convierte los ajustes del certificado en objetivo.

HECHO: el objetivo legacy combina PnL robusto y penalización CVaR, no crecimiento
logarítmico neto. Los costes fijos del instrumento no equivalen automáticamente a
infraestructura compartida del patrimonio completo. La certificación legacy sigue
siendo útil y no se sustituye en producción por este prototipo.

SOLUCIÓN IMPLEMENTADA: `quant/harpoon_quant/vector_gate.py`, investigación exacta
sobre una malla finita pequeña de lotes enteros, incluyendo CASH. Revalora cada
alternativa tras costes, incertidumbre y restricciones. Puede devolver una
combinación distinta en vez de limitarse a aceptar la propuesta anterior o CASH.

    π[t,s,q] = P[t,:,s] q - c[:,s] q - f[:,s] 1(q>0) - F[s]
    J(q) = min_s { media_t log(1 + π[t,s,q]/E)
                       - z sqrt(q' V[s] q)/E }

P: USD brutos por lote; c: variables por lote; f: fijo de activación por campaña;
F: fijo compartido una vez por horizonte; E: patrimonio USD. q entero no negativo.
Cada coste debe estar definido sin duplicar el que ya incorpora una valoración.
V es covarianza estimada de la media, en USD² por lote². El objetivo es adimensional.
La resta de incertidumbre logarítmica es una penalización local; no es un intervalo
de confianza exacto ni una garantía de crecimiento geométrico.

Para propuestas no nulas exige además media neta−zSE>0 **en cada escenario**,
funding y costes reservados, número de posiciones, límites lineales A q≤b,
solvencia en escenarios y CVaR conservador ante llenados parciales. No permite
que ganancias de una pata propuesta financien pérdidas de otra todavía no llena.
Los límites de factores, activos y exposición deben suministrarse explícitamente
en A,b; no se presume que una matriz vacía los imponga.

La matriz de incertidumbre Bartlett HAC se construye sobre filas originales,
no sobre repeticiones bootstrap. Si H es HAC e I la covarianza IID:

    V = [ I + PSD_positive_part(H-I) ] / T

Así V−I/T y V−H/T son PSD. Es un suelo conservador matricial, no un máximo
por elemento que pueda producir una matriz indefinida. No elimina sesgo,
cambios de régimen ni multiplicidad del historial global de investigación.

La búsqueda enumera completamente la malla admitida: máximo6 instrumentos,
8 escenarios,2000 filas y50000 combinaciones, además de un máximo conjunto de
20millones de elementos procesados (T×N×S×combinaciones). Rechaza presupuesto mayor; no usa
una búsqueda truncada y la llama óptima. El certificado sólo da optimalidad
respecto de esa malla, esos datos y restricciones, no del mercado ni de una
cartera continua o con posiciones existentes. No adopta holdings abiertos.
La autenticidad, cronología y originalidad de P son responsabilidad de una
capa anterior: una matriz numérica no puede certificarlas por sí sola.

## 3. Tensorial: organizar riesgo, no fabricar información

La auditoría construye un tensor **365 fechas×6 estrategias×2 costes** de curvas
existentes. El diagnóstico nominal tiene rango6, rango espectral efectivo4.08 y
primer componente42.51%de varianza. Describe dependencia entre PnL de estrategias;
no estima correlación entre indicadores ni prueba seis fuentes de alpha.

Son curvas de cuentas completas, cada una financiada con20000USD: **no se usan
como PnL por lote ni se suman para inventar otra cartera financiada**. El tensor
sirve para diagnóstico. El allocator requiere otro contrato: panel causal de
USD por lote, mismo horizonte y fechas originales, no curvas escaladas a gusto.

Un tensor adicional activo×estado×horizonte sólo ayuda si sus celdas tienen
muestras suficientes y cálculo causal. Añadir dimensiones con pocas observaciones
agrava la estimación. No se introdujeron redes tensoriales, GPU ni computación
cuántica: el problema aquí es estadístico y de decisión, no hardware cuántico.

## 4. Pruebas, límites y criterio de avance

Validación:551pruebas de la suite quant completa aprobaron antes de añadir el
último límite de trabajo;11casos específicos finales también aprobaron.
Compilación sintáctica ejecutada; lint y verificación formal de tipos no ejecutados.
No se afirma CI remota ni mejora de rentabilidad.

Casos adversos: ventajas negativas→CASH; estrés negativo→CASH; fijo de activación
una vez aunque aumenten lotes; fijo compartido no oculto; reserva de fees;
reoptimización al descartar una pata; covarianza PSD y suelo IID; presupuesto y
dimensiones inválidos; límite lineal de factor; protección frente a hedge sin
llenado simultáneo. El ejemplo de dos patas compensadas es explícitamente
sintético: demuestra formulación y selección, no alpha observado.

`tools/audit_vector_core.py` genera métricas, hashes, diagnóstico y benchmark
sobre el banco ya archivado. `evidence/vector_core/audit.json` conserva resultados.
El benchmark mide una malla sintética mínima, no escalabilidad ni latencia live.
No se han cambiado umbrales después de ver otro backtest ni declarado una nueva
estrategia ganadora. Verificar código no equivale a validar resultados futuros.

```sh
PYTHONPATH=quant OPENBLAS_NUM_THREADS=1 python3 -B -m unittest discover \
  -s quant/tests -p test_vector_gate.py -v
OPENBLAS_NUM_THREADS=1 python3 -B tools/audit_vector_core.py
```

Para8 faltan: señal/calibración cuya expectativa neta y asimetría se sostengan;
cartera financiada con ventaja conjunta que cubra F; selección con incertidumbre
fuera del conjunto usado para elegirla; ejecución y contabilidad reconciliadas.
Primero se puede corregir la matemática con este banco, como aquí; los números
que faltan no se pueden deducir mediante álgebra sin evidencia. El módulo nuevo
es optativo y de investigación: execution_allowed, liveApproved y level8_accredited
permanecen falsos. No está conectado al broker ni sustituye el core de runtime.

Referencias primarias de formulación, sin aval del proyecto:
[Boyd y Lobo, costes lineales y fijos](https://web.stanford.edu/~boyd/papers/portfolio.html),
[Boyd et al., multi-period trading](https://stanford.edu/~boyd/papers/cvx_portfolio.html).
