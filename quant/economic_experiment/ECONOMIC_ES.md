# HarpoonX · descompresión económica ejecutada · 1.3 / XXXUltimate 30.7

**Decisión: REJECTED.** El cambio finalista reduce la pérdida media sintética pero no consigue beneficio ni crecimiento logarítmico positivos. No se activó una política ni se enviaron órdenes. Se detiene la búsqueda tras 14 configuraciones; no se sigue ajustando el holdout.

## Hechos reproducidos

El experimento anterior se reprodujo exactamente: retorno normalizado −1.412289445%, −282.457889 USD, drawdown 1.622319573%, Sortino diario −0.247576904, 15 cierres. Los precios y resultados son sintéticos. El ZIP original tenía el final truncado: se recuperaron siete miembros completos con CRC verificado, incluidos script y datos. El motor 1.2 y el paquete 30.6 estaban íntegros. Se reprodujo el journal de nueve ensayos desde el script íntegro y resultados idénticos: no es un journal original autenticado recuperado.

La conciliación de los 15 cierres suma −283.458212 USD entre ventanas reiniciadas. Es distinta del P&L del índice normalizado. Gross mid-to-mid: −198.168438 USD; fricciones modeladas: 85.289773 USD. Delta −49.808595, gamma +72.887486, vega −39.635375, theta −213.065428 y residuo +31.453474 USD. Las griegas son una aproximación local bajo Black-Scholes, no una identificación causal empírica. No basta eliminar costes: el resultado bruto ya era negativo. El diagnóstico retrospectivo de salidas encuentra MFE positivo sumado de 82.25 USD y distancia a la mejor marca diaria posterior de 307.87 USD; son cotas de hindsight no ejecutables. Los tres mayores cierres negativos explican 104.17 USD, 33.72% de pérdidas brutas, no un 80% forzado.

## Hipótesis e implementación

A: estimación AR agrupada sobre 120 días pasados, integración de la distribución de precios con cuadratura de Gauss-Hermite y reserva de incertidumbre de 10% de financiación.

B: elegir entre prima larga y acción pagada para dirección call por ventaja neta estimada sobre capital. Para put se mantiene prima larga. No se vende en corto. Spreads multileg se bloquean por falta de verificación de permisos y ejecución; no se inventa soporte operativo.

C: DTE 45 y distancia de una sigma frente a DTE 21 y 1.7 sigmas.

D: filtro de antigüedad de 30 segundos, spread máximo 10% y profundidad sintética. Se aplica al candidato descubierto en opciones incluso cuando B elige la acción. No es un libro real de ejecución bursátil. No se asume fill a midpoint; las compras pagan ask modelado y las salidas reciben bid menos comisiones.

E: salida por +/-35%, invalidación conocida, parciales enteros cuando hay al menos dos lotes y límite de 72 horas.

F: máximo cuatro posiciones, factor 25% y riesgo abierto 0.8%; siempre dentro de los límites originales.

Se ejecutaron BASE, A–F, ALL y seis ablaciones NO_A–NO_F. El criterio seleccionó B sobre el peor crecimiento diario entre tres semillas de desarrollo. No se eligió el mejor camino OOS. La validación del modelo AR es rolling causal; la elección de configuración usa el bloque de desarrollo completo, no un nested CV adicional. Se purgan entradas que no pueden cerrarse dentro de las ventanas y hay separación superior a 72 horas entre desarrollo y holdout. Los nuevos caminos sintéticos usan semillas nuevas; no son un nuevo periodo observado de mercado, aunque fechas de calendario coincidan con el experimento previo.

## Cuenta financiada y riesgo

Cada camino conserva una única cuenta de 20,000 USD durante todo el periodo de evaluación, sin reinicios internos. Los cinco caminos son universos artificiales independientes, no una cartera sumada. Se reportan media, rango y resultados individuales, sin concatenarlos como si fueran riqueza real.

El replay reserva primas, efectivo y comisiones de cierre; usa lotes enteros, márgenes de exposición originales y revalúa delta/gamma/vega en tres marcas por sesión. Riesgo máximo por operación 0.25%, riesgo abierto 1.5%, exposición bruta 50%, por activo 12%, factor 50%, ocho posiciones, daily loss 2% y drawdown 8%. No se incrementan límites. Para acciones, el riesgo por lote se toma como el importe íntegro pagado: es muy conservador y limita capital desplegado; no se supone que un stop garantice pérdida máxima ante gaps.

Los costes base asumidos son 0.65 USD por contrato y lado, spread relativo de opciones 8%–12%, precios redondeados a centavos y spread de acciones 10 bps sin comisión por acción. Son supuestos del experimento, no tarifas verificadas de Alpaca.

## Calendario y Alpaca

Se recuperaron 711 sesiones del calendario Alpaca, 2024-01-02 a 2026-10-30, con festivos, cierres anticipados y zona America/New_York. Entrada 09:45; seguimiento 10:00 y 15 minutos antes del cierre. El vencimiento temporal se ajusta al último punto de negociación disponible antes de 72 horas. No hay precios de opciones de fin de semana.

