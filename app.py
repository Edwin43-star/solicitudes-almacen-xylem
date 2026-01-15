from flask import Flask, render_template, request, redirect, session, url_for, jsonify, flash
from datetime import datetime, timezone
import os
import json

import gspread
from google.oauth2.service_account import Credentials

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "xylem-secret-key")

# =========================
# CONFIG GOOGLE SHEETS (PRO)
# =========================
# Render: crea estas variables de entorno:
# 1) GOOGLE_CREDENTIALS_JSON  -> pega TODO el JSON del service account
# 2) SPREADSHEET_KEY          -> el ID del Sheet (la parte entre /d/ y /edit)
#
# IMPORTANTE:
# Usamos open_by_key para NO necesitar Drive scope.

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

SPREADSHEET_KEY = os.environ.get("SPREADSHEET_KEY", "").strip()
GOOGLE_CREDENTIALS_JSON = os.environ.get("GOOGLE_CREDENTIALS_JSON", "").strip()

_gs_client = None
_ws_solicitudes = None
_ws_catalogo = None
_ws_usuarios = None
_ws_almaceneros = None


def _now_str():
    # Hora Perú aprox (-05:00). Si quieres exacto con pytz, lo agregamos luego.
    # Para no meter más dependencias, usamos UTC y te queda consistente.
    return datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M:%S UTC")


def get_gsheets():
    """
    Inicializa una sola vez y reutiliza.
    """
    global _gs_client, _ws_solicitudes, _ws_catalogo, _ws_usuarios, _ws_almaceneros

    if _gs_client is not None:
        return _gs_client, _ws_solicitudes, _ws_catalogo, _ws_usuarios, _ws_almaceneros

    if not SPREADSHEET_KEY:
        raise RuntimeError("Falta variable de entorno SPREADSHEET_KEY (ID del Google Sheet).")

    if not GOOGLE_CREDENTIALS_JSON:
        raise RuntimeError("Falta variable de entorno GOOGLE_CREDENTIALS_JSON (JSON del service account).")

    creds_dict = json.loads(GOOGLE_CREDENTIALS_JSON)
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    _gs_client = gspread.authorize(creds)

    sh = _gs_client.open_by_key(SPREADSHEET_KEY)

    # Nombres exactos según tu hoja
    _ws_solicitudes = sh.worksheet("Solicitudes")
    _ws_catalogo = sh.worksheet("Catalogo")
    _ws_usuarios = sh.worksheet("Usuarios")
    _ws_almaceneros = sh.worksheet("Almaceneros")

    return _gs_client, _ws_solicitudes, _ws_catalogo, _ws_usuarios, _ws_almaceneros


# =========================
# HELPERS DE DATOS
# =========================
def cargar_almaceneros():
    """
    Hoja: Almaceneros
    Esperado:
      A: USUARIO
      B: CLAVE
      C: NOMBRE
      D: ACTIVO (SI/NO)
    """
    _, _, _, _, wsA = get_gsheets()
    rows = wsA.get_all_values()
    if not rows or len(rows) < 2:
        return {}

    header = [h.strip().upper() for h in rows[0]]
    data = rows[1:]

    idx_usuario = header.index("USUARIO") if "USUARIO" in header else 0
    idx_clave = header.index("CLAVE") if "CLAVE" in header else 1
    idx_nombre = header.index("NOMBRE") if "NOMBRE" in header else 2
    idx_activo = header.index("ACTIVO") if "ACTIVO" in header else 3

    out = {}
    for r in data:
        if len(r) <= max(idx_usuario, idx_clave, idx_nombre, idx_activo):
            continue
        usuario = r[idx_usuario].strip().upper()
        clave = r[idx_clave].strip()
        nombre = r[idx_nombre].strip().upper()
        activo = r[idx_activo].strip().upper()

        if usuario and activo == "SI":
            out[usuario] = {"clave": clave, "nombre": nombre}
    return out


