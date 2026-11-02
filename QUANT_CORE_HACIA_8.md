# Causas económicas y robustez del core

## Dictamen

El problema principal es **ventaja económica insuficiente y no acreditada**.
Robustecer el core reduce errores de decisión; no transforma automáticamente
una señal débil en alpha. No se acredita 8, ni un aumento de PnL en esta entrega.

Referencias públicas de proceso, no acceso a estrategias propietarias:
[Two Sigma](https://www.twosigma.com/businesses/investment-management/) separa
datos, modelado, construcción de cartera y ejecución;
[Jane Street](https://www.janestreet.com/quantitative-research/) plantea medir
impacto de mercado y tratar explícitamente dependencia/no estacionariedad;
[Citadel](https://www.citadel.com/careers/quantitative-research/) describe
hipótesis, evaluación de datos, riesgo y construcción de cartera.
[Citadel Securities](https://www.citadelsecurities.com/careers/quantitative-research/)
es una firma distinta: su descripción pública enfatiza costes, latencia,
capacidad y microestructura. Estos principios informan el diseño, no validan
HARPOON ni justifican copiar HFT con una cuenta de 20,000 USD y horizonte 72h.

## Causas, evidencia y solución

| Causa | Evidencia y alcance | Solución y condición de refutación |
| --- | --- | --- |
| El filtro no aporta alpha incremental | HECHO: residual -118.65 nominal/-598.37 estrés, peor que ranking sin umbral/hurdle +214.41/-465.14 | Cerrar esta familia; probar mecanismo distinto y comparadores congelados. Rechazar si no mejora neto y límites inferiores familiares en evaluación nueva. |
| Margen insuficiente para la estructura de costes | HECHO modelado: residual +285.35/+209.63 antes de fijo de 404/808 USD | Medir costes reales y capacidad de compartir infraestructura entre estrategias. No rebajar costes ni multiplicar tamaño para lograr un backtest positivo. Rechazar una cartera cuyo crecimiento total no cubra todos los costes una vez. |
| Universo estrecho y exposición sectorial | HECHO: señal AAPL/MSFT contra XLK; long-only, no hedge ejecutable ni alpha neutralizado | Comparar con exposición/beta/horario emparejados y ampliar universo point-in-time bajo protocolo. HIPÓTESIS: gran parte del movimiento es factor común; rechazar el nuevo modelo si desaparece al controlar exposición y costes. |
| La salida no expresa la hipótesis residual | HECHO: plantilla CLOSED_CHANNEL/BASELINE, stops y plazo, sin salida por normalización del residual | Probar salida por invalidación/normalización con información disponible, contra misma entrada y riesgo. No quitar stops por su PnL negativo: las 18 salidas STOP suman -706.42; las 49 TIME +991.77 antes de fijo, pero eso no es comparación causal. |
| Ejecución conocida sólo por modelo OHLCV | HECHO: faltan quotes/cola/fills/costes reales suficientes; fechas de disponibilidad históricas asumidas | Capturar decisiones, bid/ask, recepción, fills y facturas; medir shortfall y markout por ventana y tamaño; reconciliar fill→inventario→caja→patrimonio. Rechazar si el coste observado consume el margen o excede capacidad. |
| Reutilización del histórico | HECHO: periodo ya inspeccionado; mínimos de trades/sesiones no resuelven selección | Mantener todo el historial de ensayos y reservar evaluación nueva antes de medir. No denominar holdout virgen una nueva descarga del mismo periodo. |
| Comprobación numérica incompleta del core | HECHO de código: postcheck legacy usa result.x; cantidades finales se redondean. El constructor de escenarios no comprueba fechas de residuos por sí mismo | Nueva certificación independiente de lotes finales y cronología; casos adversos reproducibles. No se afirma que estos defectos causaran las pérdidas históricas ni que hubiera fuga observada. |
| Incertidumbre dependiente de aproximaciones | HECHO: core legacy usa n_eff/max(5,ceil(horizonte/24)); los escenarios remuestreados no son observaciones nuevas | Contrastar media/SE sobre filas originales alineadas, con Bartlett HAC y suelo IID. Es un veto adicional condicional, no garantía de cobertura ni corrección completa por selección. |

En nominal hay 34 campañas positivas (+1,262.73 USD) y 33 negativas
(-977.38 USD), antes del fijo compartido. Una tasa de acierto ligeramente
superior a 50% no basta. El rendimiento de cartera debe incorporar tamaños,
dependencia, exposición, costes, abstención y capital continuo.

## Implementado: entrada de investigación robusta

`quant/harpoon_quant/robust_core.py` reutiliza el optimizador original y emite
una propuesta sólo tras una segunda valoración de las cantidades finales:

- Identidades únicas; panel conjunto de al menos 20 filas originales;
  fechas de residuos no posteriores a la calibración.
- Lotes enteros positivos, cantidad consistente, max_qty, caja disponible
  después de reservas, exposición por activo/factor y posiciones conjuntas.
- Revaloración de holdings y candidatos; CVaR y estrés de llenados parciales
  sin financiar pérdidas de una pata con beneficios de otra propuesta.
- Media y error estándar del PnL incremental en el panel original; veto si
  media menos incertidumbre no alcanza min_edge_usd. No baja el umbral legacy.
- Recibo con hashes de solicitud/calibración/configuración y certificado.

Referencia de HAC:
[Newey–West](https://www.nber.org/papers/t0055). Lags en filas observadas,
sin interpolación de sesiones; suelo IID conservador. No certifica muestras
pequeñas, cambios de régimen, selección previa ni autenticidad de los datos.
La cronología por fecha UTC no sustituye label_known_at/first_received_at.

La decisión es **propuesta legacy verificada o CASH**. No reoptimiza tras un
veto: puede descartar una cartera aun existiendo otra factible. No crea alpha,
no cambia la calibración y no demuestra mejor retorno. Futuras extensiones
deberían llevar costes e incertidumbre al objetivo antes del solver, con
validación económica nueva, en lugar de asumir que este filtro mejora el PnL.

Los 323 bindings originales del estudio residual permanecen idénticos. La
nueva entrada es optativa de investigación; **no está conectada al runtime ni
al broker** y siempre devuelve execution_allowed/liveApproved falsos. Se
preserva el core sellado para reproducir resultados anteriores.

```sh
PYTHONPATH=quant python3 -B -m harpoon_quant.robust_core \
  --input quant/examples/request.synthetic.json \
  --model quant/examples/model.synthetic.json \
  --output /tmp/robust_receipt_new.synthetic.json
PYTHONPATH=quant python3 -B -m unittest discover -s quant/tests
```

El ejemplo es sintético y no demuestra comportamiento económico observado.
La salida debe ser nueva. Los límites existentes siguen siendo configurables;
no se relajaron para obtener más operaciones.

## Investigación propuesta: máximo tres hipótesis, seis variantes

Esto es diseño para revisión, **no reserva ya registrada ni ensayos ejecutados**.
No se ha consumido presupuesto nuevo de estrategias.

| Familia | Dos contrastes propuestos | Datos y puerta de avance |
| --- | --- | --- |
| Continuación relativa frente a reversión | Continuación residual; reversión sólo tras estabilización observable | Universo point-in-time, precios/quotes y etiqueta de beneficio neto ejecutable. Comparar ambas con ranking/control temporal; abandonar si ninguna resiste estrés e incertidumbre. |
| Salida ligada al mecanismo | Normalización residual; invalidación por persistencia con deadline ≤72h | Mismas entradas y riesgo; fills/latencia/costes y cuenta completa. Rechazar si reduce pérdidas aparentes sacrificando ganadores o incrementa turnover/coste total. |
| Complementariedad de cartera | Presupuesto total dividido en subcuentas equity/cripto; coordinador común de las mismas señales | Panel de PnL alineado y señales con ventaja condicional por comprobar. Rechazar si la asignación común no aumenta el límite inferior de crecimiento neto o empeora cola/capacidad. No sumar dos curvas con capital duplicado. |

Antes de ejecutar hay que concretar fórmulas, umbrales, timestamps, universo,
costes y receta de cada variante en un protocolo inmutable; no se han dejado
valores abiertos para ajustarlos tras ver resultados. Estas tres preguntas
evitan un barrido sin límite, pero no constituyen todavía ese protocolo.

Para la tercera familia, las dos recetas serían la referencia de subcuentas
con presupuesto total dividido y la asignación común; la misma generación de
señales y los mismos costes compartidos deben congelarse en ambas. La
comparación no presupone que las señales cripto actuales tengan alpha.

## Orden de trabajo para acreditar 8

1. Cerrar ejecución/costes y reconciliación económica reales en observación.
2. Registrar una sola familia antes de medir; no lanzar seis variantes a la vez
   si faltan sus datos, y conservar fallos y presupuesto.
3. Validación temporal purgada, controles simples, escenarios de costes y
   límites inferiores con corrección por ensayos; medir estabilidad y capacidad.
4. Sólo si hay ventaja, estudiar asignación conjunta con covarianza regularizada,
   incertidumbre y objetivo de crecimiento logarítmico neto bajo riesgo común.
5. Promover únicamente con R1–R8 satisfechos, incluida evidencia prospectiva
   reconciliada; ni tests verdes ni un Sharpe aislado acreditan 8.

Opciones no entra para incrementar la nota: faltan cadenas bid/ask, lifecycle,
asignación y marks ejecutables suficientes. Tampoco se propone más agentes,
GPU o LLM en la decisión como sustituto de una hipótesis rentable.
