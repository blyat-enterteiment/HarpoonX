# Revisión independiente por otro agente — HARPOON 30.18.0

Fecha: 2026-11-02 UTC. Revisión técnica local; **no auditoría externa, certificación financiera ni preregistro independiente**.

## Dictamen

Sin bloqueantes técnicos pendientes en el ámbito revisado. La candidata residual **no acredita nivel 8 ni ventaja económica confirmada**: falla el crecimiento neto positivo y todos los contrastes pareados ajustados, bajo ambos costes y bloques de 5/20 sesiones.

## Verificaciones realizadas

- **132/132 pruebas Python sintéticas aprobadas**, incluyendo modelo, registro, datos, estadísticas, verificador y gate forward.
- **53 pruebas Node aprobadas, 1 omitida, 0 fallidas**: adapter residual, HWM, cartera, reservas y plazos. La omisión es la comparación legacy opcional sin `HARPOON_LEGACY_RUNTIME`. Un fallo inicial de importación por falta de `ws` se resolvió mediante `npm ci` offline; la reejecución completa pasó.
- **323/323 bindings de fuente verificados**. SHA-256 del manifest: `acc9b83c2daa3a9b500e3a0aa1bc1d8b9b52681b70488ae9b1827d5e0803bdc6`.
- Reconstrucción pura del dataset desde **80 recibos originales retenidos**, con sus 80 hashes correctos: **124.182 barras**, 41.394 por activo, 533 sesiones y 5 adicionales de calendario. Cero huecos, recapturas o precios imputados frente al calendario recibido. Dataset SHA-256: `5546035f58a04255b35091191cd750bd3d86075380a8aed0c258edbff6cee530`.
- Las 78 capturas de precios son posteriores a la reserva local: reserva `2026-11-01T23:55:32.369901+00:00`; primera captura `2026-11-01T23:59:30.158Z`. Esto no acredita recepción contemporánea del mercado ni autenticación temporal externa.
- Registro/admisión verificados: **41 → 47 de 128**, secuencia final **87**, fuente ancestral preservada; seis mediciones y dos referencias CASH, sin variantes añadidas por este revisor.
- **8/8 reportes contables reauditados**. HWM y drawdown reconstruidos independientemente mediante incrementos cronológicos de entradas, marks, dividendos y costes; también coinciden los estados de decisión. Límites idénticos al protocolo, capital TEST igual al cierre de VALIDATION y máximo decisión→cierre de **71,99972222222222 horas**. Ninguna campaña cruzó el split.
- **17/17 archivos reales idénticos** entre `run_completed` y `reproduction`; hashes recalculados, no sólo lectura del recibo de reproducción. Ocho reportes y cero incidentes financieros en esta ejecución.

## Trazabilidad del protocolo

El hash reservado es `159358061b6593fc4a6c18d77e93498b8e496f8012f1a585ab8852b2758515e3`, no el hash inicialmente comunicado `67a1d2b5eea945f265c200c08d94a81604f740fe1b7761d32e3bced73434e54d`.

Se comprobó la revisión pre-reserva: revertir únicamente la aclaración `<=1e-6` a `<1e-6` y retirar `split_knowledge_contract` reconstruye exactamente el hash inicial. No cambiaron umbrales económicos, ventanas, universo ni presupuesto. El registro final precede las capturas de precios.

## Resultados y límites de interpretación

| Política | Nominal USD | Estrés USD |
|---|---:|---:|
| RESIDUAL_LONG | −118,65 | −598,37 |
| STOCK_THRESHOLD_OFF | +214,41 | −465,14 |
| SECTOR_TIMING_CONTROL | −430,18 | −898,78 |
| CASH con los mismos gastos | −404,00 | −808,00 |

La candidata realizó 67 campañas por escenario. Superar CASH descriptivamente no basta: pierde contra el control sin umbral y no supera los límites inferiores familiares. El control nominal positivo no se convierte retrospectivamente en ganador promovido.

Hubo 88 propuestas residual y 86 sector por escenario, con dos propuestas sin pareja; las campañas ejecutadas fueron 67 y 68, respectivamente. **No existe emparejamiento exacto de exposición, ejecución o duración**, ni inferencia de alpha causal o cartera cubierta.

El periodo ya fue utilizado globalmente. El score de recuperación del 50 % es una hipótesis, no un retorno esperado calibrado. Costes, fills, ajuste de precios y procedencia/publicación corporativa siguen siendo condicionales. La pérdida diaria estadística se verifica entre cierres; el HWM usa eventos modelados, no ticks ejecutables.

El freeze forward sólo fija identidad para una futura canalización de evidencia. La plantilla vacía está `DATA_BLOCKED`, `valid=false`; los indicadores de aprobación de estrategia, operación, rentabilidad y nivel 8 permanecen falsos. El gate estructural **no reconcilia por sí solo fills con PnL del libro ni certifica completitud económica real**.

## Alcance operativo del revisor

Se revisó código, se ejecutaron fixtures sintéticas y se cotejaron artefactos existentes mediante cálculos de auditoría de sólo lectura. No se ejecutó la familia financiera, no se ajustaron modelos con precios reales, no se reservaron slots reales ni se modificaron código, protocolo o datos sellados. Este archivo documental se añadió fuera del manifest de medición por solicitud del autor.
