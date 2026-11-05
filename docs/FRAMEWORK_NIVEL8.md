# HARPOONX: framework técnico cuantitativo y validación de la meta 8

Fecha de revisión: 5 de noviembre de 2026. Capital de referencia: USD 20.000.

El framework tiene una [entrada integrada en el quant core y su worker Node](QUANT_CORE_FRAMEWORK.md): `python -m harpoon_quant framework`. La selección técnica, purga, costes y evaluación de ocho cuentas comparten un contrato explícito de solicitud y respuesta.

El framework incorpora los controles técnicos disponibles y una evaluación reproducible de la evidencia. **El resultado actual es REJECT y el nivel 8 no está acreditado.** La ingeniería aprobada no demuestra una ventaja económica.

“Nivel 8” es una convención interna propuesta para ordenar la validación. No equivale a 80% de aciertos, a un rendimiento garantizado ni a una calificación reconocida en el mercado. Los umbrales de este documento son un mandato de investigación que debe congelarse antes de una nueva evaluación. Aplicarlos al historial ya conocido produce un diagnóstico retrospectivo. No convierte ese historial en muestra reservada.

## Motor e integración de las propuestas

| Necesidad | Implementación que se conserva o incorpora | Alcance y criterio de cierre |
| --- | --- | --- |
| Alpha técnico | `feature_policy.py`, `technical_swing.py`, controles en core, calibración, regímenes y rutas | Precios, volumen, volatilidad y microestructura. No valoración fundamental como señal. Los vectores numéricos sin nombres todavía requieren validar procedencia fuera del modelo. |
| Aperturas, rupturas y confirmación | `TechnicalSwing`, `sector_decision` y `run_technical_swing.py` | Ruptura de rango, fuerza relativa por ETF y volumen relativo. Decisión posterior a disponibilidad de las barras. El experimento ampliado de cinco minutos sigue necesitando datos auténticos de varios sectores. |
| Universo conocido en cada fecha | `membership_at` | Usa vigencia y recepción, rechaza ambigüedad y caducidad. La integridad de bajas, incorporaciones y acciones corporativas exige fuentes completas. |
| Purga temporal | `training_indices` | Etiqueta conocida antes del corte menos 72 horas transcurridas. El investigador debe usar los índices en cada ajuste. La función aislada no garantiza que un modelo externo los respete. |
| Equity, ETF y cripto | `swing.replay`, `compound.paired_growth` y `run_compound_swing.py` | Ocho cuentas: conjunta, equity/ETF, cripto y efectivo, cada una nominal y estrés. Cada exclusión vuelve a simular la asignación sobre un mismo patrimonio. El estudio es horario y distinto del motor de aperturas de cinco minutos. |
| Crecimiento compuesto | Patrimonio continuo y suma de rendimientos logarítmicos | El tamaño depende del capital financiable y del riesgo disponible. No se suman porcentajes de cuentas independientes ni se reinicia capital por ventana. |
| Costes económicos | `order_costs`, `roadmap9/costs.py`, `roadmap9/forward.py` | Comisiones una vez, órdenes parciales y no ejecutadas, costes fijos y conciliación de cantidades nativas. El coste de oportunidad se presenta separado del PnL de caja. PAPER y LIVE se mantienen separados. |
| Salidas y supervivencia | Límites existentes, supervisión y ejecución de Roadmap9 | 72 h desde apertura original, pausa diaria 2%, drawdown 8%, exposición inicial máxima 12% y riesgo agregado de stops 0,25%. Un stop no garantiza ese máximo ante gaps. |
| Atribución económica completa | Nueva `trade_contributions` | Reconstruye cada campaña desde BUY/SELL y atribuye el dividendo al titular en la fecha ex, aunque se cobre después de vender. Un recibo antiguo sin símbolo necesita el mapa de acciones corporativas verificado. |
| Admisión económica | Nueva `qualification.qualify_history`, integrada en `review_compound_evidence.py` | Recalcula resultados, concentración, sensibilidad a ganancias excepcionales y cotas estadísticas. Nunca interpreta un booleano del archivo como autenticidad o acreditación. |
| Evidencia prospectiva | CLI existente `roadmap9 admit-forward` | Conciliación Decimal, comisiones pendientes, antigüedad de datos, inventario residual y firma de procedencia con claves confiables aportadas por el operador. La admisión permite analizar los registros, no acredita rentabilidad. |

No se cambia el motor de ejecución ni se habilitan órdenes. Las opciones permanecen fuera de la acreditación económica: requerirían contratos, multiplicadores, griegas, vencimientos, asignación y fills propios. No se asimilan a spot para completar una etiqueta multiactivo.

## Ocho condiciones obligatorias

El módulo evalúa condiciones que no se compensan entre sí. Aprobar siete no permite ignorar una pérdida o una fuente no verificada. Los conteos de PASS/FAIL/BLOCKED no son una escala de rentabilidad.

| Condición | Umbral o evidencia exigida | Estado de la revisión histórica |
| --- | --- | --- |
| G1. Ventaja económica | Retorno anual compuesto nominal >=10%, resultado de estrés >0 y resultado positivo al quitar la mayor contribución económica o el mejor día | FAIL |
| G2. Soporte estadístico | >=365 días y >=100 campañas cerradas por escenario; todas las cotas inferiores ajustadas de crecimiento absoluto e incremental >0 | FAIL |
| G3. Aporte multiactivo | >=20 campañas por clase y ningún símbolo con >50% de la suma de contribuciones positivas por símbolo; la adición de cada clase también debe superar G2 | FAIL por soporte cripto insuficiente |
| G4. Riesgo | Límites anteriores, posiciones y órdenes pendientes conciliadas, concentración sectorial y valoración intrabar con cobertura suficiente | BLOCKED, el cumplimiento en la malla disponible no prueba riesgo entre observaciones |
| G5. Datos y selección | Universo fechado, acciones corporativas, recepción causal, protocolo congelado, muestra sin consultar y registro de intentos | BLOCKED |
| G6. Ejecución y costes | Órdenes y facturas auténticas, costes calibrados por clase/lado/tamaño y estados de liquidez, órdenes fallidas incluidas | BLOCKED |
| G7. Comparador pasivo | Cartera pasiva financiada con presupuesto de riesgo fijado usando información previa y el mismo periodo y costes | BLOCKED |
| G8. Evidencia prospectiva | >=180 días de la receta congelada, conciliación observada, comparación nominal/estrés y revisión independiente del conjunto | BLOCKED |

Los mínimos de duración y número de campañas son pisos operativos propuestos, no pruebas de potencia estadística ni garantías de rendimiento. Los bloques de remuestreo presuponen suficiente estabilidad temporal. Se usan 20.000 remuestreos, bloques de 5 y 20 días y corrección local de 16 extremos: cuatro comparaciones, dos escenarios y dos longitudes. Los remuestreos no son observaciones adicionales. La corrección local no resuelve el historial global incompleto de selección.

La prueba de quitar una campaña mantiene las facturas fijas y resta su contribución atribuida. No reasigna ese capital retrospectivamente. La prueba de quitar un día elimina su incremento logarítmico. Ambas son diagnósticos de dependencia, no nuevas simulaciones financiadas.

## Resultado comprobado y brecha económica

| Medida | Nominal | Estrés |
| --- | ---: | ---: |
| PnL neto USD | -250,69 | -670,03 |
| Retorno sobre USD 20.000 | -1,2534% | -3,3501% |
| Campañas cerradas | 41 | 40 |
| Campañas cripto | 10 | 9 |
| Contribución tras costes variables, antes de fijos USD | 114,31 | 59,97 |
| Costes fijos USD | 365,00 | 730,00 |
| Coste fijo diario de equilibrio, conservando la misma trayectoria USD | 0,3132 | 0,1643 |