OPRA fue rechazado por suscripción insuficiente. El conector disponible expone datos, no el estado de permisos de cuenta: nivel, buying power y autorización real de opciones permanecen sin verificar. Documentación oficial: long calls/puts requieren nivel correspondiente; multileg tiene requisitos distintos. La existencia del endpoint no valida la cuenta.

## Registro y resultados

`protocol.json` precede a las evaluaciones. Tres semillas de desarrollo: 610301–610303; cinco nuevas de holdout: 610311–610315. Desarrollo desde 2024-07-01 hasta 2026-06-25; holdout 2026-07-01 a 2026-10-30. Código y protocolo se congelan antes de generar los precios del holdout. La especificación numérica adicional del análisis de intervalos se fijó después de generar el holdout pero antes de inspeccionar sus cifras; se conserva esa secuencia y no se presenta como preregistro completo anterior a toda generación.

Saldo reconstruido inicial: 9/128. Nuevos ensayos reservados antes de calcular: 14. Saldo final: 23/128, quedan 105. ResearchLab heredado conserva su ledger separado: no se afirma que se haya unificado. SQLite y hashes comprueban integridad local, no autenticidad de un proveedor.

Resultado medio por camino:

| Métrica | BASE | B finalista |
|---|---:|---:|
| Beneficio neto USD | −71.72 | −38.18 |
| Retorno sobre 20,000 USD | −0.3586% | −0.1909% |
| Crecimiento logarítmico diario medio | −0.00002951 | −0.00001569 |
| Mediana Sortino diario | −0.1602 | −0.1107 |
| Peor drawdown entre caminos | 0.8254% | 0.7608% |
| Cierres totales, cinco caminos | 23 | 1,251 |

Mejora relativa media: +33.54 USD; sigue por debajo de liquidez sin interés (0 USD, supuesto). 1,240 cierres del candidato son acciones y 11 opciones: no se ha demostrado ventaja positiva en opciones. Dos caminos ganan, tres pierden. Costes x1.5: −46.75 USD de media; x2: −51.44 USD.

## Inferencia y decisión

Bootstrap jerárquico pareado: 51,200 réplicas por longitud de bloque de 3, 5 y 10 sesiones; cinco caminos y 86 sesiones por camino. Corrección familiar conservadora con cota 128. Todas las cotas inferiores de mejora son negativas. MDE aproximado a potencia 80%: 0.00008389 de retorno log por sesión; efecto observado 0.00001961. Son aproximaciones de modelo sobre cinco trayectorias artificiales; no probabilidades de ganar en mercado. PSR/DSR no deciden la aceptación.

Falla beneficio positivo, crecimiento positivo, cota inferior positiva, drawdown no peor en todos los caminos y robustez a costes. El criterio de al menos 20 cierres por camino se cumple para B; no acredita suficiencia por sí solo. No se habilita PAPER automáticamente ni real.

## Límites que quedan abiertos

Los precios son europeos sintéticos, sin dividendos, ejercicio anticipado, asignación, colas del libro, impacto por tamaño ni fills observados. Los escenarios gaps/IV son haircuts de marcas de liquidación; delay aplica un buffer a la señal y outage bloquea entradas manteniendo salidas independientes. Son aproximaciones declaradas, no simulaciones completas de shock de subyacente, IV, colas o caída de red. La profundidad y antigüedad son sintéticas. No confundir este replay con la gestión íntegra de salidas del coordinador de producción.

## Reproducción

El complemento `economic_experiment` conserva `work/HarpoonX_Motor_Quant/harpoon_quant`, `reproduction`, `study`, `evidence`, registro, conciliación y análisis. Desde esa carpeta:

```
python forensic.py
python workflow_tests.py
python analyze.py
```

El análisis terminal recalcula estadísticas sin buscar nuevas políticas. El journal del estudio finalizado impide repetir `develop` y `holdout`. Para réplica determinista aislada sin nuevo descubrimiento, `python reproduce_study.py` crea una copia temporal del protocolo y del estado inicial reconstruido, ejecuta exactamente las mismas variantes y compara el resultado con el original. No usa la copia para extender el presupuesto.

Motor offline:

```
python -m harpoon_quant.economic_lab develop --directory RUTA_ESTUDIO_REGISTRADO
python -m harpoon_quant.economic_lab holdout --directory RUTA_ESTUDIO_REGISTRADO
```

El runtime conserva su calibrador anterior y sus salidas. El nuevo módulo genera evidencia investigadora y no promueve políticas al bridge. Siguiente paso económico: precios históricos bid/ask autorizados y un nuevo protocolo de validación prospectiva; no seguir optimizando el holdout rechazado.

Fuentes primarias: https://docs.alpaca.markets/us/docs/options-trading y https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf .
