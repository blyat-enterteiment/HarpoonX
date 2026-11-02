# HARPOON XXXUltimate 30.15.0

Integral actual: lee `LEEME_30_15_0.txt`, `docs/LEVEL7_OPERACION_30_15_0.txt` y `EVALUACION_ECONOMICA_HARPOONX_30_15_0.yaml`. Incluye validación de costes, procedencia de decisiones y evaluador económico de cartera. 230 pruebas aprobadas. El nivel 7 de rentabilidad real no está acreditado. Despliegue pendiente.

## Documentación heredada

# HARPOON XXXUltimate 30.14.0

Integral actual: lee `LEEME_30_14_0.txt` y `EVALUACION_ECONOMICA_HARPOONX_30_14_0.yaml`. Se corrigieron causalidad de señales, reservas compartidas y valoración inicial. El resultado histórico permanece en +91,28 USD; el nivel 7 de rentabilidad real no está acreditado. Reproducción: `node tools/verify_portfolio_validity_study.cjs`. Despliegue pendiente.

## Documentación heredada

# Actualización 30.7.0

[Investigación económica](docs/QUANT_30_7_ES.md): resultado REJECTED, sin promoción, despliegue u órdenes. El resto conserva instrucciones heredadas.

# Actualización 30.6.0

Lee [la guía de calibración recursiva](docs/QUANT_30_6_ES.md). Sin panel observado y P&L conciliado el motor espera datos. No se ha desplegado. Las instrucciones heredadas siguientes se conservan como referencia.

# HARPOON XXXUltimate · 30.5.0

La versión actual añade el motor cuantitativo común. Lee `docs/QUANT_30_5_ES.md`: el ejemplo bloquea nuevas entradas si falta una calibración observada admisible.

1. Sigue [README.md](README.md) para configurar una cuenta Alpaca PAPER dedicada y arrancar el servidor.
2. Abre `http://127.0.0.1:10000`. Usuario `trader` y tu contraseña configurada en el servidor.
3. Revisa **Monitor del sistema**, conciliación, datos y protecciones antes de activar entradas. El HTML suelto no inicia un motor ni contiene cotizaciones de muestra.

Auditoría y verificación: `AUDITORIA_XXX.txt`, `MANIFEST_XXX.json` y `SHA256SUMS_XXX.txt`.
Selector Ridge: [contrato de datos](docs/SELECTOR_DATA.md).

Las guías XXIV/XXV y `render-legacy.yaml` corresponden a versiones anteriores. Para XXX usa `render.yaml` y `deploy/Dockerfile.xxx`.

No se ha desplegado ni conectado esta entrega a Alpaca. PAPER opera con fondos virtuales; la rentabilidad no está acreditada.
