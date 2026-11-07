# Framework integrado en el quant core

La entrada pública es `harpoon_quant.framework.evaluate(packet)`. También está conectada al comando principal `python -m harpoon_quant framework` y al worker existente `runtime/quant_bridge.cjs.framework(packet, config)`. El script de revisión económica invoca esta misma entrada. La conciliación Decimal vive en `harpoon_quant/swing_evidence.py`; el verificador de archivos conserva la comprobación de hashes y delega la contabilidad en ese módulo.

## Contrato de entrada

```json
{
  "schema": "HARPOON_QUANT_FRAMEWORK_1",
  "operation": "PURGE_LABELS",
  "payload": {
    "labels": [
      {
        "at": "2025-01-01T00:00:00Z",
        "label_end": "2025-01-03T00:00:00Z",
        "known_at": "2025-01-03T00:00:00Z"
      }
    ],
    "test_start": "2025-01-07T00:00:00Z"
  }
}
```

El ejemplo es una fixture de ingeniería y devuelve el índice entrenable `[0]`.

| Operación | Payload | Resultado |
| --- | --- | --- |
| `QUALIFY_HISTORY` | `origin: HISTORICAL_MODELED`, `accounts`, `dividend_symbols` | Reconstruye ocho libros con Decimal y aplica las ocho condiciones del framework. |
| `TECHNICAL_SWING` | `dataset`, `snapshots`, `asof` | Selección de ruptura confirmada, volumen relativo y fuerza frente al ETF sectorial conocido en esa fecha. |
| `PURGE_LABELS` | `labels`, `test_start` | Índices admisibles con 72 horas de separación desde la disponibilidad de la etiqueta. |
| `ORDER_COSTS` | Bundle `HARPOON_OBSERVED_FILLS_1`, con `orders` y `fills` | Costes de ejecución y oportunidad por separado, incluidos parciales y no ejecutados. |
| `SIMULATE_SESSION` | `session`, `command`, `now_ms`, `recovery_required`, conforme a `roadmap9.integration.process` | Sesión local persistible de órdenes, fills, cancelaciones, comisiones e inventario, con origen sintético explícito. |

`SIMULATE_SESSION` habilita el recorrido de simulación en el core. Devuelve `session` para la siguiente llamada y una vista conciliada `view`. Los comandos y eventos se suministran explícitamente conforme al contrato de Roadmap9. No genera fills de mercado auténticos ni activa una cuenta Alpaca PAPER. La salida identifica `simulation_mode: LOCAL_SYNTHETIC` y `broker_paper_connected: false`. La simulación se permite aunque la estrategia no acredite nivel 8, conservando esa calificación como falsa. Los casos ejecutables de ciclo completo están en `quant/tests/test_framework_simulation.py`.

`accounts` contiene `NOMINAL` y `STRESS`. Cada uno contiene exactamente `JOINT`, `EQUITY_ETF`, `CRYPTO` y `CASH`, en formato `HARPOON_SWING_ACCOUNT_1`. El capital nativo es USD 20.000, sin flujos externos. `dividend_symbols` vincula recibo de acción corporativa con símbolo para eventos antiguos que carecen de ese campo. Usar las fuentes verificadas para construirlo. Un hash calculado sobre un paquete suministrado no autentica al proveedor.

## Invocación

```bash
PYTHONPATH=quant python -B -m harpoon_quant framework --input paquete.json --output resultado.json
```

```python
from harpoon_quant.framework import evaluate
receipt = evaluate(packet)
```

```javascript
const quant = require('./runtime/quant_bridge.cjs');
const receipt = await quant.framework(packet, { timeoutMs: 30000 });
```

Node conserva la cola, los límites de tamaño y el presupuesto temporal del worker existente. La entrada CLI limita a 32 MiB y rechaza JSON con claves duplicadas o constantes no finitas. No admite cambiar los umbrales del framework mediante `--config`.

La respuesta incluye `status`, `result`, `ledger_audit`, hash canónico del paquete y `selected: []`. Los enteros representados como `1` o `1.0` tienen el mismo hash al atravesar Node y Python. Las firmas de otros contratos conservan su serialización anterior.

La conciliación se ejecuta con un contexto Decimal aislado de 50 dígitos para que la precisión configurada por otro módulo no cambie el recibo contable.

Una revisión válida que rechaza la estrategia devuelve `status: REJECT` y termina normalmente. Un paquete inválido devuelve `status: BLOCKED`, razón explícita y código 2 en CLI. El adaptador externo conserva `--require-level8` para terminar con código 2 cuando falta acreditación.

## Alcance operativo

Esta integración permite llamar los módulos desde el core y su worker. No programa un nuevo ciclo del coordinador, no sustituye el asignador existente y no transmite órdenes. Las nominaciones técnicas permanecen dentro de `result`, separadas de la lista ejecutable `selected`.

`execution_allowed`, `liveApproved` y `level8_accredited` permanecen falsos. La evaluación histórica exige entradas modeladas explícitas. Los registros observados se admiten mediante el contrato separado de Roadmap9, con conciliación y autenticación de procedencia.

Los umbrales, límites y requisitos pendientes están en [FRAMEWORK_NIVEL8.md](FRAMEWORK_NIVEL8.md). La integración conserva el rechazo económico de la receta archivada: nominal -250,68871465 USD y estrés -670,02673293 USD. No añade mediciones de estrategias ni acredita nivel 8.
