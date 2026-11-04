# PROFIT8: resultado del ciclo registrado

## Alcance

Fuentes congeladas en `8fc6a0da8989db970d97360bb6f4f98bbe3594cd`. Cuenta inicial: 20.000 USD. Período continuo: 2025-03-11 a 2026-10-16, 404 sesiones. Sin retiros ni reinicios.

Son resultados históricos con ejecución modelada sobre barras SIP de cinco minutos. No acreditan rentabilidad real, ejecución de broker ni una calificación de 8/10. El histórico principal ya se había examinado. La extensión reciente quedó bloqueada por indisponibilidad de Alpaca; no se midió ningún tramo nuevo.

## Todos los resultados

| Política | Neto nominal USD | Neto estrés USD | Campañas nominal/estrés | Decisión |
|---|---:|---:|---:|---|
| H1_REVERSAL24 | -728.53 | -1365.50 | 50/50 | REJECT |
| H1_REVERSAL72 | -558.69 | -1222.79 | 44/45 | REJECT |
| H2_NET24 | -686.03 | -1587.64 | 200/148 | REJECT |
| H2_NET72 | -972.95 | -1585.42 | 77/71 | REJECT |
| H3_ROBUST24 | -636.44 | -1056.77 | 54/22 | REJECT |
| H3_ROBUST72 | -837.56 | -1449.54 | 47/41 | REJECT |
| CONT_POS24 | -312.68 | -962.03 | 44/42 | CONTROL |
| CONT_POS72 | -437.56 | -1044.24 | 38/36 | CONTROL |
| GROSS_ALL24 | -810.95 | -1628.82 | 193/137 | CONTROL |
| GROSS_ALL72 | -929.67 | -1513.71 | 81/76 | CONTROL |

## Interpretación registrada

H1 prueba reversión de residuos negativos frente a continuación positiva. H2 predice el pago neto de la política real de stops y parciales, frente a predecir sólo el precio al deadline. H3 conserva exactamente las previsiones de H2 y enumera tamaños enteros bajo incertidumbre. Su efecto incluye cambios posteriores en inventario y admisión: no es una atribución pura sobre entradas idénticas.

El motor conserva un límite común IOC causal de 30 puntos básicos, exposición bruta de 12%, riesgo agregado abierto de 0,25%, límite diario de 2% y drawdown de 8%. Estos son límites del modelo; no garantizan cotizaciones ejecutables ni ausencia de gaps en vivo.

Los gastos fijos son 1 USD por fecha natural en nominal y 2 USD bajo estrés, incluidos fines de semana y calentamiento sin operaciones. Se cobran una sola vez por cuenta. Comisiones, spread y slippage figuran por separado en results.json.

Los intervalos de bootstrap usan bloques de 5 y 20 sesiones y corrección local de 48 extremos registrados. La búsqueda histórica global es incompleta y no existe validación prospectiva. Los remuestreos no crean sesiones originales nuevas.

## Reproducción

```bash
PYTHONPATH=quant:tools python tools/verify_profit8.py --directory evidence/profit8/run_01 --output /tmp/profit8-audit.json
```

Para repetir la matriz completa, usar run_profit8.py --mode run con un directorio nuevo y el mismo --source-commit. Una reproducción exacta debe declararse como tal y conservar los hashes; no habilita otra búsqueda de parámetros.

## Presupuesto y parada

Se registraron seis candidatos y cuatro controles en dos escenarios. La matriz utiliza 20 cuentas nuevas: 85 evaluaciones documentadas acumuladas. Se conservan 20 reservas sin utilizar para la extensión bloqueada, con reserva total de 105/128. Se conservan también los rechazos del ciclo anterior. El historial global de intentos sigue incompleto.

No se ejecutan órdenes ni se despliega esta investigación. Una receta con resultado positivo sólo puede clasificarse como candidata diagnóstica si supera todos los filtros; la rentabilidad de producción requiere evidencia posterior y conciliación de ejecuciones reales.
