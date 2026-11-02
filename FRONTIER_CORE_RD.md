# Núcleo cuantitativo: trayectorias, inventario y supervisor

Se implementó un núcleo **ejecutable de investigación/shadow** y un
[framework de I+D de USD 5 millones](programme/frontier/FRAMEWORK_RD_5M.md).
No se declara nivel 9, rentabilidad positiva, aprobación externa ni gasto
comprometido. El runtime anterior no se reemplaza ni el broker se activa.

## Componentes y puntos de entrada

| Archivo | Función implementada |
| --- | --- |
| `quant/harpoon_quant/frontier/features.py` | Adaptador causal opcional MACD12/30/9, RSI14 y estocástico14/3/3; separado de la receta registrada |
| `quant/harpoon_quant/frontier/paths.py` | Ajuste causal de modelo conjunto, soporte por calendario, deriva y probabilidades de primer paso con ambigüedad |
| `quant/harpoon_quant/frontier/controller.py` | Malla finita de acciones sobre inventario, continuación protectora, crecimiento logarítmico, coste completo y cola parcial |
| `quant/harpoon_quant/frontier/supervisor.py` | Revaloración de lotes/caja/límites y deadlines originales |
| `quant/harpoon_quant/frontier/assurance.py` | Segunda implementación escalar/Decimal de la propuesta seleccionada |
| `quant/harpoon_quant/frontier/journal.py` | Diario local privado, idempotencia, hashes y campañas sin reset silencioso |
| `quant/harpoon_quant/frontier/market.py` | Normalización de sesiones/halts provistos; ninguna conexión ficticia a bolsas |
| `quant/harpoon_quant/frontier/evaluation.py` | Evaluación cronológica purgada con límites Brier de identificación |
| `quant/harpoon_quant/frontier/programme.py` | Presupuesto exacto e integridad documental de puertas de avance |
| `quant/harpoon_quant/frontier_core.py` | API `shadow` y CLI fit/decide/evaluate/audit-journal/validate-programme/audit-gate |

No hay SDK de LLM, entrenamiento distribuido ni dependencia nueva de ejecución:
se reutilizan Python, NumPy y componentes cuantitativos existentes. Ruff y mypy
son herramientas de desarrollo separadas del motor.

## Uso reproducible

```sh
python3 -m pip install -r quant/requirements-tested.txt
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONPATH=quant \
  python3 -B tools/run_frontier_lab.py --output-dir /tmp/harpoon_frontier_lab
PYTHONPATH=quant python3 -B tools/frontier_restore.py /tmp/harpoon_frontier_lab \
  --dataset-output /tmp/frontier_dataset.json --model-output /tmp/frontier_model.json
PYTHONPATH=quant python3 -B -m harpoon_quant.frontier_core decide \
  --state /tmp/harpoon_frontier_lab/state_historical_modeled.json \
  --model /tmp/frontier_model.json --journal /tmp/frontier_receipts.sqlite \
  --output /tmp/frontier_decision.json
PYTHONPATH=quant python3 -B -m harpoon_quant.frontier_core audit-journal \
  --journal /tmp/frontier_receipts.sqlite --output /tmp/frontier_journal_audit.json
PYTHONPATH=quant python3 -B -m harpoon_quant.frontier_core validate-programme \
  --programme programme/frontier/programme.json --output /tmp/frontier_budget.json
```

Las salidas deben ser nuevas. Los datos y el modelo completos se reconstruyen
con shards hash-verificados y se contrastan contra sus hashes originales.
La CLI escribe archivos privados 0600, no sobrescribe resultados ni envía órdenes.
Una nueva decisión requiere una versión monotónica de estado/entrada; reutilizar
esa versión con otro modelo, configuración o código se rechaza en el diario.
La persistencia de campaña protege apertura/deadline. Los recibos sin diario
no proporcionan esa comprobación entre snapshots.

