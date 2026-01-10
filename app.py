import os
import json
from datetime import datetime

from flask import Flask, render_template, request, redirect, url_for, jsonify

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

app = Flask(__name__)

# =========================================================
# CONFIG
# =========================================================

# Tu Spreadsheet ID (lo que está entre /d/ y /edit)
SPREADSHEET_ID = os.getenv(
    "SPREADSHEET_ID",
    "1asHBISZ2xwhcJ7sRocVqZ-7oLoj7iscF9Rc-xXJWpys"
)

SHEET_SOLICITUDES = os.getenv("SHEET_SOLICITUDES", "Solicitudes")
SHEET_CATALOGO = os.getenv("SHEET_CATALOGO", "Catalogo")

# Scopes para escribir en Sheets
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# Opción A: JSON como ENV VAR (RECOMENDADO en Render)
# En Render crea una variable:
# GOOGLE_SERVICE_ACCOUNT_JSON = { ...todo el json... }
SERVICE_ACCOUNT_JSON_ENV = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()

# Opción B: archivo local (si lo usas localmente o con Secret File)
SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json")


# =========================================================
# GOOGLE SHEETS SERVICE
# =========================================================

def _load_credentials():
    """
    Carga credenciales desde:
    - ENV: GOOGLE_SERVICE_ACCOUNT_JSON (recomendado en Render)
    - Archivo: service_account.json
    """
    if SERVICE_ACCOUNT_JSON_ENV:
        info = json.loads(SERVICE_ACCOUNT_JSON_ENV)
        return Credentials.from_service_account_info(info, scopes=SCOPES)

    if os.path.exists(SERVICE_ACCOUNT_FILE):
        return Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)

    raise RuntimeError(
        "No hay credenciales. Sube un service_account.json (local) "
        "o configura GOOGLE_SERVICE_ACCOUNT_JSON (Render)."
    )


def get_sheets_service():
    creds = _load_credentials()
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


# =========================================================
# DATA HELPERS
# =========================================================

def append_solicitud(usuario: str, codigo: str, descripcion: str, cantidad: str):
    """
    Inserta una fila en la hoja Solicitudes con tu estructura:

    A FECHA
    B HORA
    C CODIGO
    D NOMBRE
    E AREA
    F CARGO
    G TIPO
    H DESCRIPCION
    I CANTIDAD
    J URGENCIA
    K OBSERVACIONES
    L ESTADO
    M REGISTRADO
    """
    now = datetime.now()
    fecha = now.strftime("%d/%m/%Y")
    hora = now.strftime("%H:%M:%S")

    # Como tu HTML solo manda 4 campos, lo demás lo ponemos por defecto:
    nombre = usuario
    area = ""
    cargo = ""
    tipo = ""            # luego lo sacamos del catálogo
    urgencia = ""
    observaciones = ""
    estado = "PENDIENTE"
    registrado = usuario

    values = [[
        fecha, hora, codigo, nombre, area, cargo, tipo,
        descripcion, cantidad, urgencia, observaciones, estado, registrado
    ]]

    service = get_sheets_service()
    body = {"values": values}

    # Append al final
    service.spreadsheets().values().append(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_SOLICITUDES}!A:M",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body=body
    ).execute()


def read_catalogo(limit: int = 5000):
    """
    Lee catálogo desde hoja Catalogo.
    Espera columnas:
    A CODIGO
    B TIPO
    C DESCRIPCION
    (Opcional) D ACTIVO (SI/NO)
    """
    service = get_sheets_service()
    resp = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_CATALOGO}!A:D"
    ).execute()

    rows = resp.get("values", [])
    if not rows:
        return []

    # Si la primera fila es encabezado, la saltamos si coincide
    header = [c.strip().upper() for c in rows[0]]
    has_header = ("CODIGO" in header) or ("DESCRIPCION" in header)

    data_rows = rows[1:] if has_header else rows

    items = []
    for r in data_rows[:limit]:
        codigo = r[0].strip() if len(r) > 0 else ""
        tipo = r[1].strip() if len(r) > 1 else ""
        desc = r[2].strip() if len(r) > 2 else ""
        activo = r[3].strip().upper() if len(r) > 3 else "SI"

        if not codigo and not desc:
            continue
        if activo not in ("SI", "S", "YES", "Y", "1", ""):
            continue

        items.append({"codigo": codigo, "tipo": tipo, "descripcion": desc})

    return items


# =========================================================
# ROUTES
# =========================================================

@app.route("/")
def inicio():
    return render_template("inicio.html")


@app.route("/solicitar", methods=["GET"])
def solicitar():
    # Si más adelante quieres llenar selects, puedes pasar el catálogo al template:
    # catalogo = read_catalogo()
    # return render_template("solicitar.html", catalogo=catalogo)
    return render_template("solicitar.html")


@app.route("/api/catalogo")
def api_catalogo():
    try:
        return jsonify({"ok": True, "items": read_catalogo()})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/enviar", methods=["POST"])
def enviar():
    # OJO: estos names deben coincidir con tu HTML
    usuario = (request.form.get("usuario") or "").strip()
    codigo = (request.form.get("codigo") or "").strip()
    descripcion = (request.form.get("descripcion") or "").strip()
    cantidad = (request.form.get("cantidad") or "").strip()

    if not all([usuario, codigo, descripcion, cantidad]):
        return "Faltan datos", 400

    try:
        append_solicitud(usuario, codigo, descripcion, cantidad)
    except Exception as e:
        # Esto te mostrará el error real si credenciales/spreadsheet fallan
        return f"Error guardando en Sheets: {e}", 500

    return redirect(url_for("inicio"))


# =========================================================
# LOCAL
# =========================================================
if __name__ == "__main__":
    app.run(debug=True)