import os
import json
from datetime import datetime
from flask import Flask, render_template, request, redirect, session, url_for, jsonify

import gspread
from google.oauth2.service_account import Credentials

# =========================
# APP
# =========================
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "super_secret_key_cambia_esto")

# =========================
# GOOGLE SHEETS
# =========================
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# 🔒 CREDENCIALES DESDE ENV
if "GOOGLE_CREDENTIALS" not in os.environ:
    raise Exception("Falta la variable GOOGLE_CREDENTIALS en Render")

creds_dict = json.loads(os.environ["GOOGLE_CREDENTIALS"])
creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
client = gspread.authorize(creds)

SPREADSHEET = client.open("Solicitudes_Almacen_App")
SH_SOL = SPREADSHEET.worksheet("Solicitudes")
SH_CAT = SPREADSHEET.worksheet("Catalogo")
SH_ALM = SPREADSHEET.worksheet("Almaceneros")

# =========================
# LOGIN
# =========================
@app.route("/", methods=["GET"])
def root():
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":

        # ---- PERSONAL ----
        if "nombre" in request.form:
            nombre = request.form.get("nombre", "").strip()
            if nombre:
                session.clear()
                session["usuario"] = nombre
                session["rol"] = "personal"
                session["items"] = []
                return redirect(url_for("solicitar"))

        # ---- ALMACENERO ----
        if "usuario" in request.form:
            user = request.form.get("usuario", "").strip()
            pwd = request.form.get("password", "").strip()

            for r in SH_ALM.get_all_records():
                if r["USUARIO"] == user and r["PASSWORD"] == pwd:
                    session.clear()
                    session["usuario"] = user
                    session["rol"] = "almacenero"
                    return redirect(url_for("bandeja"))

    return render_template("login.html")

# =========================
# SOLICITAR (PERSONAL)
# =========================
@app.route("/solicitar", methods=["GET", "POST"])
def solicitar():
    if session.get("rol") != "personal":
        return redirect(url_for("login"))

    if "items" not in session:
        session["items"] = []

    # ---- AGREGAR ITEM ----
    if request.method == "POST" and "agregar" in request.form:
        session["items"].append({
            "tipo": request.form.get("tipo"),
            "item": request.form.get("item"),
            "cantidad": request.form.get("cantidad")
        })
        session.modified = True

    # ---- ELIMINAR ITEM ----
    if request.method == "POST" and "eliminar" in request.form:
        idx = int(request.form.get("eliminar"))
        if 0 <= idx < len(session["items"]):
            session["items"].pop(idx)
            session.modified = True

    # ---- ENVIAR SOLICITUD ----
    if request.method == "POST" and "enviar" in request.form:
        fecha = datetime.now().strftime("%d/%m/%Y")
        hora = datetime.now().strftime("%H:%M:%S")

        for i in session["items"]:
            SH_SOL.append_row([
                fecha,
                hora,
                session["usuario"],
                i["tipo"],
                i["item"],
                i["cantidad"],
                "PENDIENTE"
            ])

        session["items"] = []
        return redirect(url_for("solicitar"))

    return render_template(
        "solicitar.html",
        usuario=session["usuario"],
        items=session["items"]
    )

# =========================
# BANDEJA (ALMACENERO)
# =========================
@app.route("/bandeja")
def bandeja():
    if session.get("rol") != "almacenero":
        return redirect(url_for("login"))

    solicitudes = SH_SOL.get_all_records()
    return render_template(
        "bandeja.html",
        usuario=session["usuario"],
        solicitudes=solicitudes
    )

# =========================
# CATALOGO (AJAX)
# =========================
@app.route("/catalogo/<tipo>")
def catalogo(tipo):
    if "usuario" not in session:
        return jsonify(items=[])

    items = []
    for r in SH_CAT.get_all_records():
        if r["TIPO"] == tipo:
            items.append(
                f'{r["CODIGO"]} - {r["DESCRIPCION"]} (Stock: {r["STOCK"]})'
            )
    return jsonify(items=items)

# =========================
# LOGOUT
# =========================
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# =========================
if __name__ == "__main__":
    app.run(debug=True)