# Matriz virtual de intenciones de compra

Operación pública VIRTUAL_NET del quant core. No transporta órdenes al broker ni crea fills; las celdas son intenciones de investigación. Compatible con API Python, CLI framework y puente Node existentes. No sustituye ExecutionBook, NativeFeeLedger ni sus reconciliaciones. No está conectada automáticamente al motor operativo ni persiste reservas de broker.

## Semántica de la red

Cada celda expresa exposición TOTAL deseada en dinero, no cantidad adicional. Las celdas del mismo símbolo son alternativas sobre la misma cuenta: se consolida el máximo objetivo, no su suma. No mezclar estrategias que deliberadamente busquen exposiciones aditivas bajo este contrato. La exposición existente reduce el incremento; cualquier compra pendiente del símbolo bloquea una nueva propuesta hasta conciliación. Celdas vencidas o cotizaciones con más de cinco segundos quedan descartadas. No hay neteo entre cuentas, activos distintos, compras y ventas.

Se preserva un único presupuesto suministrado de caja, exposición bruta y riesgo. Se descuenta secuencialmente y se devuelve el remanente. Orden alfabético estable; no se optimiza la selección con rendimientos retrospectivos. No incluye límites por factor/correlación. Los presupuestos y posiciones provienen del llamador, no están autenticados. El hash permite reconocer snapshots idénticos, pero NO implementa exactamente-una-vez, bloqueo transaccional ni reservas atómicas entre procesos.

## Filtro estocástico

Cada celda exige 30–256 retornos brutos de episodios históricos de igual horizonte y misma regla, no solapados, disponibles ANTES de crear la señal. El llamador debe obtenerlos sin selección retrospectiva. Se valida el tiempo declarado, pero no su procedencia ni el entrenamiento fuera de muestra.

Se restan dos lados de comisiones, fricción de ida y vuelta y dos cargos fijos. Se ejecutan 1.000 réplicas Monte Carlo mediante bootstrap circular de bloques de cinco episodios; se calcula un límite inferior de la media neta, ajustando el nivel nominal por número original de celdas (Bonferroni). Todas las celdas válidas del símbolo deben superar cero. Duplicar señales no aumenta el tamaño muestral. Con más de 50 celdas el ajuste exige colas que esta simulación no resuelve: se rechaza en vez de inventar precisión. Repetir decisiones en el tiempo y buscar parámetros introduce selección adicional NO corregida por este ajuste.

No es un certificado de seguridad ni una probabilidad de beneficio futuro. Bootstrap depende de representatividad, estacionariedad y longitud del bloque; puede fallar ante cambios de régimen. Se requiere evaluación prospectiva y sensibilidad con otros bloques antes de usarlo económicamente.

## Costes y objetivo del 80%

fee = volumen ejecutado * tarifa proporcional + número de órdenes * cargo fijo.

Agrupar cinco compras de 200 USD en una de 1.000 USD no reduce la comisión proporcional. El ejemplo de prueba usa cinco objetivos duplicados de 1.000 USD: el comparador ingenuo compra 5.000 y la matriz sólo 1.000. A igual tarifa, el coste modelado baja 80%, pero cambia la exposición y NO es un ahorro observado ni una comparación a igual riesgo. No se presenta como mejora de beneficio.

Si la comisión es cero, el porcentaje se devuelve null. Cancelar una intención no ejecutada no equivale a ahorrar una comisión ya pagada. Los costes de oportunidad, retrasos, spreads reales, fills parciales, cambios de tier y comisión en activo nativo deben conciliarse con el ledger existente. Referencia verificada: https://docs.alpaca.markets/us/docs/crypto-fees . El perfil se suministra por instrumento; no hay tarifa universal hardcodeada.

## Contrato y uso

Paquete HARPOON_QUANT_FRAMEWORK_1, operation VIRTUAL_NET, payload con:
- asof, cash_available, gross_available, risk_available: presupuestos netos de reservas previas;
- positions y pending: mapas símbolo -> nominal no negativo;
- costs: fee_bps por lado, roundtrip_friction_bps, fixed_per_order;
- seed entero reproducible;
- cells: id, symbol, created_at, expires_at, quote_at, target_notional, stop_fraction, samples, labels_available_at.

Ejemplo completo: research/intraday/virtual_net_example.json.

```bash
PYTHONPATH=quant python -m harpoon_quant framework < research/intraday/virtual_net_example.json
PYTHONPATH=quant python -m unittest discover -s quant/tests -p test_virtual_net.py -v
```

Salida: propuestas virtuales, motivos de rechazo, diagnósticos, presupuestos restantes y comparación hipotética. execution_allowed=false; savings_80_percent_verified=false; profitability_validated=false.

## Validación económica pendiente y despliegue

Comparar la política anterior y la matriz con el MISMO capital y riesgo, sobre un conjunto temporal intocado: comisiones reales, turnover, deslizamiento, oportunidades perdidas, retorno neto geométrico, drawdown y concentración. Registrar todas las celdas, incluidas descartadas, antes de conocer resultados. Rechazar la hipótesis si el ahorro se logra sólo dejando de operar y empeora retorno/riesgo. La métrica primaria es utilidad neta de cartera, no número de órdenes.

Antes del enlace operativo: repositorio durable de celdas, compare-and-swap, reserva atómica, IDs idempotentes en ExecutionBook, reconciliación de fills parciales/reintentos y broker paper. Los stops, reducciones urgentes y vencimientos de posiciones nunca pasan por el filtro de espera de compras. Esta implementación no modifica ni retrasa las salidas existentes.
