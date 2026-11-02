# Revisión vigente: HARPOON XXV.3 R2 / 25.3.2

Empieza en **EMPEZAR_XXV_3.md** y **AUTOGESTION_R2.txt**. Incluye pulso proactivo, perfil persistente y panel cloud. Ejecución de esta edición: BTC/USD y ETH/USD spot; demás clases, análisis. El paquete no acredita despliegue remoto ni rentabilidad real. A continuación se conserva la documentación de instalación heredada.

# HARPOON XXV.3

Entrada de esta entrega: **HARPOON_XXV_3.html**. Guía vigente: [EMPEZAR_XXV_3.md](EMPEZAR_XXV_3.md). Auditoría: [AUDITORIA_XXV_3.txt](AUDITORIA_XXV_3.txt).

War room nativo, ocho variantes con el mismo riesgo, opciones Alpaca como contexto L1/IV/griegas, profundidad cripto y supervisión GPT acotada. El paquete cloud incluye el mismo control. Los documentos y HTML anteriores se conservan como referencia de sus versiones.

---

**Edición actual: HARPOON XXV 25.2.0.** Empieza por [EMPEZAR_XXV.md](EMPEZAR_XXV.md) y abre HARPOON_XXV.html. La documentación que sigue conserva la instalación y arquitectura heredadas.

# Revisión 24.3.1: autenticación e inferencia

Consulta **INICIAR_REVISION.md** y **AUTHENTICATION.md** para el estado comprobado, las correcciones y el flujo de credenciales. Esta copia parte del paquete existente; el repositorio GitHub inferido sigue vacío y no se ha publicado ni desplegado esta revisión. Los resultados actuales están en `evidence/auth_verification.json`.

# Ruta recomendada: servicio gestionado Render

Lee **EMPEZAR_AQUI.md** para la instalación 24.3 sin VPS ni dominio propio. Las instrucciones siguientes conservan la alternativa Docker Compose para un VPS. El panel nuevo ya incluye controles HOT/COLD, política por ventanas, investigación manual y hallazgos. Las limitaciones antiguas sobre ausencia de esos controles quedan sustituidas por EMPEZAR_AQUI.md; chat libre y administración completa de plugins todavía permanecen en el original.

# HARPOON Cloud 24/7 — paquete de instalación PAPER

**Estado: paquete preparado y pruebas locales aprobadas; NO desplegado en un VPS.** No se enviaron órdenes ni consultas pagadas. No hay evidencia nueva de rentabilidad. Un proceso encendido no implica señales ni fills.

Este paquete ejecuta el motor en Node 24 con SQLite durable, independiente del navegador. Codex Cloud conserva su función de desarrollo y revisión; el runtime requiere un servidor permanente propio. No se ha contratado infraestructura ni creado una cuenta cloud.

## Instalar

1. Prepara un VPS Linux con Docker Engine, plugin Compose y Python 3. Como punto de partida operativo para dos motores y laboratorio: 4 vCPU, 8 GB RAM y disco SSD persistente; mide consumo real antes de ampliar. Apunta un dominio al VPS. Permite 80/443 y restringe SSH. Mantén sincronizado el reloj del servidor.
2. Extrae este ZIP en un directorio privado del VPS. Copia allí tus JSON exportados de runtime. `config/examples` contiene configuraciones de referencia **no optimizadas** para ensayar en PAPER.
3. Detén cualquier otra instancia que opere las cuentas elegidas. Esta primera migración exige cuentas PAPER dedicadas sin posiciones ni órdenes: no importa el diario del navegador ni liquida posiciones. No borres un diario para eludir esta condición.
4. Ejecuta `sudo bash install.sh`. El asistente pide dominio, contraseña del panel, JSON de cada libro y claves PAPER mediante entrada oculta. Comprueba cuenta y ausencia de inventario mediante consultas GET. Ambos motores requieren cuentas Alpaca diferentes; si sólo tienes una, elige uno.
5. Abre `https://TU_DOMINIO` con usuario `trader` y tu contraseña. El panel muestra ON/OFF, conciliación, antigüedad del pulso, posiciones, órdenes y supervisión. PAPER arranca automáticamente sujeto a las validaciones nativas. Pausar entradas conserva salidas; reanudar usa las barreras del core.
6. Verifica `sudo docker compose -f compose.json ps` y los registros. Prueba un reinicio del host en PAPER y comprueba conciliación con Alpaca antes de considerar la instalación aceptada. Aún no se ha realizado esa prueba aquí.

Docker para Ubuntu: https://docs.docker.com/engine/install/ubuntu/

## Qué se conserva y qué está adaptado

