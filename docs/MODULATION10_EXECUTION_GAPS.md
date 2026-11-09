# MODULATION10: brechas entre la cota y la ejecución nativa

## Dictamen

La [cota de factibilidad](MODULATION10_FEASIBILITY.md) no puede trasladarse automáticamente al replay. Hay dos cuestiones diferentes: **el momento en que se limita la exposición** y **el precio al que se considera ejecutada una salida**. La primera puede admitir una extensión matemática basada en las reservas; la segunda ya contiene un contraejemplo local a la equivalencia exacta con operaciones sobre los ocho precios discretos de cada barra.

El IOC protege el precio de la nueva compra. No vuelve a imponer un 12% contemporáneo sobre toda la cartera cuando esa compra se ejecuta. Por otra parte, un stop intrabar puede cobrar su umbral aunque el primer subpaso observado haya saltado por debajo. Los targets y la prioridad adversa de una barra ambigua pueden producir diferencias del signo contrario. **No se ha demostrado el signo ni la magnitud del efecto agregado.**

Esta revisión no ejecutó trayectorias económicas, no abrió resultados reservados y no cambió código, ley, costes, límites ni umbral. Se comprobaron las 47 fuentes M9 registradas, sin diferencias. Los ejemplos monetarios siguientes son identidades y fixtures propuestos, no resultados de mercado sintético.

## 1. Fuentes y contrato

Las referencias identifican funciones concretas; M10 conserva las funciones de capital y ejecución de M9 salvo sus hooks explícitos de clocks, perfiles y recepción de stops.

| Referencia | Fuente y funciones relevantes |
|---|---|
| F | [Factibilidad](MODULATION10_FEASIBILITY.md), especialmente las secciones 4 y 6: cuenta sombra, última admisión y equivalencias pendientes. |
| G | [Generador registrado](../quant/harpoon_quant/modulation9.py), `market`: `logs`, `intrabar`, `opens`, `highs`, `lows`, `closes` y `availableAt`. |
| E | [Motor nativo](../runtime30/profit8_replay.js), `causalReferencePrice`, `commonProfit8Price`, `planProfit8FundedEntry`, `planProfit8IocLimit`, `verifyFundedEntryFill`, `replayCampaign` y `replayFundedPortfolio`. |
| R | [Reservas](../runtime30/ultimate_reservations.js), `snapshotFundedReservations`, `reserveFundedEntry` y `recordFundedReservationObservation`. |
| Q | [Recepción causal](../runtime30/modulation9_exit.cjs), `causalPriceLookup`, `advance` y `queueStop`; [cronología](../runtime30/replay_chronology.cjs), `terminalTimeline`. |
| M | [Extensión M10](../runtime30/modulation10_replay.cjs), `mod10AssertSignal`, `mod10AssertSchedules`, `MOD10_PROFILES` y las dos funciones de replay. |
| P | [Protocolo M10](../research/modulation10/protocol.json): ley, costes, caps, clocks, horizonte, denominador y criterios de aceptación. |

Se conserva capital de 20.000 USD, dos activos negociables, 12% bruto/por activo y 0,25% de riesgo como límites de admisión, gates observados de 8% de drawdown y 2% de pérdida de sesión, y horizonte máximo de 72 horas. El hurdle nominal permanece en 1 pb de log-crecimiento neto por día calendario. La cota de F se refiere a una esperanza bajo sus supuestos; una trayectoria o una media finita superior no la refuta por sí sola. [F, P]

## 2. Brecha A: reserva causal, precio IOC y exposición contemporánea

### 2.1 Lo que el motor comprueba realmente

En una decisión \(d\), `causalReferencePrice` toma el cierre de mayor `end` entre las barras cuyo `availableAt <= d`. El índice de Q devuelve el mismo resultado. `commonProfit8Price` fija, antes de mirar la apertura siguiente,

\[
L=\operatorname{floor}_{tick}(1.003\,S_{disponible}).
\]

