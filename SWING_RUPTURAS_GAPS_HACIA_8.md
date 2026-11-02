# Swing24–72h: rupturas, gaps y retesteos

**Implementado y medido. No acredita8.** La rotación y los costes variables
modelados bajan, pero ninguna receta cubre la infraestructura bajo costes
nominales o de estrés. El broker, el runtime y sus estrategias vigentes no
fueron modificados. Las recetas son investigación separada, sin órdenes.

## Qué cambia frente al ensayo intradía

Se conserva el panel ampliado de **11 instrumentos**: SPY, QQQ, IWM, XLF, XLE,
XLV, XLK, AAPL, MSFT, BTC/USD y ETH/USD. No se añadieron nuevos constituyentes.
Las tres reglas operan sobre una sola cuenta inicial de20,000USD por alternativa,
con exposición equity/cripto y efectivo coordinada. No se suman cuentas ni capitales.
El horizonte previsto es24–72horas UTC, normalmente48. Stops/targets pueden cerrar antes.

| Regla fija | Condición de entrada | Protección contra entradas tardías |
| --- | --- | --- |
| Ruptura | Cierre diario por encima del máximo de las20sesiones anteriores, volumen≥1.2veces mediana previa y tendencia SMA50 | Confirmación de una hora ya cerrada; límite de extensión respecto del nivel y del último cierre conocido |
| Gap alcista | Apertura equity con gap de0.5–2ATR; continuación confirmada por encima de apertura y máximo previo | No comprar si la apertura modelada de entrada excede en0.25ATR el último cierre horario conocido |
| Retesteo | Ruptura calificada dentro de los5días completados anteriores, toque del nivel y cierre confirmado encima | ATR/nivel congelados en la ruptura; rechazar persecución del precio |

Gaps de sesión sólo se definen para equity. No se inventa una apertura nocturna
en BTC/ETH, que cotizan continuamente. Ruptura y retesteo sí permiten ambos libros.

Entrada a las12:00de Nueva York, después de confirmaciones con disponibilidad
supuestamente fin de barra+60segundos. Ninguna señal consulta high/low/close de
la barra de entrada ni el cierre diario todavía en formación. La apertura del
día equity se usa después de haber ocurrido, no su rango o cierre futuro.
La puntuación de ranking es una regla simple de tendencia/ATR: **no es una
probabilidad de acierto calibrada ni evidencia de entradas más precisas**.

Cada entrada exige un recorrido de2ATR de al menos3veces el coste variable de
ida y vuelta. Es un filtro económico sobre un recorrido posible, no una
estimación de rentabilidad esperada. Se conserva la fórmula durante el estrés.

## Riesgo y salidas

- Stop a2ATR y objetivo a3ATR, con máximo de3posiciones simultáneas.
- Riesgo estimado hasta stop:0.35%por entrada y1%conjunto; no limita pérdidas por
  gaps, falta de liquidez o ejecución peor que la modelada.
- Bruto≤60%, nombre≤20%, cripto≤20%, grupo tech AAPL/MSFT/QQQ/XLK≤30%,
  verificados al entrar, considerando la reducción de patrimonio por la comisión.
  Movimientos posteriores pueden superar esos porcentajes.
- Capacidad máxima:1%de la mediana del volumen monetario de20barras conocidas.
  No se interpreta el volumen IEX como volumen consolidado ni como profundidad.
- Caja no negativa, reserva de100USD y freno de nuevas entradas si el patrimonio
  pierde2%desde el inicio del día UTC. No liquida automáticamente posiciones existentes.
- Planificar la sesión válida más cercana a48horas dentro de24–72: festividades,
  fines de semana, cierres anticipados y DST; si no existe una sesión admisible,
  abstención. Un fin de semana de73horas no se redondea a72.
- Stop adverso por gap a la apertura peor que el stop. Si una misma vela toca stop
  y objetivo, se aplica stop primero. El target no recibe mejora de precio por gap.
- Datos ausentes en el deadline detienen la cuenta; no eliminan la operación.
  La ejecución intrabar es un modelo OHLC, no reconstrucción del recorrido real.

## Resultados2025, condicionales a la cobertura de datos

Mismos costes unitarios del ensayo anterior:5bp equity y35bp cripto por lado,
con1USDpor día calendario compartido; estrés duplica variables y fijo. No se
rebajaron comisiones ni se descontó infraestructura para fabricar un positivo.

| Regla | Trades nominal/estrés | Neto nominal USD | Neto estrés USD |
| --- | ---: | ---: | ---: |
| Ruptura |47/46| -326.39 | -773.63 |
| Gap confirmado |47/47| -81.13 | -556.89 |
| Retesteo |57/56| -562.26 | -1,044.10 |
| Efectivo con igual fijo |0/0| -365.00 | -730.00 |

