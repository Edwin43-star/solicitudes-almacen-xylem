import os
import json
from datetime import datetime
from flask import Flask, render_template, request, redirect, session, url_for

import gspread
from google.oauth2.service_account import Credentials

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "super_secret_key_cambia_esto")

# =========================================================
#  CONFIG: SPREADSHEET ID (IMPORTANTE)
#  Usa el ID de tu Google Sheet (lo saqué de tu URL).
#  Si quieres, lo puedes poner como variable en Render:
#  SPREADSHEET_ID = 1asHBISZ2xwhcJ7sRocVqZ-7oLoj7iscF9Rc-xXJWps
# =========================================================
SPREADSHEET_ID = os.environ.get(
    "SPREADSHEET_ID",
    "1asHBISZ2xwhcJ7sRocVqZ-7oLoj7iscF9Rc-xXJWps"
)

# =========================================================
#  GOOGLE CREDS: lee desde env sin reventar
#  Acepta varias variables por si en Render lo pusiste distinto.
# =========================================================
def _load_service_account_info():
    # Opciones de nombres de variable (por tus logs)
    candidates = [
        "GOOGLE_SERVICE_ACCOUNT",
        "GOOGLE_CREDENTIALS",
        "GOOGLE_CREDENTIALIALS",  # por si quedó un typo en Render
        "SERVICE_ACCOUNT_JSON",
    ]
    for key in candidates:
        raw = os.environ.get(key)
        if raw:
            try:
                return json.loads(raw)
            except Exception as e:
                raise RuntimeError(
                    f"La variable {key} existe pero no es JSON válido. Error: {e}"
                )

    # Fallback: archivo local (solo si lo subiste al repo)
    if os.path.exists("service_account.json"):
        with open("service_account.json", "r", encoding="utf-8") as f:
            return json.load(f)

    raise RuntimeError(
        "No encuentro credenciales.\n"
        "En Render crea una Environment Variable con tu JSON del service account.\n"
        "Nombre recomendado: GOOGLE_SERVICE_ACCOUNT (valor = JSON completo)."
    )


# =========================================================
#  AUTH + ABRIR SHEET POR ID (evita Drive API)
# =========================================================
SERVICE_ACCOUNT_INFO = _load_service_account_info()

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
]

creds = Credentials.from_service_account_info(SERVICE_ACCOUNT_INFO, scopes=SCOPES)
client = gspread.authorize(creds)

SPREADSHEET = client.open_by_key(SPREADSHEET_ID)

# Hojas
SHEET_SOLICITUDES = SPREADSHEET.worksheet("Solicitudes")
SHEET_USUARIOS = SPREADSHEET.worksheet("Usuarios")
SHEET_ALMACENEROS = SPREADSHEET.worksheet("Almaceneros")
SHEET_CATALOGO = SPREADSHEET.worksheet("Catalogo")


# =========================================================
#  HELPERS
# =========================================================
def _is_logged():
    return "usuario" in session and "rol" in session


def _require_login():
    if not _is_logged():
        return redirect(url_for("login"))
    return None


def _require_role(role):
    if not _is_logged():
        return redirect(url_for("login"))
    if session.get("rol") != role:
        return redirect(url_for("login"))
    return None


def _buscar_personal_por_texto(texto):
    """
    Busca por código o por coincidencia en nombre dentro de hoja Usuarios.
    Debe existir al menos una columna NOMBRE.
    Si tu hoja tiene CODIGO y NOMBRE, mejor.
    """
    t = (texto or "").strip().upper()
    if not t:
        return None

    rows = SHEET_USUARIOS.get_all_records()  # lista dict
    # intenta match exacto por CODIGO si existe
    for r in rows:
        codigo = str(r.get("CODIGO", "")).strip().upper()
        nombre = str(r.get("NOMBRE", "")).strip().upper()
        if codigo and codigo == t:
            return {"codigo": codigo, "nombre": r.get("NOMBRE", "").strip()}
        if nombre and nombre == t:
            return {"codigo": r.get("CODIGO", ""), "nombre": r.get("NOMBRE", "").strip()}

    # match parcial por nombre
    for r in rows:
        nombre = str(r.get("NOMBRE", "")).strip().upper()
        if nombre and t in nombre:
            return {"codigo": r.get("CODIGO", ""), "nombre": r.get("NOMBRE", "").strip()}

    return None