`planProfit8FundedEntry` redondea la distancia del stop hacia arriba y calcula el coste/riesgo por acción con ese techo, dos comisiones y la fricción de ambas patas. El entero \(q\) queda limitado simultáneamente por riesgo de la operación, riesgo agregado restante, notional restante y caja. `planProfit8IocLimit` vuelve a comprobar esos presupuestos sin modificar el techo al cambiar la cantidad. [E]

Para una posición ya abierta, la admisión reserva el mayor de su notional original aprobado y **toda la cantidad original** marcada al último cierre disponible. No reduce esta reserva después de una venta parcial. Las órdenes pendientes conservan su techo aprobado. `reserveFundedEntry` comprueba además las sumas de riesgo, notional y caja; `snapshotFundedReservations` sólo libera una reserva al conocer `CLOSED` o `NO_FILL`. Estas decisiones son conservadoras respecto de cantidad residual y cobros por parciales conocidos. [E: `inventoryMarks`, `committed`; R]

En la apertura planificada \(e\), el precio comprador modelado es

\[
P_{fill}=\operatorname{ceil}_{tick}\{O_e(1+f)\},\qquad
f=(spread/2+slippage)/10000.
\]

Si supera \(L\), el IOC no llena y se libera la reserva en esa apertura. Si llena, `verifyFundedEntryFill` comprueba cantidad, notional, riesgo y caja **contra los presupuestos aprobados en \(d\)**. No vuelve a dimensionar con el precio futuro ni recalcula un límite global con equity contemporánea en \(e\). Es protección ex ante de la orden, no un rebalanceo de cartera en el fill. [E]

### 2.2 El desfase relevante en los clocks registrados

| Evento MOM | Momento desde apertura | Información disponible en el replay |
|---|---:|---|
| Fin de primera barra | 5 min | Su cierre todavía no se ha recibido. |
| Decisión | 5 min + 1 s | Se recibe la primera barra de los tres símbolos. Se fija cantidad y techo. |
| Apertura IOC | 10 min | Se usa la apertura ejecutable de la nueva compra. El cierre de la segunda barra se recibirá un segundo después. |
| Recepción siguiente | 10 min + 1 s | Se actualizan las marcas causales correspondientes. |

Para CONFIRMED/QUALITY/SIMPLE ocurre lo mismo entre 60min+1s y 65min; para RETEST entre 90min+1s y 95min. El generador tiene `availableAt=end+1000` para todas las series. Por tanto, **en la decisión registrada las marcas están sincronizadas con el último subpaso completado**. Bajo la representación discreta usual, constante entre ocho actualizaciones equidistantes de 37,5s, también son contemporáneas en ese instante. Esta convención temporal del proceso debe declararse al exportar los subpasos: el dataset actual sólo conserva timestamps de barra. [G, M, P]

Los 299 segundos hasta el IOC permiten que cambien las otras posiciones. El techo de la nueva compra no limita ese cambio. Además, las observaciones de cartera en aperturas o instantes distintos del recibo común pueden utilizar marcas anteriores: `pnlAt` toma el último mark conocido o un cierre causal de respaldo. No usa precios futuros para corregir retrospectivamente esa valoración. [E: `pnlAt`, `advanceValuationClock`, `queueCampaignValuations`]

### 2.3 Por qué el techo individual no demuestra un cap global al fill

En una simplificación sin costes, sea \(W\) la equity en la decisión, \(V\) la posición existente y \(B\) el notional finalmente comprado. Si se cumple \(V+B\le gW\), pero la posición anterior gana \(\Delta>0\) antes del fill, entonces

\[
\frac{V+B+\Delta}{W+\Delta}>g
\quad\Longleftrightarrow\quad
(1-g)\Delta>gW-(V+B).
\]

La desigualdad puede cumplirse aunque \(B\) esté por debajo de su techo IOC. El redondeo entero deja holgura y puede evitarla en una operación concreta; no la excluye en general. Las comisiones, las marcas antiguas y los movimientos de otros activos requieren términos adicionales, no una garantía automática de 12%. Esta es una refutación de la equivalencia puntual de los caps, no una medición de frecuencia o gravedad.