def cargar_usuarios():
    """
    Hoja: Usuarios (tu padrón de personal)
    En tu captura:
      A: CODIGO
      B: NOMBRE
      C: AREA
      D: CARGO
      E: ACTIVO
    """
    _, _, _, wsU, _ = get_gsheets()
    rows = wsU.get_all_values()
    if not rows or len(rows) < 2:
        return set()

    header = [h.strip().upper() for h in rows[0]]
    data = rows[1:]

    # Intentamos ubicar por nombre de columna
    idx_nombre = header.index("NOMBRE") if "NOMBRE" in header else 1
    idx_activo = header.index("ACTIVO") if "ACTIVO" in header else 4

    usuarios = set()
    for r in data:
        if len(r) <= max(idx_nombre, idx_activo):
            continue
        nombre = r[idx_nombre].strip().upper()
        activo = r[idx_activo].strip().upper()
        if nombre and activo == "SI":
            usuarios.add(nombre)
    return usuarios


def cargar_catalogo():
    """
    Hoja: Catalogo
    Formato recomendado:
      A: TIPO   (EPP / CONSUMIBLE / EQUIPOS Y HERRAMIENTAS)
      B: DESCRIPCION
      C: ACTIVO (SI/NO)   (opcional)
    """
    _, _, wsC, _, _ = get_gsheets()
    rows = wsC.get_all_values()
    if not rows or len(rows) < 2:
        return {}

    header = [h.strip().upper() for h in rows[0]]
    data = rows[1:]

    idx_tipo = header.index("TIPO") if "TIPO" in header else 0
    idx_desc = header.index("DESCRIPCION") if "DESCRIPCION" in header else 1
    idx_activo = header.index("ACTIVO") if "ACTIVO" in header else None

    cat = {}
    for r in data:
        if len(r) <= max(idx_tipo, idx_desc):
            continue
        tipo = r[idx_tipo].strip().upper()
        desc = r[idx_desc].strip().upper()

        activo_ok = True
        if idx_activo is not None and len(r) > idx_activo:
            activo_ok = (r[idx_activo].strip().upper() != "NO")

        if tipo and desc and activo_ok:
            cat.setdefault(tipo, []).append(desc)

    # Ordenar alfabético
    for k in cat:
        cat[k] = sorted(list(set(cat[k])))

    return cat


def es_almacenero_logueado():
    return session.get("rol") == "almacenero"


def requiere_login():
    return "usuario" not in session