def _validar_almacenero(usuario, clave):
    u = (usuario or "").strip().upper()
    c = (clave or "").strip()

    if not u or not c:
        return None

    rows = SHEET_ALMACENEROS.get_all_records()
    for r in rows:
        ru = str(r.get("USUARIO", "")).strip().upper()
        rc = str(r.get("CLAVE", "")).strip()
        activo = str(r.get("ACTIVO", "")).strip().upper()
        nombre = str(r.get("NOMBRE", "")).strip()

        if ru == u and rc == c and activo == "SI":
            return {"usuario": u, "nombre": nombre or u}

    return None


def _get_catalogo():
    """
    Espera columnas típicas: CODIGO, DESCRIPCION, TIPO, STOCK
    """
    rows = SHEET_CATALOGO.get_all_records()
    items = []
    for r in rows:
        codigo = str(r.get("CODIGO", "")).strip()
        desc = str(r.get("DESCRIPCION", "")).strip()
        tipo = str(r.get("TIPO", "")).strip().upper()
        stock = r.get("STOCK", 0)
        try:
            stock = int(stock)
        except:
            stock = 0

        if codigo and desc:
            items.append({
                "codigo": codigo,
                "descripcion": desc,
                "tipo": tipo,
                "stock": stock
            })
    return items


# =========================================================
#  ROUTES
# =========================================================
@app.route("/")
def home():
    # SI NO HAY SESION -> LOGIN
    if not _is_logged():
        return redirect(url_for("login"))

    # si ya hay sesión, manda según rol
    if session.get("rol") == "personal":
        return redirect(url_for("solicitar"))
    if session.get("rol") == "almacenero":
        return redirect(url_for("bandeja"))

    return redirect(url_for("login"))


@app.route("/login", methods=["GET"])
def login():
    return render_template("login.html")


# ---------- LOGIN PERSONAL ----------
@app.route("/login_personal", methods=["POST"])
def login_personal():
    texto = request.form.get("personal", "")
    encontrado = _buscar_personal_por_texto(texto)

    if not encontrado:
        # vuelve al login (puedes mostrar msg en HTML si quieres)
        return redirect(url_for("login"))

    session.clear()
    session["rol"] = "personal"
    session["usuario"] = encontrado["nombre"]  # clave ÚNICA para tu app
    session["nombre"] = encontrado["nombre"]
    session["codigo_personal"] = encontrado.get("codigo", "")
    session["carrito"] = []
    # ✅ directo a solicitar
    return redirect(url_for("solicitar"))


# ---------- LOGIN ALMACENERO ----------
@app.route("/login_almacenero", methods=["POST"])
def login_almacenero():
    usuario = request.form.get("usuario", "")
    clave = request.form.get("clave", "")

    ok = _validar_almacenero(usuario, clave)
    if not ok:
        return redirect(url_for("login"))

    session.clear()
    session["rol"] = "almacenero"
    session["usuario"] = ok["nombre"]
    session["nombre"] = ok["nombre"]
    session["usuario_login"] = ok["usuario"]
    return redirect(url_for("bandeja"))


@app.route("/inicio")
def inicio():
    # si entran a /inicio sin sesión, al login
    if not _is_logged():
        return redirect(url_for("login"))

    # personal mejor que vaya a solicitar
    if session.get("rol") == "personal":
        return redirect(url_for("solicitar"))

    # almacenero a bandeja
    if session.get("rol") == "almacenero":
        return redirect(url_for("bandeja"))

    return redirect(url_for("login"))


