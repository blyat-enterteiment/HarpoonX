# HARPOON XXV · Alpaca Crypto Desk

Edición 25.0.0 — 17 de octubre de 2026.

## Abrir

Abre HARPOON_XXV.html. La mesa inicial muestra ocho funciones, su estado y la última evidencia recibida. «Conectar y operar» lleva a la conexión cripto original. Alpaca requiere API Key ID y Secret. PAPER y LIVE usan credenciales distintas. Mantén el navegador abierto y despierto si eliges ejecución local; un HTML no es un servidor 24/7.

Para ejecución persistente, el paquete conserva el servicio cloud, SQLite, gateway GPT, Dockerfile y render.yaml. La edición administrada sólo acepta HARPOON_BOOKS=crypto. El panel remoto muestra la mesa en Operación. Este paquete no ha sido desplegado ni conectado a una cuenta por esta entrega.

## Qué se reconfiguró

- Sólo cripto Alpaca en la edición XXV. Sin DEX Screener, Jupiter, Solana RPC, pump.fun, firmas de wallets ni claves privadas.
- Consulta /v2/assets?asset_class=crypto. Muestra el catálogo devuelto; no considera todos los pares como habilitados por una estrategia.
- El universo ejecutor conserva BTC/USD y ETH/USD, condicionado a que Alpaca los declare activos y negociables. Los plugins y el walk-forward originales dependen de esos dos pares; no se han extendido artificialmente a todos los activos del catálogo.
- Antes de cada compra se exige catálogo de hasta 60 segundos, clase crypto, activo negociable, mínimos e incrementos válidos y cotización de hasta 15 segundos. Un error del catálogo bloquea compras; no añade esa dependencia a las ventas del gestor vigente.
- El runtime administrado no inicia otros libros; el HTML XXV bloquea la conexión del ejecutor de acciones. La edición XXIV original está preservada por separado para recuperar sus funciones.
- Los ocho roles son funciones instrumentadas del mismo ejecutor: HEAD, SEARCH, RISK, FLOW, SIGNAL, SNIPER, EXIT y WATCH. No se simulan ocho agentes LLM, análisis de ballenas, sentimiento social ni detección de rugs.

## Take profit y compuesto

Se conserva la política de cada campaña: tendencia y sus stops, y recuperación con objetivo/salida temporal cuando el plugin aplica. La nueva mesa no añade órdenes ni altera objetivos de campañas abiertas. Recovery mantiene su restricción PAPER. El capital del ejecutor se calcula desde la cuenta y bajo los límites existentes; no se eleva automáticamente la fracción de riesgo.

La regla de 72 horas no se activa retroactivamente: el valor por defecto de tendencia sigue siendo hold_hours=0 (salida por tendencia). Para usar 72 horas, cambia la configuración admitida antes de nuevas campañas, con entradas pausadas y sin campañas abiertas. Un vencimiento provoca intención de salida, no garantiza ejecución en ese segundo.

No se implementó el corte diario del 5% del artículo: se conserva el límite de drawdown original. Tampoco se añaden reportes Telegram ni promesas de evitar rugs. El artículo no es evidencia de rentabilidad.

## GPT y loop

La mesa cuesta cero tokens. El gateway y la supervisión previos conservan sus ventanas, presupuestos, LiftOn/LiftOff, informes y restricciones. No se inicia inferencia por abrir la mesa. Las propuestas no se convierten por sí solas en estrategias rentables. El loop remoto COLD de cripto no se ha implementado en esta revisión; la investigación cripto local existente sigue disponible en el HTML.

## Pruebas y límites

Ejecutadas: npm test, npm run test:auth y npm run test:xxv. 65 comprobaciones reportadas por suites heredadas y 10 grupos nuevos; evidencia en evidence/. Se verifica carga de motor cripto, persistencia, conciliación ante ambigüedad, proxy/auth y restricciones nuevas. Son fixtures locales y análisis de sintaxis: no prueba visual completa, broker real, Docker en producción ni rentabilidad. No se enviaron órdenes ni llamadas GPT de pago.

La recuperación de comisiones sigue dependiendo de su publicación por Alpaca; el resultado estimado se distingue de beneficio conciliado. Un stop-limit puede no ejecutarse ante un salto de precio. No se debe operar el HTML y el servidor sobre la misma cuenta: usa una autoridad ejecutora y la cuenta dedicada requeridas por el paquete original.

Fuente de los contratos de Alpaca: https://docs.alpaca.markets/us/docs/crypto-trading (consultada el 17 de octubre de 2026).
