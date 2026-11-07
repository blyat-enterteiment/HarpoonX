# Capa de evidencia reutilizada del banco de pruebas

Se incorporó una capa ejecutable de clasificación, integridad y reproducción sobre HEAD `424cc9dad2f840284e19e61c3f9cb9db26b46286`. Su resultado es **historia reutilizada, ejecuciones modeladas y ninguna validación nueva de H1–H3**. No incorpora una política de trading, modifica el motor ni abre presupuesto de búsqueda.

## Resultado de esta entrega

| Comprobación ejecutada | Resultado |
|---|---|
| Archivos verificados contra SHA-256 congelados | 108 |
| Registros de cuentas clasificados | 26; no representan 26 muestras independientes |
| Extractor forense reproducido | 4 artefactos idénticos al archivo |
| Replay control/corregido, auditoría y estados causales | 10 artefactos idénticos al archivo |
| Tiempo de la reproducción y clasificación | 29.00 segundos en este host |
| Pruebas de ingeniería y regresión | 35 aprobadas: 12 nuevas y 23 existentes |
| Análisis estático / tipos | Ruff: 3 archivos; mypy: 2 archivos |
| Ensayos nuevos de políticas económicas | 0 |
| H1 / H2 / H3 | INCONCLUSO: no medidos; nominal y estrés son `null` |

Los 26 registros son 12 cuentas técnicas control/corregido, 8 horarias y 6 de matriz purgada. Los datos forenses derivados no se agregan como cuentas adicionales. Los informes horarios y de matriz se inspeccionaron y contrastaron por hash; sus motores **no se volvieron a ejecutar en esta entrega**. El modo de reproducción vuelve a ejecutar únicamente el extractor forense y la comparación técnica ya existente. Las pruebas de ingeniería contienen casos artificiales separados; no se incluyen como evidencia de mercado.

El reporte determinista es idéntico entre el modo que sólo clasifica archivos y el que además reproduce controles. `execution.json` registra por separado qué se ejecutó, tiempos y hashes de las reproducciones. No se presentan las validaciones antiguas como pruebas recién ejecutadas.

## Contrato de la capa

Cada cuenta queda vinculada al informe y cuenta originales y conserva:

- `history=REUSED`, `execution=MODELED`, `costs=ASSUMED_NOT_INVOICED`.
- `result_scope=ARCHIVED_RESULT_NOT_NEW_ESTIMATE` y `new_validation=false`.
- PnL archivado, número de campañas cerradas o compras, y la unidad explícita.
- `promotion_allowed=false`; las cuentas virtuales sin compras tienen `effect=UNIDENTIFIED_NO_BUYS`.

El reporte documenta los insumos compartidos por hash, la dependencia control/corregido y la reutilización de los mismos mercados entre políticas y escenarios de costes. El número de observaciones independientes queda `null`: contar archivos, campañas de diferentes políticas o reproducciones no lo identifica.

El ámbito sólo admite los archivos históricos modelados congelados. No importa observaciones PAPER o LIVE, fixtures sintéticas ni un holdout nuevo. Tampoco convierte las capturas retrospectivas de Alpaca en recibos originales del mercado. Los recibos de fills y facturas observados dentro de este conjunto siguen siendo cero. La comprobación de hashes acredita identidad de archivos, no su veracidad económica ni rentabilidad.

H1 protección causal, H2 presupuesto por gap y H3 gate condicionado usan su nombre completo para evitar confundirlas con recetas antiguas llamadas H1/H2/H3. Sus resultados siguen nulos, sin traducir ausencia de prueba en cero PnL, refutación o equivalencia. El presupuesto se recalcula con el auditor existente y debe coincidir con el registro congelado: total provisional 151 frente a techo 128; incluso descontando 20 reservas sin usar daría 131. No se libera esa reserva ni se certifica la conciliación global.

La capa falla con código 2 ante ausencia o alteración de archivos, contradicciones de alcance, resultados nuevos de H1–H3, afirmaciones de fills observados, claves JSON duplicadas o cambios de insumos durante la reproducción. No sobrescribe directorios de evidencia. Su reporte no permite autorizar ejecución ni acreditar nivel 8; esos campos permanecen falsos incluso ante un PnL archivado positivo.

## Reproducción

Desde la raíz del repositorio, con Python 3.12, NumPy y Node instalados:

```bash
# Clasificar y verificar los archivos existentes; no ejecuta estrategias.
PYTHONPATH=quant:tools python tools/run_reused_evidence.py --output-dir /tmp/harpoon_scope_new

# Además reproduce los controles forenses y técnicos ya existentes.
PYTHONPATH=quant:tools OPENBLAS_NUM_THREADS=1 python tools/run_reused_evidence.py --reproduce-existing --output-dir /tmp/harpoon_scope_reproduction_new

# Ingeniería e integración de la capa y regresiones relacionadas.
PYTHONPATH=quant:tools:quant/tests OPENBLAS_NUM_THREADS=1 python -m unittest quant.tests.test_evidence_scope quant.tests.test_causal_integrity quant.tests.test_forensic_features quant.tests.test_technical_swing -v

python -m ruff check quant/harpoon_quant/evidence_scope.py tools/run_reused_evidence.py quant/tests/test_evidence_scope.py
MYPYPATH=quant:tools python -m mypy --follow-imports=silent quant/harpoon_quant/evidence_scope.py tools/run_reused_evidence.py
```

Cada comando de extracción exige un directorio de salida nuevo. `research/reused_evidence/protocol.json` fija el HEAD de partida, ámbito, lista permitida de operaciones, presupuesto adicional cero y hashes de datos, código, costes, calendarios y evidencia. No se refrescan los hashes automáticamente cuando cambia una fuente: el cambio exige revisión explícita del protocolo.

## Archivos y límites

- `quant/harpoon_quant/evidence_scope.py`: contratos y validación de integridad.
- `tools/run_reused_evidence.py`: clasificación y reproducción opcional de controles existentes.
- `quant/tests/test_evidence_scope.py`: pruebas adversariales y de integración.
- `evidence/reused_evidence/report.json`: cuentas, procedencia, dependencia y veredicto.
- `evidence/reused_evidence/execution.json`: qué se ejecutó en esta entrega.
- `evidence/reused_evidence/validation.json`: comandos, pruebas, tiempos y limitaciones.
- `evidence/reused_evidence/delivery_sha256.json`: hashes de la entrega, excluyendo el propio manifiesto.

El resultado económico previo permanece documentado en `docs/CAUSAL_ECONOMIC_VERDICT.md`. Esta capa evita elevar artificialmente su fuerza probatoria. No demuestra que H1–H3 funcionen o fallen; para cambiar ese estado hacen falta ensayos autorizados con presupuesto conciliado y evidencia adecuada. No se ejecutó la suite completa del repositorio ni pruebas JavaScript en esta entrega; el runtime JavaScript no fue modificado.
