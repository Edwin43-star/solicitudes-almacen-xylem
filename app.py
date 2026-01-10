from flask import Flask, render_template, request, redirect, url_for, jsonify
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import os
import json

app = Flask(__name__)

# ===============================
# GOOGLE SHEETS CONFIG (PRO)
# ===============================
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# 🔐 Leer credencial desde ENV (Render)
service_account_info = json.loads(
    os.environ["GOOGLE_SERVICE_ACCOUNT"]
)

creds = Credentials.from_service_account_info(
    service_account_info,
    scopes=SCOPES
)

gc = gspread.authorize(creds)

SPREADSHEET_ID = os.environ["SPREADSHEET_ID"]
sh = gc.open_by_key(SPREADSHEET_ID)

ws_solicitudes = sh.worksheet("Solicitudes")
ws_catalogo = sh.worksheet("Catalogo")

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
# API CATÁLOGO (DINÁMICO)
# ===============================
@app.route("/api/catalogo")
def api_catalogo():
    tipo = request.args.get("tipo")

    filas = ws_catalogo.get_all_records()
    data = []

    for f in filas:
        if f.get("ACTIVO") != "SI":
            continue
        if tipo and f.get("TIPO") != tipo:
            continue

        data.append({
            "codigo": f.get("CODIGO"),
            "descripcion": f.get("DESCRIPCION"),
            "tipo": f.get("TIPO"),
            "stock": int(f.get("STOCK", 0)),
            "um": f.get("U.M")
        })

    return jsonify(data)

# ===============================
# REGISTRAR SOLICITUD
# ===============================
@app.route("/enviar", methods=["POST"])
def enviar():
    usuario = request.form.get("usuario")
    tipo = request.form.get("tipo")
    codigo = request.form.get("codigo")
    descripcion = request.form.get("descripcion")
    cantidad = int(request.form.get("cantidad", 0))

    if not all([usuario, tipo, codigo, descripcion, cantidad]):
        return "Faltan datos", 400

    catalogo = ws_catalogo.get_all_records()
    producto = next((p for p in catalogo if p["CODIGO"] == codigo), None)

    if not producto:
        return "Producto no existe", 400

    stock = int(producto["STOCK"])
    if cantidad > stock:
        return f"Stock insuficiente (Disponible: {stock})", 400

    ahora = datetime.now()

    ws_solicitudes.append_row([
        ahora.strftime("%d/%m/%Y"),
        ahora.strftime("%H:%M:%S"),
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