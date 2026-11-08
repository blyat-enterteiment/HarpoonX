# FWN9 M11 P9M-C4 — Contrato de alcanzabilidad del precio y envolvente condicional exacta

**Dictamen: PASS de ingeniería de catálogo finito; NO_GO N9-S.** No se modificó el generador ni ningún precio, riesgo, coste, plazo o umbral contractual. El PR #7 sigue siendo borrador. No se ejecutaron cuentas económicas ni se utilizaron semillas de mercado/final.

## Resultado material

Con una misma barra fabricada de OHLC **100/104/96/100**, los ocho subpasos **[100.2,104,103,96,97,99,100,100]**, ocho acciones compradas a **100.03**, stop nativo **98.03** y dos objetivos, se enumeraron **todas las 5.040 permutaciones distintas de los primeros siete precios, dejando el octavo cierre fijo**. Esto conserva el OHLC, multiconjunto, costes, volumen y cierre. La enumeración se reconcilió con un algoritmo independiente Python Decimal 46 y el comparador de primer cruce original.

| Resultado neto de trading, USD | Valor |
| --- | ---: |
| Replay nativo OHLC stop-first | **−16.32** |
| Mínimo exacto primer cruce discreto (catálogo fijo) | **−32.56** |
| Máximo exacto primer cruce discreto (catálogo fijo) | **−10.58** |
| Intervalo de diferencia nativo menos primer cruce | **[−5.74, +16.24]** |

Histograma completo de las 5.040 ordenaciones: −32.56: **1.680**; −24.56: **1.680**; −16.58: **840**; −10.58: **840**. En 4.200 ordenaciones el nativo paga más que primer cruce y en 840 menos. **Estos conteos NO son probabilidades**, pues el catálogo no está ponderado por la ley generativa M9 ni constituye la distribución condicional poblacional. El precio OHLC nativo queda **dentro** de esta envolvente finita, por lo que estos ejemplos no permiten afirmar que el nativo siempre sea favorable o siempre imposible.

## Dos conceptos que NO deben confundirse

1. **Precio en el proceso discreto:** el stop 98.03 no es ninguno de los ocho precios ni la apertura. No es fill de primer cruce observado. Paridad exacta de secuencia de fills con el nativo: **cero** entre las 5.040 ordenaciones.
2. **Precio alcanzable mediante interpolación adicional:** una conexión continua log-lineal entre muestras sí atraviesa 98.03. Bajo esa *nueva convención determinista de trayectoria continua*, 3.360 ordenaciones reproducen el **pago** OHLC stop-first, mientras 1.680 llegan antes a TP1 y producen otra secuencia. **Ninguna** reproduce el timestamp efectivo `bar.end` del fill nativo porque el paso de la barrera ocurre antes; el recibo `knownAt` continúa vinculado a la publicación de barra. Una interpolación matemática no aporta una cotización negociable, profundidad de mercado ni igualdad con la ley original de ocho pasos.

El contrato de precio/tiempo es, por tanto, una elección material en la contabilidad. La cota WEAK de **0.905123 pb/día** es para un proceso autofinanciado con precios coherentes; **aún no se ha probado aplicable al replay OHLC nativo**. El intento de demostrar la equivalencia por trayectoria con el primer cruce es incompatible con este catálogo y los contraejemplos anteriores.

## Evidencia y QA

- Prerregistro del catálogo, hipótesis, criterios de refutación y hashes: `research/modulation11/fwn9_phase9m_c4_protocol.json`, fuente `3ab24ecfb243c138e88c1038cfd785014e3dd594`.
- Nuevo módulo `runtime30/fwn9_p9m_c4_attainability.cjs`; siete tests `tools/fwn9_p9m_c4_test.cjs`; auditor independiente `tools/fwn9_p9m_c4_accountant.py`.
- [GitHub Actions **42479897972**](https://github.com/blyat-enterteiment/HarpoonX/actions/runs/42479897972): **7/7 PASS**, `node --check`, `checkJs` focal PASS, auditor Decimal46 de las 5.040 permutaciones PASS, hashes Git del código registrado y SHA-256 del generador M9 intactos. Dos catálogos en runner: **163.782 ms** (benchmark acotado).
- Checksum SHA-256 de nuevas fuentes en `evidence/modulation11/fwn9_phase9m_c4.json`.
- No afirmar que toda la batería histórica de CI esté verde; los intentos fallidos de fases previas se conservan.
- CASH y la mejor estrategia anterior permanecen como controles económicos originales sin nuevas corridas: la presente fase sólo estudia semántica de ejecución.
- Capital USD20.000, reserva/admisión **12% (no cap continuo)**, riesgo 0,25%, máxima tenencia 72h, costos nominales/estrés, cinco mundos, umbrales y final M10 **sin cambios**.
- Cuentas económicas nuevas **0**; candidatos nuevos **0**; consumo de alfa prospectivo **0**; final M10 **3.200 cuentas sin abrir**. Sin conexión de broker, órdenes, despliegue, merge ni terceros.

## Próximo experimento estructural

`M11_PHASE9M_C5_NATIVE_EXECUTION_CREDIT_STOCHASTIC_BOUND`: si es posible, acotar matemáticamente la **esperanza del crédito de ejecución nativa frente al primer cruce** en el proceso lognormal M9 WEAK original, con cantidades predecibles, admisiones endógenas, reservas/recibos y costes. Una cota por fixture no puede sustituir una cota poblacional. La diferencia entre el techo original y hurdle nominal es de **0.094876753 pb/día**: sólo una cota válida del crédito neto permitiría decidir si el umbral es imposible en el contrato nativo. Si no puede demostrarse, reportar exactamente la premisa que falla y no promocionar el resultado.

Permanece abierta la cobertura de parciales de entrada/rechazos/interrupciones/impacto y la coordinación multicelda, así como la verificación económica prospectiva.
