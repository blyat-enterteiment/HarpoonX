# Banco adversarial de matriz virtual

20 tests ejecutados (8 previos y 12 nuevos), con subcasos temporales, numéricos y doce asignaciones aleatorias con semilla fija. Cubren agotamiento individual de presupuestos, identidad contable de caja/riesgo/exposición, contradicciones, inventario suficiente, órdenes pendientes, orden de celdas, vencimiento exacto, frescura en cinco segundos, historia inválida, semilla inválida, costes fijos y proporcionales, y cambio de régimen.

Cinco escenarios contrafactuales sintéticos independientes comparan un objetivo único de USD 1.000, capital USD 20.000 y coste modelado de ida y vuelta de 8 pb. No se usa el comparador de cinco compras duplicadas. El filtro sólo recibe historia previa; el rendimiento posterior se usa exclusivamente para puntuar. No hay trayectorias intradía, stops ni fills en esta puntuación: son episodios abstractos, NO backtests ejecutables de mercado. No sumar sus resultados como historial compuesto.

| Escenario | Referencia neta USD | Matriz neta USD |
|---|---:|---:|
| Ventaja persistente | 19.20 | 19.20 |
| Pérdida evitada | -20.80 | 0.00 |
| Recuperación perdida | 19.20 | 0.00 |
| Cambio adverso de régimen | -30.80 | -30.80 |
| Mercado plano y costes | -0.80 | 0.00 |

Conclusión limitada: correctitud de los contratos examinados; no prueba superioridad económica ni acredita nivel 8. No se calibra ningún parámetro para ganar estos escenarios. Las frecuencias de cada régimen no están estimadas, por lo que su promedio no estima rentabilidad futura.

Reproducir desde raíz:

```bash
PYTHONPATH=quant python -m unittest discover -s quant/tests -p 'test_virtual_net*.py' -v
PYTHONPATH=quant python tools/run_virtual_net_bank.py
```

El informe JSON registra origen sintético, entradas mediante SHA-256 y tiempos de ejecución. El benchmark depende del entorno. No se ha vuelto a ejecutar toda la suite del repositorio en esta ampliación ni se ha cambiado el motor.
