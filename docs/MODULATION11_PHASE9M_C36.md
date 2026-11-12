# HARPOONX M11 C36 — Incubadora local multicapa activo × estrategia

**Estado:** ingeniería offline, investigación cuantitativa NO_GO. No hay
nuevos modelos entrenados, señales, semillas de mercado, órdenes, API,
candidatos prospectivos de Alpaca ni resultados OOS. No se modifica C22,
C25–C35, ni el protocolo económico congelado C29. M10 conserva sus
3.200 cuentas finales selladas.

## 1. Fuentes primarias y alcance real

- Kelly, J. L. (1956), *A New Interpretation of Information Rate*,
  Bell System Technical Journal:
  https://doi.org/10.1002/j.1538-7305.1956.tb03809.x
- Markowitz (Premio en Ciencias Económicas 1990), media-varianza y
  riesgo de cartera:
  https://www.nobelprize.org/prizes/economic-sciences/1990/summary/
- Gârleanu y Pedersen (2013), *Dynamic Trading with Predictable Returns
  and Transaction Costs*, Journal of Finance:
  https://www.nber.org/papers/w15205
- Lobo, Fazel y Boyd (2007), optimización con coste lineal y fijo:
  https://web.stanford.edu/~boyd/papers/portfolio.html
- Rockafellar y Uryasev, optimización CVaR:
  https://sites.math.washington.edu/~rtr/papers/rtr179-CVaR1.pdf
- NASA-STD-8739.8B, aseguramiento, testeo e IV&V:
  https://standards.nasa.gov/standard/nasa/nasa-std-87398
- DARPA Assured Autonomy, monitorización de comportamientos y
  garantía temporalmente condicionada:
  https://www.darpa.mil/research/programs/assured-autonomy
- Alpaca Crypto spot maker/taker:
  https://docs.alpaca.markets/us/docs/crypto-trading

No existe un Premio Nobel de Matemáticas; Markowitz recibió el de
Ciencias Económicas. No tenemos acceso a estrategias propietarias de
Citadel, DARPA ni NASA. Estas fuentes inspiran el problema, no
certifican ningún resultado concreto de HarpoonX.

## 2. Objetivo operativo

El producto no es un nuevo generador de señales. Recibe solamente
pares activo×estrategia que el productor original declaró evaluados
ANTES de los filtros mediante C32, junto con características
conocidas, previsiones y un escenario común. Rechaza por defecto.
El conjunto activo×familia se compara dentro del mismo bolsillo de
capital y riesgo. CASH compite contra todos.

**Capas:**

1. Fuente causal: tiempo de cotización y de pronóstico no posterior a
   la decisión, origen nativo pre-filtro declarado, escenarios alineados
   y etiquetas de procedencia sintética/no certificada.
2. Técnica: confirmación relativa de volumen, momentum de volatilidad,
   impulso o reversión, amplitud de ruptura; sin datos fundamentales.
3. Microestructura: spread de entrada/salida, costes, profundidad y
   antigüedad de cotización; no se presupone fill maker.
4. Económica: retorno inferior hipótesis después de pagar ida/vuelta,
   incertidumbre y costes de oportunidad.
5. Riesgo: pérdida modelada por stop bajo estrés, escenarios de pérdida,
   CVaR sobre log-wealth y caída de score por correlación conjunta.
6. Financiamiento: dinero efectivamente disponible, compromisos,
   reservas, patrimonio y límites congelados en un libro continuo.
7. Competencia local: un candidato por instrumento si es mejor;
   penalización por factor/cluster y mejora marginal obligatoria.
8. Auditoría: registro completo de seleccionados/rechazados, con
   causa precisa, sin permiso de ejecución.

## 3. Formulación y unidades

Cada candidato i,k dispone de retorno bruto estimado `mu_ik` en
**puntos básicos del nominal**, error estándar `se_ik`, coste total
`c_ik` en puntos básicos del nominal y fracción `w_ik` sobre el
patrimonio congelado que puede financiarse.

Definimos la sensibilidad pesimista:

    alpha_lower_ik = mu_ik - z * se_ik - c_ik

`z=2.5` es sensibilidad de investigación (no cuantíl estadístico
certificado). Los 8 costes son entrada/salida de comisión, medio
spread, impacto y deslizamiento. No se suman otra vez al NAV cuando ya
han sido contabilizados en recibos broker.

Para escenarios CONJUNTOS, identificados y sincronizados por un mismo
ID `s`, el retorno de cartera en escenario s es:

    r_p,s = sum_ik w_ik * (R_ik,s - c_ik)/10000
    W_end,s / W_begin = 1 + r_p,s

La puntuación de investigación es:

    L = mean_s log(1+r_p,s)
        - z * std_s(log(1+r_p,s))/sqrt(n_effective)
        - lambda * max(CVaR95_s(loss_log_s),
                       sum_ik w_ik*(stop_ik+c_ik)/10000)

