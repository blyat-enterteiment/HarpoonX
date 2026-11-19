# HF37: cartera con predictor de presión de operaciones

Este módulo convierte operaciones y cotizaciones en una previsión condicionada,
una decisión de entrada o permanencia y un libro financiado de investigación.
La presión es un proxy de agresión observada; no identifica propietarios,
instituciones, órdenes ocultas ni posiciones de una ballena.

## Alcance y estado

- Universo HF37 existente: 33 acciones y 11 ETF sectoriales. Su composición es
  contemporánea y exploratoria, sin certificación histórica punto en el tiempo.
- USD 20.000 iniciales por política, una cuenta continua, sin retiros ni reinicios
  entre sesiones. CASH, SECTOR y WHALE_SECTOR tienen cuentas independientes.
- Todas las ejecuciones del nuevo libro se etiquetan
  `MODELED_IOC_NOT_BROKER_FILL`. El módulo no contiene adaptador de órdenes.
- ORIGINAL sigue siendo una entrada ausente; no se reconstruye ni se sustituye
  por CASH. La puerta HF37 existente impide la promoción.
- No se modifica el núcleo productivo, la configuración privada de PostgreSQL,
  las reglas anteriores ni el holdout de noviembre de 2026.

## Predictor

`hf37_predictor.py` exige operaciones con reloj de evento y de conocimiento.
Cada operación se clasifica contra una cotización cuyo evento no es posterior a
la operación y cuyo conocimiento no es posterior al conocimiento de la operación.
Si la cotización más reciente llegó tarde, se busca una anterior causal. Se
rechazan cotizaciones cruzadas, valores no finitos y datos futuros.

El umbral de operación grande es el percentil 90 de una referencia de al menos
50 operaciones conocidas estrictamente antes de la ventana de señal. La señal
combina presión monetaria general y presión de operaciones grandes, con el mismo
peso. Requiere al menos 10 operaciones clasificadas, cobertura de clasificación
del 50 %, alguna operación grande clasificable y cotización reciente de hasta
dos segundos. La cantidad monetaria no prueba una identidad institucional.

La regresión ridge usa únicamente etiquetas con resultado ya conocido, horizonte
no superior a 72 horas y un máximo de 120 días de historia. Una observación tiene
características de sector y presión; la etiqueta es el retorno bruto posterior.
Se necesitan 40 instantes de decisión distintos. Cien activos observados en un
mismo instante cuentan como un grupo temporal, no como cien sesiones.

Se calcula una banda mediante covarianza de coeficientes agrupada por instante de
decisión, multiplicador 2 y margen adicional de 5 pb. Es una estimación dependiente
del modelo, del diseño de etiquetas y de sus supuestos; no una cota poblacional,
una garantía de acierto ni una validación independiente. La dependencia serial,
el solapamiento de horizontes y los cambios de régimen requieren evaluación
específica con datos reales antes de usar esa banda para una decisión operativa.

## Entrada, permanencia y cartera

Para comprar una acción, su retorno inferior estimado menos el coste completo
de entrada y salida debe superar tanto cero como el retorno superior estimado
de su ETF sectorial menos sus costes. El uso del extremo superior del ETF evita
declarar superioridad frente a una alternativa incierta usando su extremo inferior.

Una posición existente puede mantenerse cuando su continuación inferior sigue
superando esa alternativa, aunque ya no cubra el coste de abrir otra posición.
No se vuelve a cobrar artificialmente una entrada para decidir si conservarla.
Las compras adicionales mantienen el reloj de la posición más antigua.

La asignación maximiza una utilidad cuadrática con penalización de covarianza,
no una solución exacta de Kelly ni una maximización exacta del logaritmo. La
covarianza mezcla 50 % de la matriz empírica y 50 % de su diagonal, con piso
numérico positivo. Límites iniciales: 12 % por activo, 25 % por sector y 60 % de
exposición total. Las cotizaciones usadas para decidir deben ser conocidas y
recientes; las cotizaciones de ejecución modelada deben ser posteriores.