# =========================
# RUTAS
# =========================
@app.route("/", methods=["GET"])
def index():
    if "usuario" in session:
        # si es almacenero -> bandeja, si no -> solicitar
        return redirect(url_for("bandeja" if es_almacenero_logueado() else "solicitar"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario_in = (request.form.get("usuario") or "").strip().upper()
        clave_in = (request.form.get("clave") or "").strip()

        if not usuario_in:
            flash("Ingrese usuario.", "danger")
            return render_template("login.html", title="Login")

        # 1) Validar almaceneros (EDWIN / EDGAR)
        almaceneros = cargar_almaceneros()
        if usuario_in in almaceneros:
            if clave_in == almaceneros[usuario_in]["clave"]:
                session["usuario"] = almaceneros[usuario_in]["nombre"]
                session["rol"] = "almacenero"
                return redirect(url_for("bandeja"))
            flash("Clave incorrecta.", "danger")
            return render_template("login.html", title="Login")

        # 2) Validar usuario normal (por NOMBRE en hoja Usuarios)
        usuarios = cargar_usuarios()
        # Aquí el usuario puede escribir el nombre completo (ej: MILTON BLAS PEÑA)
        # Si quieres que entren por CODIGO, lo cambiamos, pero por tu UI actual, es nombre.
        if usuario_in in usuarios:
            session["usuario"] = usuario_in
            session["rol"] = "usuario"
            return redirect(url_for("solicitar"))

        flash("Usuario no encontrado o inactivo.", "danger")
        return render_template("login.html", title="Login")

    return render_template("login.html", title="Login")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/solicitar", methods=["GET"])
def solicitar():
    if requiere_login():
        return redirect(url_for("login"))

    # Solo render, el catálogo lo pedirá por /api/catalogo (para que cargue siempre)
    return render_template("solicitar.html", title="Nueva Solicitud")


@app.route("/api/catalogo", methods=["GET"])
def api_catalogo():
    if requiere_login():
        return jsonify({"ok": False, "error": "No autenticado"}), 401

    try:
        cat = cargar_catalogo()
        # Aseguramos estos tipos siempre presentes
        for t in ["EPP", "CONSUMIBLE", "EQUIPOS Y HERRAMIENTAS"]:
            cat.setdefault(t, [])
        return jsonify({"ok": True, "catalogo": cat})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/enviar_solicitud", methods=["POST"])
def enviar_solicitud():
    if requiere_login():
        return jsonify({"ok": False, "error": "No autenticado"}), 401

    payload = request.get_json(silent=True) or {}
    items = payload.get("items", [])

    if not items or not isinstance(items, list):
        return jsonify({"ok": False, "error": "No hay items para enviar"}), 400

    usuario = session.get("usuario", "").upper()
    fecha = _now_str()

    try:
        _, wsS, _, _, _ = get_gsheets()

        # Guardar cada item como una fila
        # Columnas sugeridas en Solicitudes:
        # A Fecha | B Usuario | C Tipo | D Producto | E Cantidad | F Estado | G AtendidoPor | H FechaAtencion
        for it in items:
            tipo = str(it.get("tipo", "")).strip().upper()
            producto = str(it.get("descripcion", "")).strip().upper()
            cantidad = str(it.get("cantidad", "")).strip()

            if not tipo or not producto or not cantidad:
                continue

            wsS.append_row([fecha, usuario, tipo, producto, cantidad, "PENDIENTE", "", ""], value_input_option="USER_ENTERED")

        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/bandeja", methods=["GET"])
def bandeja():
    if requiere_login():
        return redirect(url_for("login"))

    if not es_almacenero_logueado():
        # Usuario normal no debe ver bandeja
        return redirect(url_for("solicitar"))

    try:
        _, wsS, _, _, _ = get_gsheets()
        rows = wsS.get_all_values()
        if not rows or len(rows) < 2:
            solicitudes = []
        else:
            header = [h.strip().upper() for h in rows[0]]
            data = rows[1:]

            # indices por nombre si existen
            def idx(col, default):
                return header.index(col) if col in header else default

            i_fecha = idx("FECHA", 0)
            i_usuario = idx("USUARIO", 1)
            i_tipo = idx("TIPO", 2)
            i_prod = idx("PRODUCTO", 3)
            i_cant = idx("CANTIDAD", 4)
            i_estado = idx("ESTADO", 5)

            solicitudes = []
            for n, r in enumerate(data, start=2):  # start=2 porque fila 1 es header
                # guardamos row_num para atender
                solicitudes.append({
                    "row": n,
                    "fecha": r[i_fecha] if len(r) > i_fecha else "",
                    "usuario": r[i_usuario] if len(r) > i_usuario else "",
                    "tipo": r[i_tipo] if len(r) > i_tipo else "",
                    "producto": r[i_prod] if len(r) > i_prod else "",
                    "cantidad": r[i_cant] if len(r) > i_cant else "",
                    "estado": (r[i_estado] if len(r) > i_estado else "").upper()
                })

        return render_template("bandeja.html", title="Bandeja", solicitudes=solicitudes)
    except Exception as e:
        # En vez de 500 feo, mostramos bandeja con error controlado
        return render_template("bandeja.html", title="Bandeja", solicitudes=[], error=str(e))


@app.route("/atender", methods=["POST"])
def atender():
    if requiere_login():
        return redirect(url_for("login"))

    if not es_almacenero_logueado():
        return redirect(url_for("solicitar"))

    row = int(request.form.get("row", "0") or "0")
    if row <= 1:
        return redirect(url_for("bandeja"))

    atendido_por = session.get("usuario", "").upper()
    fecha_at = _now_str()

    try:
        _, wsS, _, _, _ = get_gsheets()

        # Columna F = Estado, G = AtendidoPor, H = FechaAtencion
        wsS.update_cell(row, 6, "ATENDIDO")
        wsS.update_cell(row, 7, atendido_por)
        wsS.update_cell(row, 8, fecha_at)

        return redirect(url_for("bandeja"))
    except Exception:
        return redirect(url_for("bandeja"))


if __name__ == "__main__":
    app.run(debug=True)