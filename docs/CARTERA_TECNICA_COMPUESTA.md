# Cartera técnica compuesta y criterio para nivel 8

## Decisión

La combinación de acciones, ETF y cripto sigue en investigación. Con una cuenta de 20,000 USD, la regla horaria de ruptura perdió 250.69 USD en nominal y 670.03 USD en estrés durante 2025. El incremento que aportó admitir BTC/USD y ETH/USD frente a la misma política con solo acciones y ETF fue de 7.03 y 0.16 USD respectivamente. Las diferencias se calculan antes de redondear los patrimonios finales. Los límites inferiores de crecimiento absoluto y marginal fueron negativos. Este resultado rechaza esta receta para promoción.

## Ajuste al núcleo

El motor de apertura de cinco minutos acepta una referencia por símbolo. El campo de entrada `benchmark` puede seguir siendo `"XLK"` para toda la lista o un mapa, por ejemplo `{"MSFT":"XLK","JPM":"XLF","XOM":"XLE"}`. Cada valor debe tener barras válidas en la misma ventana. El motor rechaza mapas incompletos y la comparación de un activo consigo mismo. El cambio permite usar varias referencias sectoriales en la misma clasificación. Para investigación histórica, el responsable del universo debe aportar la pertenencia sectorial conocida en la fecha de decisión.

El evaluador de cartera compara cuatro cuentas alternativas, cada una con el mismo capital inicial y los mismos días de valoración. La cuenta JOINT paga una sola vez el gasto compartido y financia las posiciones abiertas desde el mismo efectivo. En los controles se excluye una clase desde el inicio y se recalculan los tamaños, las restricciones y la reinversión. La comparación pareada en logaritmos mide el efecto de admitir esa clase, incluida la competencia por capital. No se suman los rendimientos independientes.

## Ensayo registrado

El banco disponible contiene barras horarias de nueve acciones/ETF y dos criptomonedas para 2025. Por eso el ensayo aplicado a ambas clases utiliza la ruptura horaria de swing ya implementada y su salida de hasta 72 horas. La apertura de cinco minutos del PR #3 es una regla diferente y todavía requiere barras completas para un universo multisectorial.

| Universo autorizado en cada simulación | Operaciones nominal / estrés | Neto nominal USD | Neto estrés USD |
|---|---:|---:|---:|
| Acciones, ETF y cripto | 41 / 40 | −250.69 | −670.03 |
| Solo acciones y ETF | 32 / 32 | −257.71 | −670.18 |
| Solo BTC/USD y ETH/USD | 10 / 9 | −355.93 | −728.07 |
| Efectivo, sin rendimiento y con infraestructura | 0 / 0 | −365.00 | −730.00 |

En estrés, la cuenta conjunta acabó en 19,329.97 USD. Aportó 59.97 USD después de costes variables y antes de los 730 USD de gasto fijo supuesto. El drawdown medido en la rejilla horaria alcanzó 3.35%. La muestra cripto tiene nueve operaciones en ese escenario.

La simulación admite hasta 12% de exposición bruta y por activo, 0.25% de riesgo por entrada y agregado abierto, pausa diaria de 2% y bloqueo de entradas al alcanzar 8% de drawdown medido. El límite por capacidad puede reducir mucho el tamaño financiado. La ventana se conoce y reutiliza. Los costes y ejecuciones son modelados; los datos horarios de acciones del estudio son IEX y los ajustes corporativos cubren de forma incompleta el universo. El reloj intrabar, el deslizamiento ejecutado y la remuneración del efectivo quedan pendientes de medición.

Cuatro variables por escenario se evalúan con bloques pareados de 5 y 20 días, 20,000 réplicas y corrección local por 16 extremos. La corrección global por búsquedas previas sigue incompleta. La conciliación Decimal comprobó todos los días de cada cuenta. Ocho libros nuevos elevan la reserva documentada de búsqueda de 111 a 119 de 128.

