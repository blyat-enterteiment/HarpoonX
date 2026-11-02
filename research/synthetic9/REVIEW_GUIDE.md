# Paquete de revisión reproducible: banco sintético

Este expediente permite revisar ingeniería y reproducibilidad. No contiene
ejecuciones de una bolsa ni certifica rentabilidad o una revisión externa.
El desarrollador escribió tanto el simulador como el verificador Decimal.

## Recorrido de un revisor

1. Conservar el commit examinado y comprobar `manifest.json`: hashes de los
   artefactos y de las fuentes, protocolo registrado y versión declarada.
   Un hash confirma identidad del contenido, no identidad de un proveedor.
2. Ejecutar `tools/verify_synthetic9.py` en un proceso nuevo. Este proceso no
   importa `synthetic9.bank`, `synthetic9.execution` ni `synthetic9.ledger`.
   Reconstruye efectivo e inventario con Decimal y contrasta todos los marks.
3. Revisar decisiones, BBO, órdenes, ACK, cancelaciones, fills y comisiones en
   los archivos de `accounts/`. Revisar especialmente las reservas por fills
   anunciados pero aún no recibidos y los intentos de doble venta.
4. Contrastar las ventanas de entrenamiento contra `markets/`. El verificador
   reconstruye features y modelos, comprueba madurez de labels y vuelve a
   valorar las propuestas admisibles con el comprobador Decimal del core.
5. Revisar `fault_matrix.json`, los tests adversariales y sus rechazos. Un halt
   que deja una posición pendiente debe aparecer como incumplimiento; nunca
   como una liquidación inventada para aprobar la prueba.
6. Reconstruir el banco desde el commit publicado y comparar índice, métricas
   y trazas. `benchmark.json` mide una carga concreta; no es un SLA de trading.
7. Emitir conclusiones propias con identidad, alcance, commit, comandos,
   limitaciones y conflictos de interés. Registrar esa revisión en un documento
   separado: ningún archivo de este paquete la afirma como realizada.

## Cuestiones que requieren juicio independiente

- ¿Los escenarios representan riesgos importantes o favorecen al candidato?
- ¿El capital continuo, los costes comunes y la comparación con CASH están
  contabilizados una sola vez? ¿Se mantienen pérdidas e inventario abierto?
- ¿El modelo consume únicamente información que ya existía al decidir?
- ¿La ventaja en una tendencia creada por el generador demuestra algo sobre
  mercados reales? El protocolo responde que no.
- ¿Los costes, disponibilidad, retrasos, rechazos y parciales son realistas?
  Aquí son supuestos. No hay L2/L3, prioridad de cola ni impacto empírico.
- ¿La resolución horaria, la latencia de coste modelada y el calendario UTC
  simplificado son adecuados para la siguiente fase?
- ¿Se informa cada incumplimiento del deadline aunque el cierre llegue después?
- ¿Se retienen periodos negativos y escenarios fallidos sin cambiar las semillas?
- ¿Existe evidencia fuera del generador para las conclusiones económicas?
  Este expediente no la contiene.

## Evidencia adicional para cerrar las puertas reales

| Puerta | Evidencia que falta |
| --- | --- |
| Fills reales | Recibos originales del broker/venue, decisiones y BBO enlazados, fees completos, inventario/caja reconciliados y derechos de uso |
| Validación prospectiva | Protocolo congelado antes del periodo real; cuenta continua, costes completos, comparación registrada, incertidumbre y criterios de abandono |
| Revisión externa | Revisión realizada por un tercero distinto del desarrollador, con identidad y alcance verificables y hallazgos resueltos |

Los estados `real_fills_present`, `real_prospective_validation`,
`external_review_completed`, `execution_allowed` y `level9_accredited`
permanecen en `false`. Cambiarlos manualmente invalida la verificación.