Para un dataset propio, `fit --dataset ... --available-at ...` exige que **todas**
sus etiquetas ya sean conocidas. No se filtran silenciosamente filas futuras
para hacer pasar un dataset incorrecto. `evaluate` realiza su propio entrenamiento
cronológico con purga, sin incorporar etiquetas futuras al modelo de cada decisión.
`frontier_restore` devuelve el dataset completo y el modelo ya calibrado a su
subconjunto registrado; no se debe ajustar ese dataset completo a una fecha
anterior a las etiquetas que contiene.

## Contrato de estado

`HARPOON_FRONTIER_STATE_1`: origen OBSERVED/HISTORICAL_MODELED/
SYNTHETIC_ENGINEERING_ONLY, `asof`, `known_at`, USD, `account_binding`, `version`,
`inventory_complete`, caja, reservas, cuentas por cobrar, PnL diario y drawdown;
assets en el mismo orden que el modelo; vector de features y su disponibilidad;
`evaluation_hours=72` para comparar acciones con idéntico coste común.

Cada asset declara símbolo, libro spot, factor, bid/ask y su recepción, status
con timestamp, capacidad de compra/venta en unidades nativas, `lot_qty`, lotes
actuales y máximo añadido, fee/slippage/fijo y origen de costes. El calendario
es una máscara explícita de 72 intervalos horarios más su hash/disponibilidad.
Una posición incluye `campaign_id`, `opened_at`, `deadline`, stop y objetivo.
No hay inferencia de FX ni instrumentos con payout no lineal sin contrato.

La falta de caja, inventario completo, BBO vigente, soporte de calendario,
originalidad de casos o plazo admisible bloquea la propuesta. Un halt no
se convierte en un fill ficticio. Si una posición está vencida pero no hay
capacidad para cerrar, el recibo bloquea y exige reconciliación/gestión operativa;
no afirma haber respetado el deadline mediante una venta inexistente.

## Contrato de dataset/modelo

`HARPOON_JOINT_PATH_DATASET_1`: símbolos, nombres de features, origen,
`price_basis=SPLIT_ADJUSTED_TO_SAMPLE_ENTRY_SHARE_UNIT`,
`dividend_basis=FRACTION_OF_ENTRY_PRICE_PER_ENTRY_SHARE`, cobertura declarada y
casos originales. Cada caso tiene ID, inicio, features conocidos antes del inicio,
label_end exactamente 72 horas después, known_at posterior a ese fin, OHLC relativo
N×72×4, cash de dividendo N×72, calendario N×72 y hash de procedencia.
La primera apertura relativa debe ser 1: dólares absolutos no se aceptan como retornos.

El pronóstico usa análogos conjuntos y conserva covariación entre activos. Sólo
usa casos anteriores a calibrar y patrones de calendario compatibles. El
calentamiento mínimo es 20 casos, vecinos≤40 por defecto y soporte efectivo≥10.
Estos mínimos son parámetros de ingeniería, no muestras suficientes para una
certificación financiera. Las ponderaciones, incertidumbre HAC y escenarios de
estrés no tienen garantía universal de cobertura ni corrigen toda la búsqueda previa.

## Laboratorio registrado y alcance económico

El protocolo está en `research/frontier/protocol.json`. Se usa exclusivamente
el histórico archivado 2025 de AAPL, MSFT, BTC/USD y ETH/USD. Ambos nombres equity
están dentro de la consulta de corporate actions archivada, y cripto es spot.
Fuera de sesiones, los precios se transportan como marcas no negociables.
La disponibilidad de barras se supone fin+60 segundos; no se la presenta como
recepción histórica real. La normalización incorpora splits y derechos de
cash dividends; no reconstruye fills reales.

El primer intento `run_01` se detuvo por un hash de datetimes y se conserva con
incidente y enmienda. `run_02` construyó 239 casos y calibró 189 antes de la consulta
registrada del 15 de octubre 2025. Sus snapshots son **hipotéticos**: no una cuenta
ni posiciones del broker. BBO, costes y capacidad se modelan explícitamente con
barras conocidas, y no se venden como observaciones ejecutables.

