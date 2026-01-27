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
WHATSAPP_TO = os.environ.get("WHATSAPP_TO")  # ej: 51939947031

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "xylem123")

SPREADSHEET_ID = os.environ["SPREADSHEET_ID"]
GOOGLE_CREDENTIALS = json.loads(os.environ["GOOGLE_CREDENTIALS"])

# ✅ GID de la hoja VALE_SALIDA (según tu captura)
GID_VALE_SALIDA = "1184202075"


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

            # CODIGO_BARRAS (si no existe se genera Code39)
            codigo_barras = str(fila.get("CODIGO_BARRAS", "")).strip()
            if not codigo_barras and codigo_sap:
                codigo_barras = f"*{codigo_sap}*"

            return codigo_sap, codigo_barras, um

    return "", "", ""


# ===============================
# USUARIOS (AREA Y CARGO)
# ===============================
def get_area_cargo_por_nombre(nombre):
    """
    Busca en hoja Usuarios:
    B = NOMBRE
    C = AREA
    D = CARGO
    E = ACTIVO
    """
    ws = get_ws("Usuarios")
    filas = ws.get_all_records()

    nombre = str(nombre).strip().upper()

    for fila in filas:
        nombre_fila = str(fila.get("NOMBRE", "")).strip().upper()
        activo = str(fila.get("ACTIVO", "")).strip().upper()

        if activo == "SI" and nombre_fila == nombre:
            area = str(fila.get("AREA", "")).strip()
            cargo = str(fila.get("CARGO", "")).strip()
            return area, cargo

    return "", ""


def get_usuario(codigo):
    """
    Retorna usuario por CODIGO
    (si tu hoja Usuarios tiene 'NOMBRE COMPLETO', se usa; si no, usa NOMBRE)
    """
    ws = get_ws("Usuarios")
    filas = ws.get_all_records()

    for fila in filas:
        if str(fila.get("CODIGO", "")).strip() == str(codigo).strip():
            nombre = str(fila.get("NOMBRE COMPLETO", "")).strip()
            if not nombre:
                nombre = str(fila.get("NOMBRE", "")).strip()

            return {
                "nombre": nombre,
                "rol": str(fila.get("ROL", "")).strip() if fila.get("ROL") else "PERSONAL",
            }
    return None


# ===============================
# WHATSAPP
# ===============================
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

        # Personal por CODIGO
        if codigo_personal:
            usuario = get_usuario(codigo_personal)
            if usuario:
                session["rol"] = "PERSONAL"
                session["nombre"] = usuario["nombre"]
                return redirect(url_for("inicio"))
            return render_template("login.html", error="Código no registrado")

        # Personal por nombre manual
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


# ===============================
# GUARDAR SOLICITUD
# ===============================
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

        # ✅ FECHA PERÚ
        fecha = datetime.now(ZoneInfo("America/Lima"))
        fecha_str = fecha.strftime("%d/%m/%Y %H:%M")

        solicitante = session.get("nombre")

        # ✅ ID_SOLICITUD único
        id_solicitud = datetime.now(ZoneInfo("America/Lima")).strftime("%Y%m%d%H%M%S")

        # ✅ WhatsApp: resumen
        lista_items = []
        for idx, item in enumerate(items, start=1):
            descripcion = item.get("descripcion", "")
            cantidad = item.get("cantidad", "")
            lista_items.append(f"✅{idx}) {descripcion} (x{cantidad})")

        tipo_general = items[0].get("tipo", "")
        descripcion_lista = "  |  ".join(lista_items)

        cantidad_total = 0
        for it in items:
            try:
                cantidad_total += int(str(it.get("cantidad", "0")).strip() or 0)
            except:
                cantidad_total += 0

        # ✅ Guardar 1 fila por item
        for item in items:
            tipo = item.get("tipo", "").strip()
            descripcion = item.get("descripcion", "").strip()
            cantidad = str(item.get("cantidad", "")).strip()

            # Buscar Catalogo
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

        # WhatsApp (opcional)
        enviar_whatsapp(solicitante, tipo_general, descripcion_lista, cantidad_total)

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

    grupos = defaultdict(list)

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

        if id_solicitud.strip() == "":
            continue

        grupos[id_solicitud].append({
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
            "detalle": detalle,   # ✅ no 'items'
        })

    solicitudes_agrupadas = sorted(
        solicitudes_agrupadas,
        key=lambda x: x["id_solicitud"],
        reverse=True
    )

    return render_template("bandeja.html", solicitudes=solicitudes_agrupadas)


# ===============================
# ACTUALIZAR ESTADO POR ITEM
# ===============================
@app.route("/actualizar_estado", methods=["POST"])
def actualizar_estado():
    if "rol" not in session or session.get("rol") != "ALMACEN":
        return redirect(url_for("login"))

    fila = int(request.form.get("fila"))
    nuevo_estado = request.form.get("estado", "").strip().upper()
    almacenero = session.get("nombre", "")

    try:
        ws = get_ws("Solicitudes")
        # J=10 estado, K=11 almacenero
        ws.update_cell(fila, 10, nuevo_estado)
        ws.update_cell(fila, 11, almacenero)

        flash(f"✅ Estado cambiado a {nuevo_estado}", "success")

    except Exception as e:
        flash(f"❌ Error al actualizar: {e}", "danger")

    return redirect(url_for("bandeja"))


# ===============================
# GENERAR VALE (CARGA + ATENDIDO + REDIRECT SHEETS)
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
        filas_para_actualizar = []

        # ===============================
        # 1) Items del mismo ID
        # ===============================
        for idx, fila in enumerate(filas[1:], start=2):
            if len(fila) < 11:
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
                    "codigo_barras": fila[5],
                    "descripcion": fila[6],
                    "um": fila[7],
                    "cantidad": fila[8],
                })

                filas_para_actualizar.append(idx)

        if not items:
            flash("❌ No se encontraron items para esta solicitud", "danger")
            return redirect(url_for("bandeja"))

        almacenero = session.get("nombre", "")

        # ===============================
        # 2) AREA y CARGO desde Usuarios
        # ===============================
        area, cargo = get_area_cargo_por_nombre(cabecera["solicitante"])

        # ===============================
        # 3) LIMPIAR SOLO TABLA (NO CABECERA)
        # ===============================
        wsVale.batch_clear(["A8:K22"])

        # ===============================
        # 4) CABECERA EXACTA SEGÚN TU FORMATO REAL
        # ===============================
        # FECHA
        wsVale.update("M2", [[cabecera["fecha"]]])

        # TRABAJADOR
        wsVale.update("C5", [[cabecera["solicitante"]]])

        # CARGO
        wsVale.update("C6", [[cargo]])

        # AREA
        wsVale.update("E6", [[area]])

        # ALMACENERO (en tu formato está en H5)
        wsVale.update("H5", [[almacenero]])

        # ===============================
        # 5) ITEMS DESDE FILA 8
        # ===============================
        fila_inicio = 8
        n = 1
        for it in items:
            f = fila_inicio + (n - 1)

            # A N°
            wsVale.update(f"A{f}", [[n]])

            # B CODIGO
            wsVale.update(f"B{f}", [[it["codigo_sap"]]])

            # C CODIGO BARRAS (se verá como barras si la fuente está aplicada)
            wsVale.update(f"C{f}", [[it["codigo_barras"]]])

            # D DESCRIPCION (celda combinada)
            wsVale.update(f"D{f}", [[it["descripcion"]]])

            # G CANTIDAD
            wsVale.update(f"G{f}", [[it["cantidad"]]])

            # H UM
            wsVale.update(f"H{f}", [[it["um"]]])

            n += 1

        # ===============================
        # 6) MARCAR ATENDIDO EN SOLICITUDES
        # ===============================
        for fila_real in filas_para_actualizar:
            wsSol.update_cell(fila_real, 10, "ATENDIDO")   # J
            wsSol.update_cell(fila_real, 11, almacenero)   # K

        flash("✅ VALE generado y solicitud marcada como ATENDIDO", "success")

        # ===============================
        # 7) REDIRECT DIRECTO A GOOGLE SHEETS VALE
        # ===============================
        url_vale = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit#gid={GID_VALE_SALIDA}"
        return redirect(url_vale)

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


if __name__ == "__main__":
    app.run(debug=True)