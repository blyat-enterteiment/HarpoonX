# HARPOONX M11 — fase 7: contabilidad multicampaña y límite del acoplamiento

**Resultado de la unidad:** el diferencial terminal entre dos carteras largas (nativa OHLC y ejecución al primer cruce observado) se descompone exactamente, en las fixtures completas comprobadas, en **P&L por diferencia de inventario**, **diferencia de pagos/fees de ejecución** y **diferencia de costes fijos**. Las decisiones de reserva nativas pasan sus verificaciones en el caso de prueba; **la equivalencia dinámica endógena de la cartera causal permanece no demostrada**. N9-S continúa **NO_GO**.

## Condición de autofinanciación y puente comprobado

Sea `q^j_{a,t-}` la cantidad larga del activo `a` antes de la marca `S_{a,t}`, y `\Delta q^j_{a,t}` una orden en el mismo reloj. Con precio llenado `P^j_{a,t}` y coste por fill `F^j_{a,t}`, el incremento de patrimonio marcado es:

`\Delta W^j = \sum_a q^j_{a,t-}\Delta S_{a,t} + \sum_a[\Delta q^j_{a,t}(S_{a,t}-P^j_{a,t})-F^j_{a,t}]-C^j_t`.

Por tanto, al comparar ambos libros `N` y `F` sobre las **mismas marcas discretas**, la diferencia se divide en términos exactos:

`W^N_T-W^F_T = (E^N-E^F) + (X^N-X^F) + (C^F-C^N)`.

La suma telescópica se reconcilia con dinero e inventario observados, sin declarar que un fill OHLC que no figura en el tape haya ocurrido realmente. Ese desajuste aparece en el **término de pago de ejecución**. **No se obtiene de esta identidad una cota de esperanza ni equivalencia causal.** Si el inventario difiere tras el primer fill, el término de exposición no desaparece y tampoco puede acotarse sumando únicamente cotas de barra con cantidad inicial común.

## Resultado de fixture de ingeniería de dos activos

Las dos operaciones usan el motor `replayFundedPortfolio` registrado, perfil `NATIVE72`, SYNA y SYNB, capital inicial 20.000 USD, fricción y comisiones nominales originales, cierre máximo 72 horas y ocho costes fijos diarios de 1 USD. No se han generado cuentas de mercado M9 ni reutilizado semillas M10.

| Concepto | Nativo | Primer cruce |
| --- | ---: | ---: |
| Equity terminal, USD | 19.975,74 | 19.977,06 |
| Neto tras todos los costes, USD | −24,26 | −22,94 |
| Caja conocida en segunda admisión, USD | 19.971,52 | 19.971,13 |

Diferencial de wealth **nativo − causal = −1,32 USD**, exactamente **+13,20 USD** por inventario expuesto, **−14,52 USD** por pagos/costes de ejecución y **0 USD** por coste fijo común. Los 0,39 USD distintos de caja conocida en la segunda decisión muestran que no debe suponerse que entradas, límites y cantidad futura siguen siendo iguales tras cambiar la ejecución, aunque en esta fixture se hayan mantenido fijos deliberadamente para aislar la comparación.

El límite triangular ex post de 2.204,71 USD es válido pero muy amplio; **no tiene interpretación de rendimiento esperado**. No se extrapola a la población WEAK ni permite contrastar el margen de la cota condicional de 0,905123 pb/día contra 1 pb/día.

## Verificación y deuda

- Protocolo preregistrado antes de CI: `research/modulation11/phase7_protocol.json`, commit `a40b03deaaf69b8840888258be255023ac3da0d8`. Códigos de objeto Git SHA-1 inmutables registrados allí y SHA-256 auditados en evidencia.
- GitHub Actions `42427635227`: **8/8 unitarias**, tipado JS con TypeScript, sintaxis Node, integridad SHA-256 del origen M9 y del registro M11, conciliación independiente con Python Decimal a 46 dígitos. Benchmark de ingeniería de 3.000 libros: 34,393 ms en un único runner (informativo).
- La suite cuantitativa **histórica** sigue con problema de trazabilidad SHA de `profit8_replay.js`; no se altera su registro para forzar verde. La auditoría independiente aquí es de **contabilidad de la fixture**, no una revisión externa económica.
- 0 candidatos nuevos, 0 cuentas económicas adicionales, alfa prospectivo 0, **3.200 finales M10 sin abrir**, sin brokers, despliegues ni merge. CASH y el mejor anterior se preservan como controles registrados pero no se usaron trayectorias económicas nuevas para compararlos.
- Se conservan incumplidos los dos gates de cobertura operativa de fallos de entrada/ejecución (parciales, rechazos, interrupciones, impacto) y coordinación multicelda. El 12% sigue siendo **límite de admisión/reserva**, nunca cap intrabar continuo.

## Siguiente unidad (aún no autorizada para búsqueda económica)

Construir el **coordinador causal mínimo de admisiones espejo**: recibir eventos exclusivamente en `knownAt`, reservar hasta `CLOSED/NO_FILL`, y redecidir cantidad IOC por libro con `risk, gross, cash` nativos exactamente registrados. Cuando diverjan admisiones por inventario/caja, no debe emparejarse a la fuerza un fill de otro libro. Sólo entonces cabe explorar una desigualdad de riqueza endógena para todas las trayectorias y comparar con la cota WEAK. No abrir una cuadrícula de señales ni el final M10.
