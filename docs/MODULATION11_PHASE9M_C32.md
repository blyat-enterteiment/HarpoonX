# HarpoonX M11 C32 — instrumentación en el código ORIGINAL antes de filtros

**Estado del cambio:** rama de investigación opt-in, sin despliegue, sin broker, sin órdenes, sin nuevas semillas. C22/C27/C28/C29 congelados. **N9-S NO_GO**.

## Hallazgo causal concreto

El productor real es `xxx/plugins.ts`, compilado en
`runtime30/plugins.js`. El motor llama `Plugins.evaluate(book,market,enabled,now)`.
C31 envolvía su retorno POSTFILTRO. C32 introduce eventos en el código
ORIGINAL, en cuatro sitios:

- `EVALUATE_SOURCE_BEFORE_FEATURES`: antes de `features()`, para no confundir
  un fallo temprano de datos con la inexistencia de oportunidades.
- `FEATURE_PRE_QUOTE`: inicio de cada activo no criptográfico dentro
  de `features()`, antes de `fresh()` y cualquier rechazo.
- `NATIVE_PAIR_PRE_QUOTE`: inicio de cada plugin×símbolo en
  `evaluate()`, antes de spread, antigüedad de precios y filtros
  específicos de estrategia.
- `OPTIONS_UNDERLYING_PRE_FILTERS`: inicio por plugin×subyacente
  en la rutina nativa `options()`, antes de validar cotización e historia.
  Esta ruta NO constituye una invocación de cada contrato de opciones.

El hook es **opcional** y no se habilita desde el servidor. Si nadie lo
instala, el motor conserva exactamente sus decisiones. La instalación no
provoca una sola evaluación. Cuando está instalado, su error de I/O se
propaga fuera del catch que convierte los errores de mercado en WAIT:
no permite usar el resultado de trading si la observación obligatoria falló.

## Evidencia y límites de identidad de seis estrategias

`runtime30/fwn9_c32_native_prefilter_gate.cjs` valida que el método
original y los cuatro sitios de instrumentación son los originales,
emite registros compactos con el SHA del código fuente y la hora de
recepción LOCAL, y verifica que las llamadas nativas plugin×símbolo,
los feature sites y los subyacentes de opciones correspondan al
universo que la fuente declara. No toma OHLC futuro ni inventa fills.

La proyección `C22.windowFor()` permite ubicar cada llamada en
**una ventana de investigación** si calendario/venue proporcionados
son válidos. Pero esto NO prueba que un plugin sea una política C22
semánticamente equivalente:

- Dos políticas C22 para equity/ETF comparten el universo de plugins
  original y difieren por ventana horaria.
- Lo mismo ocurre en las dos ventanas cripto.
- Las dos ventanas de opciones son RESEARCH_ONLY. La lógica nativa
  usa subyacentes y después selecciona contratos; C25 aún rechaza
  contabilidad de `asset.class=option`.
- No existe una tabla de correspondencia registrada y verificada entre
  las seis ventanas y una selección congelada de plugin, versión,
  condiciones de entrada, salidas y costes.

Por lo tanto `c28FrozenSixPolicyIdentityAndExecutionEquivalent=false`
sigue siendo una conclusión falsable y honesta. Elevar esa bandera a
true sin un contrato preregistrado sería selección retrospectiva.

## Enlace inequívoco para una NUEVA versión prospectiva, no retrospectiva

El módulo `runtime30/fwn9_c32_forward_binding.cjs` resuelve la
ambigüedad de identidad hacia adelante: fija para cada una de las seis
ventanas el conjunto completo de plugins **nativos actualmente habilitados**
por libro, los IDs/versiones/parámetros, el universo de activos y las
huellas del evaluador, coordinador, políticas, salidas y calendario.
Dos ventanas pueden compartir los mismos plugins, pero forman políticas
compuestas distintas por su reloj de admisión. Ningún plugin inexistente
puede atribuirse a una ventana.

`freeze()` rechaza una de las seis familias sin plugin/activo;
`link()` compara el universo registrado, los plugins habilitados y el
SHA del código original contra el registro real C32, y rechaza
cualquier instrumento o plugin agregado/desaparecido. Solo permite
afirmar **identidad local determinista de una NUEVA definición**.

Esta es una especificación alternativa que **debe ser preregistrada
externamente antes de resultados**. No puede asignarse a C22 original,
no cambia ni ejecuta los seis brazos de C29, y no autoriza opciones.
Los modos PAPER/LIVE y la certificación N9-S siguen bloqueados.

## Diario durable y pruebas

`runtime30/fwn9_c32_prefilter_journal.cjs` escribe un NDJSON
append-only privado 0600 (directorio 0700), con registro previo,
número de secuencia, SHA-256 y fsync **por cada evento pre-filtro**.
Ante corte incompleto, cambio de bytes o candado abandonado, el
reproceso falla cerrado. El candado exige revisión manual. La
escritura síncrona puede añadir latencia: no está optimizada ni
autorizada para un ciclo ejecutor de producción.

Validación:

    npm ci --ignore-scripts --no-audit --no-fund
    npm run typecheck:xxx
    npm run build:xxx
    node --check runtime30/fwn9_c32_forward_binding.cjs
    node --test tools/fwn9_c32_native_prefilter_test.cjs
    node --test tools/fwn9_c31_native_lineage_witness_test.cjs tools/fwn9_c30_study_feasibility_test.cjs

La CI prueba primero el JavaScript incluido en GitHub, luego ejecuta el
tipado estricto, recompila el TypeScript y vuelve a ejecutar las pruebas sobre
el JavaScript generado. No declara paridad byte a byte entre formatos ni
certificación externa del productor. El resultado será evidencia de ingeniería,
**no de ejecución contra mercado o broker**.

El control `auditNextBar()` solo acepta eventos completos con hora LOCAL
recibida antes del inicio de la siguiente barra. Rechaza expresamente las
invocaciones registradas después de ese instante. Esto no constituye una
sincronización independiente de relojes ni captura el estado de posiciones,
reservas y patrimonio exigido por C27.

## Siguiente cierre real para N9

1. Ejecutar el observador en un entorno aislado de HARPOONX con una
   instancia del productor original y sin órdenes; demostrar cobertura
   en ventanas genuinas y correlacionar registros C32 con C27/C28.
2. Preregistrar una tabla de bindings **semánticos**, incluyendo la
   lógica interna original de cada política o la separación explícita
   de política horaria versus plugin compartido. Si modifica C29,
   hacerlo mediante nuevo plan prospectivo, nunca reescribir C29.
3. Reconciliar C25-C26 con GET auténticos de Alpaca PAPER y el
   libro de una sola cuenta, incluyendo opciones si serán ejecutables.
4. Registrar externamente la nueva versión del plan y su hash antes
   de observar cualquier resultado; después proceder a los bloques
   prospectivos, sin fills ficticios para políticas no ejecutadas.

Mantener 3.200 cuentas M10 selladas, sin reactivar investigación recursiva
ni alterar el umbral N9-S. Los SHA locales y este PR no autentican
la fuente, la hora, Alpaca, mercados ni rentabilidad.
