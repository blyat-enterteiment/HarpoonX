# HARPOON: trabajo económico en GitHub

## Resultado comprobado de esta iteración

**Nivel 8 no alcanzado. No se ha demostrado mejora de rentabilidad.** Se
reprodujo la familia 30.18.0 antes de intervenir: ocho cuentas, cero incidentes,
17 archivos con hashes idénticos. No se cambiaron señales, costes, capital,
riesgo, recetas, ledger de ensayos ni las condiciones para acreditar el 8.

Se añadió un diagnóstico ejecutable que reconcilia cada sesión y campaña con
la cuenta continua, verifica los hashes de los ocho reportes, y atribuye el
resultado por activo y motivo de salida sin duplicar costes compartidos.
Rechaza capital reiniciado, sesiones/campañas duplicadas, inventario terminal,
costes negativos, dividendos omitidos y holding superior a 72 horas. Es una
segunda comprobación contable, no validación independiente ni un motor nuevo
de alpha. La sintaxis JSON y el checksum no autentican al proveedor de datos.

## Qué impide el crecimiento compuesto

Importes USD modelados, cuenta inicial 20,000 USD, 404 sesiones. La columna
antes de coste fijo **sí incluye** las fricciones embebidas en precios,
comisiones explícitas y dividendos. No es PnL bruto sin costes de ejecución.

| Política | Nominal neto | Estrés neto | Antes del fijo nominal | Antes del fijo estrés |
| --- | ---: | ---: | ---: | ---: |
| Residual long | -118.65 | -598.37 | 285.35 | 209.63 |
| Mismo ranking sin umbral/hurdle | 214.41 | -465.14 | 618.41 | 342.86 |
| Control sector | -430.18 | -898.78 | -26.18 | -90.78 |
| CASH | -404.00 | -808.00 | 0.00 | 0.00 |

El residual sólo soportaría un presupuesto fijo de **0.7063 USD/sesión**
nominal o **0.5189 USD/sesión** en estrés para quedar aproximadamente en cero,
si toda la trayectoria permaneciera idéntica. Son sensibilidades algebraicas;
no constituyen una oferta de costes disponible ni un replay alternativo.
Cambiar costes altera sizing, fills y capital compuesto; no se rebajan los
supuestos para fabricar un ganador. El control sector pierde incluso antes
del fijo: abaratar infraestructura por sí solo no lo rescata.

En residual nominal, 18 cierres por STOP suman -706.42 USD y 49 cierres por
TIME +991.77 USD, antes de costes compartidos. Esto **no demuestra** que quitar
stops o anticipar cierres mejore el resultado: cambia la trayectoria y la
exposición. Eliminar retrospectivamente las peores operaciones es selección
con información futura. Se retienen las 25 peores campañas en el JSON para
formular hipótesis, sin excluirlas del rendimiento reportado.

No se promueve STOCK_THRESHOLD_OFF por su nominal positivo: pierde en estrés
y ya fue inspeccionado. No se aumenta apalancamiento, riesgo ni plazo para
compensar una expectativa no acreditada. La combinación de activos necesita
ventaja neta de cartera bajo capital compartido; sumar backtests o promediar
notas no demuestra esa ventaja.

## Ejecutar

Desde la raíz del repositorio, con Python 3 y las dependencias originales:

```sh
python3 -B -m unittest discover -s tools -p test_profitability_forensics.py
python3 -B tools/profitability_forensics.py \
  --reports-dir evidence/residual_30_18_0/run_completed \
  --output /tmp/harpoon_forensics_new.json
```

La salida debe ser un archivo nuevo. La herramienta no consume presupuesto
de estrategias ni modifica entradas. La evidencia de esta iteración está en
`evidence/profitability_github_30_18_1/`. La reproducción completa sigue el
comando de `EMPEZAR_30_18.md`; la comprobación nueva no la sustituye.

## Criterio de continuación y parada

La familia residual queda rechazada. Para una nueva familia hacen falta una
hipótesis registrada con presupuesto finito antes de medir, comparadores
congelados, cuenta continua, costes observados/calibrados y evaluación que
reconozca todo el historial de selección. Los criterios R4/R5 siguen fallando;
R6 (evidencia no reutilizada) y R8 (fills/costes prospectivos reconciliados)
siguen bloqueados. No se pueden cerrar con el banco histórico ya visto.

Los scripts existentes conservan sus límites: la admisión prospectiva no
reconcilia aún toda la economía real. Opciones sigue bloqueado por ausencia de
cadenas históricas ejecutables. No hay evidencia en esta iteración de que una
nueva estrategia, cambio de salida o mezcla de activos alcance 8.

No se activó broker, despliegue, capturador ni tarea programada. El workflow
añadido sólo ejecuta diagnóstico y tests contables en GitHub para posteriores
cambios; su resultado no es un certificado financiero.
