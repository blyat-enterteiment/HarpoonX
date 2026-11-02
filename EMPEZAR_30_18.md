# HARPOON — investigación 30.18.0

**No acredita nivel 8 ni rentabilidad real. No habilita órdenes.**

Esta entrega añade una familia económica distinta a la aplicación **30.17.0**, cuyo código medido y evidencia se conservan. `package.json` sigue en 30.17.0 intencionadamente: 30.18.0 identifica esta extensión de investigación, no un despliegue.

## Resultado, no promesa

Cuenta continua de 20.000 USD; 404 sesiones del 11-03-2025 al 16-10-2026. Todos los importes son netos **modelados**, incluyendo costes fijos.

| Política | Nominal USD | Estrés USD | Campañas nominal/estrés |
|---|---:|---:|---:|
| Recuperación residual long-only | -118,65 | -598,37 | 67 / 67 |
| Mismo ranking sin umbral ni hurdle | +214,41 | -465,14 | 184 / 185 |
| Control temporal sector XLK | -430,18 | -898,78 | 68 / 68 |
| CASH con mismos costes fijos | -404,00 | -808,00 | 0 / 0 |

El residual supera CASH en la muestra, pero no a su propio control sin filtros. Ninguna ventaja del candidato supera los límites inferiores familiares. El control nominal positivo **no se selecciona ni promueve**: pierde en estrés y no acredita crecimiento estadístico positivo.

## Qué se hizo

- Hipótesis y seis recetas reservadas antes de recapturar precios: ledger 41 → 47 de 128; sin búsqueda de parámetros.
- OLS de shocks de apertura de 60 minutos, entrenado sólo en 126 sesiones; AAPL/MSFT frente a XLK.
- Señal al minuto 60 + 1 s; entrada siguiente barra al minuto 65; salida nativa ≤72 h, no salida por residual.
- 80 recibos originales nuevos: 124.182 barras RTH, 533 sesiones, cero huecos/rellenos. Es un periodo ya visto globalmente, **no holdout virgen**.
- Ocho cuentas, costes una vez, capital continuo, riesgo reducido; reproducción **17/17 hashes idénticos**.
- 132 tests Python nuevos y 4 de adapter Node; auditor independiente: 132 Python y 53 Node PASS, 1 SKIP opcional. No sumar suites solapadas.

El benchmark sector no está perfectamente emparejado: 88 propuestas residual frente a 86 sector y 67 frente a 68 campañas. Exposición, fills y duración difieren. Costes, profundidad y disponibilidad histórica de recibos/corporate actions siguen siendo condicionales.

## Archivos principales

- `EVALUACION_ECONOMICA_HARPOONX_30_18_0.yaml`: dictamen, resultados completos, rúbrica y soluciones factibles.
- `research/residual_30_18/protocol.json`: receta congelada, sin reajustes por resultados.
- `research/residual_30_18/source_manifest.json`: 323 bindings de código/datos.
- `evidence/residual_30_18_0/data/raw/`: los 80 originales; no sustituyen los 149 antiguos ausentes.
- `evidence/residual_30_18_0/run_completed/`: ocho reportes, incertidumbre, exposición y hashes.
- `evidence/residual_30_18_0/reproduction/`: reproducción exacta.
- `evidence/residual_30_18_0/registration/`: ledger descendiente, reserva y admisión inmutable.
- `evidence/residual_30_18_0/independent_review.md`: revisión independiente y límites.
- `MANIFEST_30_18.json`: integridad de esta distribución. Los manifiestos anteriores son históricos y no enumeran esta extensión.

## Reproducir offline, sin búsqueda

Desde la raíz extraída; Python 3 y Node disponibles. Dependencias Python fijadas en `quant/requirements-tested.txt`; JS en `package-lock.json`.

```sh
python3 -m pip install -r quant/requirements-tested.txt
npm ci --ignore-scripts
python3 -B -m unittest discover -s tools -p 'test_residual_*.py'
node --test tools/residual_replay_test.cjs
python3 -B tools/residual_register.py verify --source-hashes research/residual_30_18/source_manifest.json
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 -B tools/run_residual.py \
  --output-dir evidence/residual_30_18_0/mi_reproduccion \
  --verify-against evidence/residual_30_18_0/run_completed
```

El directorio de salida debe ser nuevo. No volver a reservar, borrar el ledger, alterar costes o seleccionar otro periodo. La reproducción no añade variantes ni cambia la receta. No hay ruta de broker en estos comandos.

## Camino prospectivo, no activado

`tools/residual_forward.py` congela identidades y valida cronología/estructura de un bundle de recibos reales. El freeze incluido es anterior a la primera sesión posible del 02-11-2026. **No aprueba esta estrategia negativa ni reconcilia aún toda la economía fill → ledger.** `real_economics_evidence_complete` permanece falso.

La plantilla vacía se rechaza correctamente con exit 2 / DATA_BLOCKED:

```sh
python3 -B tools/residual_forward.py validate \
  --bundle evidence/residual_30_18_0/forward/bundle_template.json \
  --freeze evidence/residual_30_18_0/forward/freeze.json \
  --output mi_validacion.json
```

Harían falta recibos originales de bars/quotes antes de decisión, cobertura corporativa conocida oportunamente, fills/facturas y cuenta continua reconciliada. Los mínimos de 100 sesiones y 20 campañas **no son prueba suficiente**. Las fechas calendario de 60/126 sesiones no garantizan resultados. No se creó cron, seguimiento automático ni orden; no es necesario esperar meses para inspeccionar esta entrega.
