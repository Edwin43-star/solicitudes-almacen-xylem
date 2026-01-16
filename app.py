import os, json
from datetime import datetime
from flask import Flask, render_template, request, redirect, session, flash
import gspread
from google.oauth2.service_account import Credentials

# =========================
# APP CONFIG
# =========================
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "xylem123")

SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID")
GOOGLE_CREDENTIALS = os.environ.get("GOOGLE_CREDENTIALS")

if not SPREADSHEET_ID:
    raise Exception("FALTA SPREADSHEET_ID en Render")

if not GOOGLE_CREDENTIALS:
    raise Exception("FALTA GOOGLE_CREDENTIALS en Render")

# =========================
# GOOGLE SHEETS
# =========================
creds_dict = json.loads(GOOGLE_CREDENTIALS)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
gc = gspread.authorize(creds)

sh = gc.open_by_key(SPREADSHEET_ID)
ws_usuarios = sh.worksheet("Usuarios")
ws_almaceneros = sh.worksheet("Almaceneros")
ws_catalogo = sh.worksheet("Catalogo")
ws_solicitudes = sh.worksheet("Solicitudes")

# =========================
# RUTAS
# =========================

@app.route("/")
def index():
    return redirect("/login")

# ---------- LOGIN ----------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = request.form["usuario"].strip().upper()
        clave = request.form.get("clave", "").strip()

        # ALMACENEROS
        for a in ws_almaceneros.get_all_records():
            if a["USUARIO"] == usuario and a["CLAVE"] == clave and a["ACTIVO"] == "SI":
                session["usuario"] = a["NOMBRE"]
                session["rol"] = "ALMACENERO"
                return redirect("/bandeja")

        # USUARIOS
        for u in ws_usuarios.get_all_records():
            if u["NOMBRE"].upper() == usuario and u["ACTIVO"] == "SI":
                session["usuario"] = u["NOMBRE"]
                session["rol"] = "USUARIO"
                return redirect("/solicitar")

        flash("Usuario o clave incorrectos")

    return render_template("login.html")

# ---------- SOLICITAR ----------
@app.route("/solicitar")
def solicitar():
    if "usuario" not in session:
        return redirect("/login")

    catalogo = ws_catalogo.get_all_records()
    return render_template("solicitar.html", catalogo=catalogo)

# ---------- GUARDAR ----------
@app.route("/guardar", methods=["POST"])
def guardar():
    if "usuario" not in session:
        return redirect("/login")

    ws_solicitudes.append_row([
        datetime.now().strftime("%d/%m/%Y %H:%M"),
        session["usuario"],
        request.form["tipo"],
        request.form["descripcion"],
        request.form["cantidad"],
        "PENDIENTE"
    ])

    flash("Solicitud enviada correctamente")
    return redirect("/solicitar")

# ---------- BANDEJA ----------
@app.route("/bandeja")
def bandeja():
    if session.get("rol") != "ALMACENERO":
        return redirect("/login")

    solicitudes = ws_solicitudes.get_all_records()
    return render_template("bandeja.html", solicitudes=solicitudes)

# ---------- LOGOUT ----------
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# =========================
# MAIN
# =========================
if __name__ == "__main__":
    app.run()