`profit8RiskEventSummary` informa excesos con el máximo entre reserva y cantidad original marcada, dividido entre equity observable. Su propio `scope` los identifica como diagnósticos de movimiento de mercado. Este cociente puede sobreestimar la posición residual después de parciales y omitir un extremo todavía no recibido. **No es una medición exacta de exposición ni de drawdown en cada subpaso.** Un exceso no prueba por sí solo una admisión incorrecta; ausencia de exceso tampoco demuestra un cap continuo. [E: `observeProfit8Risk`; R]

### 2.4 Posible cierre matemático: anclar la cota a la reserva

No es necesario imponer inmediatamente un cap continuo distinto. Existe un argumento suficiente para extender la cuenta sombra de F, condicionado a que las ejecuciones sean autofinanciadas sobre el proceso observado.

Sea \(\tau\) la última **decisión de reserva admitida** anterior a \(t\). Supóngase que en \(\tau\):

1. La equity observable \(E_\tau\) no supera la equity sombra contemporánea \(\widetilde W_\tau\).
2. Para las posiciones existentes, su valor contemporáneo está cubierto por sus reservas conservadoras; para cada pendiente, \(qL\) cubre el coste de adquisición del activo antes de costes variables.
3. La suma de ambos tipos de compromiso cumple \(B_\tau\le gE_\tau\).
4. Después de \(\tau\) no hay otra admisión: sólo fills ya reservados y ventas. No se compran unidades adicionales implícitas.

Se puede descontar virtualmente de la caja sombra todo el compromiso pendiente en \(\tau\), aunque el fill ocurra después. Quedan al menos \((1-g)\widetilde W_\tau\) en caja. Los no-fills, el ahorro frente al techo y las ventas sólo aumentan esa caja; los costes se conservan en la cuenta sombra. Si \(M_t\) es el mismo máximo de apreciación de F, las posiciones preexistentes se comparan con su precio en \(\tau\), y cada compra pendiente con su precio de fill. En consecuencia,

\[
V_t\le M_t B_\tau\le M_t g\widetilde W_\tau,
\qquad
\frac{V_t}{C_t+V_t}\le\frac{gM_t}{1-g+gM_t}.
\]

El horizonte anclado al timestamp de señal ayuda: si sigue abierta alguna posición, la última reserva admitida no precede su propia decisión; las bases relevantes permanecen dentro de las 72 horas. Las reservas conservadoras y la falta de liberación parcial ayudan a las premisas 2–3. En los clocks sincronizados del generador, la premisa 1 también tiene una vía de prueba; las comisiones y la provisión de comisión de salida reducen la equity observable. [F; E: `planCalendarHolding`, admisión y `pnlAt`; R]

**Este lema condicional no certifica todavía el motor completo.** Requiere comprobar las desigualdades de cartera con su orden de eventos, fijar la convención temporal de los subpasos y resolver la brecha B. Para un calendario genérico con marcas retrasadas no basta afirmar que una marca causal es contemporánea. El punto útil es que el retraso IOC por sí solo no obliga a abandonar la cota: una reserva virtual puede cubrirlo sin cambiar el cap numérico.

## 3. Brecha B: umbrales OHLC frente al primer cruce observado

### 3.1 Qué se pierde al comprimir la trayectoria

`market` construye ocho precios por barra mediante incrementos logarítmicos compensados. Mantiene esa secuencia en `intrabar`, conserva su último precio como cierre y calcula high/low incluyendo la apertura. **No devuelve los ocho precios ni su orden en el dataset.** No es posible recuperar de OHLC, de forma única, qué umbral se cruzó primero ni cuánto se sobrepasó. Es necesario regenerar una traza lateral exactamente equivalente, conservando todas las llamadas y el orden del RNG. [G]

`replayCampaign` decide las salidas con toda la barra: comprueba primero el vencimiento en apertura; después, stop; después, targets. Para una posición larga, si `b.l <= stop`, vende toda la cantidad restante a `min(b.o,stop)` antes de fricción y redondeo. Si no hay stop, cada target alcanzado vende su cuarto entero al nivel del target. Los fills intrabar se etiquetan en `b.end` y se conocen en `b.availableAt`; no en el primer subpaso que cruzó el umbral. [E]

