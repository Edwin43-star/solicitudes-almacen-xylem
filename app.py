from flask import Flask, render_template, request, redirect, url_for, jsonify
from datetime import datetime
import gspread
import json
import os
from google.oauth2.service_account import Credentials

app = Flask(__name__)

# ===============================
# GOOGLE SHEETS CONFIG
# ===============================
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

SPREADSHEET_ID = "1asHBISZ2xwhcJ7sRocVqZ-7oLoj7iscF9Rc-xXJWpys"

service_account_info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT"])

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
# API CATÁLOGO (FILTRADO + STOCK)
# ===============================
@app.route("/api/catalogo")
def api_catalogo():
    tipo = request.args.get("tipo")
    rows = ws_catalogo.get_all_records()

    data = []
    for r in rows:
        if r["ACTIVO"] != "SI":
            continue
        if tipo and r["TIPO"].upper() != tipo.upper():
            continue

        data.append({
            "codigo": r["CODIGO"],
            "descripcion": r["DESCRIPCION"],
            "stock": int(r["STOCK"]),
            "tipo": r["TIPO"]
        })

    return jsonify(data)

# ===============================
# ENVIAR SOLICITUD (VALIDA STOCK)
# ===============================
@app.route("/enviar", methods=["POST"])
def enviar():
    usuario = request.form["usuario"]
    codigo = request.form["codigo"]
    descripcion = request.form["descripcion"]
    tipo = request.form["tipo"]
    cantidad = int(request.form["cantidad"])

    # Buscar stock actual
    catalogo = ws_catalogo.get_all_records()
    item = next((x for x in catalogo if x["CODIGO"] == codigo), None)

    if not item:
        return "Producto no existe", 400

    if cantidad > int(item["STOCK"]):
        return "Stock insuficiente", 400

    now = datetime.now()

    ws_solicitudes.append_row([
        now.strftime("%d/%m/%Y"),
        now.strftime("%H:%M:%S"),
        codigo,
        usuario,
        tipo,
        descripcion,
        cantidad,
        "PENDIENTE",
        usuario
    ])

    return redirect(url_for("inicio"))

# ===============================
# MAIN
# ===============================
if __name__ == "__main__":
    app.run(debug=True)