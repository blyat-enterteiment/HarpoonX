# HARPOON — entrega final del ciclo offline

**Se concluyó la implementación y la investigación offline autorizada. Las seis recetas se rechazan; no queda un candidato para promoción a operativa real.** Los 49 validadores tienen dictamen: 26 PASS de alcance limitado, 22 BLOCKED y 1 FAIL. Esto concluye el ciclo de trabajo y documenta los requisitos pendientes; no declara aprobadas las doce fases ni acredita un nivel 9.

El código y la evidencia se entregan en el [PR #1, en borrador](https://github.com/blyat-enterteiment/HarpoonX/pull/1). No se realizó un despliegue ni se enviaron órdenes.

## Resultado económico

Se evaluaron tres hipótesis y seis recetas completas, cada una en nominal y estrés. Cada cuenta parte de 20.000 USD y continúa sin reinicios. El periodo reutilizado abarca 404 sesiones, del 11 de marzo de 2025 al 16 de octubre de 2026, y 585 días naturales. Son resultados históricos modelados, con costes registrados como supuestos del experimento.

| Receta | Neto nominal USD | Neto estrés USD | Campañas nominal / estrés |
| --- | ---: | ---: | ---: |
| H1 — continuación por horario a 24 h | −535,50 | −1.170,00 | 1 / 0 |
| H1 — selección entre 24, 48 y 72 h | −585,69 | −1.167,27 | 3 / 2 |
| H2 — aceptación del gap | −189,51 | −782,16 | 9 / 9 |
| H2 — gap y confirmación sectorial | −262,73 | −859,98 | 6 / 6 |
| H3 — salida total por valor | −407,08 | −1.062,23 | 52 / 52 |
| H3 — reducción parcial por valor | −463,41 | −1.102,39 | 46 / 46 |

La continuación original, reevaluada con gasto por día natural, termina en −54,42 USD nominal y −701,41 USD bajo estrés. Sus 530,58 USD de contribución nominal antes del gasto común no cubren los 585 USD modelados de infraestructura. El resultado archivado de +126,58 USD descontaba 404 sesiones; el nuevo protocolo cubre también los días sin sesión. Los importes de 1 USD/día nominal y 2 USD/día en estrés son supuestos, no facturas verificadas.

H1 y H2 no alcanzan el mínimo registrado de 20 campañas. El error predictivo del modelo de horario supera la previsión cero en los tres horizontes. Ninguna de las 96 cotas inferiores pareadas frente a los controles es positiva. La salida total H3 mejora +86,81/+62,40 USD sobre las mismas 45 entradas, cantidades y precios del control, pero su cuenta completa sigue perdiendo. Ese fragmento no se convirtió en otra receta.

Los resultados y sus límites están desarrollados en el [estudio conservado](../../research/roadmap9/README.md) y en los [resultados completos](../../evidence/roadmap9/research/results.json). La corrección del alcance de Ruff descrita más abajo prevalece sobre el párrafo de QA de ese estudio.

## Implementación comprobada

Se añadieron contabilidad Decimal de costes y comisiones nativas; reservas y conciliación de ajustes tardíos; ciclo de órdenes por eventos; recuperación y reintentos acotados; pronósticos causales por horizonte; registro de investigación; admisión de observaciones; salud, degradación y revisión de evidencia. Las salidas conservan el deadline original de cada campaña.

El replay de 108 cuentas sintéticas conserva entradas y primeros intentos de salida. Los retrasos CORE respecto al deadline planificado pasan de 16 a 0; el control pasa de 57 a 0. Los 16 casos no eran excedencias del máximo de 72 horas. La prueba verifica el comportamiento dentro de ese banco sintético, no un plazo garantizado por un broker.

También se implementó un asignador robusto discreto para acciones y ETF en USD. Una comprobación Decimal separada reconstruye sus cuentas y 121 combinaciones de fills parciales de un caso de prueba. Este componente no está integrado en las seis recetas ni en el servicio de producción; no se le atribuye rentabilidad.

## Verificación y correcciones de QA

La pasada local completa tiene **772 pruebas correctas, cero fallos, errores u omisiones**. La [regresión completa en GitHub](https://github.com/blyat-enterteiment/HarpoonX/actions/runs/41576269940) también ejecutó 772 pruebas y terminó correctamente sobre la revisión de dependencias `b5cd6f2f988272c26ee4edcd780b393b8a02c51e`.

Se reprodujeron los dos baselines archivados, las 108 cuentas sintéticas y las 20 cuentas históricas. En estas últimas coincidieron exactamente los archivos comprimidos, modelos, señales, estadísticas y atribuciones. No se añadieron nuevas recetas ni nuevos casos históricos.

**Corrección del alcance de Ruff:** el pase local inicial carecía de la configuración `quant/pyproject.toml` en la copia de trabajo. La CI detectó observaciones de estilo y cuatro scripts publicados sin permiso ejecutable. Por tanto, las afirmaciones anteriores «Ruff pasa» de `CIERRE.md`, `closure.json` y `research_qa.json` no equivalen a un pase bajo la configuración del repositorio.

La revisión de CI restaura la configuración original, declara un perfil explícito, corrige sólo los cuatro modos ejecutables y conserva las observaciones conocidas por archivo, regla, ubicación y hash. El verificador compara la salida JSON completa de Ruff contra esa línea base: un hallazgo nuevo, un cambio de fuente/configuración o una discrepancia de versión bloquean el pase. No se desactivan reglas globalmente. El resultado se denomina aceptación de la línea base, no ausencia de observaciones. Los detalles quedan en [la adenda de CI](../../evidence/roadmap9/validation/ci_lint_addendum.json).

Mypy pasa en el paquete y las herramientas no congeladas. Permanecen nueve hallazgos conocidos en dos scripts históricos congelados. Se conservan sus bytes y su reproducción económica; no se anuncia un pase estático universal.

**V040 permanece FAIL:** el perfil registrado de 288 contextos dio p95 de 2,051 s frente a un objetivo de 2,000 s. El p99 fue 2,189 s y el máximo 2,318 s. Los 279 cálculos completos y nueve rechazos previstos no tuvieron fallos inesperados. Una medición posterior en un runner de CI tiene su propio entorno y no sustituye este recibo ni cambia su dictamen.

## Incidencia preservada y requisitos pendientes

El registro mostró un recibo de once resultados y una lectura posterior con diez, aunque había doce inicios y doce resultados financieros. La causa sigue sin establecerse. Se conservaron ambos estados y se añadieron sólo los dos RESULT ausentes, ligados a resultados existentes. La reproducción exacta verificó la cadena reconciliada 12/12. No se afirma un historial global de búsqueda completo ni una atestación temporal externa.

Siguen pendientes las tarifas reales de cuenta, datos originales con disponibilidad temporal y universo elegible, flujos de subasta y contexto de volatilidad implícita, integración completa del servicio, resolución demostrada del timeout legado, adaptación de la asignación cripto, fills observados, confirmación prospectiva y revisión externa. La evidencia actual tampoco satisface rentabilidad neta positiva a riesgo comparable. No hay un candidato elegible para abrir un ensayo de promoción.

## Documentos y alcance de versión

- [Dictamen completo de las doce fases y los 49 validadores](CIERRE.md).
- [Recibo verificable del cierre](closure.json) y [afirmaciones con referencias](claims.json).
- [Implementación, comandos y límites de operación](IMPLEMENTACION_Y_OPERACION.md).
- [Protocolo y reproducción económica](../../research/roadmap9/README.md).
- [Adenda de configuración y estilo de CI](../../evidence/roadmap9/validation/ci_lint_addendum.json).

El código científico está fijado en `ba0233e94bfa7f6158c1445cf3e6512446f11286` y los recibos del cierre en `736cdf1d36bcac4ec4312e5093adbfce013f88a9`. Sus manifiestos describen esas versiones. Las revisiones posteriores de dependencias, lint, modos de archivo y este documento se identifican por separado; no se presentan retrospectivamente como parte de la medición congelada. Esta entrega final corrige el alcance de la afirmación de Ruff sin alterar las recetas, cuentas, deadlines, fuentes científicas ni el resultado de V040.
