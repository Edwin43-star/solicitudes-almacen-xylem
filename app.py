import os
import json
import csv
import requests
from datetime import datetime

from flask import Flask, render_template, request, redirect, url_for

import gspread
from google.oauth2.service_account import Credentials


# =====================================================
# APP
# =====================================================
app = Flask(__name__)


# =====================================================
# CONFIGURACIÓN GOOGLE SHEETS (SERVICE ACCOUNT)
# =====================================================

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# Render / Producción → variable de entorno
service_account_info = json.loads(
    os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
)

credentials = Credentials.from_service_account_info(
    service_account_info,
    scopes=SCOPES
)

gc = gspread.authorize(credentials)


# =====================================================
# IDs DE TUS SHEETS  (AQUÍ SOLO PEGAS IDS)
# =====================================================

# Spreadsheet principal
SPREADSHEET_ID = "1asHBISZ2xwhcJ7sRocVqZ-7oLoj7iscF9Rc-xXJWpys"

# Hojas internas
HOJA_SOLICITUDES = "Solicitudes"
HOJA_CATALOGO = "Catalogo"


# =====================================================
# FUNCIONES
# =====================================================

def leer_catalogo():
    """
    Lee el catálogo desde la hoja 'Catalogo'
    """
    sh = gc.open_by_key(SPREADSHEET_ID)
    ws = sh.worksheet(HOJA_CATALOGO)

    data = ws.get_all_records()
    return data


def guardar_solicitud(data):
    """
    Guarda una nueva solicitud en la hoja 'Solicitudes'
    """
    sh = gc.open_by_key(SPREADSHEET_ID)
    ws = sh.worksheet(HOJA_SOLICITUDES)

    ahora = datetime.now()

    fila = [
        ahora.strftime("%d/%m/%Y"),   # FECHA
        ahora.strftime("%H:%M:%S"),   # HORA
        data.get("codigo"),
        data.get("usuario"),
        data.get("area"),
        data.get("cargo"),
        data.get("tipo"),
        data.get("descripcion"),
        data.get("cantidad"),
        data.get("urgencia"),
        data.get("observaciones"),
        "PENDIENTE",
        data.get("usuario")
    ]

    ws.append_row(fila, value_input_option="USER_ENTERED")


# =====================================================
# RUTAS
# =====================================================

@app.route("/")
def inicio():
    return render_template("inicio.html")


@app.route("/solicitar", methods=["GET", "POST"])
def solicitar():
    if request.method == "POST":
        data = {
            "usuario": request.form.get("usuario"),
            "codigo": request.form.get("codigo"),
            "descripcion": request.form.get("descripcion"),
            "cantidad": request.form.get("cantidad"),
            "tipo": request.form.get("tipo"),
            "urgencia": request.form.get("urgencia"),
            "observaciones": request.form.get("observaciones"),
            "area": request.form.get("area", "almacen"),
            "cargo": request.form.get("cargo", "almacenero"),
        }

        guardar_solicitud(data)
        return redirect(url_for("inicio"))

    catalogo = leer_catalogo()
    return render_template("solicitar.html", catalogo=catalogo)


# =====================================================
# MAIN
# =====================================================
if __name__ == "__main__":
    app.run(debug=True)