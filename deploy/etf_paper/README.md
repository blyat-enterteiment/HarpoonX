# HarpoonX ETF en Alpaca Paper

Servicio aislado para la estrategia activa E90/S08 con un presupuesto inicial de USD 20,000 y exposición objetivo agregada de 33.00 %. Primera sesión prevista el 27 de noviembre de 2026. No requiere bibliotecas de terceros. La puntuación de tendencia es la de EX31, con entrada 0.90 y mantenimiento 0.08. La posición de cada familia se deduce del cierre anterior de QQQ, SPY y TLT. Las parejas ejecutables son TQQQ/SQQQ, SPXL/SPXS y TMF/TMV. Cada familia activa recibe la misma fracción del presupuesto total.

## Operación

Desde esta carpeta, ejecutar `python -m unittest -v test_core` y `python -u service.py`. El proceso sirve `/healthz` en el puerto de Render. La respuesta pública solo indica que el proceso está vivo. La cuenta, las órdenes y los recibos se comprueban en el proceso y en los registros privados de Render. No existe un endpoint de envío de órdenes.

El entorno de ejecución recibe `APCA_API_KEY_ID` y `APCA_API_SECRET_KEY` del gestor de secretos de Render. Usar credenciales emitidas desde la cuenta Paper prevista para este piloto. El host de trading está fijado a `paper-api.alpaca.markets`. Para pausar toda la ejecución se puede suspender el servicio. Las posiciones Paper existentes se conservan al suspenderlo.

Durante los primeros cinco minutos de la sesión regular, el servicio coteja la hora del mercado y la del servidor. Usa órdenes de mercado DAY sobre fracciones. Las ventas para reducir exposición se envían antes de las compras. El importe de compra respeta la caja del bróker y el capital reconstruido a partir de las órdenes del piloto. Se reserva el coste de diseño de 20 pb por lado al dimensionar. La contabilidad posterior usa el precio y la cantidad del recibo de Alpaca. El peso efectivo puede variar con el precio. Al terminar la ventana se solicita cancelar únicamente las órdenes pendientes de este piloto y se relee el estado. No se venden posiciones meramente porque termine la sesión.

El estado se reconstruye en cada ciclo con órdenes, cantidades ejecutadas y posiciones del bróker. Un identificador estable por fecha, acción y símbolo permite reanudar tras un reinicio o respuesta incierta. Las discrepancias de inventario, las órdenes externas abiertas que pueden competir por el presupuesto, las series incompletas o una cuenta bloqueada suspenden nuevas admisiones. La cuenta puede contener otros activos. La atribución de posiciones sobre los seis ETF requiere que casen con los recibos del piloto. Un evento corporativo que desajuste inventario requiere conciliación. El valor de la simulación se mide en USD con los registros Paper.

## Señal y trazabilidad

El histórico de arranque contiene 477 cierres SIP por referencia. Se verificaron el archivo congelado hasta el 30 de octubre, la coincidencia del cierre de enlace y dos lecturas de la extensión hasta el 25 de noviembre. La semilla y el módulo EX31 se validan con SHA-256 en el arranque. Los datos de noviembre solo determinan el estado vigente de la señal al iniciar. Para sesiones posteriores, las barras cerradas se solicitan en SIP y se alinean con el calendario del bróker. La conexión de datos debe poder recuperar esa historia.

En el ensayo de desarrollo, la configuración produjo USD 21,598.95 a 20 pb por lado y USD 20,742.08 a 40 pb en 399 sesiones. La referencia de los tres ETF alcistas terminó en USD 23,790.96 a 20 pb. El resultado no acredita alfa adicional sobre esa referencia.

Los eventos privados distinguen credenciales ausentes, preflight autenticado, recibo de orden releído, llenado parcial, cierre terminal y fallos de conciliación. La prueba local usa un bróker artificial y cita sus recibos exclusivamente dentro de los tests. Un estado HTTP saludable o una prueba aprobada no acredita una orden Paper.