## Siguiente prueba y criterio propuesto para 8/10

1. **Congelar universo, fuente y umbral económico.** Incluir acciones líquidas de varios sectores por reglas observables en esa fecha, con históricos de altas, bajas y cambios sectoriales. Admitir únicamente sesiones con barras comparables y acciones corporativas reconciliadas. Registrar por adelantado un objetivo de retorno anual neto acorde con el mandato y un comparador pasivo de riesgo similar. Medir los gastos efectivos.
2. **Aislar la ampliación.** Repetir la regla de cinco minutos sin modificar su entrada o salida. Comparar universo original, universo ampliado y efectivo en nominal y estrés. Mantener el mismo capital, límites y gasto común. Consumir los seis ensayos previstos solo tras cerrar el protocolo y confirmar los datos.
3. **Exigir valor incremental.** Una vez obtenida una base viable, probar la incorporación de cripto con reloj 24/7, liquidez y tarifas propias. Mantener la posibilidad de peso cero. Medir aportación al crecimiento geométrico y al riesgo de cola de la cartera. Probar información de opciones Cboe por separado cuando exista una base aceptable y cotizaciones históricas alineadas; su utilidad se decide por una comparación con y sin esa información.
4. **Confirmar fuera de muestra y después en prospectivo.** Separar por fecha y purgar etiquetas superpuestas hasta su vencimiento de 72 horas. Reservar un periodo posterior intacto y posteriormente un registro prospectivo con datos disponibles en la decisión. Exigir beneficio absoluto positivo bajo estrés, cumplimiento del objetivo previamente acordado, ventaja frente a los controles con cota inferior positiva, drawdown dentro del 8%, conciliación y estabilidad sin la mayor operación ganadora. Comprobar riesgo de concentración por emisor, sector y régimen. Una muestra con incertidumbre excesiva queda inconclusa. Para afirmar rentabilidad ejecutable se precisan ejecuciones reales reconciliadas y sus costes; la operativa simulada sirve para verificar el recorrido.

## Qué aportó la búsqueda en GitHub

| Código examinado | Uso para HARPOON |
|---|---|
| [pderer/orb_strategy](https://github.com/pderer/orb_strategy/blob/main/backtest.py) | Ejemplo contrastable de clasificación por volumen de apertura. Su cálculo de media de retornos y su lista de tickers requieren otra construcción para evaluar capital continuo y pertenencia histórica. |
| [QuantConnect/LEAN](https://github.com/QuantConnect/Lean/blob/49b4aa7022abd38e99e9c7d3ec67929fa7f6d7b8/Common/Orders/Slippage/VolumeShareSlippageModel.cs) | Referencia para sensibilidad de costes a participación en el volumen. Su rama de cripto puede devolver deslizamiento cero cuando falta volumen. En HARPOON, la calibración exige observaciones de ejecución y debe bloquear la admisión con liquidez desconocida. |
| [skfolio](https://github.com/skfolio/skfolio/blob/0db206ed812622088cbd33af2e34a0f4762fa71e/src/skfolio/model_selection/_combinatorial.py) | Referencia para validación con purga y embargo. Sus parámetros se expresan en observaciones. El horizonte efectivo del proyecto se controla con fechas y horas de maduración. |

## Reproducir

Desde la raíz del proyecto, con las dependencias de `quant/requirements-roadmap9.txt`:

```bash
PYTHONPATH=quant:tools OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  python tools/run_compound_swing.py --output-dir /tmp/harpoon-compound-replay
python tools/verify_swing8.py /tmp/harpoon-compound-replay
```

El directorio de salida debe ser nuevo. El ejecutor comprueba SHA-256 del protocolo y de los datos, conserva las ocho cuentas y ejecuta la conciliación. [Protocolo](../research/compound_swing/protocol.json) · [Resultados y cotas](../evidence/compound_swing/report.json) · [Libros y huellas](../evidence/compound_swing/).
