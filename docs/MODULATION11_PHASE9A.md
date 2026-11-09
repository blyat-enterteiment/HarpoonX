# HARPOONX M11 — Fase 9A: campañas nativas completas frente a recibos causales
**Veredicto: NO_GO.** Esta unidad vincula el módulo independiente de admisión M11/P8 a **campañas completas generadas por el motor real `replayCampaign`**, con sus propias cantidades aprobadas, recibos IOC, salidas y el adaptador observacional de ocho subpasos. No usa resultados de mercados ni semillas M9/M10 y no prueba la ley WEAK poblacional.

## Resultados de ingeniería (dos activos, capital 20.000 USD)
| Trayectoria fija | Libro OHLC nativo | Primer cruce sobre subpasos | Diferencia OHLC−causal |
| --- | ---: | ---: | ---: |
| Flat, dos campañas 72 h, neto tras todos los costes | −9,68 USD | −9,68 USD | 0 USD |
| Stop/target intrabar adversarial, neto tras todos los costes | -33.32 USD | -33.71 USD | 0.39 USD |

En la segunda fixture ambos libros admitieron SYNA y SYNB con **12 acciones en cada campaña**. Los dos anchors nativos de decisión conservaron igualdad con el replay nativo en cantidad, equity, caja y reservas; eso vale **únicamente para los relojes de decisión observados**. Una diferencia de **0.39 USD** entre salidas OHLC y primer cruce **no establece rentabilidad ni ventaja causal**. La independencia de admisiones demostrada en M11/P8 sigue vigente, pero esta fixture P9A no la vuelve a demostrar.

El adaptador produce recibos a partir de campañas completas del replay nativo (`replayCampaign`) para cada cantidad admitida; el motor de reservas no recibe resultados antes de `knownAt`. La fuente histórica y los precios de las fixtures son sintéticos; un fill de umbral OHLC no se ha convertido mágicamente en una cotización negociable.

## Verificación registrada y gastos
- Protocolo de revisión: `research/modulation11/phase9a_v2_protocol.json`, preregistro `e0b835f54e7baa7829a846b420c4167b3cb3f736`.
- CI **42432220136**: 6/6 pruebas Node, sintaxis JS, chequeo tipado focal sin errores nuevos (8 errores TS2365 heredados), conciliación independiente Python Decimal 46, integridad SHA-256 de cuatro archivos y generador M9 original; benchmark indicativo **319.225 ms para 20 comparaciones**.
- Intento fallido **42432129803**, error de sintaxis previo a pruebas; se preservó archivo/protocolo inicial y se hizo una **revisión v2** sin reintentar ni reescribir ese resultado.
- Cero cuentas económicas, cero semillas nuevas o finales, cero alfa consumido; **3.200 cuentas finales M10 selladas**. CASH y el mejor candidato M10 continúan registrados, sin nuevas comparaciones de población.
- No se ha evaluado estabilidad entre mundos, peor sesión ni concentración en campañas con datos nuevos, porque esta unidad no ejecutó cuentas estadísticas. No se modifica la definición N9-S ni costes, capital, generador, limites o hold 72 h.

## Alcance matemático y siguiente unidad
La identidad contable y las admisiones originales se reproducen para estas campañas. **Falta** demostrar paridad de toda la curva de marcas, la regla de pérdida por sesión y drawdown a cada reloj observado, y una desigualdad de riqueza poblacional para admisiones endógenas. El 12% sigue siendo sólo **admisión/reserva**. Los requisitos de parciales, rechazos, caídas de servicio, impacto y coordinador multicelda siguen bloqueando N9-S.

**M11 Fase 9B:** incorporar los relojes reales de valoración/riesgo a los libros espejo y buscar contraejemplos de paridad del gate de pérdida diaria, manteniendo la ejecución y el coste original. No abrir ninguna nueva cuadrícula de señales, ni el holdout final.