### 3.2 Tres efectos que deben separarse

| Efecto | Consecuencia respecto de ejecutar en el primer precio discreto que cruza |
|---|---|
| Stop con apertura por encima y salto intrabar por debajo | El motor puede pagar más que ese primer precio: interpolación favorable para el vendedor. |
| Target con salto por encima | Pagar el nivel suele dar menos que vender al primer precio observado: diferencia adversa o nula tras redondeo. |
| Barra que contiene stop y target | El motor elige stop primero aunque el orden de los ocho precios pudiera haber alcanzado antes un target. Se altera la secuencia de cantidades, además del precio. |

La apertura ya por debajo del stop es un caso distinto: `min(b.o,stop)` sí conserva ese gap adverso. Tampoco una prioridad stop-first demuestra que cada precio usado sea conservador. Puede coexistir con sobrepago del stop intrabar. [E]

### 3.3 Contraejemplo local con los costes nominales existentes

Una entrada con apertura 100 produce precio comprador 100,03 con fricción nominal de 0,0003 y tick 0,01. Con distancia de stop 1, el stop inicial es 99,03. Considérese la secuencia de ocho precios:

\[
(100.02,100.01,99.90,98.80,98.90,99.10,99.20,99.40).
\]

El primer precio que cruza el stop es 98,80; no aparece 99,03 entre los precios negociables definidos por esta representación discreta. El replay OHLC vende a 99,03 antes de fricción: **99,00** después de fricción y tick. El comparador que vende al primer cruce cobra **98,77**. La diferencia es **0,23 USD por acción**, con idéntica comisión por acción, sin asumir un target ni elegir un resultado económico.

La misma cuenta muestra el signo contrario para un target 101,53 cuyo primer cruce discreto sea 101,80: los precios netos de fricción/tick son 101,49 frente a 101,76. La interpolación del target resta 0,27 USD por acción respecto de ese comparador. Son ejemplos aritméticos del mecanismo; no constituyen una media de sesgo ni una ley alternativa.

Una trayectoria continua adicional podría atravesar exactamente el stop entre dos observaciones. Pero el generador registrado sólo establece estos ocho precios y sus extremos discretos. Introducir interpolación lineal, log-lineal o un puente browniano exige demostrar la propiedad financiera correspondiente; no puede suponerse que conserva automáticamente los supuestos martingala de F. El comparador mínimo debe operar sobre los ocho precios ya definidos, sin añadir una ley intermedia. [F, G]

### 3.4 Recepción y autofinanciación son controles distintos

`NATIVE_QUEUE72` repara la pérdida de un stop pendiente y aplica actualizaciones sólo al recibirse. No cambia el precio interpolado de un stop posteriormente activado. `terminalTimeline` evita que una marca tardía reabra inventario cerrado, pero tampoco prueba que el precio de salida pertenezca al proceso. Una conciliación exacta de caja demuestra consistencia con los fills registrados; no demuestra que esos fills sean ejecutables bajo la ley subyacente. [M, Q, E]

En el comparador propuesto, un stop o target activo se ejecutaría en el primer subpaso elegible, con la misma fricción, tick y comisión. Si un subpaso supera varios targets, se procesan sus cantidades al mismo precio observado. Las órdenes basadas en cierres conservan el recibo `end+1s` y la activación en la siguiente apertura permitida. El recibo de un fill intrabar puede mantenerse en `end+1s` para no mejorar artificialmente el acceso del coordinador a la caja. Se registran por separado tiempo efectivo y tiempo conocido.

Este comparador sería causal y autofinanciado sobre la rejilla discreta, con costes adversos explícitos. No sería una simulación validada de liquidez, colas o fills reales.

## 4. Qué queda demostrado y qué no

