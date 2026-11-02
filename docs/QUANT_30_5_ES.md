# XXXUltimate 30.5.0 · calibración L1 y curvas

La configuración de ejemplo añade `quant.microstructure`; sus tipos, dominios numéricos y rutas se validan antes del arranque. La lane `quant-calibration-context` corre cada 15 minutos incluso si falta el modelo de retornos. El guard puede esperar calentamiento/cobertura y mantiene las salidas independientes. Los modelos adicionales no se crean ni promueven automáticamente.

Usa `quant/LAB_ES.md` como guía de datos, calibración, base vectorial y comandos reproducibles. El registro durable predeterminado es `/var/data/quant_curves.sqlite3`; modelos `/var/data/micro_support.json` y `/var/data/correlation_regime.json`. Su ausencia se declara como no calibrada. El modelo de retornos común sigue siendo necesario para nuevas entradas. El coste adicional observado solo puede aumentar fricción, y el diagnóstico de regímenes no autoriza operaciones.

El colector usa la configuración validada del coordinador y conserva tamaños en REST/streams, incluidos mensajes OPRA MsgPack. Muestrea el último evento por segundo, hasta 360 muestras/tipo/instrumento; no representa todos los trades ni profundidad completa. Reconectar invalida el contexto L1 del book. No se añadieron otros proveedores, un LLM ni un proceso de autoentrenamiento.

La muestra observada está en `quant/observed/`; el registro de ejemplo es `quant/evidence/observed_curves.sqlite3`. No es un journal de órdenes. La API HTTP de datos es de solo lectura y la integración reutiliza los streams del coordinador. No se fusiona el servicio separado de opciones 1.2 ni se incorpora este gate al conector Ironbeam.

Verifica `npm run build:xxx`, `npm run typecheck:xxx`, `npm run test:xxx:clocked`, `npm run test:quant`, y desde `quant/` `python -m unittest discover -s tests -v`. Los resultados definitivos están en `quant/evidence/validation.json`. El build Docker y el despliegue no se ejecutaron; los datos de mercado sí se recuperaron por el conector Alpaca. La operativa autenticada de órdenes permanece sin verificar en esta entrega.
