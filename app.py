import csv
import requests
from flask import Flask, render_template, request, redirect, url_for

app = Flask(__name__)

# ===============================
# CONFIGURACIÓN
# ===============================

# 🔹 URL CSV del Catálogo (Google Sheets)
# Archivo → Compartir → Cualquiera con enlace → Ver
# URL final:
# https://docs.google.com/spreadsheets/d/ID/export?format=csv&gid=GID=1981111920
CATALOGO_URL = "PEGA_AQUI_TU_URL_CSV"

# 🔹 URL REAL del Google Form (formResponse)
# NO viewform
# NO prefill
FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLSexsRoNGpgaHT3bO0H25-m73b_rH5U6SgZz-d4SuOLQEzy8TQ/formResponse"

# ===============================
# FUNCIONES
# ===============================

def leer_catalogo():
    r = requests.get(CATALOGO_URL)
    r.encoding = "utf-8"
    filas = csv.DictReader(r.text.splitlines())
    return filas

def guardar_solicitud(data):
    payload = {
        "entry.858502707": data["usuario"],
        "entry.378566943": data["codigo"],
        "entry.1302630630": data["descripcion"],
        "entry.1355846591": data["cantidad"],
    }

    r = requests.post(FORM_URL, data=payload)
    return r.status_code in (200, 302)

# ===============================
# RUTAS
# ===============================

@app.route("/")
def inicio():
    return render_template("inicio.html")

@app.route("/solicitar")
def solicitar():
    return render_template("solicitar.html")

@app.route("/enviar", methods=["POST"])
def enviar():
    data = {
        "usuario": request.form.get("usuario"),
        "codigo": request.form.get("codigo"),
        "descripcion": request.form.get("descripcion"),
        "cantidad": request.form.get("cantidad"),
    }

    guardar_solicitud(data)

    return redirect(url_for("inicio"))

# ===============================
# MAIN
# ===============================
if __name__ == "__main__":
    app.run(debug=True)