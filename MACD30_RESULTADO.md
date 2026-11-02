# MACD diario de 30 barras con confirmación y anticipación

No se acredita 8. Se implementaron tres reglas nuevas de investigación con el
mismo capital continuo de 20,000 USD, horizonte previsto de 24–72 horas y costes
completos del motor swing. No se modificaron el runtime ni el broker.

“30 días” se interpreta como EMA lenta de 30 barras diarias: MACD(12,30,9).
Equity usa sesiones y cripto días UTC; no significa velas mensuales ni un plazo
de tenencia de 30 días. Semilla EMA: media simple; RSI14: suavizado de Wilder;
estocástico14/3/3; calentamiento mínimo de 150 cierres completos, recuperados del
histórico disponible antes de decidir. Sin extrapolación ni datos futuros.

- CROSS: histograma anterior ≤0 y actual >0.
- CONFIRMED: CROSS, RSI entre 45 y 70 y creciente, K>D y K<85.
- EARLY: tres histogramas estrictamente crecientes todavía ≤0, más los mismos
  osciladores. No exige ni predice que el cruce vaya a ocurrir después.

Las tres variantes comparten filtros de precio: tendencia sobre SMA50, cierre
previo cercano al máximo20, ruptura del máximo del día anterior mediante hora
ya cerrada, anti-persecución y recorrido potencial frente a costes. Así no se
atribuye al oscilador un cambio paralelo de stop, capital o tarifas. Esta familia
estudia anticipación cerca de ruptura; no añade otra búsqueda de parámetros de gaps.

| Regla | Trades nominal/estrés | Neto nominal USD | Neto estrés USD |
| --- | ---: | ---: | ---: |
| Cruce MACD | 15/15 | -378.62 | -781.51 |
| Cruce y osciladores | 5/5 | -398.55 | -773.03 |
| Histograma anticipado y osciladores | 16/16 | -323.46 | -732.81 |

Costes sin rebajar: 5 bp equity y 35 bp cripto por lado, más 365 USD anuales
compartidos; estrés duplica ambos. EARLY aporta 41.54 USD nominales antes del
fijo, pero pierde 2.81 USD en estrés antes del fijo. No hay ventaja neta robusta.
Los osciladores usan los mismos precios: no son confirmaciones estadísticamente
independientes. Anticipación de una condición de indicador no prueba mejor
precio, exactitud predictiva ni rentabilidad. Las reglas tampoco son estrategias
propietarias atribuidas a Citadel, Jane Street o Two Sigma.

Seis pruebas nuevas de indicadores aprobaron; compilación sintáctica ejecutada.
El verificador Decimal anterior comprueba las seis cuentas completas, inventario,
caja, cronología y plazos mediante un adaptador explícito de metadatos. No es
validación externa independiente. No se reejecutó la suite quant completa de 535
pruebas en esta entrega; lint y comprobación formal de tipos siguen sin ejecutarse.

Protocolo y fuentes publicados antes de medir: commit
3f0d0dbcf0d940b20ba788e1a3db42f7b5979777. Tres reglas por dos costes, sin afinación
posterior. Se conservan cuentas, señales con recibos de indicadores y hashes.
La comparación es exploratoria sobre 2025 reutilizado, con las limitaciones del
banco anterior: acciones corporativas incompletas, capacidad cripto reducida,
ningún fill live y ninguna validación nueva de 2026. No se afirmó resolver esos
bloqueos mediante estos indicadores. El calibrador de fills real anterior permanece
disponible, sin recibos nuevos para ejecutarlo.

```sh
PYTHONPATH=quant python3 -B -m unittest discover -s quant/tests -p test_macd30.py
OPENBLAS_NUM_THREADS=1 python3 -B tools/run_macd30.py --output-dir /tmp/macd30_new
python3 -B tools/verify_macd30.py /tmp/macd30_new
```

El adapter de investigación usa un reemplazo acotado y sin concurrencia de la
función de señales del replay; no cambia los archivos sellados ni está habilitado
como entrada del runtime. No representa datos sintéticos de prueba como fills reales.
