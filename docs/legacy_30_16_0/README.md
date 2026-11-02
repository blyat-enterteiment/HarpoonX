# HARPOON XXXUltimate 30.16.0

## Banco histórico reconstruido y ejecutado

Esta es la aplicación integral, con código compilado, datos originales, modelos históricos, pruebas y resultados. Empieza por [LEEME_30_16_0.txt](LEEME_30_16_0.txt) y [EVALUACION_ECONOMICA_HARPOONX_30_16_0.yaml](EVALUACION_ECONOMICA_HARPOONX_30_16_0.yaml).

**Resultado: `VENTAJA_NO_DEMOSTRADA`. El nivel 7 de rentabilidad real no está acreditado.** Las seis carteras produjeron resultados económicos modelados negativos. La cuenta continua comenzó con 20.000 USD y evaluó 294 sesiones de julio de 2023 a agosto de 2024.

| Política | Neto nominal | Neto estrés |
|---|---:|---:|
| Motor histórico | −424,94 USD | −893,68 USD |
| Ridge | −366,88 USD | −773,98 USD |
| SVR | −481,56 USD | −893,63 USD |

El banco conserva 208.152 barras de cinco minutos para AAPL, MSFT, SPY y XLK, con 375 sesiones de entrenamiento, 126 de validación y 168 de prueba. Las características usan sólo precios disponibles al decidir. El patrimonio continúa entre las dos fases de evaluación y los costes se descuentan antes del tamaño de posición. Los dividendos se registran como derechos hasta su fecha de pago modelada.

Hay 123 pruebas actuales aprobadas y una reproducción exacta de 12 archivos de resultados. Los tests prueban contratos de software. Los modelos históricos, los fills modelados y la comparación retrospectiva conservan su clasificación; no se activan como modelos de producción.

El control de este estudio es `NATIVE_HISTORICAL_ULTIMATE`; no se confunde con el `Coordinator` de producción. La recalibración walk-forward sigue siendo una investigación posterior: esta medición usó un ajuste fijo y parámetros congelados.

## Reproducción

Con las dependencias de `quant/requirements-tested.txt` y Node instaladas:

```bash
npm ci
npm run build:xxx
python tools/run_historical_bank.py --data-dir evidence/historical_bank_30_16_0/data --registration-dir evidence/historical_bank_30_16_0/registration --output-dir evidence/historical_bank_30_16_0/reproduction_user --verify-against evidence/historical_bank_30_16_0/run_completed
```

La salida debe ser una carpeta nueva. El comando reutiliza las seis reservas existentes y conserva incidentes. La rama actual del journal tiene 29/128 consumidos; no se reinicia desde el ancestro 23/128.

## Archivos de consulta

- `evidence/historical_bank_30_16_0/run_completed/`: seis resultados y modelos.
- `evidence/historical_bank_30_16_0/reproduction/`: comparación exacta.
- `evidence/historical_bank_30_16_0/analysis/`: gráfico y atribución.
- `evidence/historical_bank_30_16_0/data/`: 130 fuentes, calendario, acciones y reconstrucción.
- `evidence/historical_bank_30_16_0/qa/`: pruebas, incidentes y auditoría.
- `evidence/historical_bank_30_16_0/frozen_control_30_15_0/`: control anterior portable con sus bytes originales.

El despliegue sigue diferido. La [documentación heredada](docs/legacy_30_15_0/README.md) conserva las versiones y el alcance anteriores.
