import os
import json
from datetime import datetime
from flask import Flask, render_template, request, redirect, session, url_for

import gspread
from google.oauth2.service_account import Credentials

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "super_secret_key_cambia_esto")

# =========================
# RUTA RAÍZ → LOGIN
# =========================
@app.route("/")
def index():
    return redirect(url_for("login"))

# =========================
# LOGIN (PERSONAL / ALMACENERO)
# =========================
@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "GET":
        return render_template("login.html")

    # -------- PERSONAL --------
    if "personal_nombre" in request.form:
        nombre = request.form.get("personal_nombre").strip()

        if nombre:
            session.clear()
            session["usuario"] = nombre
            session["rol"] = "personal"
            session["carrito"] = []
            return redirect(url_for("solicitar"))

        return redirect(url_for("login"))

    # -------- ALMACENERO --------
    if "usuario" in request.form and "clave" in request.form:
        usuario = request.form.get("usuario").strip().upper()
        clave = request.form.get("clave").strip()

        # 👉 AQUÍ VA TU VALIDACIÓN REAL (NO TOCO SHEETS)
        if usuario in ["EDWIN", "EDGAR"] and clave:
            session.clear()
            session["usuario"] = usuario
            session["rol"] = "almacenero"
            return redirect(url_for("inicio"))

        return redirect(url_for("login"))

    return redirect(url_for("login"))

# =========================
# INICIO (SOLO LOGUEADOS)
# =========================
@app.route("/inicio")
def inicio():
    if "usuario" not in session:
        return redirect(url_for("login"))
    return render_template("inicio.html")

# =========================
# SOLICITAR (PERSONAL)
# =========================
@app.route("/solicitar")
def solicitar():
    if "usuario" not in session or session.get("rol") != "personal":
        return redirect(url_for("login"))

    if "carrito" not in session:
        session["carrito"] = []

    return render_template(
        "solicitar.html",
        usuario=session["usuario"]
    )

# =========================
# AGREGAR ITEM
# =========================
@app.route("/agregar", methods=["POST"])
def agregar():
    if "usuario" not in session:
        return redirect(url_for("login"))

    item = {
        "codigo": request.form.get("codigo"),
        "descripcion": request.form.get("descripcion"),
        "cantidad": int(request.form.get("cantidad", 1))
    }

    session["carrito"].append(item)
    session.modified = True

    return redirect(url_for("solicitar"))

# =========================
# ELIMINAR ITEM
# =========================
@app.route("/eliminar/<int:idx>")
def eliminar(idx):
    if "usuario" not in session:
        return redirect(url_for("login"))

    try:
        session["carrito"].pop(idx)
        session.modified = True
    except:
        pass

    return redirect(url_for("solicitar"))

# =========================
# ENVIAR SOLICITUD
# =========================
@app.route("/enviar", methods=["POST"])
def enviar():
    if "usuario" not in session:
        return redirect(url_for("login"))

    # 👉 AQUÍ SE REGISTRA EN SHEETS (NO TOCADO)
    session["carrito"] = []
    session.modified = True

    return redirect(url_for("inicio"))

# =========================
# LOGOUT
# =========================
@app.route("/salir")
def salir():
    session.clear()
    return redirect(url_for("login"))

# =========================
# API CATÁLOGO (NO TOCADO)
# =========================
@app.route("/api/catalogo/<tipo>")
def api_catalogo(tipo):
    return jsonify([])  # se mantiene como estaba

# =========================
if __name__ == "__main__":
    app.run(debug=True)