En el modelo, gap nominal aporta395.51USDbrutos, paga111.64USDvariables y deja
283.87USDantes del fijo de365USD. En estrés deja173.11USDantes del fijo de730USD.
Es el mejor resultado nominal de estas recetas, **no una estrategia promovida**.
Todos los límites inferiores descriptivos de crecimiento logarítmico frente a
CASH, calculados como media−3SEHAC, son negativos. No hay corrección completa
del historial global de ensayos ni un resultado fuera de muestra virgen.

Los costes variables nominales de las tres reglas fueron95–112USD, frente a
1,747.99USDde la regla conjunta intradía2025. Eso prueba una diferencia observada
en estos modelos: cambian señales, tamaños, riesgo y horizonte conjuntamente;
no identifica causalmente cuánto ahorro se debe sólo al tiempo de tenencia.

Ruptura nominal suma29.54USD equity y9.07USD cripto después de variables, antes
del fijo. Retesteo suma−201.13USD equity y+3.87USD cripto. En estrés, ruptura
queda−45.56/+1.93USD; retesteo−311.89/−2.21USD. No hay beneficio por sumar ambos
libros que sostenga la estructura total de costes. Cripto permanece limitado
por la capacidad del feed: exposición máxima de entrada inferior al0.62%del
patrimonio. No se acredita una cartera de20%cripto con esa evidencia.

## Integridad, datos faltantes y fills

La descarga2026de los11símbolos falló por timeout del MCP, incluidos reintentos;
no se generaron barras sustitutivas. Se conservan fallos y el calendario que sí
respondió. La enmienda anterior a medir limita este estudio a2025. No hay
resultado2026ni validación temporal nueva. Los diarios2024–2026 existentes se
filtran causalmente por disponibilidad; el futuro no interviene en las señales2025.

Las acciones corporativas archivadas cubren AAPL, MSFT y XLK. El motor implementa
dividendos como cuenta por cobrar en ex-date y caja en payable-date, sin duplicar
patrimonio; splits ajustan cantidad y niveles. **Los otros seis valores no tienen
cobertura completa**: sus dividendos/splits no se consideran reconciliados.
El valor0de dividendos en estas cuentas significa cero derechos identificados
en las posiciones cubiertas, no ausencia de todos los dividendos del universo.
Los resultados de la tabla son condicionales y no certifican la cuenta real.

No hay fills live nuevos. Se conserva el importador/calibrador de
[MULTIACTIVO_HACIA_8.md](MULTIACTIVO_HACIA_8.md), que exige IDs de ejecuciones,
quotes recibidos antes de decidir y fees explícitas; no confunde PAPER con LIVE.
No se debe convertir una tarifa publicada o un fill OHLC en una calibración real.
[Alpaca publica](https://docs.alpaca.markets/us/docs/crypto-fees) tarifas distintas
maker/taker: no se presupone descuento maker ni fill de una orden limitada por
el mero hecho de que el precio toque un nivel.

## Evidencia reproducible

- Protocolo antes del experimento:7437ac943c437a9e1b90a4614d7190930cb2d723.
- Implementación y enmienda antes de medir:9da060270fb08a3c8c9f656595509b13a587b842.
- Una familia de tres reglas×dos costes, más dos CASH: sin afinación posterior
  de parámetros. No se declara reconciliado el presupuesto histórico global.
- **535pruebas quant aprobadas**, incluidas15mecánicas swing; otras7mutaciones
  comprueban que el verificador detecte caja/inventario/cronología/autoridad alterados.
- Ocho cuentas completas comprimidas y señales, eventos, curvas y checksums.
  La segunda ejecución local reproduce los ocho archivos comprimidos exactamente.
- Verificador separado con Decimal: errores diarios inferiores a3.1e-11USD.
  Es revisión del mismo autor, no auditoría independiente externa.
- Benchmark de una ejecución original:aproximadamente5.50spara ocho cuentas.
  No es una medición de rentabilidad ni de latencia de ejecución de mercado.
- Compilación sintáctica ejecutada; lint y comprobación formal de tipos Python
  no ejecutados por no estar instalados. La CIqueda preparada; no se afirma
  ejecución remota verificada en esta entrega.

```sh
python3 -m pip install -r quant/requirements-tested.txt
PYTHONPATH=quant python3 -B -m unittest discover -s quant/tests -p test_swing.py -v
python3 -B -m unittest discover -s tools -p test_swing8_verifier.py -v
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 -B tools/run_swing8.py \
  --output-dir /tmp/harpoon_swing_new
python3 -B tools/verify_swing8.py /tmp/harpoon_swing_new
```

La adopción de swing sí reduce la fricción en este experimento. Para acreditar8
siguen fallando resultado neto total y robustez estadística, y faltan cobertura
de acciones corporativas, datos nuevos y fills/costes reconciliados. No se
atribuye a Citadel, Jane Street o Two Sigma una receta propietaria ni se usa su
nombre como validación del algoritmo.
