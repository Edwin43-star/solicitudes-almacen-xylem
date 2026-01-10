from flask import Flask, render_template, request, redirect, url_for, jsonify, session, abort, flash
import os
import json
from datetime import datetime

import gspread
from google.oauth2.service_account import Credentials


# =========================================================
# CONFIG
# =========================================================
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-change-me")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "").strip()

# Nombres de hojas (Sheets)
SHEET_SOLICITUDES = "Solicitudes"
SHEET_CATALOGO = "Catalogo"
SHEET_USUARIOS = "Usuarios"
SHEET_ALMACENEROS = "Almaceneros"   # <-- crea esta hoja

# Cache simple en memoria (para catálogo/usuarios)
_cache = {
    "catalogo": {"ts": 0, "data": []},
    "usuarios": {"ts": 0, "data": []},
}
CACHE_SECONDS = 60


# =========================================================
# GOOGLE AUTH (Render: ENV VAR / Local: file opcional)
# =========================================================
def _get_gspread_client():
    """
    Render: GOOGLE_SERVICE_ACCOUNT debe contener el JSON COMPLETO (pegado).
    Local: si no existe esa variable, intenta usar service_account.json (opcional).
    """
    env_json = os.getenv("GOOGLE_SERVICE_ACCOUNT", "").strip()

    if env_json:
        info = json.loads(env_json)
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    else:
        # SOLO para local (no recomendado para Render)
        creds = Credentials.from_service_account_file("service_account.json", scopes=SCOPES)

    return gspread.authorize(creds)


def _open_spreadsheet():
    if not SPREADSHEET_ID:
        raise RuntimeError("Falta SPREADSHEET_ID en Render (Environment Variables).")
    client = _get_gspread_client()
    return client.open_by_key(SPREADSHEET_ID)


def ws(name: str):
    sh = _open_spreadsheet()
    return sh.worksheet(name)


# =========================================================
# HELPERS
# =========================================================
def now_date_time():
    # fecha/hora local del servidor (Render usa UTC, pero sirve)
    # si quieres hora PERÚ exacta luego lo ajustamos con pytz
    return datetime.now().strftime("%d/%m/%Y"), datetime.now().strftime("%H:%M:%S")


def normalize(s: str) -> str:
    return (s or "").strip()


def is_logged_in():
    return bool(session.get("role"))


def require_login():
    if not is_logged_in():
        return redirect(url_for("login"))
    return None


def require_role(role_name: str):
    if session.get("role") != role_name:
        abort(403)


def get_session_user_name():
    return session.get("user_name", "")


# =========================================================
# LOAD DATA (CATALOGO / USUARIOS) con cache
# =========================================================
def get_catalogo_cached(force=False):
    import time
    t = time.time()
    if (not force) and (t - _cache["catalogo"]["ts"] < CACHE_SECONDS) and _cache["catalogo"]["data"]:
        return _cache["catalogo"]["data"]

    w = ws(SHEET_CATALOGO)
    rows = w.get_all_records()  # usa encabezados fila 1
    # Espera columnas: CODIGO, TIPO, DESCRIPCION, U.M, STOCK, ACTIVO
    data = []
    for r in rows:
        activo = normalize(r.get("ACTIVO", "SI")).upper()
        if activo != "SI":
            continue
        data.append({
            "codigo": normalize(r.get("CODIGO", "")),
            "tipo": normalize(r.get("TIPO", "")),
            "descripcion": normalize(r.get("DESCRIPCION", "")),
            "um": normalize(r.get("U.M", r.get("UM", ""))),
            "stock": int(r.get("STOCK", 0) or 0),
        })

    _cache["catalogo"] = {"ts": t, "data": data}
    return data


def get_usuarios_cached(force=False):
    import time
    t = time.time()
    if (not force) and (t - _cache["usuarios"]["ts"] < CACHE_SECONDS) and _cache["usuarios"]["data"]:
        return _cache["usuarios"]["data"]

    w = ws(SHEET_USUARIOS)
    rows = w.get_all_records()
    # Espera columnas: CODIGO, NOMBRE, AREA, CARGO, ACTIVO
    data = []
    for r in rows:
        activo = normalize(r.get("ACTIVO", "SI")).upper()
        if activo != "SI":
            continue
        data.append({
            "codigo": str(r.get("CODIGO", "")).strip(),
            "nombre": normalize(r.get("NOMBRE", "")),
            "area": normalize(r.get("AREA", "")),
            "cargo": normalize(r.get("CARGO", "")),
        })

    _cache["usuarios"] = {"ts": t, "data": data}
    return data


