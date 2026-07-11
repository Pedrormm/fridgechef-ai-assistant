# Automatización UiPath con REFramework

## Config.xlsx

Crear las claves:
- AutomationEnabled: True/False
- AutomationEngine: UiPath
- SendEmail: True/False
- EmailTo: email válido
- AppUrl: URL local o Cloud Run
- BlinkBatPath: C:\FridgeChef\scripts\hacer_foto_blink.bat
- DefaultDiet: vacío/vegana/vegetariana/sin lactosa
- DefaultAllergies: lista separada por coma

## Init

1. Leer Config.xlsx.
2. Validar booleanos.
3. Validar email si SendEmail=True.
4. Abrir navegador con AppUrl.

## Get Transaction Data

1. Preparar una única transacción: ejecutar análisis de nevera.
2. Si hay más perfiles de prueba, cada perfil será una transacción.

## Process

1. Ejecutar el .bat de Blink si se usa cámara.
2. Esperar a que exista blink_latest.jpg nuevo.
3. Subir la foto en la app web.
4. Rellenar formulario de dieta/intolerancias.
5. Pulsar Analizar.
6. Extraer resultado o guardar captura.
7. Enviar email si está habilitado.

## End Process

1. Cerrar navegador.
2. Guardar logs.
3. Notificar resultado.
