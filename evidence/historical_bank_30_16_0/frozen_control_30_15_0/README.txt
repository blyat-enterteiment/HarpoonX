CONTROL CONGELADO PORTABLE PROCEDENTE DE 30.15.0

Objeto
  Reproducir exactamente el resultado ya registrado del ensayo
  HARPOON_PORTFOLIO_CAUSAL_RESERVATIONS_20261101_01.
  Este subdirectorio contiene 55 archivos originales, copiados sin editar:
  los 29 bindings del registro, el runtime30 completo, el verificador,
  los registros y las dependencias congeladas utilizadas por el loader.
  Los recibos de comprobación y este documento se añaden por separado.

Comando portable
  Desde la raíz de la integral 30.16.0:

  cd evidence/historical_bank_30_16_0/frozen_control_30_15_0
  node tools/verify_portfolio_validity_study.cjs

  El segundo comando puede ejecutarse directamente desde este subroot.
  Utiliza únicamente archivos relativos a él. No necesita la integral
  original, red, credenciales, node_modules ni el runtime30 exterior.
  Entorno utilizado para la comprobación: Node v24.22.1.

Integridad sin recalcular el resultado
  Desde este mismo subroot:

  node -e 'const r=require("./tools/portfolio_validity_study.cjs").requireRegistration("verify"); console.log(JSON.stringify({verified:true,trial_id:r.trial_id,bindings:Object.keys(r.bindings).length},null,2))'
  sha256sum -c SHA256SUMS.txt

  requireRegistration("verify") comprueba los bindings del registro y la
  cadena REGISTER/COMPLETE, incluida la huella del resultado persistido.
  El verificador completo también vuelve a calcular con la implementación
  congelada y exige igualdad exacta de los bytes JSON UTF-8 persistidos.
  No registrar ni ejecutar un intento nuevo con los modos register/run.

Contenido e identidad
  preservation_manifest.json enumera los originales copiados, sus tamaños
  y SHA-256. SHA256SUMS.txt cubre todos los archivos del subroot excepto el
  propio archivo de sumas, incluidos los recibos de verificación.
  verification/registration_integrity.json conserva la comprobación del
  registro. verification/result_reproduction.json conserva la reproducción
  exacta. Su salida estándar de error se conserva en el archivo contiguo.
  No se duplicó el ZIP de la integral ni las capturas ajenas al loader.
  Los 41.003.646 bytes de archivos originales incluyen prepared.json,
  requerido por su SHA-256 exacto; no se lo sustituyó por datos nuevos.

Frontera metodológica
  Es el control heredado, con su historial examinado, sus costes externos
  no establecidos y su ejecución histórica modelada. La reproducción no
  acredita rentabilidad real, un nivel 7 ni independencia prospectiva.
  El resultado, registro, journal y contador originales permanecen intactos.
  Esta comprobación incorpora cero variantes financieras nuevas.
  El banco histórico 30.16.0 y sus nuevos modelos se ejecutan fuera de este
  subroot; no quedan autorizados ni ejecutados por este verificador.
