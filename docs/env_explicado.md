# Guía del fichero .env de FridgeChef AI

Este proyecto necesita un fichero `.env` en la raíz. Ya viene incluido en este ZIP. No tienes que crearlo desde cero.

## Lo mínimo para que funcione en Windows local

1. Copia tu JSON real a la raíz del proyecto con el nombre `credentials.json`.
2. Copia tu `blink_auth.json` a la raíz si quieres usar la cámara Blink.
3. Deja `.env` como viene en el ZIP.
4. Ejecuta:

```powershell
python scripts\verify_credentials.py
streamlit run streamlit_app\app.py
```

## Variables clave

- `GOOGLE_APPLICATION_CREDENTIALS=credentials.json`: indica dónde está la service account.
- `GOOGLE_CLOUD_PROJECT=`: puede estar vacío; el código lo lee desde `credentials.json`.
- `GOOGLE_CLOUD_LOCATION=us-central1`: región de Vertex AI/Gemini.
- `VERTEX_MODEL=gemini-2.5-flash`: modelo usado para visión y recetas.
- `ALLOW_CHAT_PERSISTENCE=false`: si está en true permite guardar sesiones en Firestore.
- `ALLOW_IMAGE_STORAGE=false`: si está en true permite guardar fotos en Cloud Storage.
- `BLINK_AUTH_FILE=blink_auth.json`: ruta de sesión Blink.
- `AUTOMATION_ENABLED=false`: activa/desactiva automatización.
- `AUTOMATION_ENGINE=python`: usa python o uipath.
- `AUTOMATION_SEND_EMAIL=false`: activa/desactiva envío de email.
