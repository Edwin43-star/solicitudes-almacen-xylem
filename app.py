import os
import json
from datetime import datetime

from flask import Flask, render_template, request, redirect, url_for, jsonify

import gspread
from google.oauth2.service_account import Credentials

# ===============================
# FLASK
# ===============================
app = Flask(__name__)

# ===============================
# GOOGLE SHEETS CONFIG
# ===============================
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# 🔐 CREDENCIALES DESDE VARIABLE DE ENTORNO (Render)
service_account_info = json.loads(
    os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
)

creds = Credentials.from_service_account_info(
    service_account_info,
    scopes=SCOPES
)

gc = gspread.authorize(creds)

# 📄 ID DEL SPREADSHEET
SPREADSHEET_ID = "1asHBISZ2xwhcJ7sRocVqZ-7oLoj7iscF9Rc-xXJWpys"

# 📄 Hojas
SHEET_SOLICITUDES = "Solicitudes"
SHEET_CATALOGO = "Catalogo"

# ===============================
# RUTAS HTML
# ===============================
@app.route("/")
def inicio():
    return render_template("inicio.html")

@app.route("/solicitar")
def solicitar():
    return render_template("solicitar.html")

# ===============================
# API CATALOGO (SELECT DINÁMICO)
# ===============================
@app.route("/api/catalogo")
def api_catalogo():
    sh = gc.open_by_key(SPREADSHEET_ID)
    ws = sh.worksheet(SHEET_CATALOGO)

    rows = ws.get_all_records()

    # Ajusta campos según tu hoja
    data = []
    for r in rows:
        data.append({
            "codigo": r.get("CODIGO"),
            "tipo": r.get("TIPO"),
            "descripcion": r.get("DESCRIPCION")
        })

    return jsonify(data)

# ===============================
# GUARDAR SOLICITUD
# ===============================
@app.route("/enviar", methods=["POST"])
def enviar():
    usuario = request.form.get("usuario")
    codigo = request.form.get("codigo")
    descripcion = request.form.get("descripcion")
    cantidad = request.form.get("cantidad")
    tipo = request.form.get("tipo", "")
    urgencia = request.form.get("urgencia", "")
    observaciones = request.form.get("observaciones", "")

    if not all([usuario, codigo, descripcion, cantidad]):
        return "Faltan datos", 400

    now = datetime.now()

    fila = [
        now.strftime("%d/%m/%Y"),  # FECHA
        now.strftime("%H:%M:%S"),  # HORA
        codigo,
        usuario,
        "",              # AREA (futuro)
        "",              # CARGO (futuro)
        tipo,
        descripcion,
        cantidad,
        urgencia,
        observaciones,
        "PENDIENTE",
        usuario
    ]

    sh = gc.open_by_key(SPREADSHEET_ID)
    ws = sh.worksheet(SHEET_SOLICITUDES)
    ws.append_row(fila)

    return redirect(url_for("inicio"))

# ===============================
# MAIN
# ===============================
if __name__ == "__main__":
    app.run(debug=True)