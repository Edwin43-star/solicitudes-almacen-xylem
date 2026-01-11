from flask import Flask, render_template, request, redirect, url_for, session
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import os
import json

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "xylem123")

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
creds_info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT"])
creds = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
gc = gspread.authorize(creds)

SPREADSHEET_ID = os.environ["SPREADSHEET_ID"]
sh = gc.open_by_key(SPREADSHEET_ID)

ws_usuarios = sh.worksheet("Usuarios")
ws_almaceneros = sh.worksheet("Almaceneros")
ws_catalogo = sh.worksheet("Catalogo")
ws_solicitudes = sh.worksheet("Solicitudes")

# ================= LOGIN =================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        tipo = request.form.get("tipo")

        if tipo == "personal":
            nombre = request.form.get("nombre").strip().upper()
            session["usuario"] = nombre
            session["rol"] = "personal"
            return redirect("/solicitar")

        if tipo == "almacenero":
            user = request.form.get("usuario").upper()
            clave = request.form.get("clave")

            rows = ws_almaceneros.get_all_records()
            for r in rows:
                if r["USUARIO"] == user and str(r["CLAVE"]) == clave and r["ACTIVO"] == "SI":
                    session["usuario"] = r["NOMBRE"]
                    session["rol"] = "almacenero"
                    return redirect("/bandeja")

    return render_template("login.html")

@app.route("/salir")
def salir():
    session.clear()
    return redirect("/login")

# ================= INICIO =================
@app.route("/")
def inicio():
    if "usuario" not in session:
        return redirect("/login")
    return render_template("inicio.html")

# ================= SOLICITAR =================
@app.route("/solicitar", methods=["GET", "POST"])
def solicitar():
    if session.get("rol") != "personal":
        return redirect("/login")

    catalogo = ws_catalogo.get_all_records()
    return render_template("solicitar.html", catalogo=catalogo)

@app.route("/enviar", methods=["POST"])
def enviar():
    items = request.form.getlist("item[]")
    cantidades = request.form.getlist("cantidad[]")

    fecha = datetime.now().strftime("%d/%m/%Y")
    hora = datetime.now().strftime("%H:%M:%S")

    catalogo = ws_catalogo.get_all_records()

    for i, codigo in enumerate(items):
        cant = int(cantidades[i])
        prod = next(p for p in catalogo if p["CODIGO"] == codigo)

        ws_solicitudes.append_row([
            fecha,
            hora,
            prod["CODIGO"],
            session["usuario"],
            prod["TIPO"],
            prod["DESCRIPCION"],
            cant,
            "PENDIENTE",
            "SISTEMA"
        ])

    return redirect("/")

# ================= BANDEJA =================
@app.route("/bandeja")
def bandeja():
    if session.get("rol") != "almacenero":
        return redirect("/login")

    data = ws_solicitudes.get_all_records()
    return render_template("bandeja.html", data=data)

if __name__ == "__main__":
    app.run(debug=True)