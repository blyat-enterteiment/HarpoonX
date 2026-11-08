# HARPOONX FWN9 — M11 Fase 9M-C8: ancla nativa de reservas (unidad A)

**Dictamen de alcance:** se refuta una desigualdad que usa el `snapshot.notionalUsd` bruto como ancla a precios actuales. Se confirma, sólo en fixtures con el API nativo de reservas, que un ancla que revaloriza la cantidad **original completa** puede cubrir la exposición. **No** se cierra la prueba universal del motor M9 ni se acredita N9-S.

## Fuente y exclusión

Esta unidad se preregistró en `research/modulation11/fwn9_phase9m_c8_protocol.json` antes de ejecutar sus fixtures. Usa **directamente** las funciones `reserveFundedEntry`, `snapshotFundedReservations` y `recordFundedReservationObservation` de `runtime30/ultimate_reservations.js` (no una sustitución del libro). El planificador nativo `planProfit8FundedEntry` se examinó en fuente: él añade `Math.max(0, quantity_original * reference.price - notionalUsd)` al gross **antes** de dimensionar, pero el snapshot del libro preserva el nocional nominal aprobado. **Las dos estructuras NO son el mismo B.** Los fixtures no ejecutan `replayFundedPortfolio`, no fabrican señales alcanzables y no reclaman equivalencia end-to-end.

Se conservaron la ley M9, el capital USD 20.000, las comisiones nominales USD 0,005 por acción y lado, la fricción nominal 3 pb por lado, el 12% como cap de **admisión/reserva**, el 0,25% de riesgo y el máximo 72 h. El capital de CASH y M9_BEST permanece de referencia, sin reejecutar sus cuentas.

## Contraejemplo nativo del snapshot bruto

En un libro de dos activos se reserva y abre SYNA (10 títulos a 200 USD; techo registrado 200,03 USD), y antes de la segunda decisión se conoce su marca de 220 USD. La equity de decisión, conciliada con comisión de entrada, es USD **20.199,95**. Con una reserva nueva SYNB de una unidad y techo 100,03 USD (riesgo conjunto USD 49,07 < 0,25% de equity), el API nativo admite la segunda reserva. La cantidad entera y el notional **sí** caben dentro del presupuesto de la decisión que añade la marca conservadora.

En el instante después del IOC, manteniendo los precios constantes desde esa decisión, la razón máxima de apreciación `M_tau,b` es **1**. Se obtiene:

| Magnitud | USD |
| --- | ---: |
| `B_tau = snapshot.notionalUsd` bruto | 2.100,33 |
| `q_b*S_b`: inventario real marcado | 2.300,00 |
| `B*_tau`: máximo(nocional reservado, cantidad original × marca) + techo pendiente | 2.300,03 |
| Límite bruto de admisión `0,12 × 20.199,95` | 2.423,994 |

Así, **`q_b S_b > B_tau M_tau,b` para B bruto**, incluso cuando ambas reservas se aceptan. Es un **contraejemplo del ancla equivocada**, no de la ancla corregida, del límite de riesgo M9 ni de una estrategia en mercado.

Un control adicional fuerza una marca previa de SYNA de 260 USD. `reserveFundedEntry` aislada todavía acepta SYNB atendiendo al nocional histórico, aunque `B*_tau=2.700,03` supera `0,12 × 20.599,95=2.471,994`. **El planificador nativo previo sí habría bloqueado** esa solicitud. Por tanto, ningún certificado puede depender sólo del resultado de la función de reservas; debe vincular los eventos de la **cadena completa** y sus valores conocidos en la decisión.

En el control `NO_FILL`, SYNB no genera inventario y la reserva sólo desaparece tras su recibo. En una venta parcial conocida de SYNA de tres títulos se comprueba que el snapshot conserva los diez originales y que caja, inventario y gastos se reconcilian sin liberar unilateralmente la reserva.

## Cota de momentos de precios (no de patrimonio)

Para WEAK y un instante terminal **fijo**, el mismo argumento compensado del diagnóstico M10 permite acotar los máximos retrospectivos de precios de ambos símbolos en una ventana con 312 barras y cuatro noches. Para `q>r`, acotando volatilidad, actividad y drift con el soporte original,

`E[M_t^r] <= { 2 (q/(q-1))^q exp(312[q*delta_max + ell_bar(q)] + 4[ell_night(q)+ell_jump(q)]) }^(r/q)`.

Con `r=2,q=4` el límite es **2,576834246631**; con `r=4,q=8`, **2,585329754532**. Se reprodujeron numéricamente mediante aritmética Decimal de precisión 60 independiente de JavaScript. La correlación entre los activos no se reemplaza por independencia: `max^q <= suma` y la cota se calcula por activo. La ventana extendida evita reducir falsamente el máximo a tres sesiones.

**Esto NO acota `E[W_tau^2]` ni `E[W_tau^4]`.** Tampoco certifica las marcas, divisiones por precio, liquidez y autofinanciación para todos los eventos nativos; las admisiones posteriores cambian al cambiar las salidas. Así, no existe todavía una cota numérica end-to-end para `E[W_T]`, y no procede aplicar Jensen para proclamar imposibilidad. El límite WEAK previo de **0,905123 pb/día** sigue siendo condicional, frente a 1 pb/día original.

## Verificación reproducible y presupuesto

- Fuente nueva: `tools/fwn9_p9m_c8_anchor_probe.cjs`, pruebas `tools/fwn9_p9m_c8_anchor_test.cjs`.
- Contador independiente Decimal-60: `tools/fwn9_p9m_c8_accountant.py`.
- Workflow de lectura/CI: `.github/workflows/fwn9_p9m_c8.yml`.
- Test de integridad de los tres hashes SHA-256 de fuentes M9 (según `research/modulation9/registration.json`) en CI; Git blob SHA-1 para fuentes nuevas en `evidence/modulation11/fwn9_phase9m_c8_anchor.json`.
- Se ejecutó la función real de reservas con un cargador aislado del archivo **idéntico al blob Git**: cuatro fixtures produjeron el rechazo del ancla cruda y las conciliaciones esperadas. Benchmark del probe aislado: 1.000 generaciones en alrededor de 246 ms; **no es un benchmark de replay económico**.
- Validación CI y de tipos: consultar estado del workflow, no confundir la prueba aislada con CI aprobada.

**Presupuesto de esta unidad:** 0 nuevas recetas, 0 cuentas económicas, 0 nuevas semillas, 0 alfa prospectiva y 0 de 3.200 finales M10 abiertos. El oráculo diagnóstico no participa. No hay órdenes, brokers, despliegues, fusiones ni contactos externos.

## Decisión y continuación

**NO_GO N9-S.** La próxima unidad debe certificar por inducción de eventos el **ancla corregida** usando el `referenceAt` causal, el planificador, el IOC real del replay y la recuperación de parciales/NO_FILL, antes de usar un lema de momentos de riqueza. Después es necesario acoplar la riqueza de políticas con admisiones divergentes y acotar `E[W_T]` bajo la ley WEAK. Los dos bloqueos operativos —ejecuciones parciales/rechazos/outages/impact completas y coordinación multicelda— permanecen abiertos. No abrir nuevos grids de señales.
