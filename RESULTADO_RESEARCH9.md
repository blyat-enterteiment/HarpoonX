# Implementación y resultado de las propuestas económicas

**No se acredita nivel 9. Las tres nuevas recetas fallan en estrés.**

Se ejecutaron tres políticas por dos escenarios de costes con el banco histórico
íntegro 30.18, capital continuo de 20,000 USD y 404 sesiones. No se cambiaron
costes, límites ni máximo de 72 horas para obtener resultados positivos.

| Política | Neto nominal USD | Neto estrés USD | Campañas nominal/estrés |
| --- | ---: | ---: | ---: |
| Continuación relativa | 126.58 | -347.24 | 60/60 |
| Reversión estabilizada y normalización | -177.12 | -622.52 | 35/34 |
| Reversión e invalidación | -423.27 | -892.16 | 78/78 |
| Residual original, control conservado | -118.65 | -598.37 | 67/67 |

Las salidas adicionales usan sólo barras recibidas antes de la apertura donde
se ejecuta el cierre modelado. Se mantienen stops y deadline nativos. La salida
por normalización mide el retorno relativo desde las aperturas de la sesión de
entrada con beta/mu/sigma congelados; no constituye un modelo OU ni hedge.
La regla estabilizada cambia entrada y salida conjuntamente: su diferencia de
PnL no permite atribuir causalmente la mejora o pérdida a un solo componente.

## Evidencia y límites

- Código y recetas congelados en GitHub antes de la nueva medición:
  `cbd6df89cb3af41ecfae4b7c349482cfc984805b`.
- Primera ejecución conservada. Cuatro cuentas se detuvieron al exigir una
  barra fresca en la apertura después de una noche. Corrección de ingeniería
  registrada en `amendment_01.json` antes del retry; sin cambio de umbrales.
  La corrección se hizo después de observar los resultados iniciales: no es
  preregistro independiente ni experimento ciego.
- Seis cuentas completas auditadas: caja, inventario, dividendos, comisiones,
  costes fijos una vez, continuidad, cantidades y holding.
- Siete pruebas sintéticas del mecanismo y dos pruebas de equivalencia sobre
  todos los controles nominales/estrés: funded, curve, accounting y summary.
- Diagnósticos bootstrap pareados: bloques 5/20, 120,000 remuestreos y 24
  endpoints. Estadística descriptiva del histórico ya visto; no corrección
  completa de búsqueda global ni aprobación financiera.
- El workflow reproduce el experimento y compara hashes de cuentas y señales
  exactamente; admite hasta16ULP sólo en estadísticas derivadas. Las seis
  cuentas y señales completas quedan versionadas como JSON gzip con doble
  checksum en run_02. El artefacto adicional de CI se conserva90días.

`evidence/research9_30_19/run_02/diagnosis.json` contiene resultados por activo,
salida, concentración, equilibrio de costes y límites inferiores. La primera
ejecución y los incidentes quedan identificados en `run_01`.

## Ejecutar

```sh
npm ci --ignore-scripts
python3 -m pip install -r quant/requirements-tested.txt
node --test tools/research9_test.cjs tools/research9_parity_test.cjs
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 -B tools/run_research9.py \
  --output-dir /tmp/harpoon_research9_new
```

La salida debe ser nueva. El runner verifica fuentes congeladas y la enmienda
explícita; no modifica el estudio 30.18 ni registra órdenes. Los seis ensayos
se declaran de 47 a 53 de un presupuesto de 128 heredado; esto no pretende ser
una reconciliación independiente de todo ensayo histórico o trabajo paralelo.

## Alcance que sigue bloqueado

Se implementaron y contrastaron continuación, estabilización y salidas ligadas
al residual. No se implementó una ampliación del universo point-in-time, una
cartera equity/cripto validada, calibración con fills reales ni operación live:
faltan datos ejecutables y ventaja acreditada. El core robusto previo sigue
siendo una entrada optativa; no está integrado al broker. No se afirma haber
implementado todas las propuestas institucionales con este estudio.

La familia queda cerrada sin promoción. Mantener o combinar estas recetas
negativas no acredita 9. Antes de otro ensayo se necesitan un mecanismo nuevo
y datos adecuados, con protocolo y presupuesto previos; se conserva este
resultado para impedir reutilizarlo como un supuesto descubrimiento nuevo.
