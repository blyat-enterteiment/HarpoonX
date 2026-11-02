# Contrato de entradas · Harpoon Quant 1

Las validaciones efectivas están en `features`, `predict`, `instrument`, `pnl_lot`, `allocate` y `fit`. Todas las horas son ISO8601 con zona; los snapshots del coordinador contienen milisegundos Unix. Ninguna entrada puede conocerse después de la decisión. Moneda USD y posiciones long únicamente.

## Panel para fit

Objeto JSON con `origin`, `rows` y `asset_metadata`. Origen: `OBSERVED` o `SYNTHETIC_ENGINEERING_ONLY`. Cien fechas distintas es un mínimo técnico, no suficiencia estadística universal.

Cada fila:

| Campo | Tipo y unidad |
|---|---|
| `underlying` | Identificador estable del subyacente |
| `session` | Fecha UTC de `at`, YYYY-MM-DD |
| `at` | Momento de decisión |
| `features_known_at` | Disponibilidad real de las ocho variables, anterior o igual a `at` |
| `features` | Lista de ocho números, en el orden exacto de `core.FEATURES` |
| `label_end` | Momento de valoración al horizonte exacto del modelo |
| `label_known_at` | Disponibilidad del resultado; posterior o igual a `label_end` |
| `target_return` | Retorno simple del subyacente, por ejemplo 0.01 equivale a 1% |
| `iv_change` | Opcional; variación relativa de IV al mismo horizonte. 0.10 significa +10% de IV |

`available_at` del artefacto debe ser posterior a todas las etiquetas conocidas. Se permite una fila por activo y sesión. Las particiones exigen por activo al menos 40 fechas de entrenamiento, 10 de validación y 20 de test tras purga. El test de MSE no implica aceptación de una estrategia de trading ni valida la predictibilidad de IV. Para cada nombre, `asset_metadata[nombre]` debe incluir `book`, `factor` y `reference`; el descubridor de acciones exige `book=equity` y referencia no vacía. La etiqueta de metadatos y el origen son declaraciones del productor: el motor no certifica su autenticidad.

El cálculo de variables debe ser idéntico en entrenamiento y decisión. La red del coordinador usa acciones/ETF/opciones con barras 5Min y cripto con 15Min; no mezcles coeficientes entre escalas. La sesión de las barras para RVOL es la del mercado local; la sesión del panel de entrenamiento se expresa en UTC, según el contrato de `fit`.

## Request de allocate

Objeto con `asof`, `account`, `candidates` y `holdings`. Una decisión común para todos los activos, máximo 96 candidatos; el optimizador permite hasta 48 campañas configurables. El benchmark usa 48 candidatos, no 48 órdenes.

`account`: `equity`, `cash`, `buying_power` en USD; `pending_cash` no negativo; `daily_pnl` en USD; `drawdown_fraction` como fracción no negativa. Las cifras deben reflejar reservas reales y una misma cuenta. No hay consolidación automática de cuentas ni monedas.

Cada candidato:

| Campo | Significado |
|---|---|
| `id`, `symbol`, `underlying` | Identidad de propuesta, instrumento y modelo |
| `book` | `equity`, `etf`, `crypto`, `options` o `futures` |
| `currency`, `side` | `USD`, `long` |
| `factor` | Grupo de exposición compartida |
| `asof`, `known_at`, `quote_at` | Decisión, disponibilidad y tiempo del BBO |
| `bid`, `ask`, `spot` | BBO del instrumento y precio del subyacente; positivos, ask ≥ bid |
| `features` | Ocho variables del subyacente con unidades exactas de `FEATURES` |
| `multiplier` | Unidades económicas por contrato; no asumir siempre 100 |
| `step`, `lot_qty`, `max_qty` | Paso negociable, cantidad por lote computacional y máximo elegible |
| `entry` | Límite de compra; se valora al menos al ask |
| `fee_per_side_usd` | Comisión por unidad de cantidad y lado, no por nocional |
| `fixed_fee_usd` | Coste fijo total de campaña, opcional, no negativo |

Acciones, ETF, futuros y opciones requieren lotes enteros. Cripto admite fracciones según `step`. Los lotes computacionales de cripto del puente equivalen aproximadamente a USD250 y se ajustan al paso del catálogo; no son un tope de presupuesto. El núcleo decide cuántos lotes comprar según efectivo y riesgos.

Opciones: añadir `iv` anualizada en fracción, `delta` con signo válido, `rate`, `dividend_yield`, `strike`, `right` (`call`/`put`), `style` (`american`/`european`), `expiry_at` y `lifecycle_reviewed=true`. El horizonte debe terminar más de un día antes del vencimiento. El artefacto del subyacente debe contener variaciones de IV para las mismas fechas de residuos. Una serie genérica de IV por ticker puede ser insuficiente: el productor debe construir una calibración coherente con el contrato, tenor y régimen. No se imputa una curva ni se presume revisión de ejercicio/dividendos.

Futuros: añadir `initial_margin_usd` por contrato, `margin_verified=true` y `roll_reviewed=true`; `multiplier` refleja el valor monetario de un punto. El margen inmovilizado y la exposición nocional son conceptos separados. El modelo de estrés no es una garantía frente a margin calls o precios fuera de los escenarios.

`holdings`: mismo esquema, con `lot_qty` igual a la cantidad efectivamente poseída. Se revalora todo el inventario existente. Un activo sin modelo o datos suficientes bloquea nuevas entradas. La cuenta de cartera conserva el riesgo de las posiciones existentes; el asignador no vende ni coloca órdenes.

## Salida y auditoría

`selected` contiene cantidades operables por propuesta; `expected_net_usd` es una esperanza condicional del escenario, nunca un fill. `robust_incremental_usd` resta una penalización aproximada de incertidumbre. `cvar_usd` y `stress_worst_loss_usd` se calculan para la cartera propuesta. Los campos `partial_fill_cvar_upper_usd` y `partial_fill_stress_upper_usd` acotan cualquier subconjunto de nuevas entradas bajo los mismos escenarios, sin crédito por ganancias de otras propuestas. No son límites físicos a pérdidas futuras.

`model_hash`, `config_hash`, fecha y rechazos facilitan trazabilidad. `execution_allowed` solo habilita la admisibilidad técnica del plan cuando el origen declarado es observado. El estado continúa siendo de investigación, `liveApproved=false`, hasta que se establezca una validación financiera independiente. El puente Node además verifica condiciones operativas, PAPER y riesgo del coordinador antes de emitir una orden.
