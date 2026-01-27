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
WHATSAPP_TO = os.environ.get("WHATSAPP_TO")  # Ej: 51939947031

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "xylem123")

SPREADSHEET_ID = os.environ["SPREADSHEET_ID"]
GOOGLE_CREDENTIALS = json.loads(os.environ["GOOGLE_CREDENTIALS"])

# ✅ GID VALE_SALIDA
VALE_GID = int(os.environ.get("VALE_GID", "1184202075"))


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


def url_vale_sheets():
    # abre directamente la hoja VALE_SALIDA
    return f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit#gid={VALE_GID}"


# ===============================
# CATALOGO
# ===============================
def buscar_en_catalogo(tipo, descripcion):
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
            if not codigo_barras and codigo_sap:
                codigo_barras = f"*{codigo_sap}*"

            return codigo_sap, codigo_barras, um

    return "", "", ""


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
        print("✅ WhatsApp enviado:", r.status_code, r.text)
    except Exception as e:
        print("❌ Error WhatsApp:", e)


# ===============================
# USUARIOS
# ===============================
def get_usuario(codigo):
    ws = get_ws("Usuarios")
    filas = ws.get_all_records()

    for fila in filas:
        if str(fila.get("CODIGO", "")).strip() == str(codigo).strip():
            return {
                "nombre": str(fila.get("NOMBRE COMPLETO", fila.get("NOMBRE", ""))).strip(),
                "rol": str(fila.get("ROL", "")).strip(),
            }
    return None


def buscar_datos_usuario_por_nombre(nombre):
    """
    Devuelve: codigo, area, cargo
    """
    if not nombre:
        return "", "", ""

    ws = get_ws("Usuarios")
    filas = ws.get_all_records()
    nombre_u = str(nombre).strip().upper()

    for fila in filas:
        n1 = str(fila.get("NOMBRE", "")).strip().upper()
        n2 = str(fila.get("NOMBRE COMPLETO", "")).strip().upper()

        if nombre_u == n1 or nombre_u == n2:
            codigo = str(fila.get("CODIGO", "")).strip()
            area = str(fila.get("AREA", "")).strip()
            cargo = str(fila.get("CARGO", "")).strip()
            return codigo, area, cargo

    return "", "", ""


# ===============================
# LOGIN
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
        id_solicitud = datetime.now(ZoneInfo("America/Lima")).strftime("%Y%m%d%H%M%S")

        lista_items = []
        for idx, item in enumerate(items, start=1):
            descripcion = item.get("descripcion", "")
            cantidad = item.get("cantidad", "")
            lista_items.append(f"{idx}) {descripcion} (x{cantidad})")

        tipo_general = items[0].get("tipo", "")
        descripcion_lista = "  |  ".join(lista_items)

        cantidad_total = 0
        for it in items:
            try:
                cantidad_total += int(str(it.get("cantidad", "0")).strip() or 0)
            except:
                cantidad_total += 0

        for item in items:
            tipo = item.get("tipo", "").strip()
            descripcion = item.get("descripcion", "").strip()
            cantidad = str(item.get("cantidad", "")).strip()

            codigo_sap, codigo_barras, um = buscar_en_catalogo(tipo, descripcion)

            ws.append_row([
                id_solicitud,
                fecha_str,
                solicitante,
                tipo,
                codigo_sap,
                codigo_barras,
                descripcion,
                um,
                cantidad,
                "PENDIENTE",
                ""
            ])

        enviar_whatsapp(solicitante, tipo_general, descripcion_lista, cantidad_total)

        flash("✅ Solicitud registrada. El almacén la atenderá en breve.", "success")
        return redirect(url_for("solicitar"))

    except Exception as e:
        print("ERROR guardar_solicitud:", e)
        flash(f"Error al guardar solicitud: {e}", "danger")
        return redirect(url_for("solicitar"))


