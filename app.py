from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import os
import json
import gspread
from google.oauth2.service_account import Credentials

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "xylem123")

SPREADSHEET_ID = os.environ["SPREADSHEET_ID"]
GOOGLE_CREDENTIALS = json.loads(os.environ["GOOGLE_CREDENTIALS"])

def get_gsheet():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    credentials = Credentials.from_service_account_info(
        GOOGLE_CREDENTIALS, scopes=scopes
    )
    client = gspread.authorize(credentials)
    return client.open_by_key(SPREADSHEET_ID)

# ===============================
# RUTAS PRINCIPALES
# ===============================

@app.route("/", methods=["GET"])
def root():
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":

        # --- PERSONAL ---
        codigo_personal = request.form.get("codigo_personal", "").strip()
        nombre_personal = request.form.get("nombre_personal", "").strip()

        # --- ALMACENERO ---
        almacenero = request.form.get("almacenero", "").strip()
        password = request.form.get("password", "").strip()

        # ========= VALIDACIÓN =========

        # Almacenero
        if almacenero:
            if almacenero == "EDWIN ROMERO" and password == "6982":
                session["rol"] = "ALMACEN"
                session["nombre"] = almacenero
                return redirect(url_for("inicio"))

            if almacenero == "EDGAR GARCIA" and password == "1234":
                session["rol"] = "ALMACEN"
                session["nombre"] = almacenero
                return redirect(url_for("inicio"))

            return render_template("login.html", error="Contraseña incorrecta")

        # Personal
        if codigo_personal or nombre_personal:
            session["rol"] = "PERSONAL"
            session["nombre"] = nombre_personal if nombre_personal else f"Código {codigo_personal}"
            return redirect(url_for("inicio"))

        return render_template("login.html", error="Complete los datos de ingreso")

    return render_template("login.html")

@app.route("/bandeja")
def bandeja():
    if "nombre" not in session or session.get("rol") != "ALMACEN":
        return redirect(url_for("login"))

    return render_template("bandeja.html")

@app.route("/inicio")
def inicio():
    if "nombre" not in session:
        return redirect(url_for("login"))

    # 🔑 ALMACENERO → BANDEJA
    if session.get("rol") == "ALMACEN":
        return redirect(url_for("bandeja"))

    # 👷 PERSONAL → INICIO NORMAL
    return render_template("inicio.html")


@app.route("/solicitar")
def solicitar():
    if "nombre" not in session:
        return redirect(url_for("login"))
    return render_template("solicitar.html")


@app.route("/guardar_solicitud", methods=["POST"])
def guardar_solicitud():
    if "nombre" not in session:
        return redirect(url_for("login"))

    items_json = request.form.get("items_json", "")
    if not items_json:
        flash("No hay ítems en la solicitud", "danger")
        return redirect(url_for("solicitar"))

    items = json.loads(items_json)
    flash("Solicitud enviada correctamente", "success")
    return redirect(url_for("solicitar"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/api/catalogo")
def api_catalogo():
    tipo = request.args.get("tipo", "").strip().upper()

    try:
        sh = get_gsheet()
        ws = sh.worksheet("Catalogo")
        filas = ws.get_all_records()

        print("TIPO SOLICITADO:", tipo)
        print("TOTAL FILAS:", len(filas))

        items = []

        for fila in filas:
            if fila["ACTIVO"] == "SI" and fila["TIPO"].upper() == tipo:
                items.append({
                    "descripcion": fila["DESCRIPCION"],
                    "stock": fila["STOCK"]
                })

        print("ITEMS DEVUELTOS:", len(items))
        return jsonify({"items": items})

    except Exception as e:
        print("ERROR /api/catalogo:", e)
        return jsonify({"items": [], "error": str(e)}), 2000