# Harpoon XXXUltimate 30.4.0 · integración cuantitativa

## Cambios efectivos

- `xxx/coordinator.ts` aplica un plan común para las entradas de acciones, ETF, cripto y opciones. Las señales originales siguen proponiendo entradas; el motor cuantitativo decide admisibilidad y cantidad. La salida heredada y los límites originales de riesgo siguen operando.
- El worker Python corre fuera del mutex de órdenes. La falta de Python, timeout, salida inválida o modelo ausente bloquea entradas. Las salidas conservan prioridad. Un cambio de cuenta, posiciones o pendientes durante el cálculo invalida la propuesta.
- `runtime/quant_bridge.cjs` agrega posiciones y reservas, sin enviar credenciales al modelo. Obtiene señales actuales de los cuatro books, aplica el máximo de cantidad de la política original y recibe lotes económicamente asignados. Dentro del mutex se vuelven a revisar las condiciones operativas y se limita la cantidad a ambos máximos.
- El screener de acciones consulta movers y most-actives SIP durante sesión cada 15 minutos; añade solo nombres calibrados, clasificados y negociables hasta un total de 48 acciones. No se incluyen automáticamente 48 opciones ni toda la bolsa. Las posiciones existentes se preservan.
- El calendario del broker cubre 55 días anteriores y 60 posteriores. El puente filtra barras a las sesiones suministradas, incluidos cierres anticipados. Cripto usa 25 días de barras 15Min para RVOL comparable.
- `deploy/Dockerfile.xxx` instala Python y el entorno numérico. La imagen no se construyó ni desplegó en esta validación.

## Configuración

El ejemplo `config/examples/xxx.json` activa `quant.enabled`, horizonte de 24 horas, timeout de ocho segundos y descubrimiento de acciones. La configuración actual conserva sus propios topes de capital, riesgo, pérdidas y concentración. Esta entrega no modifica ni integra el servicio independiente de opciones 1.2 ni sus límites.

Modelo: `HARPOON_QUANT_MODEL` tiene prioridad sobre `quant.calibrationFile`; por defecto `/var/data/quant_calibration.json`. Ejecutable Python: `quant.python` o `HARPOON_QUANT_PYTHON`, por defecto `python3`. En Docker se establece `/opt/harpoon-quant/bin/python3`; no lo reemplaces por un Python sin NumPy/SciPy.

Desde la raíz del paquete:

```bash
npm ci --ignore-scripts --no-audit --no-fund
npm run build:xxx
python3 -m venv .quant-venv
.quant-venv/bin/pip install -r quant/requirements-tested.txt
export HARPOON_QUANT_PYTHON="$PWD/.quant-venv/bin/python3"
```

El archivo calibrado se prepara con `python -m harpoon_quant fit` desde `quant/`, según `quant/INPUTS_ES.md`. No hay modelo observado aceptado incluido. La bandera de origen se declara en el insumo y no autentica por sí misma la procedencia. `accepted` significa habilidad de MSE condicionada al panel; no certificación de rentabilidad. El estado PAPER y la identidad, conciliación, permisos, protección y riesgo del coordinador continúan siendo requisitos independientes.

Las opciones exigen metadatos adicionales de tasa, dividendo, estilo, hora de vencimiento y revisión de ciclo de vida en el activo, además de IV/delta y calibración conjunta de IV. El catálogo actual no los fabrica: una señal sin ellos se rechaza. Los futuros pueden valorarse en el núcleo normalizado, pero el conector Ironbeam heredado permanece separado y no utiliza esta nueva puerta de ejecución. Alpaca no se presenta como broker de futuros.

## Verificar

```bash
npm run typecheck:xxx
npm run test:xxx:clocked
npm run test:quant
cd quant
python -m unittest discover -s tests -v
```

El reloj anclado de pruebas se importa exclusivamente por scripts de QA. Las fixtures históricas desactivan el nuevo gate para aislar la regresión de protecciones y riesgo; los tests de `tools/quant_bridge_test.cjs` lo activan explícitamente. Los órdenes de esas pruebas son FakeBroker. El test de progreso del scheduler espera tres ciclos reales con plazo máximo de dos segundos, en lugar de depender de una espera fija de 40 milisegundos. No se usa salida forzada del runner, para no ocultar casos pendientes.

## Límites de la validación

Las pruebas demuestran contratos y ecuaciones con fixtures fabricadas. No se ejecutó una calibración observada, una estrategia rentable nueva, una conexión autenticada a Alpaca o Ironbeam, una imagen Docker ni un despliegue. Los informes y manifests anteriores se conservan como históricos; `MANIFEST_XXXUltimate.json` y `quant/evidence/validation.json` describen esta versión. No hay cuenta multi broker consolidada ni prueba prospectiva. El modelo de valoración terminal no equivale al P&L de la política de salidas completa.
