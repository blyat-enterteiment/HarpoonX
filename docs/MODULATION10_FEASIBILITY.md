# MODULATION10: factibilidad teórica del umbral en WEAK

## Conclusión y alcance

**La ley WEAK contiene una restricción económica que puede impedir la meta antes de elegir una señal.** Para una clase de cuentas con precios de ejecución coherentes, posiciones largas, caja no negativa, admisión total del 12% y tenencia máxima de 72 horas, se obtiene una cota superior de **0.905124 puntos básicos de log-crecimiento neto esperado por día calendario**. La cota utiliza simultáneamente el drift y la volatilidad máximos admitidos en la fase final, conoce favorablemente el régimen actual, omite todos los costes variables e incorpora el coste fijo nominal. Es inferior al umbral de **1 punto básico/día** registrado.

Con los parámetros de desarrollo la misma cota es **0.762839 pb/día**. Son cotas de una esperanza bajo supuestos declarados, no rentabilidades simuladas, máximos por trayectoria ni predicciones sobre mercados reales. Los valores están redondeados hacia arriba en este párrafo; la evidencia conserva los cálculos completos.

**Esto no certifica todavía la imposibilidad del replay nativo.** Faltan dos equivalencias entre el modelo de la demostración y su implementación: la valoración contemporánea del cap frente a las marcas disponibles y reservas anteriores al IOC, y la ejecución a precios del proceso frente al pago de umbrales interpolados mediante OHLC. Estos puntos pueden modificar la riqueza simulada aunque los precios subyacentes estén correctamente compensados. El resultado obliga a examinar esas equivalencias antes de atribuir a una nueva señal una supuesta superación de la restricción.

El diagnóstico no generó precios, no ejecutó políticas, no consultó resultados económicos para ajustar sus constantes y no alteró costes, hurdle ni generador. Verificó las **47 fuentes registradas** antes y después del cálculo. El artefacto reproducible es [feasibility.json](../evidence/modulation10/feasibility.json), producido por [diagnose_modulation10_feasibility.py](../tools/diagnose_modulation10_feasibility.py).

## 1. Contrato que se analiza

La especificación vinculante procede de [protocol.json de MODULATION9](../research/modulation9/protocol.json), su [registro](../research/modulation9/registration.json) y el generador [modulation9.py](../quant/harpoon_quant/modulation9.py). El diagnóstico fija sus identidades SHA-256 y rechaza cualquier diferencia; no reinterpreta una versión posterior como si fuera la ley examinada.

| Magnitud | Valor y significado |
|---|---|
| Capital inicial compartido | 20,000 USD para SYNA y SYNB; SYNM es benchmark |
| Dirección | Posiciones largas y caja, sin préstamo |
| Cap nativo | 12% de exposición total y por activo al admitir/reservar |
| Riesgo abierto | 0.25%; se relaja para construir una cota favorable |
| Tenencia máxima | 72 horas transcurridas |
| Coste fijo nominal | 1 USD por fecha calendario cargada |
| Periodo evaluado | 126 sesiones, del 18 de marzo al 9 de septiembre de 2024 |
| Denominador | 176 fechas calendario inclusivas, incluidos fines de semana |
| Rejilla | 78 barras de cinco minutos por sesión, ocho subpasos por barra |
| Umbral final nominal | Límite inferior ajustado mayor que 0.0001 de log-crecimiento neto diario |

El score de desarrollo positivo es otra condición: resta un error estándar ajustado por 1.645 a una media y exige superar cero. **Un score positivo no sustituye el hurdle nominal final de 1 pb/día.** Tampoco basta alcanzar ese valor como media puntual: el contrato exige el límite inferior ajustado y sus demás gates.

La cota estudia la esperanza poblacional que ese requisito busca respaldar. Una muestra finita puede producir una media o un intervalo aparente superiores por azar. Repetir búsquedas hasta observar ese evento no demuestra que la esperanza haya cambiado.

## 2. Ley exacta relevante y tratamiento nocturno

Para cada activo negociable, el régimen inicial toma valores −1, 0 y +1 con probabilidades 0.4, 0.2 y 0.4. En cada sesión puede refrescarse, pero la nueva extracción usa las mismas probabilidades. Por ello la distribución marginal permanece estacionaria. Los dos regímenes son independientes entre activos; la correlación de las innovaciones de precio no cambia este hecho. La probabilidad de que exista al menos un activo con drift positivo es

\[
p_A=1-(1-0.4)^2=0.64.
\]