La prueba temporal de noviembre puntuó 64 observaciones activo-decisión en total, con 3 decisiones
bloqueadas por falta de soporte de calendario. El Brier de identificación
condicional fue aproximadamente [0.132030, 0.132584] frente a
[0.132936, 0.133840] con pesos uniformes. Es una diferencia pequeña en histórico reutilizado;
no es una mejora predictiva prospectiva acreditada ni rentabilidad. Los límites
son de identificación por orden OHLC ambiguo, no intervalos de confianza muestral.
El comparador uniforme usa los mismos análogos seleccionados: no contrasta por
sí solo todo el valor de la selección de vecinos o de las features.

No se ejecutó un nuevo backtest económico, no se calibraron fills live y no se
promueve el modelo. El hecho de que la propuesta flat sea WAIT y la del ejemplo
con inventario sea EXIT no demuestra que esas decisiones produzcan alpha.

## Verificación y riesgos que permanecen

Las pruebas cubren futuros, madurez, normalización, identidad de modelo/estado,
calendario, halts, liquidez declarada, caja, financiación parcial, costes fijos,
riesgo/exposición, campañas, idempotencia, corrupción de recibos, fronteras de
barreras y CLI completa. La segunda valoración Decimal reproduce los pagos y
colas de la propuesta seleccionada con otra implementación del mismo autor.
No constituye revisión externa, prueba del óptimo dinámico global ni autenticación
de las fuentes. El benchmark mide únicamente cargas y hardware declarados.

El controlador implementa una acción actual y continuación protectora fija,
no una política futura aprendida completa. Una nueva llamada puede cambiar la
acción con un nuevo estado, pero nunca reinicia el plazo de la campaña observada.
El conjunto de tres escenarios, spreads futuros relativos constantes y capacidades
supuestas siguen siendo hipótesis por validar con observaciones adecuadas.

Todas las decisiones conservan `execution_allowed=false`, `liveApproved=false` y
`level9_accredited=false`. El código antiguo se mantiene para reproducir controles;
la incorporación a un servicio con autoridad de ejecución exige una fase distinta,
con revisión externa, reconciliación y aprobación explícita.

## Integración de los osciladores existentes

`frontier.features.oscillator_context` reutiliza los indicadores ya implementados,
con 150 días completados y corte por disponibilidad. `frontier_dataset.build`
acepta `context_mode="OSCILLATORS24"` para construir seis componentes por activo
(volatilidad, tendencia, histograma MACD, cambio de histograma, RSI y diferencia
estocástica), hasta cuatro activos. Es un adaptador funcional y probado; no
se ejecutó otro experimento para elegirlo después de observar resultados. El
laboratorio registrado conserva BASELINE16 y sus parámetros: no se sustituyen
retrospectivamente las features para mejorar sus métricas. La alternativa de
osciladores requiere su propio protocolo y evaluación antes de promoverla.

## Evidencia final de ingeniería

La reconstrucción final está archivada en [run_04](evidence/frontier/run_04/summary.json),
con ocho shards completos, metadatos del modelo y hashes. Conserva la receta y los
resultados iniciales; las ampliaciones de ingeniería están registradas por separado.
El [verificador](tools/frontier_verify.py) restaura el modelo, comprueba las fuentes,
repite las decisiones y verifica los pagos seleccionados mediante Decimal.

La suite completa aprobó **611 tests**, incluidos **59 del módulo nuevo**. Ruff
0.17.3 no reportó incidencias en las fuentes/pruebas nuevas y mypy 2.4.1 aprobó
16 archivos fuente con el alcance explícito del workflow. Los logs, versiones y
huellas están en [qa.json](evidence/frontier/qa/qa.json). El
[workflow](.github/workflows/frontier-core.yml) repite regresión, análisis,
reconstrucción y verificación de los artefactos archivados.

El [benchmark final](evidence/frontier/final_reproduction_and_benchmark.json)
reprodujo exactamente ambos recibos en este entorno: medianas de 0.178 s para el
estado sin posiciones y 0.270 s para el estado con inventario, tres repeticiones
por snapshot. Esos dos casos no son un SLA ni una medición de ejecución live.
La diferencia máxima de medias en la segunda valoración fue 5.69e-14 USD.