con `lambda=0.25`. `n_effective` se recibe explícitamente; nunca
se estima a posteriori dentro del cribado. La fórmula **no es** un
lower confidence bound matemáticamente garantizado con dependencia
temporal, incertidumbre de ejecución o colas WEAK. La parte de stop
es una penalización modelada; gaps pueden excederla.

Cada entrada potencial debe superar además la zona de inacción:

    w * alpha_lower_ik > (h/24) * 1 bp + 0.25 bp

con `h <=72h`, y su aumento marginal de L debe ser estrictamente
positivo y superior al buffer de 0,25 puntos básicos del NAV. La
competencia es conservadora: no hay obligación de llenar el presupuesto.

## 4. Conservación del contrato económico

El presupuesto de patrimonio financiado queda:

    base = min(equity_observed, 20000 USD)
    cash_available = max(0, settled_cash - commitments - unsettled)
    gross_headroom = max(0, 0.12 * base - gross_outstanding)
    risk_headroom = max(0, 0.0025 * base - risk_outstanding)

Un candidato no puede superar esos límites. **Solo en investigación**
se añade un techo más conservador del 4% del patrimonio base por
propuesta, para permitir aproximadamente tres exposiciones de igual
nominal dentro del presupuesto bruto compartido de 12%.

No se redefine el capital admisible continuo como 12% de cada minuto
ni se ordenan liquidaciones automáticas. El gestor de riesgo original
sigue gestionando posiciones persistentes y caídas de patrimonio.

Compounding es **riqueza financiada única y continua**:

    W_{t+1} = W_t + PnL_neto_economico_t

sin empezar de nuevo desde USD 20.000 en cada bloque. El beneficio
acumulado incrementa el NAV, pero no eleva por sí mismo la base dura
de nuevas admisiones, que permanece limitada a 20.000 USD.

## 5. Modelo por activo y estrategia

| Libro | Variables locales | Rechazo natural |
| --- | --- | --- |
| Equity/ETF | confirmación de ruptura, volumen relativo, momentum, liquidez, coste de spread | ausencia de cierre causal o comisión estimada sin recibos |
| BTC/ETH cripto | momentum/volatilidad/volumen, costes maker/taker, slippage, profundidad | alpha bruto incapaz de cubrir comisión de ida/vuelta |
| Opciones | subyacente, cadena, griegas, prima, liquidez de contratos | siempre shadow hasta certificar multiplicador, ejercicio, liquidación y broker |
| CASH | remuneración y liquidez observada, coste de oportunidad | predeterminado ganador si ningún activo supera todos los gates |

Tarifario base documentado por Alpaca (primer tramo): cripto maker
15 bp por lado, taker 25 bp por lado. Pasar hipotéticamente de taker
a maker reduciría 20 bp por round trip, **solo si ambas órdenes se
ejecutaran realmente con esa clasificación**. Una orden limitada
puede no ejecutarse y tener adverse selection. El motor no presume
probabilidad de fill ni genera órdenes; todo coste es hipótesis local
hasta que C25/C26/C35 lo midan.

## 6. Pruebas y falsación

Archivos implementados:

- `quant/harpoon_quant/incubation_matrix.py`
- `quant/tests/test_m11_incubation_matrix.py`
- `quant/benchmark_m11_incubator.py`
- `.github/workflows/fwn9_p9m_c36.yml`

Reproducir desde raíz:

    PYTHONPATH=quant python3 -m unittest discover -s quant/tests -p test_m11_incubation_matrix.py -v
    PYTHONPATH=quant python3 quant/benchmark_m11_incubator.py

El benchmark usa únicamente **40 instrumentos sintéticos × cuatro
familias de estrategias × 32 escenarios sintéticos comunes**. Mide
latencia, determinismo y ausencia de órdenes; **no** producción,
rentabilidad real ni mejora probada de alfa.

Para conceder valor económico, una futura revisión independiente
deberá preregistrar los filtros y probar frente a CASH y la política
original con coste broker observado, una sola cartera continua y
control de multiplicidad. Una sola ablation con el mismo conjunto
prospectivo debe comparar: sin matriz, solo coste, coste+regímenes,
coste+riesgo y matriz completa. Si el crecimiento geométrico neto OOS
no mejora o el número de operaciones omitidas oculta alfa rentable
mayor que el ahorro comprobable, se rechaza la incubadora.

## 7. Bloqueos que NO desaparecen

- Modelos predictivos calibrados y bandas poblacionales WEAK.
- Cobertura real de la oportunidad pre-filtro C32/C27/C28.
- Costes y fills alcanzables de Alpaca C25/C26/C35.
- Versionado semántico verdadero de seis familias C22.
- Opciones, ejercicio y flujos contables.
- Registro temporal externo C34 independiente.
- Prueba futura de N9-S 1 bp/día con familywise 0.025.

**Todo SHORTLIST es hipótesis local no ejecutable. NO_GO.
3.200 cuentas M10 finales selladas.**
