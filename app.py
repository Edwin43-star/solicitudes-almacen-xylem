from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import os
import json
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
from zoneinfo import ZoneInfo
import requests

# ===============================
# WHATSAPP NOTIFICACIÓN
# ===============================
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN")
WHATSAPP_PHONE_ID = os.environ.get("WHATSAPP_PHONE_ID")
WHATSAPP_TO = os.environ.get("WHATSAPP_TO")  # Tu número con código país, ej: 51987654321

def enviar_whatsapp(solicitante, tipo, descripcion, cantidad):
    if not WHATSAPP_TOKEN or not WHATSAPP_PHONE_ID or not WHATSAPP_TO:
        print("⚠️ WhatsApp no configurado")
        return

    url = f"https://graph.facebook.com/v18.0/{WHATSAPP_PHONE_ID}/messages"

    mensaje = (
        f"📦 *Nueva solicitud de almacén*\n\n"
        f"👤 Solicitante: {solicitante}\n"
        f"📂 Tipo: {tipo}\n"
        f"📝 Ítem: {descripcion}\n"
        f"🔢 Cantidad: {cantidad}\n\n"
        f"⏱ Estado: PENDIENTE"
    )

    payload = {
        "messaging_product": "whatsapp",
        "to": WHATSAPP_TO,
        "type": "text",
        "text": {"body": mensaje}
    }

    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }

    try:
        r = requests.post(url, json=payload, headers=headers)
        print("WhatsApp enviado:", r.status_code, r.text)
    except Exception as e:
        print("Error WhatsApp:", e)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "xylem123")

SPREADSHEET_ID = os.environ["SPREADSHEET_ID"]
GOOGLE_CREDENTIALS = json.loads(os.environ["GOOGLE_CREDENTIALS"])


def get_gsheet():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    credentials = Credentials.from_service_account_info(GOOGLE_CREDENTIALS, scopes=scopes)
    client = gspread.authorize(credentials)
    return client.open_by_key(SPREADSHEET_ID)


def get_ws(nombre):
    sh = get_gsheet()
    return sh.worksheet(nombre)


def get_usuario(codigo):
    ws = get_ws("Usuarios")
    filas = ws.get_all_records()

    for fila in filas:
        if str(fila.get("CODIGO", "")).strip() == str(codigo).strip():
            # OJO: devolvemos claves "nombre" y "rol"
            return {
                "nombre": str(fila.get("NOMBRE COMPLETO", "")).strip(),
                "rol": str(fila.get("ROL", "")).strip(),
            }
    return None

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

        # Personal (con validación desde sheet Usuarios por CODIGO)
        if codigo_personal:
            usuario = get_usuario(codigo_personal)
            if usuario:
                session["rol"] = "PERSONAL"
                session["nombre"] = usuario["nombre"]
                return redirect(url_for("inicio"))
            return render_template("login.html", error="Código no registrado")

        # (si quieres permitir login por nombre sin código, lo dejamos como estaba)
        if nombre_personal:
            session["rol"] = "PERSONAL"
            session["nombre"] = nombre_personal
            return redirect(url_for("inicio"))

        return render_template("login.html", error="Complete los datos de ingreso")

    return render_template("login.html")


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

    items_json = request.form.get("items_json", "").strip()

    if not items_json:
        flash("No hay ítems en la solicitud", "danger")
        return redirect(url_for("solicitar"))

    try:
        items = json.loads(items_json)
        ws = get_ws("Solicitudes")

        # ✅ FECHA Y HORA REAL DE PERÚ
        fecha = datetime.now(ZoneInfo("America/Lima"))
        fecha_str = fecha.strftime("%d/%m/%Y %H:%M")

        solicitante = session.get("nombre")

        for item in items:
    ws.append_row([
        fecha_str,                   # A FECHA
        solicitante,                 # B SOLICITANTE
        item.get("tipo", ""),        # C TIPO
        item.get("descripcion", ""), # D DESCRIPCION
        item.get("cantidad", ""),    # E CANTIDAD
        "PENDIENTE",                 # F ESTADO
        "",                          # G ALMACENERO
    ])

    # 🔔 DISPARAR WHATSAPP (UNA VEZ POR ÍTEM)
    enviar_whatsapp(
        solicitante,
        item.get("tipo", ""),
        item.get("descripcion", ""),
        item.get("cantidad", "")
    )

        flash("✅ Solicitud registrada. El almacén la atenderá en breve.", "success")
        return redirect(url_for("solicitar"))

    except Exception as e:
        print("ERROR guardar_solicitud:", e)
        flash(f"Error al guardar solicitud: {e}", "danger")
        return redirect(url_for("solicitar"))

@app.route("/bandeja")
def bandeja():
    if "rol" not in session or session.get("rol") != "ALMACEN":
        return redirect(url_for("login"))

    ws = get_ws("Solicitudes")
    filas = ws.get_all_values()

    solicitudes = []

    # Esperado:
    # A FECHA, B SOLICITANTE, C TIPO, D DESCRIPCION, E CANTIDAD, F ESTADO, G ALMACENERO
    for i, fila in enumerate(filas[1:], start=2):  # fila real en Sheets
        # protege por si vienen filas cortas
        fecha = fila[0] if len(fila) > 0 else ""
        solicitante = fila[1] if len(fila) > 1 else ""
        tipo = fila[2] if len(fila) > 2 else ""
        descripcion = fila[3] if len(fila) > 3 else ""
        cantidad = fila[4] if len(fila) > 4 else ""
        estado = fila[5] if len(fila) > 5 else ""
        almacenero = fila[6] if len(fila) > 6 else ""

        solicitudes.append({
            "fila": i,
            "fecha": fecha,
            "solicitante": solicitante,
            "tipo": tipo,
            "descripcion": descripcion,
            "cantidad": cantidad,
            "estado": estado,
            "almacenero": almacenero,
        })

    return render_template("bandeja.html", solicitudes=solicitudes)


@app.route("/actualizar_estado", methods=["POST"])
def actualizar_estado():
    if "rol" not in session or session.get("rol") != "ALMACEN":
        return redirect(url_for("login"))

    fila = int(request.form.get("fila"))
    nuevo_estado = request.form.get("estado", "").strip().upper()
    almacenero = session.get("nombre")

    try:
        ws = get_ws("Solicitudes")

        # Col F = ESTADO (6), Col G = ALMACENERO (7)
        ws.update_cell(fila, 6, nuevo_estado)
        ws.update_cell(fila, 7, almacenero)

        flash(f"Solicitud {nuevo_estado}", "success")

    except Exception as e:
        flash(f"Error al actualizar: {e}", "danger")

    return redirect(url_for("bandeja"))


@app.route("/api/catalogo")
def api_catalogo():
    tipo = request.args.get("tipo", "").strip().upper()

    try:
        ws = get_ws("Catalogo")
        filas = ws.get_all_records()

        items = []
        for fila in filas:
            # claves esperadas: TIPO, DESCRIPCION, STOCK, ACTIVO
            activo = str(fila.get("ACTIVO", "")).strip().upper()
            tipo_fila = str(fila.get("TIPO", "")).strip().upper()

            if activo == "SI" and tipo_fila == tipo:
                items.append({
                    "descripcion": fila.get("DESCRIPCION", ""),
                    "stock": fila.get("STOCK", ""),
                })

        return jsonify({"items": items})

    except Exception as e:
        print("ERROR /api/catalogo:", e)
        # 500 para que en logs se note como error real
        return jsonify({"items": [], "error": str(e)}), 500


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))