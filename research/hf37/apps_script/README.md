# Puente de Drive para el piloto HF38

El puente acepta únicamente el primer lote de la cohorte congelada, AAPL SIP del
1 de mayo de 2026 entre 13:30 y 13:35 UTC. El archivo ZIP admite hasta 5 MiB.
Las operaciones firmadas son reservar, guardar y releer. No se cambia el uso
compartido de la carpeta ni del archivo.

## Configuración

1. Crea un proyecto en Apps Script y copia Code.gs. En Configuración del proyecto,
   muestra el manifiesto y copia appsscript.json. El manifiesto habilita el servicio
   avanzado Drive v3 y solicita el alcance Drive a la cuenta que publica el script.
   El código fija una carpeta y un lote. El alcance OAuth de Apps Script abarca
   el Drive de esa cuenta, así que para aislar el piloto conviene una cuenta dedicada.
2. En Propiedades del script guarda HF38_GOOGLE_DRIVE_FOLDER_ID y
   HF38_BRIDGE_SECRET. Genera un secreto aleatorio de al menos 32 bytes y
   consérvalo en un gestor seguro. HF38_PILOT_FILE_ID lo asigna el script.
3. Publica una aplicación web que se ejecute como la cuenta que despliega y que
   permita invocaciones sin sesión Google, si tu organización lo permite. El
   endpoint exige HMAC, ventana temporal y nonce antes de acceder a Drive.
4. En Render guarda HF38_APPS_SCRIPT_URL con la URL /exec, el mismo
   HF38_BRIDGE_SECRET y HF38_GOOGLE_DRIVE_FOLDER_ID. Reutiliza la conexión
   privada PostgreSQL y las credenciales de lectura de Alpaca. Despliega este
   commit en el servicio de investigación y activa HF38_DRIVE_PROBE=1.
5. Comprueba el log HF38_DRIVE_PROBE y exige
   DRIVE_AND_POSTGRES_READBACK_VERIFIED. Desactiva HF38_DRIVE_PROBE tras la
   prueba. La reserva y el archivo se reutilizan en los reintentos.

## Lectura de latencias

El recibo contiene el tiempo total, adquisición SIP y compresión, finalización
y relectura PostgreSQL, y tiempos de ida y vuelta por llamada al puente. El
script informa su propio tiempo por llamada. La diferencia con la ida y vuelta
incluye red, arranque y entrega de respuesta y no mide red por separado.

Para identificar el cuello de botella, divide la suma de ida y vuelta del
puente, el tiempo de captura y el tiempo de finalización PostgreSQL entre el
tiempo total. Conserva el residuo como tiempo local o de preparación sin
atribuir. Compara el primer intento con una relectura idempotente, que omite la
captura. Una ejecución aislada no permite estimar percentiles.
