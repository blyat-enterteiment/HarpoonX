# HARPOON XXV · Mesa agéntica Alpaca

Revisión **25.1.0**, 17 de octubre de 2026. Sustituye la revisión 25.0.0 que sólo proyectaba estados del motor.

## Uso

1. Abre **HARPOON_XXV.html**. La nueva mesa aparece al inicio; también puedes abrirla con «XXV · Mesa agéntica».
2. En **API keys y conexión**, conecta Alpaca cripto. Para pruebas usa credenciales PAPER. La cuenta debe ser dedicada, estar activa y pasar la conciliación del motor.
3. En **Estrategias y operación**, comprueba los plugins cargados y el estado de entradas. La mesa no inventa señales para operar a la fuerza.
4. Revisa **Oportunidades** para ver el ID, los pasos, el motivo de rechazo o el plan aprobado. En PAPER la política automática predeterminada evita aprobar cada oportunidad. Puedes desactivarla. LIVE siempre exige `APPROVE ID` literal sobre un plan preparado y vigente.
5. En **GPT y sandbox**, configura primero el gateway, ventana y presupuesto existentes. HOT permite revisiones agrupadas; COLD permite investigación histórica local. LiftOff IA detiene nuevos ciclos, sin anular el coste de solicitudes ya enviadas ni las salidas existentes.

Un HTML necesita navegador abierto y equipo despierto. Para operación persistente el paquete incluye el servicio cloud y su panel, Dockerfile, SQLite y render.yaml. Esta entrega **no ha sido desplegada ni conectada a una cuenta real**. No ejecutes HTML y cloud sobre la misma cuenta: elige una autoridad ejecutora y respeta el bloqueo del motor.

## Los ocho agentes implementados

Son agentes de software especializados con handlers ejecutables, tareas delegadas, memoria, resultados y límites. No son ocho modelos LLM ni ocho ejecutores con acceso al dinero.

| Agente | Trabajo y límite |
|---|---|
| HEAD | Coordina objetivo, dependencias e informes. Nunca envía órdenes. |
| SEARCH | Valida par y plugin contra Alpaca. No incorpora tokens de DEX. |
| RISK | Comprueba capital, inventario, costes y corte diario. No aumenta riesgo. |
| FLOW | Confirma cotización, spread y profundidad cuando el plugin la exige. No identifica ballenas. |
| SIGNAL | Confirma señal causal y vigencia del plugin. No compra por texto o sentimiento. |
| SNIPER | Prepara plan y permiso consumible. El ejecutor original es quien envía la orden. |
| EXIT | Revisa las campañas y su protección. No añade ni promedia pérdidas. |
| WATCH | Detecta continuidad deficiente e intenciones inciertas. No se presenta como detector de rugs. |

Cada oportunidad pasa SEARCH → RISK → FLOW + SIGNAL → SNIPER → ejecutor Alpaca → cierre observado. Las dos confirmaciones cubren dimensiones distintas; no son dos pruebas independientes de rentabilidad.

Las tareas, resultados y mensajes se persisten. Cada mensaje lleva ID, par, secuencia y hash SHA-256 enlazado. El archivo conserva mensajes completos por clave; la interfaz muestra una ventana acotada. Esta cadena detecta inconsistencias locales, pero no es una firma de un tercero ni garantiza inmutabilidad ante quien controle el almacenamiento.

El plan limita cantidad, precio, stop, política y caducidad. Cambiarlo invalida la aprobación. El permiso se consume y guarda **antes** del envío; una respuesta ambigua no permite reutilizarlo. La conciliación nativa determina fills y protección. Los handlers no reciben claves ni herramientas de órdenes.

## Universo y salidas

Sólo **BTC/USD y ETH/USD**, siempre que Alpaca los declare negociables. El catálogo puede mostrar otros pares, que no se activan sin soporte de plugins e investigación. Se mantienen tendencia y recuperación; Recovery sigue restringida a PAPER.

Las políticas originales de salida permanecen congeladas por campaña. La mesa no introduce parciales adicionales ni modifica campañas abiertas. El hold de tendencia predeterminado sigue siendo 0, salida por tendencia; puedes elegir un plugin de 72 horas antes de nuevas campañas. Stop-limit o plazo de salida no garantizan un fill a un precio o segundo determinado.

## Corte diario y compuesto

Corte máximo de nuevas entradas al perder 5% desde la primera observación del día local de Ciudad de México; puede reducirse. Persiste tras reinicios y no puede restablecerse el mismo día. Al siguiente día exige `RESET DESK AAAA-MM-DD` y una reanudación explícita. El drawdown del core sigue aplicando. El corte diario no liquida por sí mismo toda la cartera: se conserva la gestión de salidas vigente.

