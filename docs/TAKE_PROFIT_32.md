# HARPOON XXX 30.2 — salidas, evidencia y competición

La prioridad es capturar beneficio neto con inventario conciliado y protección comprobable. No existe una política de salida universalmente superior. Esta revisión no acredita rentabilidad ni resultados reales de una cuenta.

## Decisión de investigación

Se registraron tres políticas antes del cálculo: referencia 30.1, Trend Runner y Regime Adaptive. El código de sus parámetros tiene SHA-256 en `research/tp32/protocol.json`. El perfil del régimen usa sólo observaciones disponibles al entrar; las reglas y el riesgo inicial quedan congelados para esa campaña. No se aprende de precios futuros ni se cambian posiciones abiertas al elegir otro perfil.

La métrica principal es **mejora de P&L diario neto a las mismas entradas y riesgo**, con intervalo bootstrap por bloques ajustado por tres ensayos. Esperanza en R, drawdown, pérdida media del peor 5% de sesiones, Sharpe HAC, Sortino, profit factor y captura del pico observado ayudan a evaluar el resultado. Un retorno alto por sí solo no aprueba un candidato.

- Históricos observados de Alpaca: septiembre de 2024 a octubre de 2026; evaluación desde octubre de 2024. Acciones/ETF en sesión regular según calendario, incluidos cierres anticipados.
- Doce folds de 126 sesiones previas y 21 de prueba; purga de 72 horas y embargo de tres sesiones. Holdout final de 63 sesiones, separado de la selección de entrenamiento.
- Costes, spread estimado, gaps, límites de entrada, lotes mínimos y precedencia adversa del stop. Estrés de doble coste, retraso de una barra y fills parciales del 50%.
- Comparación de oportunidades con entradas comunes y riesgo fijo. Cartera con capital/exposición compartidos en un segundo análisis, usando sólo oportunidades con cobertura común entre políticas.
- Barras stock/ETF SIP completas para los símbolos solicitados tras filtrar el calendario: 41.394 por símbolo. Cripto contiene numerosos periodos sin volumen/huecos; se excluyen las trayectorias afectadas. No se inventan cotizaciones históricas de opciones.
- Las características rápidas se contrastaron con 30 cálculos de la función nativa. Se usa la misma función de salida de `xxx/policy.ts` compilada que utiliza el coordinador.

La muestra común OOS queda en **7 operaciones** y la final en **5**, frente a los mínimos de 100 y 30. La referencia suma aproximadamente **−USD 53,12 OOS / −USD 45,68 holdout**; Trend Runner **−USD 113,81 / −USD 6,43**; Regime Adaptive **−USD 90,77 / −USD 50,09**. Son P&L de oportunidades bajo un modelo de barras, no rendimientos obtenidos en Alpaca. Ningún candidato supera las barreras. La referencia se conserva sin certificar su rentabilidad. El informe JSON contiene todas las ventanas, métricas, exclusiones y resultados de estrés.

No se reconstruye la cola del broker, los tres segundos de llegada de barras, el TTL real de 15/20 segundos ni el recorrido bid/ask de cada cinco minutos. Se modelan fills; no se atribuye a las correcciones de ejecución un beneficio que estos datos no permiten medir. Las protecciones OCO y la reacción a eventos necesitan observación prospectiva. El histórico SIP tampoco valida automáticamente el feed IEX configurado por defecto.

## Ejecución implementada

1. La intención se persiste antes del envío. Respuestas inciertas se buscan por client_order_id; nunca se reenvían a ciegas.
2. El plan de TP conserva cantidad acumulada y precio mínimo mientras se cancela la protección. La venta restante se recalcula con fills y posiciones confirmados.
3. Un stop/flatten/vencimiento/plazo tiene prioridad sobre un parcial pendiente. DELETE no acredita cancelación: se exige respuesta de órdenes e inventario antes de otra venta.
4. El stop se compara al tick con el precio confirmado, sin el antiguo umbral de 0,5%. Se limita su frecuencia de actualización; la deriva pendiente es visible y bloquea nueva asignación.
5. Acciones/ETF admiten grupos OCO por parcial y runner protegido. El trailing nativo sólo se usa como orden independiente. Se identifican y concilian padre y piernas; sus fills se cuentan una sola vez.
6. Un rechazo confirmado de OCO/trailing permite volver a un stop simple. La incertidumbre no se interpreta como rechazo. Cripto y opciones no envían tipos OCO incompatibles.
7. WebSocket real para órdenes, cotizaciones y flujo de plugins; OPRA binario MsgPack. Se validan suscripciones, timestamps, identidad y acumulados. Repeticiones/regresiones no crean fills. Reconexión invalida el calentamiento de flujo; REST confirma inventario.
8. La guardia y su pulso acotado continúan con investigación pausada o agotada. Cada posición, ciclo, contrato, transporte y coste conserva su estado observado.