La persistencia cambia la dificultad de inferir el régimen y la distribución de secuencias, pero no esta probabilidad. La cota concede conocer el régimen actual: incluye un oráculo causal de señal que no conoce precios futuros.

En WEAK, el parámetro positivo de drift por barra es \(\delta=2.5\times10^{-5}\), multiplicado por el factor de drift. En la fase final ese factor pertenece a [0.75, 1.10]. Un subpaso, con régimen \(r\), satisface

\[
\frac{S_{k+1}}{S_k}
=\exp\left\{\frac{\delta r-\sigma^2/2}{8}
                 +\frac{\sigma}{\sqrt8}Z_k\right\},
\qquad
\mathbb E[S_{k+1}/S_k\mid\mathcal F_k]=e^{\delta r/8}.
\]

La volatilidad por barra incluye el multiplicador 1.25 propio de WEAK, actividad máxima \(e^{0.7}\), factor final de sigma hasta 1.20 y una mezcla que multiplica sigma por cuatro con probabilidad 0.004. La actividad AR(0.88) se genera independientemente de las innovaciones normales de precios; no es retroalimentación de retornos pasados a volatilidad.

El overnight utiliza otro normal compensado y un salto común: 0.97 con probabilidad 0.003, 1.03 con probabilidad 0.003 y 1 con probabilidad 0.994. Ambos factores tienen media aritmética uno. **WEAK no tiene drift nocturno positivo.** El salto adverso adicional de 0.94 pertenece a GAP y no se incorpora falsamente a WEAK. Por concavidad del logaritmo, un overnight de media uno no añade log-crecimiento esperado positivo a una cartera causal sin préstamo. Sus colas sí pueden aumentar la exposición posterior y por eso aparecen en la cota de admisión.

## 3. Aproximación inicial y su límite

Si se supusiera, provisionalmente, una exposición continua del 12%, la cuenta de primer orden sería

\[
0.12\times0.64\times78\times\delta\times\frac{126}{176}
-\frac{1}{20000}.
\]

Da **0.572145 pb/día** con parámetros de desarrollo y **0.679360 pb/día** con drift final máximo. La primera contribución corresponde a sesiones negociadas; el coste se cobra también en fechas sin negociación. Este cálculo es una aproximación: trata un coste fijo en dólares como una fracción constante del capital inicial y supone un cap continuo que no es el contrato nativo.

Una desigualdad que trata correctamente el coste fijo, manteniendo el supuesto de cap continuo, eleva esas cotas a **0.586674** y **0.695319 pb/día**, respectivamente. Sigue sin describir la apreciación permitida después de una admisión. La sección siguiente admite expresamente esa apreciación.

## 4. Extensión: admisión, apreciación y 72 horas

### 4.1 Supuestos de la clase matemática

Se exige que cada compra sea causal, se ejecute a un precio observado del proceso compensado y valore toda la cartera de forma coherente en ese momento. Cada admisión deja exposición total como máximo \(g=0.12\) de la equity real. No hay caja negativa, préstamo ni aportaciones. Cada posición desaparece antes de 72 horas. Las ventas posteriores pueden reducir cantidades y añadir caja; no crean exposición nueva.

Se permiten decisiones mucho más capaces que las recetas ensayadas: conocimiento del régimen actual, cualquier señal causal y elecciones de exposición dentro del contrato. Se relajan las restricciones de acciones enteras, stop, drawdown y riesgo abierto, y todos los costes variables se consideran no negativos y se omiten de la cota favorable. Una restricción adicional no puede aumentar el máximo de esta clase.

### 4.2 Cuenta sombra y exposición

Definimos una cuenta sombra \(\widetilde W\) con exactamente las mismas cantidades y operaciones que la cuenta real, pero que conserva en caja todos los costes pagados. Su equity es al menos la real y su exposición proporcional al admitir también es, como máximo, \(g\).

Sea \(\tau\) la última admisión anterior al instante \(t\). Si queda alguna posición, \(\tau\) pertenece a las últimas 72 horas. En \(\tau\), la cuenta sombra tiene al menos \((1-g)\widetilde W_\tau\) en caja y como máximo \(g\widetilde W_\tau\) invertido. Después sólo hay ventas. Definimos

\[
M_t=\max\left(1,\max_{j=1,2}\sup_{s\in[t-72h,t]}\frac{S_j(t)}{S_j(s)}\right).
\]

Entonces, trayectoria por trayectoria,

\[
f_t\le h(M_t),\qquad h(x)=\frac{gx}{1-g+gx}.
\]

