# HarpoonX M11 — P9M-C3: superficie causal finita de eventos, reservas y recibos

**Dictamen:** PASS de ingeniería delimitada, **NO_GO N9-S**. Hipótesis y catálogo finito registrados antes de ejecutar el código en `research/modulation11/fwn9_phase9m_c3_protocol.json` (commit `99f2cf317dae116cd994004a033d5ade3a0517d1`). Lease adquirido con CAS del HEAD; no se abrió un nuevo experimento económico. PR #7 continúa apilada sobre #6 y en borrador.

## Hallazgo causal confirmado
Para una barra de igual **OHLC, volumen, precio inicial, precio final y multiconjunto de ocho subpasos**, el motor nativo registra siempre el mismo stop y **-16,32 USD** netos. Dos órdenes admisibles de esos mismos subpasos producen, tras los mismos costes y la reconstrucción independiente de las ocho acciones, **-16,58 USD** (target primero) y **-32,56 USD** (stop primero). La distancia entre ambos caminos es **15,98 USD**; el nativo paga **0,26 USD más** que el más favorable de **esos dos caminos solamente**.

**Límite lógico:** no se enumeraron todas las permutaciones ni todos los caminos del proceso generador, así que la diferencia de 0,26 USD no es una cota global de optimismo del replay. Los resultados son fixtures de ingeniería reciclados y combinados, no alfa, ni mejora causal de rentabilidad, ni prueba de un sesgo esperado positivo/negativo para WEAK. El carácter causal del modelo de primer cruce tampoco demuestra profundidad/cola ni fills reales.

## Conciliación conjunta de dos activos
Se integraron dos casos de `P9M-C2` (SYNA financiado/SYNB IOC NO_FILL y el inverso) con el comparador de estado `P9M-C1`. Ambos auditan la marca disponible en la señal, la secuencia de reserva/recibo, el reloj `knownAt`, ausencia de inventario fantasma, costes por acción, caja y equity terminal. Se conserva expresamente que **12% es un gate de admisión/reserva y no un techo de exposición continuo**. `CASH` queda como control contable bajo el coste de calendario idéntico; el candidato previo se conserva como referencia histórica, no se recalcula con este catálogo sin simulación económica autorizada.

Se implementó `runtime30/fwn9_p9m_c3_surface_bridge.cjs`, con ocho pruebas de catálogo y mutación adversarial en `tools/fwn9_p9m_c3_test.cjs`. Ninguna firma ni checksum acredita operaciones observadas.

## Control de calidad y errores conservados
- Intento 1: [Actions 42474975346](https://github.com/blyat-enterteiment/HarpoonX/actions/runs/42474975346), **FAIL**, ocho pruebas focales PASS, pero el wrapper eliminó el prefijo `P9MC1_EVIDENCE=` requerido por el contador previo. El resultado negativo se conserva y cuenta como intento de ingeniería.
- Intento 2, workflow nuevo e inmutable: [Actions 42475052166](https://github.com/blyat-enterteiment/HarpoonX/actions/runs/42475052166), **SUCCESS**: **8/8 tests**, `node --check`, contador independiente Decimal-46 P9MC1 y P9MC2 (dos activos), Ruff y mypy estricto del contador previo. Benchmark diez verificaciones **135,121 ms**. Los workflows históricos ajenos a la fase no se declaran aprobados en bloque.
- SHA-256 de fuentes, protocolo y JSON de prueba: `evidence/modulation11/fwn9_phase9m_c3.json`. El resultado completo se reproduce con `node tools/fwn9_p9m_c3_test.cjs --emit-proof` y `--bench`. El archivo crudo grande histórico permanece en Library con identificador registrado en `state.raw_archive`.

## Alcance decisorio
La evidencia integrada **refuta la equivalencia exacta del precio OHLC nativo con el precio ejecutable al primer cruce observado** para este catálogo. No basta para certificar la cota WEAK de **0,905123 pb diarios** para toda la población del motor implementado: el teorema exige precios autofinanciados del proceso observado, mientras el nativo interpola algunos umbrales de salida. La no equivalencia no demuestra imposibilidad universal de alcanzar 1 pb diario; se prohíbe inferirlo.

Sin cambiar generador, capital 20.000 USD, límites, costes, hold máximo 72 h ni umbrales: **0 nuevos candidatos, 0 cuentas económicas, 0 alpha prospectiva, 0 finales M10 abiertas**. Los dos requisitos operativos pendientes (fallos/partiales/rechazo/impacto y multicelda) permanecen bloqueantes. No hubo broker, órdenes, despliegue, fusión ni terceros.

**Siguiente unidad estructural:** `P9M-C4`, analizar si existe una política de precios nativos causalmente realizable a nivel de toda la ley de ocho subpasos y reconciliar los marks de todas las decisiones/recibos. Construir un certificado de alcance definido antes de aplicar o refutar la cota de WEAK. No ampliar la cuadrícula de señales.