# ---------- SOLICITAR ----------
@app.route("/solicitar", methods=["GET"])
def solicitar():
    guard = _require_role("personal")
    if guard:
        return guard

    catalogo = _get_catalogo()
    tipos = sorted({i["tipo"] for i in catalogo if i["tipo"]})

    tipo_sel = (request.args.get("tipo") or "").strip().upper()
    items_filtrados = [i for i in catalogo if (not tipo_sel or i["tipo"] == tipo_sel)]

    carrito = session.get("carrito", [])

    return render_template(
        "solicitar.html",
        usuario=session.get("nombre", ""),
        tipos=tipos,
        tipo_sel=tipo_sel,
        items=items_filtrados,
        carrito=carrito
    )


# ---------- AGREGAR ITEM ----------
@app.route("/agregar", methods=["POST"])
def agregar():
    guard = _require_role("personal")
    if guard:
        return guard

    codigo = request.form.get("codigo", "").strip()
    descripcion = request.form.get("descripcion", "").strip()
    tipo = request.form.get("tipo", "").strip().upper()
    stock = request.form.get("stock", "0")
    cantidad = request.form.get("cantidad", "1")

    try:
        stock = int(stock)
    except:
        stock = 0

    try:
        cantidad = int(cantidad)
    except:
        cantidad = 1

    if cantidad < 1:
        cantidad = 1

    # opcional: validar contra stock
    if stock > 0 and cantidad > stock:
        cantidad = stock

    carrito = session.get("carrito", [])
    carrito.append({
        "codigo": codigo,
        "descripcion": descripcion,
        "tipo": tipo,
        "cantidad": cantidad,
        "stock": stock
    })
    session["carrito"] = carrito

    return redirect(url_for("solicitar", tipo=tipo))


# ---------- ELIMINAR ITEM ----------
@app.route("/eliminar/<int:i>")
def eliminar(i):
    guard = _require_role("personal")
    if guard:
        return guard

    carrito = session.get("carrito", [])
    if 0 <= i < len(carrito):
        carrito.pop(i)
    session["carrito"] = carrito
    return redirect(url_for("solicitar"))


# ---------- ENVIAR SOLICITUD ----------
@app.route("/enviar", methods=["POST"])
def enviar():
    guard = _require_role("personal")
    if guard:
        return guard

    carrito = session.get("carrito", [])
    if not carrito:
        return redirect(url_for("solicitar"))

    fecha = datetime.now().strftime("%d/%m/%Y")
    hora = datetime.now().strftime("%H:%M:%S")

    nombre_personal = session.get("nombre", "")
    # REGISTRADO: para personal, queda su propio nombre
    registrado = nombre_personal

    # columnas esperadas (según tu sheet):
    # FECHA | HORA | CODIGO | NOMBRE | TIPO | DESCRIPCION | CANTIDAD | ESTADO | REGISTRADO
    for item in carrito:
        SHEET_SOLICITUDES.append_row([
            fecha,
            hora,
            item.get("codigo", ""),
            nombre_personal,
            item.get("tipo", ""),
            item.get("descripcion", ""),
            int(item.get("cantidad", 1)),
            "PENDIENTE",
            registrado
        ])

    # limpiar carrito
    session["carrito"] = []
    # vuelve a solicitar
    return redirect(url_for("solicitar"))


# ---------- BANDEJA (ALMACENERO) ----------
@app.route("/bandeja")
def bandeja():
    guard = _require_role("almacenero")
    if guard:
        return guard

    rows = SHEET_SOLICITUDES.get_all_records()
    pendientes = []
    for r in rows:
        estado = str(r.get("ESTADO", "")).strip().upper()
        if estado == "PENDIENTE":
            pendientes.append(r)

    return render_template("bandeja.html", solicitudes=pendientes, usuario=session.get("nombre", ""))


# ---------- SALIR ----------
@app.route("/salir")
def salir():
    session.clear()
    return redirect(url_for("login"))


if __name__ == "__main__":
    app.run(debug=True)