# =========================================================
# AUTH: LOGIN / LOGOUT
# =========================================================
@app.route("/login", methods=["GET", "POST"])
def login():
    # POST: personal o almacenero
    if request.method == "POST":
        mode = request.form.get("mode")  # "personal" o "almacenero"

        if mode == "personal":
            # Personal: SIN contraseña
            valor = normalize(request.form.get("usuario_personal"))
            if not valor:
                flash("Ingresa tu CÓDIGO o selecciona tu nombre.", "error")
                return redirect(url_for("login"))

            usuarios = get_usuarios_cached(force=True)

            # Permite: "1001 - NOMBRE..." o solo "1001" o nombre
            codigo = ""
            if " - " in valor:
                codigo = valor.split(" - ")[0].strip()
            elif valor.isdigit():
                codigo = valor.strip()

            elegido = None
            if codigo:
                for u in usuarios:
                    if u["codigo"] == codigo:
                        elegido = u
                        break
            else:
                # buscar por nombre (primer match)
                vup = valor.upper()
                for u in usuarios:
                    if vup in u["nombre"].upper():
                        elegido = u
                        break

            if not elegido:
                flash("Usuario no encontrado o no activo.", "error")
                return redirect(url_for("login"))

            session.clear()
            session["role"] = "personal"
            session["user_code"] = elegido["codigo"]
            session["user_name"] = elegido["nombre"]
            session["user_area"] = elegido["area"]
            session["user_cargo"] = elegido["cargo"]
            return redirect(url_for("inicio"))

        elif mode == "almacenero":
            # Almacenero: CON contraseña (en hoja Almaceneros)
            user = normalize(request.form.get("user_alm"))
            pwd = normalize(request.form.get("pass_alm"))
            if not user or not pwd:
                flash("Ingresa usuario y contraseña.", "error")
                return redirect(url_for("login"))

            w = ws(SHEET_ALMACENEROS)
            rows = w.get_all_records()
            # Espera columnas: USUARIO, CLAVE, NOMBRE, ACTIVO
            ok = None
            for r in rows:
                if normalize(r.get("ACTIVO", "SI")).upper() != "SI":
                    continue
                if normalize(r.get("USUARIO", "")).lower() == user.lower() and normalize(r.get("CLAVE", "")) == pwd:
                    ok = {
                        "nombre": normalize(r.get("NOMBRE", user)),
                        "usuario": user
                    }
                    break

            if not ok:
                flash("Credenciales incorrectas.", "error")
                return redirect(url_for("login"))

            session.clear()
            session["role"] = "almacenero"
            session["user_name"] = ok["nombre"]   # aquí debe salir EDWIN ROMERO / EDGAR GARCIA
            session["user_user"] = ok["usuario"]
            return redirect(url_for("inicio"))

        else:
            flash("Modo inválido.", "error")
            return redirect(url_for("login"))

    # GET
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# =========================================================
# VISTAS
# =========================================================
@app.route("/")
def inicio():
    guard = require_login()
    if guard:
        return guard

    return render_template(
        "inicio.html",
        role=session.get("role"),
        user_name=get_session_user_name()
    )


@app.route("/solicitar")
def solicitar():
    guard = require_login()
    if guard:
        return guard

    # quien solicita (personal o almacenero)
    solicitante = get_session_user_name()
    role = session.get("role")

    return render_template(
        "solicitar.html",
        solicitante=solicitante,
        role=role
    )


# =========================================================
# API: usuarios / tipos / catalogo / stock
# =========================================================
@app.route("/api/usuarios")
def api_usuarios():
    guard = require_login()
    if guard:
        return guard

    q = normalize(request.args.get("q", "")).upper()
    usuarios = get_usuarios_cached()
    out = []
    for u in usuarios:
        label = f'{u["codigo"]} - {u["nombre"]}'
        if not q or q in label.upper():
            out.append(label)
        if len(out) >= 50:
            break
    return jsonify(out)


@app.route("/api/tipos")
def api_tipos():
    guard = require_login()
    if guard:
        return guard

    cat = get_catalogo_cached()
    tipos = sorted({c["tipo"] for c in cat if c["tipo"]})
    return jsonify(tipos)


@app.route("/api/catalogo")
def api_catalogo():
    guard = require_login()
    if guard:
        return guard

    tipo = normalize(request.args.get("tipo", ""))
    q = normalize(request.args.get("q", "")).upper()

    cat = get_catalogo_cached()
    items = []
    for c in cat:
        if tipo and c["tipo"].upper() != tipo.upper():
            continue

        label = f'{c["codigo"]} - {c["descripcion"]}'
        if q and q not in label.upper():
            continue

        items.append({
            "codigo": c["codigo"],
            "descripcion": c["descripcion"],
            "um": c["um"],
            "stock": c["stock"],
            "tipo": c["tipo"],
            "label": label
        })

        if len(items) >= 80:
            break

    return jsonify(items)


