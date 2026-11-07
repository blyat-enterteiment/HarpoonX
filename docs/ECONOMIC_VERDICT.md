# Veredicto económico reproducible

Decisión: NO PROMOVER. Receta histórica horaria: RECHAZADA. Matriz virtual y variantes A/B: EVIDENCIA INSUFICIENTE; comparación no ejecutada. No es un rechazo estadístico de toda estrategia posible ni prueba de que la matriz carezca de utilidad.

Se reprodujo desde datos archivados el protocolo congelado de 2025, once activos, capital compartido USD 20.000, cuatro carteras en dos escenarios. Se ejecutó dos veces para contrastar hashes. No se optimizaron parámetros ni añadieron indicadores. La conciliación comprueba caja/inventario y cronología; no es una auditoría externa.

| Cartera conjunta | Nominal | Estrés |
|---|---:|---:|
| Resultado neto USD | -250.68871465 | -670.02673293 |
| Rentabilidad | -1.253444% | -3.350134% |
| Operaciones | 41 | 40 |
| Coste fijo supuesto USD | 365 | 730 |
| Neto más coste fijo, sólo descomposición USD | 114.31128535 | 59.97326707 |

Los costes fijos son supuestos de USD1/día y USD2/día, no facturas ni comisiones verificadas. Suprimirlos aritméticamente no demuestra el resultado de una nueva simulación con otra trayectoria de capital. La referencia de efectivo soporta los mismos costes de infraestructura; no representa dinero sin operar fuera de la plataforma. Los resultados exceden esa referencia en el punto estimado, pero no acreditan crecimiento absoluto positivo.

Bootstrap emparejado: 20.000 réplicas por combinación escenario/bloque, bloques circulares de 5 y 20 días, semilla319, nivel local0.05/16. Los 16 límites inferiores calculados son negativos: no respaldan las condiciones de superioridad del protocolo. Historia reutilizada: no es prueba final intocada. La incertidumbre no autoriza afirmar que toda ventaja sea imposible.

## Comparación prometida: bloqueo concreto

La referencia VIRTUAL_NET sólo recibe snapshots, objetivos y muestras suministradas; no reconstruye decisiones históricas, reservas y fills sobre una cuenta continua. A (zona de no operar) y B (exposición gradual) siguen siendo propuestas, sin código ejecutable congelado ni parámetros preregistrados. Los resultados anteriores pertenecen al motor horario BREAKOUT, NO a ninguna de esas tres políticas. No fabricamos resultados A/B sustituyéndolos por cinco casos sintéticos.

Faltan para decidir esa hipótesis: replay común que genere las mismas oportunidades y datos disponibles en cada instante, implementación congelada de A/B, historial de estimación sin anticipación y validación temporal nueva. Hasta disponer de ello, mantener no promoción y no declarar ahorros reales o nivel8. Esta entrega cierra la reproducción y el veredicto sobre la evidencia disponible; la comparación económica A/B permanece pendiente.

## Reproducción

Desde raíz del repositorio, con dependencias cuantitativas instaladas:

```bash
PYTHONPATH=quant OPENBLAS_NUM_THREADS=1 python tools/economic_verdict.py --output-dir /tmp/harpoon_verdict_new
```

El directorio debe ser nuevo. Produce ocho libros comprimidos, report.json, audit.json, verdict.json y sha256.json. Datos de entrada verificados contra el manifiesto archivado y protocolo con hash fijo. Resultados resumidos conservados en evidence/economic_verdict; los libros pueden regenerarse. Se conservan las limitaciones de cobertura corporativa y ejecución OHLC del experimento original. No se activó broker.
