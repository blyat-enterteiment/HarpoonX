# HARPOON: cierre económico del ciclo PROFIT8

Fecha: 4 de noviembre de 2026. Estado: investigación concluida; seis candidatos rechazados.

## Conclusión

No existe evidencia para calificar la rentabilidad de HARPOON con 8/10. Se implementó y ejecutó el ciclo completo: seis candidatos, cuatro controles y dos escenarios de costes, veinte cuentas continuas. Todas terminaron con pérdida neta. Diez de las doce cuentas de candidatos perdieron incluso antes del gasto fijo compartido. La asignación robusta redujo algunas pérdidas mediante menor exposición, sin convertir la estrategia en rentable. Ninguna receta se promueve a operación.

## Alcance y cambio de datos documentado

Capital inicial: 20.000 USD, sin reinicios ni retiros. Período: 11 de marzo de 2025 a 16 de octubre de 2026, 404 sesiones y 585 fechas naturales. Acciones negociadas: AAPL/MSFT; XLK como contexto sectorial. Plazos máximos de 24 y 72 horas transcurridas. Barras SIP de cinco minutos, con ejecución y recepción históricas modeladas. No son fills de broker ni evidencia prospectiva.

El código inicial quedó publicado en 6074020387f1de403a78c38459e6db17670ba30b antes de consultar el tramo reciente. Las cinco consultas de Alpaca y un reintento de calendario fallaron por timeout del endpoint MCP. Los recibos originales y el informe DATA_BLOCKED se conservan. La enmienda A01 redujo expresamente el alcance al corpus ya verificado; no cambió hipótesis, parámetros, costes, límites ni criterios estadísticos. Se publicó y verificó en 8fc6a0da8989db970d97360bb6f4f98bbe3594cd antes de calcular etiquetas, pronósticos o cuentas. No se presenta la extensión fallida como validación reciente. publication_receipt.json vincula los 54 archivos relevantes contra sus objetos Git.

## Resultados completos

| Política | Neto nominal USD | Neto estrés USD | Campañas nominal / estrés | Decisión |
|---|---:|---:|---:|---|
| H1_REVERSAL24 | -728.53 | -1,365.50 | 50 / 50 | RECHAZADA |
| H1_REVERSAL72 | -558.69 | -1,222.79 | 44 / 45 | RECHAZADA |
| H2_NET24 | -686.03 | -1,587.64 | 200 / 148 | RECHAZADA |
| H2_NET72 | -972.95 | -1,585.42 | 77 / 71 | RECHAZADA |
| H3_ROBUST24 | -636.44 | -1,056.77 | 54 / 22 | RECHAZADA |
| H3_ROBUST72 | -837.56 | -1,449.54 | 47 / 41 | RECHAZADA |
| CONT_POS24 | -312.68 | -962.03 | 44 / 42 | CONTROL |
| CONT_POS72 | -437.56 | -1,044.24 | 38 / 36 | CONTROL |
| GROSS_ALL24 | -810.95 | -1,628.82 | 193 / 137 | CONTROL |
| GROSS_ALL72 | -929.67 | -1,513.71 | 81 / 76 | CONTROL |

La cuenta de caja sin intereses y con el mismo gasto habría perdido 585 USD en nominal y 1.170 USD bajo estrés. Es una referencia contable del gasto, no una alternativa de inversión recomendada. El mejor control nominal de esta matriz, CONT_POS24, produjo 272,32 USD antes de esos 585 USD y terminó en −312,68 USD. Tampoco supera el criterio de rentabilidad absoluta.

## Qué aportó cada hipótesis

**H1, reversión del residuo negativo:** empeoró los controles de continuación positiva en ambos horizontes y escenarios. La única contribución positiva nominal, 26,31 USD a 72 horas antes del gasto fijo, dependió de un ganador de 96,34 USD. Al retirarlo aritméticamente queda −70,03 USD antes del gasto fijo. No se ejecutó un replay contrafactual sin esa operación.

**H2, pronóstico del pago neto:** a 24 horas mejoró respecto al control de precio bruto en 124,92 USD nominales y 41,18 USD bajo estrés. A 72 horas empeoró en 43,28 y 71,71 USD, respectivamente. Ninguna cuenta obtuvo beneficio neto. Ampliar las oportunidades produjo hasta 200 campañas nominales a 24 horas, con −101,03 USD antes del gasto fijo; la escasez de operaciones no era el único problema.

**H3, asignación entera robusta:** mejoró frente a H2 en 49,59/530,87 USD a 24 horas y 135,39/135,88 USD a 72 horas, nominal/estrés. En estrés a 24 horas redujo campañas de 148 a 22, exposición media aproximadamente 84,76% y rotación 84,46%. El resultado fue menor pérdida, −1.056,77 USD. Su contribución de 113,23 USD antes del gasto cubrió sólo 9,68% del gasto fijo. Los cinco mayores ganadores sumaron 150,65 USD, dejando −37,42 USD en el resto.

Los dos escenarios reentrenan y seleccionan según sus costes registrados, por lo que cambian también las decisiones. No equivalen a revalorizar exactamente las mismas órdenes al doble de coste. H3 reutiliza las mismas previsiones que H2, pero sus cantidades cambian el inventario y las entradas posteriores; las diferencias no prueban un efecto aislado sobre entradas idénticas.