Las cotizaciones observadas no prueban un fill. El modelo IOC limita cantidad
al 10 % de la profundidad mostrada, cancela el remanente dentro de su hipótesis,
vende antes de comprar y usa exclusivamente la caja disponible. Incluye spread,
impacto y comisiones supuestas, que no representan un tarifario verificado del
broker. La riqueza se marca a bid menos impacto y coste de salida. La liquidación
terminal también paga costes y se reconcilia contra todos los movimientos de caja.

El riesgo evalúa pérdida por sesión de 2 %, caída desde el máximo de 10 %,
trailing entre 2 % y 10 % según volatilidad estimada y antigüedad máxima de 72 h.
Son umbrales de reacción en observaciones discretas: no garantizan pérdidas
continuas acotadas. Una salida parcial o sin profundidad al vencer el horizonte
conserva el inventario pendiente, registra la violación y suspende nuevas compras;
nunca se inventa una salida ejecutada para cumplir el plazo.

## Persistencia y verificación

`CheckpointStore` persiste estados JSON en SQLite con transacción, comparación
de versión, identificador de configuración y cadena de hashes. Un replay idéntico
es idempotente; un contenido diferente para el mismo evento falla. La carga
verifica el estado y todo el diario. `ModeledBook.restore` recupera caja, posiciones,
reloj más antiguo, máximos, suspensiones y recibos modelados.

El laboratorio restaura objetos desde una conexión SQLite nueva en el paso 89;
una prueba de integración compara una corrida con reinicio y otra sin reinicio.
Los checkpoints del laboratorio son temporales. La API `CheckpointStore` acepta
una ruta persistente para otro productor, pero este cambio no despliega un
productor de mercado ni un proceso autónomo 24/7.

## Reproducción

Desde la raíz del repositorio, con Python 3.12 o compatible:

```bash
python -m pip install -r research/hf37/requirements-model.txt
python -m unittest research.hf37.test_hf37_model -v
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python -m research.hf37.hf37_model_lab --output hf37_model_output
```

Para repetir también el diagnóstico real, descomprimir el paquete de evidencia
en `evidencia/` y agregar `--real-raw evidencia/raw`. No hace falta una clave del
broker para reproducir esos archivos ya descargados.

`hf37_model_preregistered.json` fija tres mundos sintéticos, dos multiplicadores
de costes, semilla 3701 y 180 sesiones artificiales: seis casos, sin búsqueda de
parámetros ni selección de un ganador. PRESSURE_EDGE impone deliberadamente una
relación favorable de presión y retorno. NULL la elimina. REGIME_REVERSAL invierte
su signo a mitad de la trayectoria. Las fechas sintéticas son un reloj de prueba,
sin calendario bursátil, acciones corporativas ni universo histórico certificados.
Sus resultados no son proyecciones de rentabilidad de mercado.

El diagnóstico real usa AAPL IEX del 15 de octubre de 2026, 13:30–13:31 UTC.
Divide referencia y señal en dos tramos de 30 segundos. El reloj de conocimiento
se supone igual al evento más 100 ms: no se presenta como recibo real. El conector
no expone prueba de agotamiento de paginación. Tampoco se certifican elegibilidad
de condiciones, unidades de profundidad, cobertura SIP ni resultados posteriores.
Sin etiquetas maduras suficientes, el diagnóstico conserva efectivo.

## Límites para una decisión económica

Faltan una cohorte multiactivo completa y utilizable, referencias de sector
causales, calibración real del horizonte swing, reconstrucción exacta de ORIGINAL,
reconciliación de ejecución y evaluación independiente registrada. La puerta sigue
en NO_GO incluso si el caso artificial favorable presenta crecimiento positivo.
La migración PostgreSQL verificada anteriormente acredita metadatos; no acredita
adquisición de la cinta completa ni ventaja económica del predictor.

Referencias primarias de contexto, sin afirmar que reproduzcamos sus resultados:

- [Cont, Kukanov y Stoikov: The Price Impact of Order Book Events](https://arxiv.org/abs/1011.6402).
  Su relación de microestructura a intervalos cortos motiva una hipótesis; no prueba
  que esta señal tenga valor predictivo durante 24–72 horas.
- [Alpaca: diferencias entre IEX y SIP](https://docs.alpaca.markets/docs/market-data-faq).
- [Alpaca: operaciones históricas y paginación](https://docs.alpaca.markets/us/reference/stocktrades-1).
