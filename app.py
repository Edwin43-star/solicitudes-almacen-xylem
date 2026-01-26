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
WHATSAPP_TO = os.environ.get("WHATSAPP_TO")  # Tu número con código país, ej: 51939947031

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


def buscar_en_catalogo(tipo, descripcion):
    """
    Busca en hoja Catalogo según tipo + descripcion
    Devuelve: codigo_sap, codigo_barras, um
    """
    wsCat = get_ws("Catalogo")
    filas = wsCat.get_all_records()

    tipo = str(tipo).strip().upper()
    descripcion = str(descripcion).strip().upper()

    for fila in filas:
        tipo_fila = str(fila.get("TIPO", "")).strip().upper()
        desc_fila = str(fila.get("DESCRIPCION", "")).strip().upper()

        if tipo_fila == tipo and desc_fila == descripcion:
            codigo_sap = str(fila.get("CODIGO", "")).strip()
            um = str(fila.get("U.M", "")).strip() or str(fila.get("UM", "")).strip()

            codigo_barras = str(fila.get("CODIGO_BARRAS", "")).strip()

            # si no hay CODIGO_BARRAS lo generamos en formato Code39
            if (not codigo_barras) and codigo_sap:
                codigo_barras = f"*{codigo_sap}*"

            return codigo_sap, codigo_barras, um

    return "", "", ""


def enviar_whatsapp(solicitante, tipo, descripcion, cantidad):
    if not WHATSAPP_TOKEN or not WHATSAPP_PHONE_ID or not WHATSAPP_TO:
        print("⚠️ WhatsApp no configurado")
        return

    url = f"https://graph.facebook.com/v18.0/{WHATSAPP_PHONE_ID}/messages"

    payload = {
        "messaging_product": "whatsapp",
        "to": WHATSAPP_TO,
        "type": "template",
        "template": {
            "name": "solicitud_almacen_xylem_nueva",
            "language": {"code": "es_PE"},
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": str(solicitante)},
                        {"type": "text", "text": str(tipo)},
                        {"type": "text", "text": str(descripcion)},
                        {"type": "text", "text": str(cantidad)}
                    ]
                }
            ]
        }
    }

    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }

    try:
        r = requests.post(url, json=payload, headers=headers)
        print("✅ WhatsApp plantilla enviado:", r.status_code, r.text)
    except Exception as e:
        print("❌ Error WhatsApp:", e)


def get_usuario(codigo):
    ws = get_ws("Usuarios")
    filas = ws.get_all_records()

    for fila in filas:
        if str(fila.get("CODIGO", "")).strip() == str(codigo).strip():
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
        codigo_personal = request.form.get("codigo_personal", "").strip()
        nombre_personal = request.form.get("nombre_personal", "").strip()

        almacenero = request.form.get("almacenero", "").strip()
        password = request.form.get("password", "").strip()

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
        if codigo_personal:
            usuario = get_usuario(codigo_personal)
            if usuario:
                session["rol"] = "PERSONAL"
                session["nombre"] = usuario["nombre"]
                return redirect(url_for("inicio"))
            return render_template("login.html", error="Código no registrado")

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

    if session.get("rol") == "ALMACEN":
        return redirect(url_for("bandeja"))

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

        fecha = datetime.now(ZoneInfo("America/Lima"))
        fecha_str = fecha.strftime("%d/%m/%Y %H:%M")

        solicitante = session.get("nombre")

        # ID único para toda la solicitud
        id_solicitud = datetime.now(ZoneInfo("America/Lima")).strftime("%Y%m%d%H%M%S")

        # WhatsApp (resumen)
        lista_items = []
        for idx, item in enumerate(items, start=1):
            desc = item.get("descripcion", "")
            cant = item.get("cantidad", "")
            lista_items.append(f"✅{idx}) {desc} (x{cant})")

        tipo_general = items[0].get("tipo", "")
        descripcion_lista = "  |  ".join(lista_items)

        cantidad_total = 0
        for it in items:
            try:
                cantidad_total += int(str(it.get("cantidad", "0")).strip() or 0)
            except:
                pass

        # Guardar en Sheets: 1 fila por item
        for item in items:
            tipo = item.get("tipo", "").strip()
            descripcion = item.get("descripcion", "").strip()
            cantidad = str(item.get("cantidad", "")).strip()

            codigo_sap, codigo_barras, um = buscar_en_catalogo(tipo, descripcion)

            ws.append_row([
                id_solicitud,     # A
                fecha_str,        # B
                solicitante,      # C
                tipo,             # D
                codigo_sap,       # E
                codigo_barras,    # F
                descripcion,      # G
                um,               # H
                cantidad,         # I
                "PENDIENTE",      # J
                ""                # K
            ])

        enviar_whatsapp(solicitante, tipo_general, descripcion_lista, cantidad_total)

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

    # A ID, B FECHA, C SOLICITANTE, D TIPO, E COD_SAP, F COD_BARRAS, G DESC, H UM, I CANT, J ESTADO, K ALMACENERO
    for i, fila in enumerate(filas[1:], start=2):
        id_solicitud = fila[0] if len(fila) > 0 else ""
        fecha = fila[1] if len(fila) > 1 else ""
        solicitante = fila[2] if len(fila) > 2 else ""
        tipo = fila[3] if len(fila) > 3 else ""
        codigo_sap = fila[4] if len(fila) > 4 else ""
        codigo_barras = fila[5] if len(fila) > 5 else ""
        descripcion = fila[6] if len(fila) > 6 else ""
        um = fila[7] if len(fila) > 7 else ""
        cantidad = fila[8] if len(fila) > 8 else ""
        estado = fila[9] if len(fila) > 9 else ""
        almacenero = fila[10] if len(fila) > 10 else ""

        solicitudes.append({
            "fila": i,
            "id_solicitud": id_solicitud,
            "fecha": fecha,
            "solicitante": solicitante,
            "tipo": tipo,
            "codigo_sap": codigo_sap,
            "codigo_barras": codigo_barras,
            "descripcion": descripcion,
            "um": um,
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

        # J=10 estado, K=11 almacenero
        ws.update_cell(fila, 10, nuevo_estado)
        ws.update_cell(fila, 11, almacenero)

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
            activo = str(fila.get("ACTIVO", "")).strip().upper()
            tipo_fila = str(fila.get("TIPO", "")).strip().upper()

            if activo == "SI" and tipo_fila == tipo:
                items.append({
                    "codigo_sap": fila.get("CODIGO", ""),
                    "tipo": fila.get("TIPO", ""),
                    "descripcion": fila.get("DESCRIPCION", ""),
                    "um": fila.get("U.M", ""),
                    "stock": fila.get("STOCK", ""),
                    "codigo_barras": fila.get("CODIGO_BARRAS", "")
                })

        return jsonify({"items": items})

    except Exception as e:
        print("ERROR /api/catalogo:", e)
        return jsonify({"items": [], "error": str(e)}), 500


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))