| Afirmación | Estado de esta revisión |
|---|---|
| El techo IOC se fija con información disponible y limita el fill de la nueva compra. | Demostrable por el código y las desigualdades de presupuesto. |
| Reservas pendientes, caja y cantidad original no se liberan por anticipado tras parciales. | Demostrable por R y el bucle de cartera. |
| El 12% se impone de nuevo a riqueza/precios contemporáneos de toda la cartera al fill. | No: no hay tal comprobación; existe un contraargumento algebraico. |
| La cota puede anclarse a una reserva anterior al IOC. | Lema condicional presentado; falta cerrar su aplicación completa. |
| Un fill stop OHLC siempre coincide con el primer cruce de los ocho precios. | Falso en general; el ejemplo local lo refuta. |
| Stop-first hace conservador el PnL agregado del replay. | No demostrado. Los mecanismos tienen signos distintos. |
| El exceso de rentabilidad observado, si existiera, se debe a estos mecanismos. | No evaluado. Requiere comparación emparejada, sin búsqueda de recetas. |
| La cota 0,905124 pb/día ya certifica imposibilidad del replay nativo. | No. Sigue pendiente la equivalencia financiera; el campo de certificación debe permanecer falso. |

## 5. Experimento mínimo siguiente, sin cambiar ley ni hurdle

### Fase 0: cerrar identidades antes de medir resultados

Crear exclusivamente archivos nuevos, enlazados por SHA a las fuentes actuales. El exportador lateral debe conservar `intrabar` sin introducir llamadas aleatorias ni alterar su orden. Para cada entrada debe reconstruir **exactamente el mismo dataset OHLCV**, su hash y las mismas señales que el generador registrado; cualquier diferencia bloquea el diagnóstico. La estrategia nunca recibe subpasos futuros, regímenes ni etiquetas de mundo. La traza es entrada del simulador de ejecución y de la revisión.

Cuatro familias de fixtures bastan inicialmente:

1. Una posición previa se mueve durante los 299s de espera y la nueva compra llena por debajo del techo: comparar reserva, mark disponible, valor contemporáneo y riqueza sombra; comprobar las premisas del lema.
2. El IOC supera el techo o hay parciales previos: verificar no-fill/liberación, ausencia de caja anticipada y conservadurismo de las cantidades reservadas.
3. Un único stop sobrepasado y un único target sobrepasado: reproducir precio, signo de diferencia y comisiones exactamente.
4. Los mismos OHLC con dos órdenes distintas de subpasos: demostrar que stop-first no equivale al primer cruce; comprobar timestamps, vencimientos y activación posterior al recibo.

No requieren semillas de desarrollo ni finales. La refutación de equivalencia exacta ya es estructural; estos fixtures vuelven ejecutables sus contraejemplos y permiten verificar el comparador.

### Fase 1, sólo si se necesita cuantificar la diferencia

Prerregistrar un diagnóstico **excluido de selección y promoción** con una sola receta ya definida: `CONFIRMED_NATIVE_QUEUE72_R2500`. Utiliza targets y stop, por lo que permite estudiar ambos mecanismos, y no se escoge por rendimiento. Reutilizar únicamente las 40 trayectorias M10 de desarrollo ya abiertas —8 seeds por 5 mundos— y los dos costes. Si todavía no se han abierto, esperar al cierre de esa etapa; **no utilizar el final sellado**. Los resultados de este diagnóstico serán exploratorios y no gastarán retrospectivamente una etiqueta de validación.

Si la fase 0 cierra el lema de reservas para el contrato registrado, basta comparar ejecución OHLC y ejecución por subpasos, más CASH: **240 cuentas diagnósticas**. Si la equivalencia de admisión sigue abierta, prerregistrar desde el comienzo el máximo de cuatro brazos, más CASH: **400 cuentas**.

| Brazo | Precio/orden de salida | Comprobación al IOC |
|---|---|---|
| A | Replay OHLC registrado | Presupuestos causales registrados |
| B | Primer cruce de ocho subpasos | Mismos presupuestos y reglas de reserva |
| C, si hace falta | Replay OHLC registrado | Guard adicional del 12% contemporáneo |
| D, si hace falta | Primer cruce de ocho subpasos | Mismo guard contemporáneo |

El guard de C/D sólo puede **rechazar** un IOC de cantidad ya fijada; no redimensionarlo favorablemente con el precio futuro. Es una intervención diagnóstica más restrictiva, no una afirmación de que el motor actual ya la cumple. Se conserva el valor 12%, la ley y el hurdle; se identifica explícitamente el cambio de semántica. No procede presentar C/D como la misma política ejecutada sin cambios.