La brecha nominal hasta el objetivo propuesto de USD 2.000 anuales es **USD 2.250,69**. Eliminar todos los costes fijos en esta descomposición todavía dejaría solo USD 114,31 de contribución. Esa operación contable no vuelve a simular el tamaño de posiciones y no es una proyección de otra cuenta o escala de capital.

Los dividendos del libro conjunto archivado son cero, de modo que la corrección de atribución no cambia estos resultados. Las pruebas sintéticas sí reproducen el caso en que el error permitía aprobar indebidamente la eliminación de la mejor operación. No se inventa una mejora histórica a partir de esa corrección.

## Secuencia de incorporación y criterio de parada

1. Conservar los experimentos rechazados, sus fuentes y hashes. Esta revisión consume cero mediciones de nuevas estrategias. El último protocolo conserva una reserva documentada de 119/128, con historial global incompleto.
2. Completar el universo real de cinco minutos, ETFs de referencia y su historial de vigencias. Mantener la receta de apertura confirmada ya implementada y el control AAPL/MSFT. Registrar datos, código, costes y fechas antes de medir. No usar la fixture duplicada TESTA/TESTB como evidencia económica.
3. Reservar el lote previsto de seis cuentas solamente al contar con esos insumos y congelar su protocolo. Llevaría la reserva conocida a 125/128. No se ejecutó ni se reservó en esta revisión. Si se requieren más recetas, documentar la ampliación y su multiplicidad antes de explorar.
4. Evaluar el coste de cada oportunidad y la asignación con los componentes existentes. Una política nueva de abstención por margen neto, régimen, MACD o salida adaptativa constituye una nueva receta y consume presupuesto. No ajustar umbrales al ver el periodo de evaluación.
5. Si nominal o estrés pierden, rechazar esa receta. Si el rendimiento es positivo pero la incertidumbre o la procedencia siguen abiertas, mantenerla en investigación. No elevar exposición para ocultar la ausencia de ventaja.
6. Una receta que supere los diagnósticos necesita un comparador pasivo preregistrado y una evaluación prospectiva congelada. Reconciliar registros con `admit-forward`, verificar costes, riesgo y firmas, y someter toda la evidencia a revisión independiente. Los controles G4–G8 no se cierran con el comando histórico ni con un archivo que declare PASS.

## Uso y evidencia

Desde la raíz del repositorio, Python 3.12 y Node 24:

```bash
PYTHONPATH=quant:tools python -B tools/review_compound_evidence.py evidence/compound_swing --level8
PYTHONPATH=quant:tools python -B tools/review_compound_evidence.py evidence/compound_swing --require-level8
PYTHONPATH=quant OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python -B -m unittest discover -s quant/tests
```

El primer comando entrega el diagnóstico sin autorizar ejecución. El segundo termina con código **2**, esperado mientras no haya acreditación. Una excepción de integridad termina con error y debe investigarse. El informe conserva hashes de fuentes, código y cuentas. Los hashes prueban consistencia de bytes, no procedencia de mercado.

Para los registros originales se conserva la interfaz `python -m harpoon_quant.roadmap9 admit-forward --packet ARCHIVO --protocol ARCHIVO --trust-store ARCHIVO --now-ms EPOCH_MS --output INFORME`. Requiere el contrato normalizado de `roadmap9/forward.py`; no fabrica órdenes, cuentas, firmas ni datos faltantes. Los registros privados y claves no deben subirse al repositorio.

El informe ejecutado está en `evidence/compound_swing/level8_review.json`. El recibo de validación y su manifiesto SHA-256 están en `evidence/compound_swing/qualification_validation.json` y `qualification_sha256.json`.

Referencias primarias: [limitaciones de PAPER de Alpaca](https://docs.alpaca.markets/us/docs/paper-trading) y [Bailey y López de Prado sobre sesgo de selección y múltiples pruebas](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf). El módulo usa remuestreo por bloques, no declara haber implementado el DSR de ese artículo.
