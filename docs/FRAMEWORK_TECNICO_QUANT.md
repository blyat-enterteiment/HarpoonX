# HARPOON · Framework de trading técnico cuantitativo

La pregunta económica es si una ruptura sostenida por precio, participación y fuerza relativa deja margen después de entrar a un precio alcanzable. La primera prueba termina en **RECHAZO**. Con 20,000 USD y 404 sesiones, la cuenta confirmada obtuvo +4.88 USD nominales y −687.95 USD con costes estresados. Queda disponible para reproducir el experimento y auditar las decisiones.

## Qué puede mover una decisión

| Etapa | Datos y operación | Conducta ante un fallo |
|---|---|---|
| Señal | El módulo lee OHLCV de cinco minutos del activo y de su ETF sectorial, reloj de recepción y calendario. Un split que cruza la comparación de volumen invalida esa ventana. | Abstención con motivo por símbolo ante barra faltante, tardía, volumen histórico nulo o ventana insuficiente. |
| Pronósticos del núcleo | Ridge y SVR usan los ocho predictores técnicos registrados. Los modelos de trayectorias, costes de microestructura y régimen de correlaciones comprueban los nombres permitidos al entrenar y al usar un modelo. | Una columna declarada como ventas, EPS, noticias u otro predictor fuera del contrato bloquea el modelo o la candidatura. |
| Trayectorias y asignación | Los precios históricos y su distribución condicionan entrada, tamaño, mantenimiento y salida. Se retiró el crédito por dividendos de episodios análogos en el optimizador y en su comprobador Decimal. | El modelo de trayectorias también admite muestras de entrenamiento con OHLC y sin campos de dividendo. |
| Contabilidad y contratos | El libro registra efectivo, reservas, comisiones, dividendos devengados y splits. La valoración contractual de opciones puede requerir tasa y rendimiento por dividendo. | La señal propuesta opera sobre acciones al contado. Una entrada en derivados requiere su propia validación de valoración y ejecución. |

Los vectores posicionales históricos conservan el orden técnico documentado. Comprobar nombres y dimensiones no autentica la procedencia de números importados. La nueva señal calcula sus valores directamente a partir de barras con tiempos de disponibilidad. Las reglas sobre anuncios de empresas, balances, noticias, valoraciones y previsiones de ventas quedan fuera de la estrategia.

## Primera regla registrada

1. **Decisión.** Una vez por sesión, a los 60 minutos y un segundo de la apertura regular. Se usan doce barras de cinco minutos completas y disponibles.
2. **Ruptura.** El último cierre supera el máximo de los primeros 30 minutos. El control simple aplica esta condición.
3. **Confirmación.** El cierre penúltimo también supera ese máximo, el retorno logarítmico desde la apertura excede el del sector y el volumen de los últimos diez minutos supera la mediana de esa misma franja en las veinte sesiones anteriores.
4. **Selección.** Entre los elegibles se nomina un activo por cartera y sesión. Se ordenan por fuerza relativa y se desempata por símbolo. Las dos políticas usan el mismo criterio y requieren datos válidos comparables.
5. **Ejecución y salida.** Entrada modelada en la apertura de la siguiente barra, con un límite IOC fijado sobre el último cierre conocido más 30 puntos básicos. La distancia inicial de stop es el cierre de decisión menos el mínimo de los primeros 30 minutos. El motor común dimensiona en acciones enteras y gestiona el stop, las dos salidas parciales de 25% con redondeo y el resto hasta la salida protectora o temporal. El reloj de 72 horas comienza con la decisión.
6. **Riesgo.** Patrimonio continuo de 20,000 USD sin aportaciones ni retiros. Tope bruto y por activo de 12%, riesgo presupuestado por entrada y agregado abierto de 0.25%, pausa diaria configurada de 2% y drawdown máximo de evaluación de 8%. Son límites modelados y se verifica el riesgo realizado.
7. **Decisión económica.** Una hipótesis, un control de ruptura simple y una cuenta de efectivo. Se exigen beneficio absoluto y riesgo aceptable en nominal y estrés, al menos 20 campañas cerradas por escenario, 100 sesiones, beneficio sin la mayor ganancia y límites inferiores positivos para crecimiento absoluto y diferencias frente a los dos controles. El remuestreo pareado usa bloques de 5 y 20 sesiones, 20,000 réplicas y corrección local por 12 comparaciones. Un resultado satisfactorio da acceso a evaluación prospectiva.

## Resultado del ensayo

Evaluación del 11 de marzo de 2025 al 16 de octubre de 2026. AAPL y MSFT como acciones, XLK como referencia. El conjunto histórico ya se había usado en el proyecto. Las seis cuentas comparten calendario y patrimonio inicial. El escenario nominal supone spread completo de 2 pb, deslizamiento de 2 pb por lado, comisión de 0.005 USD por acción y lado, más 1 USD por fecha natural. En estrés se duplica cada coste. El gasto compartido se cobra una vez por fecha e incluye fines de semana.

| Política | Campañas nominal / estrés | Neto nominal USD | Neto estrés USD | Drawdown nominal / estrés |
|---|---:|---:|---:|---:|
| Ruptura confirmada | 47 / 45 | +4.88 | −687.95 | 1.73% / 4.24% |
| Ruptura simple | 89 / 87 | −261.88 | −1,020.62 | 2.96% / 5.47% |
| Efectivo con gasto común | 0 / 0 | −585.00 | −1,170.00 | 2.93% / 5.85% |

La confirmación aportó +266.76 USD nominales y +332.67 USD bajo estrés frente a la ruptura simple, con distinta exposición realizada. En estrés generó +482.05 USD después de costes variables frente a 1,170 USD de gasto fijo. En nominal, al restar aritméticamente el mayor ganador, el resultado baja a −175.06 USD. Los doce límites inferiores quedaron por debajo de cero. La mayor tenencia desde decisión a cierre fue inferior a 72 horas. Histórico reutilizado, dos emisoras y ejecuciones sobre barras limitan la inferencia. La cartera equity/cripto y las ejecuciones reales requieren evidencia propia.

## Reproducir y comprobar

Desde la raíz, con Python 3.12, Node 24 y las dependencias de quant/requirements-roadmap9.txt:

```bash
PYTHONPATH=quant:tools OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  python tools/run_technical_swing.py --output-dir /tmp/harpoon-technical-run
PYTHONPATH=quant:tools python -m unittest discover -s quant/tests -p test_technical_swing.py -v
```

El directorio de salida debe ser nuevo. El recorrido ejecuta los tres libros en ambos escenarios, concilia operaciones con Decimal y conserva decisiones, señales, libros completos, costes, drawdown y límites estadísticos. Se puede consultar una sola decisión con la acción `python -m harpoon_quant technical-swing --available-at TIMESTAMP --input solicitud.json` usando `PYTHONPATH=quant`. El JSON lleva `dataset` con el objeto HARPOON-ULTIMATE-DATA-1, `symbols` como lista de activos y `benchmark` como símbolo de referencia. Devuelve las propuestas para estudio y los motivos de abstención.

[Protocolo anterior al cálculo](../research/technical_swing/protocol.json) · [Resultado y límites estadísticos](../evidence/technical_swing/results.json) · [Libros, decisiones, señales y SHA-256](../evidence/technical_swing/)
