from flask import Flask, render_template, request, redirect, session, url_for, jsonify
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
import os, json

app = Flask(__name__)
app.secret_key = "xylem-secret-key"

# ============================
# GOOGLE SHEETS
# ============================
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds_dict = json.loads(os.environ.get("GOOGLE_CREDENTIALS"))
creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
gc = gspread.authorize(creds)

SHEET_NAME = "Solicitudes_Almacen_App"
ws_solicitudes = gc.open(SHEET_NAME).worksheet("Solicitudes")
ws_catalogo = gc.open(SHEET_NAME).worksheet("Catalogo")

# ==============================
# LOGIN
# ==============================
@app.route("/")
def root():
    return redirect("/login")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":

        # PERSONAL
        if "nombre" in request.form:
            session.clear()
            session["rol"] = "personal"
            session["usuario"] = request.form["nombre"].upper()
            return redirect("/solicitar")

        # ALMACENEROS
        if "usuario" in request.form and "password" in request.form:
            usuario = request.form["usuario"].upper()
            password = request.form["password"]

            if usuario in ["EDWIN ROMERO", "EDGAR GARCIA"] and password == "1234":
                session.clear()
                session["rol"] = "almacenero"
                session["usuario"] = usuario
                return redirect("/bandeja")

    return render_template("login.html")

@app.route("/", methods=["GET"])
def root():
    return redirect("/login")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        nombre = request.form["nombre"].upper()
        if nombre in USUARIOS:
            session["usuario"] = nombre
            session["rol"] = USUARIOS[nombre]
            return redirect("/bandeja" if USUARIOS[nombre] == "almacenero" else "/solicitar")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# ============================
# SOLICITAR
# ============================
@app.route("/solicitar")
def solicitar():
    if "usuario" not in session:
        return redirect("/login")
    return render_template("solicitar.html", usuario=session["usuario"])

# ============================
# API CATÁLOGO (CLAVE 🔑)
# ============================
@app.route("/api/catalogo")
def api_catalogo():
    data = ws_catalogo.get_all_records()
    return jsonify(data)

# ============================
# GUARDAR SOLICITUD
# ============================
@app.route("/enviar_solicitud", methods=["POST"])
def enviar_solicitud():
    data = request.json
    fecha = datetime.now().strftime("%d/%m/%Y %H:%M")

    for item in data["items"]:
        ws_solicitudes.append_row([
            fecha,
            session["usuario"],
            item["tipo"],
            item["descripcion"],
            item["cantidad"],
            "PENDIENTE"
        ])

    return jsonify({"ok": True})

# ============================
# BANDEJA ALMACENERO
# ============================
@app.route("/bandeja")
def bandeja():
    if session.get("rol") != "almacenero":
        return redirect("/solicitar")

    registros = ws_solicitudes.get_all_records()
    return render_template("bandeja.html", registros=registros, usuario=session["usuario"])