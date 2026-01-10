from flask import Flask, render_template, request, redirect, url_for, jsonify
from datetime import datetime
import gspread
import json
import os
from google.oauth2.service_account import Credentials

# ===============================
# APP
# ===============================
app = Flask(__name__)

# ===============================
# GOOGLE SHEETS CONFIG
# ===============================
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

SPREADSHEET_ID = "1asHBISZ2xwhcJ7sRocVqZ-7oLoj7iscF9Rc-xXJWpys"

# ===============================
# AUTENTICACIÓN SEGURA (RENDER)
# ===============================
service_account_info = json.loads(
    os.environ.get("GOOGLE_SERVICE_ACCOUNT")
)

credentials = Credentials.from_service_account_info(
    service_account_info,
    scopes=SCOPES
)

gc = gspread.authorize(credentials)
sh = gc.open_by_key(SPREADSHEET_ID)

ws_solicitudes = sh.worksheet("Solicitudes")
ws_catalogo = sh.worksheet("Catalogo")

# ===============================
# RUTAS
# ===============================
@app.route("/")
def inicio():
    return render_template("inicio.html")

@app.route("/solicitar")
def solicitar():
    return render_template("solicitar.html")

# ===============================
# API CATÁLOGO
# ===============================
@app.route("/api/catalogo")
def api_catalogo():
    tipo = request.args.get("tipo")

    rows = ws_catalogo.get_all_records()

    if tipo:
        rows = [r for r in rows if r["TIPO"].upper() == tipo.upper()]

    return jsonify(rows)

# ===============================
# ENVIAR SOLICITUD
# ===============================
@app.route("/enviar", methods=["POST"])
def enviar():
    nombre = request.form["usuario"]
    codigo = request.form["codigo"]
    tipo = request.form["tipo"]
    descripcion = request.form["descripcion"]
    cantidad = request.form["cantidad"]

    now = datetime.now()

    ws_solicitudes.append_row([
        now.strftime("%d/%m/%Y"),
        now.strftime("%H:%M:%S"),
        codigo,
        nombre,
        tipo,
        descripcion,
        cantidad,
        "PENDIENTE",
        nombre
    ])

    return redirect(url_for("inicio"))

# ===============================
# MAIN
# ===============================
if __name__ == "__main__":
    app.run(debug=True)