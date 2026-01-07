import os
import json
from datetime import datetime, timezone

from flask import Flask, render_template, request, redirect, url_for, session, flash

import gspread
from google.oauth2.service_account import Credentials


# ======================================================
#  CONFIG
# ======================================================
APP_NAME = "Solicitudes Almacén Xylem"

# Render/Flask secret key (set in Render as SECRET_KEY)
SECRET_KEY = os.getenv("SECRET_KEY", "dev_secret_change_me")

# Google service account JSON (set in Render as GOOGLE_SERVICE_ACCOUNT_JSON)
GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")

# Google Sheet ID ONLY (set in Render as SPREADSHEET_ID)
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "")

# Worksheet/tab name inside the spreadsheet (optional; default "Hoja 1")
WORKSHEET_NAME = os.getenv("WORKSHEET_NAME", "Hoja 1")

# Allowed users (comma-separated). Example: "edwin,edgar"
ALLOWED_USERS = [u.strip() for u in os.getenv("ALLOWED_USERS", "edwin").split(",") if u.strip()]


# ======================================================
#  APP
# ======================================================
app = Flask(__name__)
app.secret_key = SECRET_KEY


# ======================================================
#  GOOGLE SHEETS (lazy init)
# ======================================================
_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def _get_gspread_client():
    """
    Create a gspread client using service account JSON stored in env.
    IMPORTANT: We DON'T connect at import time to avoid crashing Render deploy.
    """
    if not GOOGLE_SERVICE_ACCOUNT_JSON:
        raise RuntimeError(
            "Falta la variable GOOGLE_SERVICE_ACCOUNT_JSON en Render. "
            "Pega TODO el JSON (service account) como valor."
        )

    try:
        info = json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            "GOOGLE_SERVICE_ACCOUNT_JSON no es un JSON válido. "
            "Asegúrate de pegarlo completo (incluyendo llaves {})."
        ) from e

    creds = Credentials.from_service_account_info(info, scopes=_SCOPES)
    return gspread.authorize(creds)


def get_worksheet():
    """
    Return the worksheet object. Raises user-friendly errors.
    """
    if not SPREADSHEET_ID:
        raise RuntimeError(
            "Falta la variable SPREADSHEET_ID en Render. "
            "Debe ser SOLO el ID (lo que va entre /d/ y /edit)."
        )

    client = _get_gspread_client()
    try:
        sh = client.open_by_key(SPREADSHEET_ID)
    except gspread.exceptions.SpreadsheetNotFound as e:
        # Most common: sheet not shared with service account email
        raise RuntimeError(
            "No se encontró el Spreadsheet (404). "
            "Causas comunes:\n"
            "1) El SPREADSHEET_ID está mal (usa SOLO el ID, no la URL)\n"
            "2) NO compartiste el Google Sheet con el email de la Service Account (client_email)\n\n"
            "Solución rápida:\n"
            "• Abre tu Sheet → Compartir → pega el client_email del JSON → rol Editor → Compartir.\n"
        ) from e

    try:
        ws = sh.worksheet(WORKSHEET_NAME)
    except gspread.exceptions.WorksheetNotFound as e:
        raise RuntimeError(
            f"No existe la pestaña (worksheet) '{WORKSHEET_NAME}'. "
            f"Cambia WORKSHEET_NAME en Render o renombra la pestaña en Google Sheets."
        ) from e

    return ws


def append_solicitud(data: dict):
    """
    Append a new request row into the sheet.
    Expected columns:
    FECHA, HORA, CODIGO, NOMBRE, AREA, CARGO, TIPO, DESCRIPCION, CANTIDAD, URGENCIA, OBSERVACION, ESTADO, REGISTRADO
    """
    ws = get_worksheet()

    now = datetime.now().astimezone()  # local tz in Render is UTC; still ok
    fecha = now.strftime("%d/%m/%Y")
    hora = now.strftime("%H:%M:%S")

    row = [
        fecha,
        hora,
        data.get("codigo", "").strip(),
        data.get("nombre", "").strip(),
        data.get("area", "").strip(),
        data.get("cargo", "").strip(),
        data.get("tipo", "").strip(),
        data.get("descripcion", "").strip(),
        data.get("cantidad", "").strip(),
        data.get("urgencia", "").strip(),
        data.get("observacion", "").strip(),
        "PENDIENTE",
        session.get("user", ""),
    ]

    ws.append_row(row, value_input_option="USER_ENTERED")


def fetch_solicitudes(limit=200):
    ws = get_worksheet()
    values = ws.get_all_values()
    if not values or len(values) < 2:
        return []

    headers = values[0]
    rows = values[1:]
    # Keep last N (most recent at bottom in sheets)
    rows = rows[-limit:]
    out = []
    for r in rows:
        item = {headers[i]: (r[i] if i < len(r) else "") for i in range(len(headers))}
        out.append(item)
    # reverse to show newest first
    out.reverse()
    return out


# ======================================================
#  AUTH HELPERS
# ======================================================
def require_login():
    if "user" not in session:
        return redirect(url_for("login"))
    return None


# ======================================================
#  ROUTES
# ======================================================
@app.route("/")
def home():
    if "user" not in session:
        return redirect(url_for("login"))
    return render_template("index.html", app_name=APP_NAME, user=session["user"])


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("usuario", "").strip().lower()
        if not username:
            flash("Ingrese usuario.", "error")
            return redirect(url_for("login"))

        if username not in [u.lower() for u in ALLOWED_USERS]:
            flash("Usuario no autorizado.", "error")
            return redirect(url_for("login"))

        session["user"] = username
        return redirect(url_for("home"))

    return render_template("login.html", app_name=APP_NAME)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/solicitar", methods=["GET", "POST"])
def solicitar():
    r = require_login()
    if r:
        return r

    if request.method == "POST":
        # Basic validation
        cantidad = request.form.get("cantidad", "").strip()
        try:
            if cantidad:
                float(cantidad.replace(",", "."))
        except ValueError:
            flash("Cantidad inválida. Use número (ej: 1 o 2.5).", "error")
            return redirect(url_for("solicitar"))

        data = {
            "codigo": request.form.get("codigo", ""),
            "nombre": request.form.get("nombre", ""),
            "area": request.form.get("area", ""),
            "cargo": request.form.get("cargo", ""),
            "tipo": request.form.get("tipo", ""),
            "descripcion": request.form.get("descripcion", ""),
            "cantidad": cantidad,
            "urgencia": request.form.get("urgencia", ""),
            "observacion": request.form.get("observacion", ""),
        }

        try:
            append_solicitud(data)
        except Exception as e:
            flash(str(e), "error")
            return redirect(url_for("solicitar"))

        flash("✅ Solicitud registrada correctamente.", "ok")
        return redirect(url_for("bandeja"))

    return render_template("form.html", app_name=APP_NAME, user=session["user"])


@app.route("/bandeja")
def bandeja():
    r = require_login()
    if r:
        return r

    try:
        items = fetch_solicitudes(limit=300)
    except Exception as e:
        flash(str(e), "error")
        items = []

    return render_template("bandeja.html", app_name=APP_NAME, user=session["user"], items=items)


@app.route("/health")
def health():
    """
    Healthcheck: verifies env + connection to the sheet.
    Use this to debug quickly.
    """
    try:
        ws = get_worksheet()
        return {
            "ok": True,
            "spreadsheet_id": SPREADSHEET_ID,
            "worksheet": WORKSHEET_NAME,
            "title": ws.title,
        }, 200
    except Exception as e:
        return {"ok": False, "error": str(e)}, 500


# ======================================================
#  LOCAL RUN
# ======================================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=True)
