# Veredicto económico reproducible

Decisión: NO PROMOVER. Receta histórica horaria: RECHAZADA. Matriz virtual y variantes A/B: EVIDENCIA INSUFICIENTE. Actualización del 7 de noviembre de 2026: la comparación A/B y su walk-forward purgado ya se ejecutaron; las tres políticas no aprobaron ninguna orden. Ver `VIRTUAL_AB_WALK_FORWARD.md` y `FORENSIC_OPPORTUNITY.md`. No es un rechazo estadístico de toda estrategia posible ni prueba de que la matriz carezca de utilidad.

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

## Comparación de matriz: estado actualizado

La entrega original de este documento precedió al replay de matriz. Desde el commit `bab1746d5735158605feb96c58ee7102c5cb005a`, `virtual_ab.py` conecta CURRENT, A (zona de no operar) y B (exposición gradual) a una cuenta continua y a protocolos congelados. El ensayo purgado produjo 316 celdas candidatas por cuenta y cero compras: -365 USD nominal y -730 USD estrés, enteramente por costes fijos supuestos. Las diferencias entre variantes son cero porque no hubo exposición; no se identifica su efecto económico. Los resultados de la tabla horaria anterior pertenecen a BREAKOUT y no a estas políticas.

Falta demostrar una ventaja condicionada al setup con ejecución suficiente para comparar variantes, datos no reutilizados y costes calibrados. No se debe forzar la aprobación de órdenes para conseguir esa muestra. Se mantiene no promoción, sin ahorros reales acreditados ni nivel8. Los informes originales se conservan como evidencia de cada etapa, no como descripción del estado actual del código.

## Reproducción

Desde raíz del repositorio, con dependencias cuantitativas instaladas:

```bash
PYTHONPATH=quant OPENBLAS_NUM_THREADS=1 python tools/economic_verdict.py --output-dir /tmp/harpoon_verdict_new
```

El directorio debe ser nuevo. Produce ocho libros comprimidos, report.json, audit.json, verdict.json y sha256.json. Datos de entrada verificados contra el manifiesto archivado y protocolo con hash fijo. Resultados resumidos conservados en evidence/economic_verdict; los libros pueden regenerarse. Se conservan las limitaciones de cobertura corporativa y ejecución OHLC del experimento original. No se activó broker.