Las salidas gestionadas de cripto/opciones pueden tener una porción reservada en un TP sin protección nativa simultánea. Se protege la cantidad libre y la guardia cancela/prioriza ante un stop. La caída del proceso/red y la falta de liquidez impiden garantizar esa reacción. Stop-limit puede no ejecutar en un gap; OCO tampoco garantiza que ambas piernas nunca ejecuten en mercados extremos. Esas limitaciones se muestran, no se reemplazan por una cobertura ficticia.

## Métricas y UI

Take profit lab presenta stop calculado/confirmado, cantidad cubierta, deriva, plan persistido, estado de flujos y resultados del protocolo. Las latencias son observaciones de envío/ACK/fill, no cronómetros decorativos. Giveback usa picos brutos observados en campañas cerradas; no un máximo intrabar omnisciente. El tiempo descubierto es muestreado, no una certificación del mercado.

Los fills ya incorporan el precio ejecutado: no se descuenta slippage una segunda vez al P&L. Las comisiones estimadas y las actividades USD reportadas son bases diferentes. CFEE sin moneda USD explícita queda sin valoración; no se certifica neto total ni se interpreta una actividad ausente como coste cero.

## Operación y actualización

La instalación nueva usa `nativeProtection: oco`, refresco mínimo de cinco segundos y flujos activados. `stop` conserva la protección gestionada anterior; `oco_trailing` es una alternativa configurable. Siempre PAPER y cuenta dedicada.

Una instalación 30.1 puede ejecutar los arreglos conservando **su configuración original y SQLite**. Cambiar la configuración ligada al diario mantiene el bloqueo de migración existente; no se recomienda borrar la base ni modificar su huella para evadirlo. Para usar una configuración nueva se necesita una cuenta PAPER dedicada vacía con diario nuevo y conservar el anterior como evidencia. No se adoptan posiciones ajenas.

La selección de perfiles en UI sí es una acción persistida para entradas futuras y no modifica el vínculo de riesgo. Las variantes requieren reconocimiento experimental. No se cambian parámetros para volver a probar el holdout consumido.

## Reproducción

```bash
npm ci --ignore-scripts --no-audit --no-fund
npm run build:xxx
python3 -m pip install -r research/tp32/requirements.txt
npm run walkforward:xxx
npm run test:xxx
npm run audit:xxx
```

El ZIP incluye datos y metadatos de origen para reproducir la comparación. Una repetición técnica no genera evidencia prospectiva ni habilita ajustar contra el mismo holdout. Los datos son para este análisis privado y conservan los términos del proveedor.

## World Cup Trading Championships

La organización identifica el 11.376% de Larry Williams como el resultado anual de **1987**. La tabla adjunta no representa el retorno que deba alcanzarse en 2026 ni aporta drawdown de cada competidor. Las divisiones de esta competición son futuros y forex, con brokers/cuentas y requisitos propios. El ejecutor actual de Alpaca no negocia esos instrumentos: no se afirma inscripción, compatibilidad ni resultados de campeonato. La capa de estrategia/riesgo puede reutilizarse al integrar y validar un broker admitido con contratos, multiplicadores, margen, roll y horarios propios; ese adaptador no se inventa en esta entrega.

Fuentes primarias consultadas el 18 de octubre de 2026:

- https://www.worldcupchampionships.com/
- https://docs.alpaca.markets/us/docs/orders-at-alpaca
- https://docs.alpaca.markets/us/docs/websocket-streaming
- https://docs.alpaca.markets/us/docs/real-time-option-data
- https://docs.alpaca.markets/us/docs/account-activities
- https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf
