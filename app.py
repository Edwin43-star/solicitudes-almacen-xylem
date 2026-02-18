from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import os
import json
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
from zoneinfo import ZoneInfo
import requests
from collections import defaultdict

# ===============================
# WHATSAPP NOTIFICACIÓN
# ===============================
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN")
WHATSAPP_PHONE_ID = os.environ.get("WHATSAPP_PHONE_ID")

# ✅ Destinatarios almacén (2 almaceneros)
WHATSAPP_TOS = os.environ.get("WHATSAPP_TOS", "")  # JSON: ["519...","519..."] o 519...


def get_whatsapp_tos():
    """
    Lee destinatarios SIEMPRE desde Render (dinámico).
    Acepta:
    - '["51939947031","51999174320"]'
    - '51939947031,51999174320'
    """
    raw = (os.environ.get("WHATSAPP_TOS") or "").strip()

    if not raw:
        print("⚠️ WHATSAPP_TOS vacío en Render")
        return []

    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [str(x).strip().replace(" ", "") for x in data if str(x).strip()]
    except Exception:
        pass

    if "," in raw:
        return [x.strip().replace(" ", "") for x in raw.split(",") if x.strip()]

    return [raw.replace(" ", "")]


def formatear_mensaje_whatsapp_solicitud(solicitante: str, items: list) -> str:
    """Mensaje bonito: solicitante + items + cantidades + hora"""
    ahora = datetime.now(ZoneInfo("America/Lima")).strftime("%d/%m/%Y %H:%M")
    solicitante = (solicitante or "").strip().upper()

    lineas = []
    lineas.append("📦 *NUEVA SOLICITUD DE ALMACÉN*")
    if solicitante:
        lineas.append(f"👷 *Solicitante:* {solicitante}")
    lineas.append(f"🕒 *Hora:* {ahora}")
    lineas.append("")
    lineas.append("📝 *Ítems:*")

    if not items:
        lineas.append("• (sin ítems)")
    else:
        for i, it in enumerate(items, 1):
            tipo = (it.get("tipo") or "").strip()
            desc = (it.get("descripcion") or "").strip()
            cant = str(it.get("cantidad") or "").strip()
            if tipo and desc:
                lineas.append(f"{i}. [{tipo}] {desc}  x{cant}")
            elif desc:
                lineas.append(f"{i}. {desc}  x{cant}")
            else:
                lineas.append(f"{i}. x{cant}")

    lineas.append("")
    lineas.append("✅ Ingresar a la bandeja para atender.")
    return "\n".join(lineas)


app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "xylem123")

SPREADSHEET_ID = os.environ["SPREADSHEET_ID"]
GOOGLE_CREDENTIALS = json.loads(os.environ["GOOGLE_CREDENTIALS"])


# ===============================
# GOOGLE SHEETS
# ===============================
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


# ===============================
# CATALOGO (BUSQUEDA)
# ===============================
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

            # CODIGO_BARRAS puede estar guardado o lo generamos automático
            codigo_barras = str(fila.get("CODIGO_BARRAS", "")).strip()

            if not codigo_barras and codigo_sap:
                # Formato Code39 para lectura con Free 3 of 9
                codigo_barras = f"*{codigo_sap}*"

            return codigo_sap, codigo_barras, um

    return "", "", ""


# ===============================
# WHATSAPP
# ===============================

def enviar_whatsapp_solicitud(solicitante: str, items: list):
    """Notificación WhatsApp: solicitante + ítems.
    Destinatarios salen de Render (WHATSAPP_TOS).
    """
    if not WHATSAPP_TOKEN or not WHATSAPP_PHONE_ID:
        print("⚠️ WhatsApp no configurado")
        return

    tos = get_whatsapp_tos()
    if not tos:
        print("⚠️ Lista de destinatarios WhatsApp vacía")
        return

    mensaje = formatear_mensaje_whatsapp_solicitud(solicitante, items)

    url = f"https://graph.facebook.com/v18.0/{WHATSAPP_PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }

    for numero in tos:
        payload = {
            "messaging_product": "whatsapp",
            "to": numero,
            "type": "text",
            "text": {"body": mensaje}
        }

        try:
            r = requests.post(url, json=payload, headers=headers, timeout=20)
            print(f"✅ WhatsApp enviado a {numero}: ", r.status_code, r.text)
        except Exception as e:
            print(f"❌ Error WhatsApp ({numero}):", e)



def get_usuario(codigo):
    ws = get_ws("Usuarios")
    filas = ws.get_all_records()

    for fila in filas:
        if str(fila.get("CODIGO", "")).strip() == str(codigo).strip():
            return {
                "codigo": str(fila.get("CODIGO", "")).strip(),
                "nombre": str(fila.get("NOMBRE COMPLETO", "")).strip(),
                "cargo": str(fila.get("CARGO", "")).strip(),
                "area": str(fila.get("AREA", "")).strip(),
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

        # Login por nombre sin código
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

        # ✅ generar ID_SOLICITUD único para toda la solicitud
        id_solicitud = datetime.now(ZoneInfo("America/Lima")).strftime("%Y%m%d%H%M%S")

        # ✅ armamos 1 mensaje con lista
        lista_items = []
        for idx, item in enumerate(items, start=1):
            descripcion = item.get("descripcion", "")
            cantidad = item.get("cantidad", "")
            lista_items.append(f"✅{idx}) {descripcion} (x{cantidad})")

        tipo_general = items[0].get("tipo", "")
        descripcion_lista = "  |  ".join(lista_items)

        # ✅ suma real de cantidades
        cantidad_total = 0
        for it in items:
            try:
                cantidad_total += int(str(it.get("cantidad", "0")).strip() or 0)
            except:
                cantidad_total += 0

        # ✅ GUARDAR EN GOOGLE SHEETS (1 fila por cada item)
        for item in items:
            tipo = item.get("tipo", "").strip()
            descripcion = item.get("descripcion", "").strip()
            cantidad = str(item.get("cantidad", "")).strip()

            # ✅ BUSCAR EN CATALOGO: CODIGO SAP + CODIGO BARRAS + UM
            codigo_sap, codigo_barras, um = buscar_en_catalogo(tipo, descripcion)

            ws.append_row([
                id_solicitud,     # A ID_SOLICITUD
                fecha_str,        # B FECHA
                solicitante,      # C SOLICITANTE
                tipo,             # D TIPO
                codigo_sap,       # E CODIGO_SAP
                descripcion,      # F DESCRIPCION
                um,               # G UM
                cantidad,         # H CANTIDAD
                "PENDIENTE",      # I ESTADO
                ""                # J ALMACENERO
            ])

        # ✅ ENVIAR WHATSAPP (UN SOLO MENSAJE)
        enviar_whatsapp_solicitud(solicitante, items)

        flash("✅ Solicitud registrada. El almacén la atenderá en breve.", "success")
        return redirect(url_for("solicitar"))

    except Exception as e:
        print("ERROR guardar_solicitud:", e)
        flash(f"Error al guardar solicitud: {e}", "danger")
        return redirect(url_for("solicitar"))


# ===============================
# BANDEJA AGRUPADA (CORREGIDA)
# ===============================
@app.route("/bandeja")
def bandeja():
    if "rol" not in session or session.get("rol") != "ALMACEN":
        return redirect(url_for("login"))

    ws = get_ws("Solicitudes")
    filas = ws.get_all_values()

    # A ID_SOLICITUD
    # B FECHA
    # C SOLICITANTE
    # D TIPO
    # E CODIGO_SAP
    # F DESCRIPCION
    # G UM
    # H CANTIDAD
    # I ESTADO
    # J ALMACENERO
    grupos = defaultdict(list)

    # Recorremos filas (desde la 2 porque la 1 es cabecera)
    for i, fila in enumerate(filas[1:], start=2):
        id_solicitud = fila[0] if len(fila) > 0 else ""
        fecha = fila[1] if len(fila) > 1 else ""
        solicitante = fila[2] if len(fila) > 2 else ""
        tipo = fila[3] if len(fila) > 3 else ""
        codigo_sap = fila[4] if len(fila) > 4 else ""
        descripcion = fila[5] if len(fila) > 5 else ""
        um = fila[6] if len(fila) > 6 else ""
        cantidad = fila[7] if len(fila) > 7 else ""
        estado = fila[8] if len(fila) > 8 else ""
        almacenero = fila[9] if len(fila) > 9 else ""

        if id_solicitud.strip() == "":
            continue

        grupos[id_solicitud].append({
            "fila": i,  # fila real en Google Sheets (para actualizar_estado)
            "id_solicitud": id_solicitud,
            "fecha": fecha,
            "solicitante": solicitante,
            "tipo": tipo,
            "codigo_sap": codigo_sap,
            "descripcion": descripcion,
            "um": um,
            "cantidad": cantidad,
            "estado": estado,
            "almacenero": almacenero,
        })

    # Armamos lista final para la vista (agrupada)
    solicitudes_agrupadas = []
    for id_s, detalle in grupos.items():
        cab = detalle[0]
        solicitudes_agrupadas.append({
            "id_solicitud": id_s,
            "fecha": cab["fecha"],
            "solicitante": cab["solicitante"],
            "tipo": cab["tipo"],
            "estado": cab["estado"],
            "almacenero": cab["almacenero"],
            "detalle": detalle,   # ✅ OJO: 'detalle' (NO 'items')
        })

    # Ordenar por id desc (más reciente arriba)
    solicitudes_agrupadas = sorted(
        solicitudes_agrupadas,
        key=lambda x: x["id_solicitud"],
        reverse=True
    )

    return render_template("bandeja.html", solicitudes=solicitudes_agrupadas)

# ===============================
# ACTUALIZAR ESTADO
# ===============================
@app.route("/actualizar_estado", methods=["POST"])
def actualizar_estado():
    if "rol" not in session or session.get("rol") != "ALMACEN":
        return redirect(url_for("login"))

    fila = int(request.form.get("fila"))
    nuevo_estado = request.form.get("estado", "").strip().upper()
    almacenero = session.get("nombre")

    try:
        ws = get_ws("Solicitudes")

        # I=10 estado, J=11 almacenero
        ws.update_cell(fila, 10, nuevo_estado)
        ws.update_cell(fila, 11, almacenero)

        flash(f"Solicitud {nuevo_estado}", "success")

    except Exception as e:
        flash(f"Error al actualizar: {e}", "danger")

    return redirect(url_for("bandeja"))


# ===============================
# GENERAR VALE (COPIAR ITEMS A VALE_SALIDA)
# ===============================
@app.route("/generar_vale/<id_solicitud>", methods=["POST"])
def generar_vale(id_solicitud):
    if "rol" not in session or session.get("rol") != "ALMACEN":
        return redirect(url_for("login"))

    try:
        wsSol = get_ws("Solicitudes")
        wsVale = get_ws("VALE_SALIDA")

        filas = wsSol.get_all_values()

        items = []
        cabecera = None
        filas_para_actualizar = []  # filas reales en sheet Solicitudes

        # ===============================
        # 1) Buscar todos los items del ID_SOLICITUD
        # ===============================
        for idx, fila in enumerate(filas[1:], start=2):  # idx = fila real en Sheets
            if len(fila) < 10:
                continue

            if fila[0].strip() == id_solicitud.strip():
                if cabecera is None:
                    cabecera = {
                        "id": fila[0],
                        "fecha": fila[1],
                        "solicitante": fila[2],
                        "tipo": fila[3]
                    }

                items.append({
                    "codigo_sap": fila[4],
                    "descripcion": fila[5],
                    "um": fila[6],
                    "cantidad": fila[7],
                })

                filas_para_actualizar.append(idx)

        if not items:
            flash("❌ No se encontraron items para esta solicitud", "danger")
            return redirect(url_for("bandeja"))

        almacenero = session.get("nombre", "")

        # ===============================
        # 2) LIMPIAR SOLO ZONA DE ITEMS (NO TOCAR EL DISEÑO)
        # ===============================
        # Borra solo tabla de items (filas 6 a 15 aprox)
        wsVale.batch_clear(["A6:K15", "B6:B15", "C6:C15", "D6:D15", "G6:G15", "H6:H15", "I6:I15", "K6:K15"])

        # ===============================
        # 3) CARGAR CABECERA DEL VALE (CELDAS EXACTAS)
        # ===============================
        # FECHA
        wsVale.update("J2", [[cabecera["fecha"]]])

        # TRABAJADOR (solicitante)
        wsVale.update("C4", [[cabecera["solicitante"]]])

        # ALMACENERO (logueado)
        wsVale.update("F4", [[almacenero]])

        # ===============================
        # 🔹 DATOS DEL TRABAJADOR DESDE USUARIOS
        # ===============================
        codigo_trab = ""
        cargo_trab = ""
        area_trab = ""

        wsUsuarios = get_ws("Usuarios")
        filas_usr = wsUsuarios.get_all_records()

        nombre_sol = str(cabecera["solicitante"]).strip().upper()

        for fila in filas_usr:
            nombre_usr = str(fila.get("NOMBRE", "")).strip().upper()
            nombre_usr2 = str(fila.get("NOMBRE COMPLETO", "")).strip().upper()

            if nombre_sol == nombre_usr or nombre_sol == nombre_usr2:
                codigo_trab = str(fila.get("CODIGO", "")).strip()
                cargo_trab = str(fila.get("CARGO", "")).strip()
                area_trab = str(fila.get("AREA", "")).strip()
                break

        # ===============================
        # 4) CARGAR ITEMS (fila 6 en adelante)
        # ===============================
        fila_inicio = 6

        datos = []

        n = 1

        for it in items:
            fila = [""] * 11  # columnas A-G

            fila[0] = n                        # A
            fila[1] = it["codigo_sap"]        # B
            fila[2] = it["descripcion"]       # C
            fila[5] = it["cantidad"]          # F
            fila[6] = it["um"]                # G
            fila[7] = "NUEVO"                 # H
            fila[8] = "CAMBIO"                # J

            datos.append(fila)

            n += 1

        # Escribir todo en una sola operación
        rango = f"A{fila_inicio}:K{fila_inicio + len(datos) - 1}"

        wsVale.update(rango, datos)

        # ===============================
        # 5) MARCAR SOLICITUD COMO ATENDIDA (TODAS LAS FILAS DEL ID)
        # ===============================
        # I=10 ESTADO, J=11 ALMACENERO
        updates = []
        for fila_real in filas_para_actualizar:
            updates.append({
                "range": f"I{fila_real}:J{fila_real}",
                "values": [["ATENDIDO", almacenero]]
            })

        wsSol.batch_update(updates)

        flash("✅ VALE generado y solicitud marcada como ATENDIDO", "success")
        return redirect(url_for("bandeja"))

    except Exception as e:
        flash(f"❌ Error al generar vale: {e}", "danger")
        return redirect(url_for("bandeja"))


# ===============================
# API CATALOGO
# ===============================
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


# ============================================================
#   WEBHOOK META WHATSAPP (VERIFICACION + RECEPCION EVENTOS)
#   URL: /webhook
# ============================================================

@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    # 1) VERIFICACION (GET) - Meta envia hub.challenge
    if request.method == "GET":
        mode = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")

        # ✅ Tu verify token definido en Meta (Config. Webhook)
        VERIFY_TOKEN = os.environ.get("WHATSAPP_VERIFY_TOKEN", "antamina-xylem-2026")

        if mode == "subscribe" and token == WHATSAPP_VERIFY_TOKEN:
            print("✅ Webhook verificado correctamente")
            return challenge, 200
        else:
            print("❌ Webhook verificación fallida")
            return "Forbidden", 403

    # 2) EVENTOS (POST) - Meta enviará mensajes / estados
    try:
        data = request.get_json(silent=True) or {}
        print("📩 Webhook recibido:", data)

        # Aquí podrías procesar mensajes entrantes si luego lo necesitas.
        # Por ahora SOLO respondemos 200 para que Meta no reintente.
        return "EVENT_RECEIVED", 200
    except Exception as e:
        print("❌ Error webhook:", e)
        return "ERROR", 500


if __name__ == "__main__":
    app.run(debug=True)