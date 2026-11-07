# HarpoonX: framework intradía técnico cuantitativo

Estado: implementado para investigación reproducible por instrumento; no es una acreditación de rentabilidad ni una activación de broker. La captura del usuario se identifica como «hoy» por su declaración; no se ha reconstruido su sesión ni autenticado precios a partir de la imagen.

## Objetivo y recetas congeladas

Capturar tramos negociables después de una señal observable, maximizando el crecimiento neto del capital y controlando pérdidas. Tres hipótesis propias, no réplicas exactas de publicaciones:

- ORB5: rango de los primeros cinco minutos; cierre posterior fuera del rango y al mismo lado del VWAP acumulado.
- ORB15: misma regla con quince minutos.
- PULLBACK15: ruptura previa y posterior vela que retestea el nivel y cierra fuera del rango, confirmada por VWAP. El armado se actualiza con la dirección; no constituye un clasificador de régimen entrenado.

Cada receta admite dirección larga o corta. Una venta corta es hipotética y exige shortable=true y coste explícito de préstamo. Para estudiar un ETF inverso se deben suministrar sus propias barras; no multiplicar los retornos del índice. Esta versión no enruta una señal de QQQ a SQQQ automáticamente.

Filtro de actividad: volumen del rango inicial >=1.2 veces la mediana de veinte ventanas equivalentes previas. El proveedor debe construir correctamente esas veinte observaciones; history_asof sólo valida el corte temporal declarado, no autentica su procedencia.

## Ejecución y capital

Velas completas de un minuto, identificadas por inicio. Señal al cierre y entrada al inicio de la siguiente vela, con medio spread y slippage adversos. No se ejecuta retroactivamente al precio de ruptura. Ventana de señales: después del rango y antes del minuto 120; nunca en los últimos seis minutos.

Stop en el extremo opuesto del rango. Si una apertura atraviesa el stop se usa la apertura adversa, no el stop ideal. Un stop dentro de una vela se informa con el inicio de esa vela: su instante exacto es desconocido. Salida temporal al inicio de la vela situada cinco minutos antes del cierre suministrado. No hay take-profit optimizado ni reentradas.

Presupuesto experimental fijo: 0.25% del patrimonio por operación incluyendo costes estimados y máximo 12% de exposición bruta. Una operación por sesión. No son límites óptimos acreditados; un gap puede superar el presupuesto nominal. Se rechazan entradas cuya distancia al stop supere dos rangos o costes estimados de ida y vuelta superiores al 20% de la distancia al stop. El saldo continúa entre sesiones, sin reinicios. La curva incluye PnL neto, comisiones y préstamo; spread/slippage están incorporados en precios.

Cada ejecución procesa un instrumento. NO sumar cuentas independientes como si compartieran capital. La integración intradía con el coordinador swing/cripto, reservas simultáneas de riesgo y exposición por factor queda pendiente. Para ese despliegue se requiere presupuesto único, reservas atómicas, conciliación de órdenes y límites agregados Nasdaq/renta variable/bonos. No declarar esta fase completada con un backtest individual.

## Contrato ejecutable

Entrada pública: schema HARPOON_QUANT_FRAMEWORK_1; operation INTRADAY_REPLAY; payload contiene origin, symbol, strategy, capital, costs y sessions. origin es SYNTHETIC o HISTORICAL_MODELED. costs exige spread_bps, slippage_bps, fee_bps, borrow_bps (cargo por operación sobre nominal, NO tasa anual) y shortable.

Cada sesión contiene open, close, history_asof, prior_opening_volumes y bars. Fechas ISO con zona horaria; horarios suministrados desde calendario de mercado, incluidos cierres anticipados. Cada barra exige t,o,h,l,c,v. Se rechazan campos no previstos, datos no finitos, OHLC inválido, barras faltantes/desalineadas, sesiones superpuestas y referencias históricas posteriores a apertura. Máximo 2.000 sesiones de 390 minutos.

Ejemplo sintético íntegro: research/intraday/example_packet.json.

```bash
PYTHONPATH=quant python -m harpoon_quant framework < research/intraday/example_packet.json
PYTHONPATH=quant python -m unittest discover -s quant/tests -p 'test_intraday.py' -v
```

El mismo paquete es accesible mediante runtime/quant_bridge.cjs.framework. La salida incluye hash canónico de entrada y conserva execution_allowed=false, liveApproved=false y level8_accredited=false.

## Protocolo para demostrar ventaja

1. Obtener barras y cotizaciones auténticas ajustadas correctamente por splits, con calendario, feed, zona, integridad y fecha de descarga. La sesión de la captura es un estudio de caso, no el conjunto de validación.
2. Predefinir universo, tres recetas y dos escenarios de costes (nominal/estrés). No elegir retrospectivamente el mejor ETF o período. Comparar contra no operar y exposición pasiva al mismo riesgo.
3. Separar exploración y prueba temporal intocada, cubrir tendencias, caídas y lateralidad; purgar etiquetas solapadas. Las veinte ventanas de volumen siempre pertenecen al pasado.
4. Medir crecimiento geométrico neto, expectativa en dinero y R, drawdown, concentración en mejores días, frecuencia, capacidad y sensibilidad a costes. Bootstrap por bloques de sesiones para intervalos; ajustar por selección entre recetas. No dar por robusto un Sharpe elevado con pocas operaciones.
5. Rechazar si el beneficio fuera de muestra desaparece con costes plausibles, depende de pocos días o no supera la referencia ajustada a riesgo. La eliminación del mejor día es un diagnóstico, no una prueba estadística suficiente.
6. Sólo después: cartera común y paper prospectivo con reconciliación de fills, datos obsoletos, parciales, rechazos, desconexiones y pérdidas conjuntas. La rentabilidad paper tampoco garantiza rentabilidad real.

## Alcance verificado y límites

Pruebas de ingeniería sintéticas separadas de evidencia económica. Sin datos históricos nuevos ni backtest de la sesión de hoy. Modelo OHLC: no reproduce cola, impacto, profundidad ni fills parciales. Calendario y procedencia suministrados no se verifican contra proveedor. Contabilidad flotante de investigación, distinta del ledger Decimal existente. El drawdown usa peores marcas intravela contra máximos de capital realizados; no es un drawdown tick a tick.

## Referencias

- Zarattini y Aziz, Can Day Trading Really Be Profitable?: https://doi.org/10.2139/ssrn.4416622
- Gao et al., Market Intraday Momentum: https://doi.org/10.1016/j.jfineco.2018.05.009
- ProShares SQQQ, objetivo diario y límites: https://www.proshares.com/our-etfs/leveraged-and-inverse/sqqq

Estas fuentes motivan experimentos; sus resultados no se atribuyen a HarpoonX. La receta implementada añade filtros propios y no hereda estadísticas de esos trabajos.
