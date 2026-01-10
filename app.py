from flask import Flask, render_template, request, redirect, url_for, jsonify
from datetime import datetime

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

app = Flask(__name__)

# ======================================
# GOOGLE SHEETS CONFIG
# ======================================
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SPREADSHEET_ID = "1asHBISZ2xwhcJ7sRocVqZ-7oLoj7iscF9Rc-xXJWpys"

SHEET_SOLICITUDES = "Solicitudes!A:M"
SHEET_CATALOGO = "Catalogo!A2:C"

creds = Credentials.from_service_account_file(
    "service_account.json",
    scopes=SCOPES
)

service = build("sheets", "v4", credentials=creds)

# ======================================
# RUTAS VISTAS
# ======================================
@app.route("/")
def inicio():
    return render_template("inicio.html")

@app.route("/solicitar")
def solicitar():
    return render_template("solicitar.html")

# ======================================
# API CATALOGO
# ======================================
@app.route("/api/catalogo")
def api_catalogo():
    result = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=SHEET_CATALOGO
    ).execute()

    values = result.get("values", [])

    catalogo = []
    for row in values:
        if len(row) >= 3:
            catalogo.append({
                "codigo": row[0],
                "tipo": row[1],
                "descripcion": row[2]
            })

    return jsonify(catalogo)

# ======================================
# GUARDAR SOLICITUD
# ======================================
@app.route("/enviar", methods=["POST"])
def enviar():
    usuario = request.form.get("usuario")
    codigo = request.form.get("codigo")
    tipo = request.form.get("tipo")
    descripcion = request.form.get("descripcion")
    cantidad = request.form.get("cantidad")

    if not all([usuario, codigo, tipo, descripcion, cantidad]):
        return "Faltan datos", 400

    now = datetime.now()

    fila = [
        now.strftime("%d/%m/%Y"),   # FECHA
        now.strftime("%H:%M:%S"),   # HORA
        codigo,
        usuario,
        "almacen",                  # AREA (por ahora fijo)
        "almacenero",               # CARGO (por ahora fijo)
        tipo,
        descripcion,
        cantidad,
        "",                          # URGENCIA
        "",                          # OBSERVACIONES
        "PENDIENTE",
        usuario
    ]

    service.spreadsheets().values().append(
        spreadsheetId=SPREADSHEET_ID,
        range=SHEET_SOLICITUDES,
        valueInputOption="USER_ENTERED",
        body={"values": [fila]}
    ).execute()

    return redirect(url_for("inicio"))

# ======================================
# MAIN
# ======================================
if __name__ == "__main__":
    app.run(debug=True)