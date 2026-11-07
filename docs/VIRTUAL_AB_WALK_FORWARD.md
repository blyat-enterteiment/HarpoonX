# Comparación CURRENT/A/B y walk-forward purgado

Se implementó un replay con cuenta continua que llama a virtual_net.plan, no una aproximación de su filtro. CURRENT utiliza las propuestas completas; A omite incrementos inferiores al 0.5% del patrimonio; B aplica A y ejecuta el 50% del incremento. Son políticas de compras: las salidas protectoras se ejecutan por la misma regla en todas. La zona de no operar es un umbral experimental fijo, no un umbral óptimo estimado. B no exige confirmación adicional aparte de volver a superar el filtro en el siguiente ciclo.

Universo acotado: BTC/USD y ETH/USD, histórico archivado 2025, capital común USD20.000, costes de 35/70pb por lado y USD1/2 por día. Costes agregados de ejecución, sin separar tarifa y slippage ni asumir que sean fills reales. Decisiones a las12UTC, ejecuciones modeladas al open horario, stops al2% y salida a las72h. Aumentar posición no reinicia plazo ni ensancha stop. La señal común es cierre diario conocido sobre media20. Muestras del filtro: treinta retornos de tres días no solapados, disponibles antes del corte; son un proxy incondicional y NO resultados de operaciones de esa estrategia. No confundir esta prueba con el motor horario BREAKOUT ni con el detector Kullamägi.

## Walk-forward

Cuatro ventanas de prueba consecutivas: Q1,Q2,Q3,Q4 de2025. Para cada ventana, la muestra de estimación se congela usando sólo etiquetas disponibles estrictamente antes de inicio del trimestre menos72h. Ese corte impide solapamiento de las etiquetas de entrenamiento con el período de prueba y añade una separación conservadora. No hay entrenamiento con datos futuros ni necesidad de un embargo posterior por mezcla de folds. Al avanzar al siguiente trimestre puede incorporarse historia ya conocida de trimestres anteriores. Los indicadores de precio se actualizan causalmente dentro del trimestre; el filtro conserva su muestra congelada. No se ajustan parámetros. La cuenta y las posiciones continúan entre ventanas, sin reinicio de capital.

Es una evaluación temporal purgada sobre historia YA REUTILIZADA, no un holdout nuevo ni validación prospectiva. Los folds no son cuatro experimentos independientes. Bootstrap de diferencias diarias emparejadas,20.000 réplicas, bloques5/20d,semilla319,ajuste local0.05/8 para dos variantes,dos costes,dos bloques. Si las curvas coinciden por ausencia de operaciones, un intervalo[0,0] no demuestra equivalencia ni acierto: el efecto de A/B no está identificado.

## Validación

26 pruebas ejecutadas (20 de matriz y6 de replay): contabilidad continua, cash no negativo, venta por gap al precio adverso de apertura, primer tramoB a mitad deA, ausencia de influencia de filas futuras, vencimiento inmutable y etiquetas anteriores a corte purgado. Análisis estático y tipos aprobados. Son pruebas propias de ingeniería, no auditoría externa.

Los resultados y hashes se encuentran en evidence/virtual_ab. Los libros completos se regeneran con:

```bash
PYTHONPATH=quant OPENBLAS_NUM_THREADS=1 python tools/run_virtual_ab.py --output-dir /tmp/ab_new
PYTHONPATH=quant OPENBLAS_NUM_THREADS=1 python tools/run_virtual_ab.py --purged --output-dir /tmp/ab_purged_new
PYTHONPATH=quant python -m unittest discover -s quant/tests -p 'test_virtual*.py' -v
```

Se necesitan las dependencias cuantitativas del repositorio; el directorio de salida debe ser nuevo. Se conservan hashes del protocolo y datos; los parámetros son constantes en el código, no se cargan como configuración modificable desde JSON. Cambiar código o protocolo invalida la comparación archivada.

Límites: ejecución OHLC instantánea sin cola ni parciales; reservas sólo dentro del replay; intersección de horas disponibles; drawdown marcado en cierres horarios (no intrabar); contabilidad flotante con conciliación de tests; sin dividendos por tratar sólo cripto. No activación de broker ni acreditación de nivel8.

## Resultado ejecutado

Con y sin purga:316 celdas por política,0 compras; neto nominal -365USD y estrés -730USD, exclusivamente coste fijo supuesto. Bootstrap de diferencias A/B frente a CURRENT:0 en todos los límites. No hay evidencia identificable del efecto de A/B al no existir entradas aprobadas. Decisión: NO PROMOVER; no relajar el filtro retrospectivamente para forzar operaciones. Falta calibrar muestras condicionales a la estrategia en un estudio separado y con validación nueva.