Se consultan actividades publicadas por Alpaca para separar flujos monetarios. Flujos desconocidos, transferencias no monetarias o cargos tardíos pueden impedir métricas fiables; sin conciliación suficiente no se certifica neto económico. Una retirada no reconocida puede provocar un corte conservador.

Por defecto, el tamaño del nuevo plan no capitaliza ganancias flotantes: usa el ancla de la cuenta más el resultado realizado estimado de campañas cerradas, acotado por equity y capital_limit. Comisiones pendientes y aportaciones externas requieren conciliación. No se eleva automáticamente la fracción de riesgo.

## GPT y sandbox

GPT sigue usando el único gateway existente. Recibe un resumen acotado de la mesa, no las credenciales. Sus hallazgos válidos se convierten en propuestas de investigación identificadas, con evidencia, coste e iteraciones consumidas. No autorizan operaciones, código ni cambios de riesgo. No se añadió una segunda API de modelos ni ocho llamadas por ciclo.

El sandbox ejecuta el walk-forward cripto nativo: al menos 938 días comunes, entrenamiento de 365 días, bloques de prueba de 90, embargo nativo y 180 días finales. Busca entre cuatro variantes predefinidas; conserva costes, referencia y límites de riesgo. El estudio remoto usa un worker con máximo de 60 segundos para separar su cómputo del ejecutor. El HTML hace ese estudio localmente; puede bloquear brevemente su hilo, por lo que el servidor es la opción para operación continua.

Cada intento se reserva antes de iniciarlo. Un estudio fallido sigue contado. Se rechaza volver a observar el mismo final histórico. La política comienza con COLD apagado y 8 iteraciones compartidas con propuestas GPT. Un resultado histórico favorable permanece como candidato exportable; **no hay promoción automática a trading**, ML entrenándose en vivo ni rentabilidad demostrada. Requiere validación prospectiva y una decisión de despliegue.

Sharpe y Sortino se mantienen vacíos hasta reunir al menos 30 retornos diarios consecutivos con flujos observados; son descriptivos, con RF=0. Alpha se mantiene vacío sin benchmark comparable. El drawdown mostrado es el observado sobre NAV y puede estar afectado por flujos sin conciliar.

## Informes y Telegram

HEAD prepara informes a las 09:00 y 21:00, hora de Ciudad de México, y revisión semanal el domingo a las 21:00. Si el proceso estuvo apagado, el siguiente ciclo genera el informe pendiente y no inventa vigilancia del período ausente. El informe incluye estados del embudo, posiciones, resultado estimado, win rate observado y mejor/peor campaña cuando existen cierres con fills, errores, métricas y una mejora a investigar.

Los informes están disponibles en la aplicación. Telegram es opcional y sólo se configura mediante secretos del servidor:

```
HARPOON_TELEGRAM_ENABLED=1
HARPOON_TELEGRAM_TOKEN=<token del bot>
HARPOON_TELEGRAM_CHAT_ID=<chat autorizado>
```

No pegues secretos en el chat. Una entrega incierta se marca UNKNOWN y no se reenvía automáticamente para evitar duplicados. Telegram no recibe comandos de trading: las aprobaciones se hacen en el panel autenticado o en el HTML. En esta entrega no se envió ningún mensaje Telegram.

## Validación y alcance

Las suites heredadas y las nuevas verifican persistencia SQLite, reintentos ambiguos, autenticación, tareas paralelas, integridad de mensajes, aprobación literal, caducidad, corte diario, sandbox en worker y continuidad de salidas. El HTML se probó en Chromium con vista de escritorio y móvil; se corrigieron los hashes CSP que impedían ejecutar scripts modificados en 25.0.0.

Pruebas reproducibles:

```
npm ci --ignore-scripts
npm test
npm run test:auth
npm run test:xxv
npm run test:agents
node tools/agents25_cloud.cjs
npm run typecheck
npm run typecheck:agents
npm run test:service
```

La prueba de navegador está en tools/agents25_browser.cjs; necesita Playwright y Chromium disponibles. Las verificaciones de tipos cubren el núcleo de agentes, control y proxy, no todos los módulos heredados. Se incluye un benchmark local del embudo en memoria; no mide latencia de Alpaca.

No se enviaron órdenes externas ni llamadas GPT de pago. Los fills y barras sintéticos usados por las pruebas están identificados como fixtures y no constituyen resultados financieros. No se ejecutó un despliegue Docker/Render en producción. Resultados detallados en evidence/ y controles de integridad en SHA256SUMS.txt.

Referencias de contratos consultadas: [Alpaca cripto](https://docs.alpaca.markets/us/docs/crypto-trading), [actividades de cuenta](https://docs.alpaca.markets/us/docs/account-activities), [seguridad de agentes OpenAI](https://developers.openai.com/api/docs/guides/agent-builder-safety), [Telegram Bot API](https://core.telegram.org/bots/api).