@app.route("/api/stock/<codigo>")
def api_stock(codigo):
    guard = require_login()
    if guard:
        return guard

    codigo = normalize(codigo)
    cat = get_catalogo_cached()
    for c in cat:
        if c["codigo"] == codigo:
            return jsonify({"codigo": codigo, "stock": c["stock"], "um": c["um"], "tipo": c["tipo"], "descripcion": c["descripcion"]})
    return jsonify({"error": "no_encontrado"}), 404


# =========================================================
# ENVIAR SOLICITUD (VALIDA STOCK)
# =========================================================
@app.route("/enviar", methods=["POST"])
def enviar():
    guard = require_login()
    if guard:
        return guard

    solicitante = get_session_user_name()
    tipo = normalize(request.form.get("tipo"))
    codigo = normalize(request.form.get("codigo"))
    descripcion = normalize(request.form.get("descripcion"))
    cantidad = normalize(request.form.get("cantidad"))

    if not all([solicitante, tipo, codigo, descripcion, cantidad]):
        return "Faltan datos", 400

    try:
        cant_int = int(cantidad)
    except ValueError:
        return "Cantidad inválida", 400

    if cant_int <= 0:
        return "Cantidad inválida", 400

    # validar producto y stock
    cat = get_catalogo_cached(force=True)
    prod = None
    for c in cat:
        if c["codigo"] == codigo:
            prod = c
            break

    if not prod:
        return "Producto no existe", 400

    if prod["tipo"].upper() != tipo.upper():
        return "Tipo no corresponde al producto", 400

    if cant_int > int(prod["stock"]):
        return f"Stock insuficiente. Disponible: {prod['stock']}", 400

    fecha, hora = now_date_time()

    # Guardar solicitud (REGISTRADO debe ser almacenero, así que al crear: vacío)
    w = ws(SHEET_SOLICITUDES)
    # Encabezado esperado:
    # FECHA | HORA | CODIGO | NOMBRE | TIPO | DESCRIPCION | CANTIDAD | ESTADO | REGISTRADO
    w.append_row([
        fecha,
        hora,
        codigo,
        solicitante,
        tipo,
        descripcion,
        cant_int,
        "PENDIENTE",
        ""  # <-- registrado lo llena el almacenero en bandeja (Edwin/Edgar)
    ])

    return redirect(url_for("inicio"))


# =========================================================
# BANDEJA (SOLO ALMACENEROS)
# =========================================================
@app.route("/bandeja")
def bandeja():
    guard = require_login()
    if guard:
        return guard
    require_role("almacenero")

    estado = normalize(request.args.get("estado", "PENDIENTE")).upper()

    w = ws(SHEET_SOLICITUDES)
    values = w.get_all_values()

    # values[0] = encabezados
    if len(values) <= 1:
        rows = []
    else:
        headers = values[0]
        data = values[1:]

        # armado con índice de fila real (sheet row number)
        rows = []
        for i, row in enumerate(data, start=2):  # start=2 porque fila 1 es header
            # proteger tamaños
            row = row + [""] * (len(headers) - len(row))
            rec = dict(zip(headers, row))
            if normalize(rec.get("ESTADO", "")).upper() == estado:
                rec["_rownum"] = i
                rows.append(rec)

        # mostrar recientes primero
        rows.reverse()

    return render_template(
        "bandeja.html",
        rows=rows,
        estado=estado,
        user_name=get_session_user_name()
    )


@app.route("/bandeja/accion", methods=["POST"])
def bandeja_accion():
    guard = require_login()
    if guard:
        return guard
    require_role("almacenero")

    accion = normalize(request.form.get("accion")).upper()  # APROBAR / DESPACHAR
    rownum = normalize(request.form.get("rownum"))
    if not rownum.isdigit():
        return "Fila inválida", 400

    rownum = int(rownum)
    almacenero = get_session_user_name()

    w = ws(SHEET_SOLICITUDES)
    headers = w.row_values(1)

    # ubicar columnas
    def col_index(name):
        try:
            return headers.index(name) + 1
        except ValueError:
            return None

    col_estado = col_index("ESTADO")
    col_reg = col_index("REGISTRADO")

    if not col_estado or not col_reg:
        return "Faltan columnas ESTADO o REGISTRADO en Solicitudes", 500

    if accion == "APROBAR":
        w.update_cell(rownum, col_estado, "APROBADO")
        w.update_cell(rownum, col_reg, almacenero)
    elif accion == "DESPACHAR":
        w.update_cell(rownum, col_estado, "DESPACHADO")
        w.update_cell(rownum, col_reg, almacenero)
    else:
        return "Acción inválida", 400

    return redirect(url_for("bandeja", estado=request.form.get("estado_back", "PENDIENTE")))


# =========================================================
# RUN LOCAL
# =========================================================
if __name__ == "__main__":
    app.run(debug=True)