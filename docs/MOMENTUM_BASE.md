# Momentum, consolidación y ruptura

Implementación de investigación inspirada en la referencia a Kristjan Kullamägi del reel https://www.instagram.com/reel/DfaNHpVg-ny/ . Se verificó la descripción visible y algunas imágenes del vídeo; no se obtuvo una transcripción completa ni se auditó la cifra publicitaria de ganancias. La especificación se contrastó con la fuente del trader: https://qullamaggie.com/my-3-timeless-setups-that-have-made-me-tens-of-millions .

## Implementado

Operación pública MOMENTUM_BASE, accesible por framework.evaluate, CLI framework y puente Node. Es detector y plan de investigación, no estrategia de ejecución completa.

Reglas propias congeladas: impulso previo >=30% en 30 barras diarias anteriores a la base; base de diez sesiones; rango medio de las últimas cinco <=75% del de las cinco anteriores; mínimos ascendentes por mitades; último cierre >=SMA10>=SMA20 y SMA20 creciente. Ruptura confirmada por bid por encima del máximo de la base y del rango de apertura completado. Stop de referencia en mínimo del día conocido, con distancia <=ATR20. Spread <=10 pb y cotización de antigüedad máxima de cinco segundos. No se usa el mínimo futuro del día.

Presupuesto: 0.25% de riesgo y 12% de exposición, descontando reserved_risk y reserved_gross suministrados. Colchón fijo de costes de 10 pb de ida y vuelta. No es calibración con fills. Las reservas no son atómicas ni verificadas con broker; esta interfaz no reemplaza el coordinador de cartera.

## Uso

Paquete HARPOON_QUANT_FRAMEWORK_1, operation MOMENTUM_BASE. payload: symbol, asof, daily (60–260 barras), quote, capital, reserved_risk, reserved_gross. Cada barra contiene available_at (momento real de disponibilidad tras cierre), o,h,l,c,v. quote contiene at, session_open, opening_complete_at, bid, ask, day_low y opening_high. Ventana de apertura de 5–30 minutos, consulta durante las primeras dos horas. Se exige historia diaria anterior a la apertura y fechas estrictamente ordenadas.

Ejemplo reproducible en quant/tests/test_momentum_base.py; fixture sintética de ingeniería, no cotizaciones reales. Ejecutar PYTHONPATH=quant python -m unittest discover -s quant/tests -p test_momentum_base.py -v.

## Diferencias y pendientes

La receta no reproduce la selección discrecional ni los percentiles de líderes del trader. Los diez días de base y los umbrales de contracción son decisiones propias, pendientes de validación. No incluye fundamentales, episodic pivots ni cortos parabólicos.

La metodología original permite mantener ganadores más allá de 72 horas. El plan devuelto conserva max_hold_hours=72 por el contrato de HarpoonX; no implementa aquí ese cierre ni las ventas parciales o trailing multidiario. Esas salidas requieren un replay y un ejecutor posteriores. NO presentar el detector como una reproducción de los beneficios originales.

Sin autenticación de procedencia, calendario, ajustes corporativos ni reservas. No hay ranking transversal, backtest económico nuevo ni conexión a broker. execution_allowed y profitability_validated permanecen false. La integración posterior debe probar idénticos datos y costes con/sin el filtro, fuera de muestra, registrando descartes, beneficio neto y concentración en ganadores. Rechazar la propuesta si reduce crecimiento neto o sólo mejora el tramo usado para elegir parámetros.
