# Solicitudes Almacén Xylem (Flask + Google Sheets)

## 1) Columnas en Google Sheets (fila 1)
FECHA | HORA | CODIGO | NOMBRE | AREA | CARGO | TIPO | DESCRIPCION | CANTIDAD | URGENCIA | OBSERVACION | ESTADO | REGISTRADO

> La pestaña por defecto se llama **Hoja 1**. Si tu pestaña tiene otro nombre, configúralo en Render como `WORKSHEET_NAME`.

## 2) Render (variables de entorno)
En Render → Service → Environment, agrega:

- `SECRET_KEY` = una clave (ej: solicitudes_almacen_2026)
- `SPREADSHEET_ID` = SOLO el ID del Sheet (entre /d/ y /edit)
- `GOOGLE_SERVICE_ACCOUNT_JSON` = pega TODO el JSON de la cuenta de servicio
- (opcional) `WORKSHEET_NAME` = Hoja 1
- (opcional) `ALLOWED_USERS` = edwin,edgar,otro

## 3) Compartir el Sheet con la Service Account
Abre el JSON y copia el **client_email** (ej: algo@algo.iam.gserviceaccount.com)

Google Sheets → **Compartir** → pega ese email → rol **Editor** → **Compartir**.

## 4) Deploy en Render
- Build Command: `pip install -r requirements.txt`
- Start Command: (Render lo toma de Procfile) `gunicorn app:app`

## 5) Probar conexión
Abre:
`https://TU-APP.onrender.com/health`

Si sale ok:true, ya está listo.
