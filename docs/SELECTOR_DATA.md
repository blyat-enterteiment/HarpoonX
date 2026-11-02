# Datos Ridge · HARPOON XXX 30.1.0

El archivo contiene observaciones históricas, no órdenes. Tamaño máximo HTTP: 64 MB; el panel admite hasta 63 MB para dejar espacio al envoltorio JSON. Máximos por importación: 50.000 muestras, 600.000 eventos y 1.200 sesiones. Después del primer import sólo se admite el mismo contenido normalizado. Para otro histórico se necesita un experimento nuevo.

Campos obligatorios:

| Campo | Contrato |
|---|---|
| samples | Array de muestras con id único, at ISO, day NY, feature y, para ETF, selection_cohort observado |
| events | Array de eventos con id único, kind COTIZACIONES, at ISO y data.quotes |
| sessions | Objeto indexado por fecha NY YYYY-MM-DD con open, close, first, last, gap y market_return |
| source | SYNTHETIC_TEST conserva procedencia de prueba y prohíbe instalación. Otro histórico se identifica como USER_IMPORTED_OBSERVATIONS; no acredita origen broker |

Cada tupla de `data.quotes` tiene `[symbol, epochMilliseconds, bid, ask]`. El timestamp debe estar a no más de 15 segundos de la recepción del evento, con tolerancia futura de dos segundos; bid > 0 y ask >= bid. No se aceptan eventos futuros, muestras con barras posteriores a su observación ni fechas de sesión sin cerrar.

`feature` conserva el formato observado del evaluador: symbol, book (equity/etf), bar_end ISO, bid, ask, atr y las ocho variables numéricas rvol, momentum_bps, spread_bps, volume_acceleration, atr_pct, vwap_distance, sector_relative_bps y session_minutes. El replay necesita también los campos de elegibilidad de la receta, descritos en `src/plugins/securities_entries.js`, `src/lab_rules.js` y en los datasets de las pruebas de XII. Un registro que pasa estructura puede seguir siendo insuficiente para replay, ajuste o aceptación: ese motivo se devuelve por el worker.

`open`, `close`, `first` y `last` están en milisegundos Unix; `gap` es el mayor hueco de captura, también en milisegundos. `market_return` es retorno decimal observado de SPY en esa sesión. Para sesión completa se exige primera observación antes de open+10min, última después de close-30s y hueco máximo de 60s. No rellenes huecos con precios supuestos.

El histórico importado se restringe a observaciones anteriores al registro del experimento. Las 63 sesiones prospectivas sólo se acreditan a partir del registro propio del servidor. La exportación contiene `samples`, `events`, `sessions`, `source` y el indicador prospectivo calculado; no es un certificado de autenticidad del histórico importado.

API autenticada, mismo origen y cabecera de acción para POST:

- `POST /v1/control`: action selector-register, book equity/etf y costs con dataUsd, infraUsd, confirmed.
- `POST /v1/selector-data`: trialId y data con el contrato anterior.
- `GET /v1/selector-data?trialId=...`: observaciones reunidas.
- `POST /v1/research`: operation selector, trialId y diagnostic boolean.
- `POST /v1/control`: action selector-install, trialId y confirmation exacta INSTALAR SELECTOR PAPER.
- `POST /v1/control`: action selector-retire con trialId; selector-revoke con book.

Los resultados se producen internamente; no existe una ruta HTTP para cargar un informe aceptado ni pesos arbitrarios. Las pruebas positivas de instalación inyectan evidencia de control únicamente en el almacén aislado de QA y lo declaran en su nombre y comentarios.