# ===============================
# BANDEJA (AGRUPADA)
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
        if id_solicitud.strip() == "":
            continue

        grupos[id_solicitud].append({
            "fila": i,
            "id_solicitud": id_solicitud,
            "fecha": fila[1] if len(fila) > 1 else "",
            "solicitante": fila[2] if len(fila) > 2 else "",
            "tipo": fila[3] if len(fila) > 3 else "",
            "codigo_sap": fila[4] if len(fila) > 4 else "",
            "codigo_barras": fila[5] if len(fila) > 5 else "",
            "descripcion": fila[6] if len(fila) > 6 else "",
            "um": fila[7] if len(fila) > 7 else "",
            "cantidad": fila[8] if len(fila) > 8 else "",
            "estado": fila[9] if len(fila) > 9 else "",
            "almacenero": fila[10] if len(fila) > 10 else "",
        })

    solicitudes_agrupadas = []
    for id_s, detalle in grupos.items():
        cab = detalle[0]

        estados = [str(it.get("estado", "")).strip().upper() for it in detalle]
        estado_cab = "ATENDIDO" if estados and all(e == "ATENDIDO" for e in estados) else (cab.get("estado") or "PENDIENTE")
        estado_cab = str(estado_cab).strip().upper() if estado_cab else "PENDIENTE"

        alm_cab = ""
        for it in detalle:
            if str(it.get("almacenero", "")).strip():
                alm_cab = str(it.get("almacenero", "")).strip()
                break

        solicitudes_agrupadas.append({
            "id_solicitud": id_s,
            "fecha": cab.get("fecha", ""),
            "solicitante": cab.get("solicitante", ""),
            "tipo": cab.get("tipo", ""),
            "estado": estado_cab,
            "almacenero": alm_cab,
            "detalle": detalle
        })

    solicitudes_agrupadas = sorted(
        solicitudes_agrupadas,
        key=lambda x: x["id_solicitud"],
        reverse=True
    )

    return render_template(
        "bandeja.html",
        solicitudes=solicitudes_agrupadas,
        vale_url=url_vale_sheets()
    )


# ===============================
# GENERAR VALE
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
        filas_a_actualizar = []

        for idx, fila in enumerate(filas[1:], start=2):
            if len(fila) < 10:
                continue

            if str(fila[0]).strip() == str(id_solicitud).strip():
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

                filas_a_actualizar.append(idx)

        if not items or cabecera is None:
            flash("❌ No se encontraron items para esta solicitud", "danger")
            return redirect(url_for("bandeja"))

        almacenero = session.get("nombre", "").strip()
        solicitante = cabecera.get("solicitante", "").strip()

        codigo_trab, area, cargo = buscar_datos_usuario_por_nombre(solicitante)

        # ✅ LIMPIAR SOLO DETALLE (NO borrar cabecera)
        # tu tabla va desde A8 hasta K22 aprox.
        wsVale.batch_clear(["A8:K22"])

        # ✅ CABECERA (celdas combinadas se llenan escribiendo en la primera celda del merge)
        fecha_vale = datetime.now(ZoneInfo("America/Lima")).strftime("%d/%m/%Y %H:%M")

        # FECHA (J2-K2-L2 en merge: escribir en J2 o J3 según tu plantilla)
        wsVale.update("J3", fecha_vale)

        # CODIGO trabajador
        wsVale.update("B5", codigo_trab)

        # TRABAJADOR (merge D5:E5:F5) -> escribir en D5
        wsVale.update("D5", solicitante)

        # CARGO (merge B6:C6:D6) -> escribir en B6
        wsVale.update("B6", cargo)

        # AREA (merge D6:E6:F6) -> escribir en D6
        wsVale.update("D6", area)

        # ALMACENERO (tu plantilla: el nombre va en G6 según tu captura)
        wsVale.update("G6", almacenero)

        # ✅ ITEMS
        # Columnas:
        # A N°
        # B CODIGO
        # C CODIGO BARRAS
        # D DESCRIPCION (merge D:E:F) -> escribir en D
        # G CANT
        # H UM
        # I "NUEVO"
        # J "CAMBIO"
        fila_inicio = 8
        data_rows = []

        for n, it in enumerate(items, start=1):
            cb = str(it.get("codigo_barras", "")).strip()
            # para mostrar en barras: *CODIGO*
            if cb and not (cb.startswith("*") and cb.endswith("*")):
                cb = f"*{cb}*"

            data_rows.append([
                n,
                str(it.get("codigo_sap", "")).strip(),
                cb,
                str(it.get("descripcion", "")).strip(),
                "",  # E (parte del merge de descripcion)
                "",  # F (parte del merge de descripcion)
                str(it.get("cantidad", "")).strip(),
                str(it.get("um", "")).strip(),
                "NUEVO",
                "CAMBIO",
                ""   # K (PERDIDA queda vacío)
            ])

        # rango debe ser exacto al tamaño: A..K
        rango = f"A{fila_inicio}:K{fila_inicio + len(data_rows) - 1}"
        wsVale.update(rango, data_rows, value_input_option="USER_ENTERED")

        # ✅ MARCAR ATENDIDO en todas filas de ese ID
        batch_updates = []
        for r in filas_a_actualizar:
            batch_updates.append({"range": f"J{r}", "values": [["ATENDIDO"]]})
            batch_updates.append({"range": f"K{r}", "values": [[almacenero]]})

        wsSol.batch_update(batch_updates, value_input_option="USER_ENTERED")

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


if __name__ == "__main__":
    app.run(debug=True)