La función \(h\) es creciente y cóncava. El máximo sobre todos los instantes \(s\) cubre la elección endógena de la última admisión: no se supone que esa admisión sea un instante determinista independiente del precio.

### 4.3 Momentos del máximo de precios

Un intervalo de 72 horas toca como máximo cuatro fechas calendario. Para evitar sutilezas de extremos y barras parciales, la demostración cubre **cuatro sesiones completas, 312 barras y cuatro overnights**. La comprobación de la rejilla encuentra únicamente 1,872 subpasos —234 barras equivalentes— y tres eventos nocturnos en ventanas semiabiertas de 72 horas. La prueba emplea deliberadamente la cobertura más amplia.

Condicionando las trayectorias de régimen, actividad y mezcla, los factores compensados de precio son independientes entre instantes y tienen media uno. Para un tiempo final fijo, el producto de los últimos \(k\) factores, revelados en orden inverso, es una martingala. **Se invierte el orden de los productos, no los multiplicadores.** La desigualdad \(L^q\) de Doob controla su máximo; no requiere independencia entre los dos activos. La referencia matemática primaria es Amir Dembo, [Probability Theory, Corollary 5.2.13](https://web.stanford.edu/class/stats310c/NOTES/lnotes.pdf).

Para \(q>1\), sea \(c_q=q(q-1)/2\). Usando la mayor sigma negociable,

\[
\sigma_b=0.00085(1.25)\sigma_{scale}e^{0.7},
\qquad \sigma_n=0.0035\sigma_{scale}e^{0.7},
\]

\[
\ell_b(q)=\log\left(0.996e^{c_q\sigma_b^2}
                         +0.004e^{16c_q\sigma_b^2}\right),
\]

\[
\ell_n(q)=c_q\sigma_n^2,\qquad
\ell_J(q)=\log\left(0.994+0.003(0.97)^q+0.003(1.03)^q\right).
\]

La suma de momentos de los dos activos y Doob dan la siguiente cota, uniforme para cada trayectoria de regímenes:

\[
\mathbb E[M_t\mid\text{regímenes}]
\le U(q)=e^{312\delta}\frac{q}{q-1}
\left[2e^{312\ell_b(q)+4\ell_n(q)+4\ell_J(q)}\right]^{1/q}.
\]

Integrar las mezclas devuelve sus probabilidades exactas; la actividad se limita por su máximo, sin presumir que las actividades de días distintos sean independientes. Por Jensen,

\[
\mathbb E[f_t\,1_A]\le0.64\,h(U(q)).
\]

Esta operación no supone independencia entre exposición y régimen favorable: la cota es uniforme condicionada a cada trayectoria de regímenes. El script toma el menor valor entre las desigualdades válidas para los enteros \(q=2,\ldots,500\). Optimiza una desigualdad determinista, no una política ni una muestra económica.

### 4.4 Crecimiento y coste fijo sin aproximar su unidad

Poniendo \(a=e^{\delta/8}-1\), \(\gamma=h(U(q))\) y \(n=126\times78\times8\), la desigualdad \(\log(1+x)\le x\) implica

\[
\mathbb E\log(\widetilde W_T/W_0)\le n(0.64)\gamma a.
\]

Los overnights aportan como máximo cero a este término. La cuenta sombra satisface también

\[
\mathbb E[\widetilde W_T]\le W_0e^{9828\delta},
\]

porque su fracción invertida nunca excede uno. **No se sustituye esa fracción por \(\gamma\) en esta última desigualdad:** la riqueza y la exposición pueden estar correlacionadas.

El cargo fijo total es \(C=176\) USD. Como \(W_T\le\widetilde W_T-C\), para riqueza final positiva,

\[
\mathbb E\log(W_T/W_0)
\le\mathbb E\log(\widetilde W_T/W_0)-C\mathbb E[1/\widetilde W_T]
\le n(0.64)\gamma a-\frac{C}{W_0}e^{-9828\delta}.
\]

La primera desigualdad utiliza \(\log(1-x)\le-x\), y la segunda Jensen aplicado a \(1/x\). No hace falta inventar un piso de equity o mantener una fracción constante de coste. Si la riqueza termina no positiva, el log-crecimiento deja de ser admisible para el objetivo y no invalida la conclusión favorable a las estrategias solventes.

## 5. Resultados del cálculo determinista

| Magnitud | Desarrollo | Extremo favorable del soporte final |
|---|---:|---:|
| Multiplicador de drift | 1.00 | 1.10 |
| Multiplicador de sigma | 1.00 | 1.20 |
| Orden de momento usado | 44 | 37 |
| Cota de \(\mathbb E[M_t\mid\text{regímenes}]\) | 1.087578 | 1.104735 |
| Cota condicional de exposición media \(\gamma\) | 12.915204% | 13.092265% |
| Log-crecimiento bruto superior, pb/día | 1.153917 | 1.286710 |
| Penalización fija inferior, pb/día | 0.391078 | 0.381587 |
| **Log-crecimiento neto superior, pb/día** | **0.762839** | **0.905124** |
| Hurdle nominal registrado | **1.000000** | **1.000000** |

El máximo de sigma se usa porque permite una cota más amplia de apreciación y exposición, no porque aumentar volatilidad mejore necesariamente una estrategia. El extremo conjunto domina el soporte registrado de los factores; no se escoge un seed que lo produzca. Las doce autocomprobaciones incluyen momentos de orden uno, dimensiones monetarias y temporales, probabilidad de régimen, finitud y cobertura del calendario. Los cálculos usan doble precisión; no constituyen una prueba formal mediante aritmética de intervalos ni una auditoría externa.

## 6. Qué falta demostrar respecto al motor

El replay nativo no rebalancea continuamente al 12%. Evalúa admisiones con información causal disponible y reservas, y ejecuta un IOC posteriormente. Que una reserva use un precio techo puede ayudar a una demostración conservadora, pero no resuelve automáticamente el desfase de valoración de otras posiciones. Se necesita reconstruir un argumento de cartera que cubra marcas, caja, reservas pendientes y su orden temporal.

La segunda brecha es independiente. Las barras provienen de ocho subpasos correctamente compensados, pero las salidas OHLC pueden pagar un stop o target interpolado entre esos precios. Un proceso martingala de precios no garantiza que toda regla de pagos interpolados sea una operación causal autofinanciada sobre ese proceso. Hay que comprobar el precio del primer cruce y la recepción de la orden, o construir un comparador que opere directamente en los subpasos.

Por ello el campo `native_ohlc_replay_infeasibility_certified` permanece en `false`. Superar numéricamente la cota en ese motor exigiría investigar primero qué supuesto no se cumplió. No autorizaría a declarar rentabilidad real, ni demostraría por sí solo que la ley WEAK contiene una oportunidad económica explotable.

## 7. Diagnóstico de oráculo propuesto, no seleccionable

Si se necesita atribuir la brecha restante, el siguiente experimento debe registrarse como **diagnóstico privilegiado excluido de candidatos y promoción**. Conservaría exactamente generador, capital, calendario, costes, límites y seeds autorizados; conocería sólo el régimen de la sesión presente en el momento de decidir. No recibiría precios futuros, extremos futuros, estado de la próxima sesión ni etiquetas de un resultado ganador.

Una política de referencia sencilla y fijada antes de medir elegiría un activo con régimen positivo mediante desempate léxico, permanecería en caja si no existe ninguno y conservaría el límite conjunto del 12%, el riesgo abierto y las 72 horas. Su desempeño permitiría preguntar cuánto se pierde al inferir la señal. No sería, por ser sencilla, una solución demostrablemente óptima al problema de control.

Se necesitan dos contabilidades claramente separadas: el diagnóstico con ejecución nativa permite localizar pérdidas de filtros, tamaño, costes y salidas; un comparador con precios reales de los subpasos permite comprobar los supuestos de la cota. Una diferencia entre ambos es evidencia sobre ejecución y valoración. No puede incorporarse como nueva señal favorable.

Si incluso este diagnóstico privilegiado falla, se refuerza la hipótesis de que modular señales no basta, pero el fracaso de una única política no prueba imposibilidad universal. La conclusión matemática procede de la cota sobre toda la clase declarada. Si se cierra la equivalencia con el motor, esa cota ofrece un criterio de parada: bajo el mismo contrato, seguir buscando no puede elevar su esperanza por encima del límite. Cambiar una restricción necesitaría un estudio explícitamente distinto; no se altera aquí ninguna.

## Reproducción

Desde la raíz del repositorio, el primer comando recalcula en stdout sin modificar evidencia; el segundo crea un archivo nuevo y rechaza cualquier sobrescritura:

```bash
python -B tools/diagnose_modulation10_feasibility.py
python -B tools/diagnose_modulation10_feasibility.py --output /tmp/harpoon_modulation10_feasibility_reproduced.json
cmp evidence/modulation10/feasibility.json /tmp/harpoon_modulation10_feasibility_reproduced.json
sha256sum tools/diagnose_modulation10_feasibility.py evidence/modulation10/feasibility.json docs/MODULATION10_FEASIBILITY.md
```