A–B estima el cambio de la convención de salida con reglas de admisión iguales. A–C y B–D describen el efecto del guard; la diferencia de diferencias muestra su interacción. Se mantienen señales y reglas de tamaño; las cantidades futuras pueden diferir por la evolución de equity. Para distinguir ese efecto de la diferencia inmediata de precio, registrar también cada orden elegible, cantidad, nivel, primer cruce, overshoot, prioridad, coste y diferencia local. Una revaloración de fills fijos es un diagnóstico de precios, no una cartera contrafactual completa.

El presupuesto de hasta 400 cuentas debe declararse aparte del presupuesto M10: son nuevas ejecuciones aunque los precios y seeds se reutilicen. No se ejecutó ninguna en esta revisión.

### Métricas y criterios que refutan las hipótesis

- **Identidad de ley/datos:** igualdad exacta de hashes OHLCV y señales. Un fallo invalida la comparación antes de interpretar rentabilidad.
- **Cap y reservas:** registrar \(B_\tau\), \(E_\tau\), \(\widetilde W_\tau\), caja, inventario real y observado, precio disponible y contemporáneo, y cada premisa del lema. Un contraejemplo válido basta para refutar su aplicación universal al contrato.
- **Precios:** diferencias separadas de stop, target y orden intrabar, tanto antes como después de fricción/tick. Una diferencia no nula refuta identidad exacta; su signo local no establece el signo global.
- **Cartera:** caja por fill y comisión, inventario, reservas terminales, coste fijo de 176 fechas, log-retorno diario, DD observable y DD en subpasos por separado. El segundo es diagnóstico adicional, no reemplazo silencioso del gate registrado.
- **Sesgo agregado:** diferencias emparejadas A–B por seed, mundo y coste, con incertidumbre descriptiva. Una media positiva no prueba explotación real; una diferencia no significativa con ocho seeds no demuestra ausencia de sesgo.
- **Cota:** sólo si se cierran las premisas de ejecución y reserva puede aplicarse la cota a la clase correspondiente. Contrastar una esperanza con la mejor trayectoria, o repetir el diagnóstico hasta superar 1 pb/día, no es un criterio válido de refutación.

No se propone otra búsqueda de entradas antes de resolver estas diferencias. El resultado útil será una equivalencia demostrada, un contraejemplo localizado o una estimación de cuánto cambia el replay al respetar la rejilla de precios. Ninguno autoriza operaciones reales ni completa las brechas operativas de producción.

## 6. Integridad de la revisión

Identidades leídas para este documento:

| Fuente | SHA-256 |
|---|---|
| `quant/harpoon_quant/modulation9.py` | `9d4afa402d2b70791f175e79219495f9bbbe25eb3cd0b7e9212cef6bccbd68ab` |
| `runtime30/profit8_replay.js` | `303aa6956cfa0a249f0432bea23894b3ee8e514c60ff011177baabc7a6974810` |
| `runtime30/modulation10_replay.cjs` | `a6090964de4e16a821ce0fab5bac8a15611adcbcdfb888ebc26527ef08d146ce` |
| `runtime30/ultimate_reservations.js` | `94553547da3e02b972d72e8ea296a2e1ecc468a82133c75868eaea5fbe2ba494` |
| `runtime30/replay_chronology.cjs` | `04b9163c5174d844ed1654e48aa32d3813c14ab6917a572246c20dd75abe1e12` |
| `research/modulation10/protocol.json` | `a5edb060459f0f6aeb149eb8d07bcc2a0f7bb5a63ee693457ed7e517d039bea0` |
| `docs/MODULATION10_FEASIBILITY.md` | `e02c311d9e628012540a479d5f72f2a77a8f5bb569c0448df186483ca04102af` |

Los tres archivos ejecutables M10 entregados previamente permanecen sin cambios. Esta revisión es interna y documental, apoyada en el código y en álgebra explícita; no es una auditoría externa ni una certificación formal del teorema.
