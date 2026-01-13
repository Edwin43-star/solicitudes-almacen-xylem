from flask import Flask, render_template, request, redirect, session, url_for, jsonify
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
import os
import json

app = Flask(__name__)
app.secret_key = "xylem-secret-key"

# ===============================
# GOOGLE SHEETS
# ===============================
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

google_creds = os.environ.get("GOOGLE_CREDENTIALS")
if not google_creds:
    raise RuntimeError("❌ GOOGLE_CREDENTIALS no está configurada en Render")

creds_dict = json.loads(google_creds)

creds = Credentials.from_service_account_info(
    creds_dict, scopes=SCOPES
)

try:
    gc = gspread.authorize(creds)
    SHEET_NAME = "Solicitudes_Almacen_App"
    ws_solicitudes = gc.open(SHEET_NAME).worksheet("Solicitudes")
    ws_catalogo = gc.open(SHEET_NAME).worksheet("Catalogo")
except Exception as e:
    print("❌ Error Google Sheets:", e)
    ws_solicitudes = None
    ws_catalogo = None

# ==============================
# LOGIN
# ==============================
@app.route("/")
def root():
    return redirect("/login")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":

        # ---- PERSONAL ----
        if "nombre" in request.form:
            nombre = request.form["nombre"].strip()
            if nombre:
                session.clear()
                session["rol"] = "personal"
                session["usuario"] = nombre.upper()
                return redirect("/solicitar")

        # ---- ALMACENEROS ----
        if "usuario" in request.form and "password" in request.form:
            usuario = request.form["usuario"].strip().upper()
            password = request.form["password"].strip()

            almaceneros = {
                "EDWIN ROMERO": "6982",
                "EDGAR GARCIA": "1234"
            }

            if usuario in almaceneros and almaceneros[usuario] == password:
                session.clear()
                session["rol"] = "almacenero"
                session["usuario"] = usuario
                return redirect("/bandeja")

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# ==============================
# SOLICITAR
# ==============================
@app.route("/solicitar")
def solicitar():
    if "usuario" not in session or session["rol"] != "personal":
        return redirect("/login")
    return render_template("solicitar.html")

# ==============================
# CATÁLOGO DINÁMICO
# ==============================
@app.route("/catalogo")
def catalogo():
    rows = ws_catalogo.get_all_records()
    data = {"EPP": [], "CONSUMIBLE": []}

    for r in rows:
        data[r["TIPO"].upper()].append(r["DESCRIPCION"])

    return jsonify(data)

# ==============================
# GUARDAR SOLICITUD
# ==============================
@app.route("/guardar_solicitud", methods=["POST"])
def guardar_solicitud():
    if "usuario" not in session:
        return jsonify(ok=False), 401

    data = request.json
    usuario = session["usuario"]
    fecha = datetime.now().strftime("%d/%m/%Y %H:%M")

    for item in data["items"]:
        ws_solicitudes.append_row([
            fecha,
            usuario,
            item["tipo"],
            item["desc"],
            item["cant"],
            "PENDIENTE"
        ])

    return jsonify(ok=True)

# ==============================
# BANDEJA ALMACENERO
# ==============================
@app.route("/bandeja")
def bandeja():
    if "usuario" not in session or session["rol"] != "almacenero":
        return redirect("/login")

    rows = ws_solicitudes.get_all_records()
    return render_template("bandeja.html", solicitudes=rows)


if __name__ == "__main__":
    app.run(debug=True)