# HarpoonX M11 — fase 5: cota por barra del diferencial de ejecución

**Dictamen:** cota superior e inferior **trayectoria por trayectoria** demostrada y comprobada para una barra OHLC con dos modelos de salida y el **mismo inventario anterior a la barra**. Esta cota **no es una cota de esperanza del replay completo** ni una prueba de imposibilidad de N9-S. La PR #7 sigue siendo borrador.

## 1. Contrato y resultado matemático

Sea una posición larga existente de `Q` acciones sin nuevas compras en la barra, con `L` mínimo, `H` máximo y `C` precio de cierre. Sea el precio realizable neto por acción `N(p)=tick*floor(p*(1-friction)/tick + 1e-8)-comision_por_accion`; el redondeo y costes coinciden con el comparador registrado. Para `p∈[L,H]`, `N(L)≤N(p)≤N(H)`.

Sean `sN` acciones vendidas por la salida OHLC nativa (stop-first, pago al umbral y contabilización al fin de la barra) y `sF` vendidas por el primer cruce de precios discretos. Ambas comienzan con el mismo inventario y coste de compra. Como toda acción no vendida se valora a `C`, el diferencial de wealth marcada `D=W_nativo-W_subpasos` satisface:

`sN*(N(L)-C)-sF*(N(H)-C) ≤ D ≤ sN*(N(H)-C)-sF*(N(L)-C)`.

Sin condicionar en `sN,sF`, una cota de valor absoluto es `|D|≤Q*(max(C,N(H))-min(C,N(L)))`. Ambas cotas son válidas **para cada barra que satisface las premisas**. No requieren que las reglas OHLC sean órdenes pasivas causales, y por ello no reparan la equivalencia refutada en fase 4. No se permite inferir una cota poblacional sin cotar de forma válida el valor esperado de inventario × rango de barra y sus dependencias causales.

## 2. Verificación determinista e independiente

La fixture bifurcada de fase 4, entrada 100,03 USD, ocho títulos, fricción por lado 0,0003, comisión 0,005 USD por título y tick 0,01:

| Rama | D nativo − observado (USD) | Límite inferior (USD) | Límite superior (USD) | Acciones vendidas N/F |
|---|---:|---:|---:|---:|
| Sólo target | −0,54 | −3,58 | +3,58 | 2/2 |
| Target previo seguido de stop | +15,66 | −50,32 | +50,32 | 8/8 |

Se reprodujeron **729 barras deterministas de ingeniería** con tres niveles discretos y seis posiciones variables, no una simulación del generador M9 ni nuevas observaciones económicas. Ocho tests cubren doble target, gap de apertura, barras sin cruce, sobrepaso de stop, corrupción de OHLC e invariantes de capital. Contabilidad externa en **Python Decimal** reprodujo ambos límites y diferenciales; TypeScript `--checkJs`, comprobación sintáctica y SHA-256 de fuentes M11 registradas aprobaron. **GitHub CI `42417069961`: 8/8**. Microbenchmark diagnóstico: 3.000 invocaciones en 97,815 ms (un solo host, no objetivo de rendimiento).

La ejecución inicial `42417009467` obtuvo 7/8: un test comparaba `-0` con `+0` mediante igualdad estricta de JavaScript. Se registró el fallo y corrigió únicamente esa expectativa de test, conservando intacto el módulo y los resultados de la primera ejecución. Ninguna de las dos ejecuciones representa una cuenta económica.

## 3. Significado para N9-S

La cota anterior de **0,9051232469572758 pb/día** para el modelo ideal WEAK permanece **condicional**. Su diferencia respecto al hurdle registrado de 1 pb/día es **0,0948767530427242 pb/día** de log-crecimiento esperado bajo el modelo hipotético de la demostración. **No es un beneficio demostrado ni un requerimiento cuantificado del motor nativo**, pues su ejecución y reservas no satisfacen aún las hipótesis del teorema.

Una cota por barra que depende de la trayectoria no limita automáticamente la esperanza del diferencial ni su concentración en estados favorables. Sin demostrar qué renta adicional produce el mecanismo OHLC bajo el generador congelado y cómo se financian todos los inventarios admitidos, **no hay certificado de imposibilidad del motor nativo ni aprobación N9-S**.

## 4. Reproducción y controles

- Protocolo inmutable de esta unidad: `research/modulation11/phase5_protocol.json`.
- Código de diagnóstico: `runtime30/modulation11_payoff_envelope.cjs` (sin salida al broker).
- Pruebas: `tools/modulation11_phase5_test.cjs` y `tools/modulation11_phase5_accountant.py`; workflow `.github/workflows/modulation11_phase5.yml`.
- Evidencia con checksums e intentos: `evidence/modulation11/phase5_payoff_envelope.json`.
- Capital compartido 20.000 USD, fricción y tick sin cambios, ninguna semilla de validación o final, 0 cuentas económicas, 0 nuevas recetas, 0 alfa gastado, 3.200 cuentas finales M10 intactas.
- La suite histórica cuantitativa conserva un problema distinto de procedencia SHA-256 en `runtime30/profit8_replay.js`; aprobar la suite focal no lo corrige ni equivale a auditoría general.

**Próxima unidad registrada:** integrar la contabilidad de inventario/reserva **en tiempo de evento** con el generador congelado y derivar una cota **en esperanza** del crédito potencial de ejecución nativa, o formular un protocolo económico nuevo para un motor de ejecución causal versionado. En ambos casos, no abrir nuevas señales hasta resolver el contrato económico y la demostración global de reservas. Faltan, además, ejecuciones de entrada parciales/rechazos/interrupciones/impacto y coordinador multicelda. 