| Componente | Alcance de esta entrega |
|---|---|
| Fuentes del core y plugins | Copia byte a byte de `harpoon-src/src` de la aplicación actual; evidencia de hashes incluida. |
| Acciones, ETF y rutas de opciones existentes | AstraEngine actual sobre adaptador remoto. Las opciones dependen de permisos, configuración y reglas existentes; no se fuerza una entrada. |
| Cripto | XXCryptoDesk actual, activo continuamente; BTC/USD y ETH/USD canónicos. No se convierte una estrategia diaria en scalping. |
| Calendario | El core conserva calendario/reloj Alpaca para instrumentos con sesión. |
| Journal | SQLite WAL, transacciones y lease. Una réplica por cuenta. Verificación de lease antes de mutaciones. |
| Salidas y compuesto | Reglas nativas conservadas, sin aumentar riesgo ni modificar TP por instalar el cloud. |
| Investigación | LabController remoto existente para securities y supervisor por ventanas para ambos libros. La investigación cripto ampliada continúa en el sandbox original. |
| UI completa, chat 24.2 y loop visual XXIII | Se conservan en `HARPOON_original_24_2_0.zip`. No se han convertido todas estas pantallas en controles remotos. El nuevo panel controla exclusivamente los ejecutores cloud. |
| LIVE | No habilitado por este instalador. Cambiar un campo a live provoca rechazo. Las fuentes originales se conservan. |

La aplicación HTML anterior NO observa automáticamente la base SQLite del VPS. No conectes su modo operativo a las mismas cuentas. Este paquete no presenta un panel reducido como si fuera una migración completa de toda la UX.

## GPT y control de costes

El asistente puede instalar el gateway original en un servicio independiente con base persistente. Pide modelo disponible en tu cuenta, tarifas y techos reales; no presupone precios. La clave OpenAI sólo se guarda en el gateway. El ejecutor recibe el token del gateway.

El JSON de arranque puede contener `supervision` según `config/examples/supervision.json`. Por defecto está desactivada; para ventanas de cinco minutos usa `enabled:true`, `mode:"periodic"`, `interval_seconds:300` ANTES de la primera instalación. Una revisión admitida no es autorización de órdenes ni cambio libre de estrategia. La caída de GPT no detiene salidas. No se ha probado inferencia real aquí. El panel muestra estado, pero no incorpora chat ni un nuevo control LiftOn/LiftOff. El chat original permanece en el archivo completo.

La configuración inicial se fija en el diario. No cambies silenciosamente archivos con campañas abiertas. Para modificar estrategias o políticas persistidas hace falta una migración controlada; este instalador no resuelve todavía esa administración remota completa.

## Continuidad, seguridad y recuperación

- `unless-stopped` recupera procesos después de fallos/reinicio de Docker. Una detención manual permanece detenida. No usar réplicas múltiples, rolling updates ni bases separadas para una misma cuenta.
- Watchdog supervisa que el proceso responda, con margen de arranque. No reinicia porque falten señales o el motor esté pausado. El pulso de mercado se muestra por separado. No equivale a un SLA ni a una alerta externa: configura monitoreo externo del VPS.
- Claves fuera de imagen y repo, permisos restringidos. Volúmenes contienen historial financiero; permisos no equivalen a cifrado en disco. Mantén el VPS y sus backups privados.
- Backups SQLite consistentes cada seis horas en `backups/`, con comprobación de integridad. Son locales al VPS: configura copia cifrada fuera del servidor. No hay retención automática; vigila disco.
- Para backup manual: `sudo docker compose -f compose.json exec backups python /app/backup.py`.
- Restauración: detener el motor, archivar su directorio completo, restaurar un backup verificado como `data/BOOK/runtime.sqlite` con UID/GID 1000, retirar WAL/SHM del directorio restaurado y reiniciar. **Un backup atrasado puede carecer de fills/intentos: conciliar contra Alpaca antes de reanudar; nunca reenviar por intuición una orden ambigua.** Para el gateway conservar reservas de presupuesto; no restaurarlo para reiniciar gasto.
- `sudo bash stop.sh` detiene procesos, no cierra posiciones. Salidas gestionadas por software dejan de ejecutarse durante la parada; stops ya aceptados permanecen sujetos a condiciones del broker.
- El lease evita duplicados sobre la misma base, no bloquea otros equipos o aplicaciones que usen la cuenta.

## Evidencia y pendientes

`node tools/runtime_test.cjs`: 7 pruebas del adaptador/core, incluidas persistencia, lease y orden ambigua sin duplicación.
`node tools/cloud_test.cjs`: 7 pruebas de arranque/panel/pausa persistente con motor inyectado y carga del motor cripto actual.
`python3 tools/install_test.py`: comprobaciones de configuración de instalación.
Las pruebas no consumen Alpaca/OpenAI. No se construyó la imagen: el entorno de trabajo no dispone de Docker. Pendientes: build real, DNS/TLS, arranque/reinicio en VPS, feeds y permisos, estrategia con datos reales, fills PAPER y costes reales de GPT. No se certifica rentabilidad, operación LIVE ni migración completa del chat/loop visual.

Referencias técnicas: https://docs.docker.com/engine/containers/start-containers-automatically/ · https://caddyserver.com/docs/command-line#caddy-hash-password