## Riesgo e inferencia

Las restricciones de admisión conservaron exposición bruta/por activo de 12%, riesgo de entrada/abierto de 0,25%, pérdida diaria configurada de 2% y drawdown configurado de 8%. El drawdown observado por eventos excedió 8% en H2 bajo estrés: 8,0743% a 24 horas y 8,0180% a 72 horas. Ambas fallaron también el criterio de riesgo. Un límite de admisión no garantiza que una cuenta nunca rebase el umbral con posiciones abiertas o gastos posteriores.

No hubo déficits de caja. Se conservaron los diagnósticos de sobrepasos de exposición/riesgo reservado tras cambios de valoración; no se ocultan ni se confunden con una orden admitida fuera de límites. El filtro de pérdida por sesión usa cierres consecutivos y no certifica un límite diario para cada marca.

Los 48 extremos registrados usan 20.000 remuestreos, semilla 319 y bloques de 5/20 sesiones. Ninguno de los 24 límites inferiores de diferencia pareada fue positivo; tampoco los 24 de crecimiento absoluto. Son diagnósticos sobre historia reutilizada, con búsqueda global incompleta. No hay confirmación de superioridad estadística ni económica, y la igualdad de límites no implica riesgo realizado comparable.

## Implementación conservada

Quedan implementados y probados: etiquetas del resultado realizable con stops, parciales, comisiones y dividendos; madurez completa del plazo incluso tras stop temprano/no ejecución; predicciones causales con purga y estandarización sólo sobre entrenamiento; filtro de calibración; IOC común determinado antes del siguiente precio; reservas sobre cantidad comprometida; enumeración de cantidades enteras con incertidumbre; auditor separado con conciliación Decimal. La rama anterior permanece intacta.

La identidad monetaria de las salidas redondeadas se comprobó para cantidades de 1 a 12. Si T=Pnl(1)/Pref y E=(Pnl(4)−2Pnl(1))/(2Pref), entonces Pnl(q)=Pref[2 floor(q/4) E+(q−2 floor(q/4)) T]. Esto permite modelar las discontinuidades de lote; no demuestra que el pronóstico posea ventaja económica.

## Validación y reproducción

Antes de medir: 54 pruebas de Python y 28 del motor nativo aprobadas; Ruff sin hallazgos con el comando documentado desde la raíz; Mypy sin incidencias en seis archivos fuente. Las pruebas son sintéticas y cubren causalidad, purga, no ejecución, disponibilidad, parciales, reservas, unidades y manipulaciones adversariales.

La matriz completa y su auditor terminaron en 97.59 segundos en el entorno registrado. El verificador separado concilió las veinte cuentas, 274 modelos archivados y 3.886 snapshots listos. No reentrenó modelos. Los 67.900 usos de filas de entrenamiento reflejan ventanas solapadas, no nuevas observaciones independientes. Los 34 archivos del manifiesto y 42 entradas del diario conservan integridad. Esta revisión no sustituye una auditoría externa ni autentica los tiempos originales de mercado.

```bash
PYTHONPATH=quant:tools python tools/verify_profit8.py \
  --directory evidence/profit8/run_01 \
  --output /tmp/profit8-audit.json

PYTHONPATH=quant:tools OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  python tools/run_profit8.py --mode run \
  --source-commit 8fc6a0da8989db970d97360bb6f4f98bbe3594cd \
  --directory /tmp/profit8-exact-reproduction
```

La segunda orden es una reproducción exacta, no autorización para ajustar recetas después de conocer resultados. El primer directorio de medición se conserva sin cambios.

## Decisión de cierre

No se aumenta capital, apalancamiento, exposición ni rotación para rescatar estos resultados. Las seis recetas se rechazan. Se conservan herramientas de investigación y la evidencia negativa; no se integran las políticas como mejora rentable. La reserva documentada queda en 105/128, con 85 evaluaciones documentadas y 20 reservas de extensión no utilizadas; el historial global sigue incompleto.

Para sostener una calificación económica alta faltan una señal con contribución positiva estable, beneficio neto positivo con costes estresados, riesgo dentro de límites y confirmación en datos posteriores con ejecución conciliada. Este ciclo no satisface esos requisitos. El siguiente paso justificable depende de una fuente nueva de información y datos temporales disponibles; volver a ajustar estas mismas recetas sobre este histórico acumularía selección retrospectiva. No queda programada ninguna tarea ni autorizada una operación financiera.

## Fuentes y evidencia

- Protocolo, diez recetas y enmienda: research/profit8/.
- Resultado completo: evidence/profit8/run_01/results.json.
- Conciliación separada: evidence/profit8/run_01/audit.json.
- Integridad: evidence/profit8/run_01/manifest.json y journal.jsonl.
- Estado anterior: evidence/profit8/state_review.json.
- Motivación de reversión residual: https://www.newyorkfed.org/research/staff_reports/sr513.html .
- Motivación de control con costes: https://www.nber.org/papers/w15205 .

Las publicaciones motivan hipótesis generales. No acreditan que estas recetas de HARPOON sean rentables ni permiten reproducir estrategias privadas.
