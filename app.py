from flask import Flask, render_template, request, redirect, session, jsonify
import gspread
from google.oauth2.service_account import Credentials
import os
import json

app = Flask(__name__)
app.secret_key = "xylem_secret_key_2025"

# ==============================
# GOOGLE SHEETS CONFIG
# ==============================
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

service_account_info = json.loads(os.environ["GOOGLE_CREDENTIALS"])
creds = Credentials.from_service_account_info(service_account_info, scopes=SCOPES)
client = gspread.authorize(creds)

SPREADSHEET = client.open("Solicitudes_Almacen_App")
SHEET_INVENTARIO = SPREADSHEET.worksheet("INVENTARIO")
SHEET_SOLICITUDES = SPREADSHEET.worksheet("SOLICITUDES")

# ==============================
# LOGIN
# ==============================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":

        # -------- PERSONAL --------
        if "personal_nombre" in request.form:
            nombre = request.form["personal_nombre"].strip()
            if not nombre:
                return redirect("/login")

            session.clear()
            session["rol"] = "personal"
            session["nombre"] = nombre
            session["carrito"] = []

            return redirect("/solicitar")

        # -------- ALMACENERO --------
        if "usuario" in request.form:
            usuario = request.form["usuario"]
            password = request.form["password"]

            if usuario == "admin" and password == "1234":
                session.clear()
                session["rol"] = "almacenero"
                session["nombre"] = usuario
                return redirect("/bandeja")

            return redirect("/login")

    return render_template("login.html")


# ==============================
# INICIO (PROTEGIDO)
# ==============================
@app.route("/")
@app.route("/inicio")
def inicio():
    if not session.get("rol"):
        session.clear()
        return redirect("/login")

    return render_template("inicio.html")


# ==============================
# SOLICITAR (SOLO PERSONAL)
# ==============================
@app.route("/solicitar", methods=["GET", "POST"])
def solicitar():
    if session.get("rol") != "personal":
        session.clear()
        return redirect("/login")

    inventario = SHEET_INVENTARIO.get_all_records()

    if "carrito" not in session:
        session["carrito"] = []

    if request.method == "POST":
        codigo = request.form.get("codigo")
        descripcion = request.form.get("descripcion")
        cantidad = int(request.form.get("cantidad", 1))

        session["carrito"].append({
            "codigo": codigo,
            "descripcion": descripcion,
            "cantidad": cantidad
        })
        session.modified = True

    return render_template("solicitar.html", inventario=inventario)


# ==============================
# ELIMINAR ITEM DEL CARRITO
# ==============================
@app.route("/eliminar_item/<int:index>")
def eliminar_item(index):
    if session.get("rol") != "personal":
        session.clear()
        return redirect("/login")

    try:
        session["carrito"].pop(index)
        session.modified = True
    except:
        pass

    return redirect("/solicitar")


# ==============================
# ENVIAR SOLICITUD
# ==============================
@app.route("/enviar_solicitud", methods=["POST"])
def enviar_solicitud():
    if session.get("rol") != "personal":
        session.clear()
        return redirect("/login")

    nombre = session.get("nombre")
    carrito = session.get("carrito", [])

    for item in carrito:
        SHEET_SOLICITUDES.append_row([
            nombre,
            item["codigo"],
            item["descripcion"],
            item["cantidad"],
      "PENDIENTE"
        ])

    session["carrito"] = []
    session.modified = True

    return redirect("/inicio")


# ==============================
# BANDEJA (ALMACENERO)
# ==============================
@app.route("/bandeja")
def bandeja():
    if session.get("rol") != "almacenero":
        session.clear()
        return redirect("/login")

    solicitudes = SHEET_SOLICITUDES.get_all_records()
    return render_template("bandeja.html", solicitudes=solicitudes)


# ==============================
# LOGOUT
# ==============================
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# ==============================
# RUN
# ==============================
if __name__ == "__main__":
    app.run(debug=True)