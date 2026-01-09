import csv
import requests
from flask import Flask, render_template, request, redirect, url_for

app = Flask(__name__)

# ===============================
# CONFIGURACIÓN
# ===============================

# 🔹 URL CSV del Catálogo (Google Sheets)
# Ejemplo:
# https://docs.google.com/spreadsheets/d/1asHBISZ2xwhcJ7sRocVqZ-7oLoj7iscF9Rc-xXJWpys/edit?gid=1981111920#gid=1981111920
CATALOGO_URL = "PEGA_AQUI_TU_URL_CSV"

# 🔹 URL Google Form para guardar solicitudes
# Ejemplo:
# https://https://docs.google.com/forms/d/e/1FAIpQLSexsRoNGpgaHT3bO0H25-m73b_rH5U6SgZz-d4SuOLQEzy8TQ/formResponse
FORM_URL = "PEGA_AQUI_TU_FORM_URL"

# ===============================
# FUNCIONES
# ===============================

def leer_catalogo():
    """
    Lee el catálogo desde Google Sheets (CSV)
    y devuelve solo los productos ACTIVOS
    """
    r = requests.get(CATALOGO_URL)
    r.encoding = "utf-8"
    filas = csv.DictReader(r.text.splitlines())
    return [f for f in filas if f.get("ACTIVO", "").upper() == "SI"]


import requests

def guardar_solicitud(data):
    payload = {
        "entry.858502707": data.get("usuario"),
        "entry.378566943": data.get("codigo"),
        "entry.1302630630": data.get("descripcion"),
        "entry.1355846591": data.get("cantidad"),
    }

    r = requests.post(FORM_URL, data=payload)
    return r.status_code == 200

# ===============================
# RUTAS
# ===============================

@app.route("/")
def inicio():
    return render_template("inicio.html")


@app.route("/solicitar", methods=["GET", "POST"])
def solicitar():
    catalogo = leer_catalogo()

    if request.method == "POST":
        solicitud = {
            "usuario": request.form["usuario"],
            "codigo": request.form["codigo"],
            "descripcion": request.form["descripcion"],
            "cantidad": request.form["cantidad"],
        }
        guardar_solicitud(solicitud)
        return redirect(url_for("inicio"))

    return render_template("solicitar.html", catalogo=catalogo)


# ===============================
# MAIN (solo para local)
# ===============================
if __name__ == "__main__":
    app.run(debug=True)

@app.route("/solicitar")
def solicitar():
    return render_template("solicitar.html")