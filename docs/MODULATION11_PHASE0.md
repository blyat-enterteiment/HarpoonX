# HarpoonX M11: control estructural de ejecución, fase 0

**Estado:** instrumentación diagnóstica aislada; no se ha repetido una búsqueda de alpha, no se ha abierto el final M10 y no se certifica N9-S.

Se fijó un [protocolo nuevo](../research/modulation11/protocol.json) con cero políticas nuevas, cero cuentas económicas y ningún gasto de alfa de validación. No se cambian el generador M9, los costes M10, el capital de USD 20.000, la reserva del 12%, los límites de riesgo, las 72 horas ni los hurdles. Se conservaron los resultados negativos de M9/M10 y el holdout M10 sellado.

## Evidencia reproducible y alcance

- `quant/harpoon_quant/modulation11_substeps.py` observa la variable `intrabar` de ocho subpasos directamente en el generador M9 original mediante un trace acotado a su frame; **no** modifica la función, el estado del RNG ni el orden de sus llamadas. Bloquea el escenario final, rechaza una fuente distinta del hash M9 original, compara el hash del OHLCV con una segunda generación sin instrumentación y exige OHLC, cierre, timestamps y señales idénticos. Los subpasos se destinan sólo a ejecución/auditoría y no a ranking.
- `runtime30/modulation11_execution_equivalence.cjs` es un comparador independiente de una barra: replica la semántica stop-first y targets por cuartos del replay nativo a nivel OHLC; contrasta ventas al primer precio discreto que cruza en ocho subpasos. Mantiene `availableAt` para conocer un fill al publicarse la barra, separándolo del instante efectivo propuesto; no supone que la rejilla sea un mercado real líquido.
- `tools/modulation11_fixture_test.cjs` implementa cuatro familias causales: marca atrasada durante IOC; reserva retenida hasta el recibo y tras parcial; sobrepaso separado de stop y target; mismos OHLC con distinto orden intrabar. La cuenta de caja por fill y las comisiones por acción se reconcilian en un libro separado para cada barra.
- `quant/tests/test_modulation11_substeps.py` exige identidad de OHLCV y señales del generador real y falla ante cambios de ley o acceso al final. `.github/workflows/modulation11.yml` ejecuta pruebas de integración de código, Ruff, mypy y Node cuando GitHub Actions inicia el job.

## Hallazgo estructural

Para el stop 99,03 de una compra a 100,03, con apertura 100 y primer cruce discreto 98,80, idénticos 3 pb de fricción de salida, tick 0,01 y comisión, la convención OHLC cobra **99,00** y el comparador **98,77**: diferencia **+0,23 USD/acción para OHLC**. Para el target 101,53 cruzado por primera vez en 101,80, la convención OHLC cobra **101,49** frente a **101,76**: diferencia **−0,27 USD/acción para OHLC**. El signo del sesgo no es universal.

Dos permutaciones de los mismos ocho precios con los mismos OHLC producen fills distintos: target parcial antes del stop en un camino, y stop total antes del target en otro. El algoritmo OHLC nativo aplica stop-first a ambos. Así se rechaza **equivalencia exacta** entre ambos procedimientos. No se ha cuantificado su sesgo esperado agregado ni una mejora económica.

Con una reserva conforme al límite de admisión, la revalorización de una posición existente durante los 299 segundos entre decisión e IOC puede elevar la exposición observada sobre el 12% sin constituir por sí misma una nueva admisión incorrecta. La fixture de cartera muestra ese contraejemplo semántico; **no** prueba ni refuta todavía el lema anclado a reservas bajo toda la cronología real. La cota de 0,9051232470 pb/día para WEAK continúa siendo **condicional** y no certifica imposibilidad del replay nativo.

## Verificación y pendientes

En la máquina de construcción se ejecutaron cinco comprobaciones Node aisladas con éxito: familia 1, dos sobrepasos en familia 3, familia 4 y rechazo de OHLC alterado. La prueba de reservas usa explícitamente el módulo nativo `ultimate_reservations.js`, ausente del checkout local, por lo que aún **no** se declaró pasada en local. La prueba Python del generador real queda asimismo para GitHub CI. `node --check` y `compileall` locales pasaron; Ruff y mypy quedaron para CI. Una ejecución CI exitosa valida estas fixtures, **no** toda la integración de cartera.

El siguiente paso es conciliar la cuenta sombra con los eventos nativos de reserva/IOC y verificar el comparador contra `replayCampaign` de manera integrada, incluyendo salida, deadlines, trailing y recibos. Sólo después podrá decidirse si corresponde el diagnóstico prerregistrado de 240 o 400 cuentas de desarrollo, nunca final y nunca elegible para selección. No debe declararse un techo continuo de exposición ni operar con brokers. Los requisitos de parciales/rechazos/outages/impacto y coordinador multicelda siguen abiertos.

**Checklist de cierre de N9-S:** no elegible en M10; final no abierto; rentabilidad real no probada; cota del motor no certificada; revisión externa y requisitos operativos incompletos.
