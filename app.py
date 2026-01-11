from flask import Flask, render_template, request, redirect, session, jsonify
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
import os
import json

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "xylem-secret")

# ===============================
# GOOGLE SHEETS (ESTABLE)
# ===============================
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets"
]

service_account_info = json.loads(
    os.environ.get("GOOGLE_SERVICE_ACCOUNT")
)

creds = Credentials.from_service_account_info(
    service_account_info,
    scopes=SCOPES
)

client = gspread.authorize(creds)

SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID")
SPREADSHEET = client.open_by_key(SPREADSHEET_ID)

SHEET_SOLICITUDES = SPREADSHEET.worksheet("Solicitudes")
SHEET_USUARIOS = SPREADSHEET.worksheet("Usuarios")
SHEET_ALMACENEROS = SPREADSHEET.worksheet("Almaceneros")
SHEET_CATALOGO = SPREADSHEET.worksheet("Catalogo")

# ===============================
# LOGIN
# ===============================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":

        # PERSONAL
        if "personal_nombre" in request.form:
            nombre = request.form["personal_nombre"].strip()
            if not nombre:
                return redirect("/login")

            session.clear()
            session["rol"] = "personal"
            session["nombre"] = nombre
            session["carrito"] = []
            return redirect("/inicio")

        # ALMACENERO
        if "usuario" in request.form:
            usuario = request.form["usuario"].upper()
            clave = request.form["clave"]

            for a in SHEET_ALMACENEROS.get_all_records():
                if (
                    a["USUARIO"].upper() == usuario
                    and str(a["CLAVE"]) == clave
                    and a["ACTIVO"] == "SI"
                ):
                    session.clear()
                    session["rol"] = "almacenero"
                    session["usuario"] = usuario
                    return redirect("/bandeja")

            return redirect("/login")

    return render_template("login.html")

# ===============================
# INICIO
# ===============================
@app.route("/")
@app.route("/inicio")
def inicio():
    if "rol" not in session:
        return redirect("/login")
    return render_template("inicio.html")

# ===============================
# SOLICITAR
# ===============================
@app.route("/solicitar")
def solicitar():
    if session.get("rol") != "personal":
        return redirect("/login")
    return render_template("solicitar.html")

# ===============================
# API CATALOGO
# ===============================
@app.route("/api/catalogo/<tipo>")
def api_catalogo(tipo):
    data = []
    for i in SHEET_CATALOGO.get_all_records():
        if i["TIPO"].upper() == tipo.upper():
            data.append({
                "codigo": i["CODIGO"],
                "descripcion": i["DESCRIPCION"],
                "stock": i["STOCK"]
            })
    return jsonify(data)

# ===============================
# AGREGAR ITEM
# ===============================
@app.route("/agregar", methods=["POST"])
def agregar():
    session["carrito"].append({
        "codigo": request.form["codigo"],
        "descripcion": request.form["descripcion"],
        "cantidad": int(request.form["cantidad"])
    })
    return redirect("/solicitar")

# ===============================
# ELIMINAR ITEM
# ===============================
@app.route("/eliminar/<int:i>")
def eliminar(i):
    session["carrito"].pop(i)
    return redirect("/solicitar")

# ===============================
# ENVIAR
# ===============================
@app.route("/enviar", methods=["POST"])
def enviar():
    fecha = datetime.now().strftime("%d/%m/%Y")
    hora = datetime.now().strftime("%H:%M:%S")

    for item in session["carrito"]:
        SHEET_SOLICITUDES.append_row([
            fecha,
            hora,
            item["codigo"],
            session["nombre"],
            "SOLICITUD",
            item["descripcion"],
            item["cantidad"],
            "PENDIENTE",
            session["nombre"]
        ])

    session["carrito"] = []
    return redirect("/inicio")

# ===============================
# BANDEJA
# ===============================
@app.route("/bandeja")
def bandeja():
    if session.get("rol") != "almacenero":
        return redirect("/login")

    pendientes = [
        s for s in SHEET_SOLICITUDES.get_all_records()
        if s["ESTADO"] == "PENDIENTE"
    ]
    return render_template("bandeja.html", solicitudes=pendientes)

# ===============================
# SALIR
# ===============================
@app.route("/salir")
def salir():
    session.clear()
    return redirect("/login")