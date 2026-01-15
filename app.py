from flask import Flask, render_template, request, redirect, session, url_for, jsonify, flash
from datetime import datetime, timezone
import os, json

import gspread
from google.oauth2.service_account import Credentials

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "xylem-secret-key")

# =========================
# GOOGLE SHEETS (BLINDADO)
# =========================
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# OJO: aceptamos varios nombres por si Render los creó con otro nombre
SPREADSHEET_KEY = (os.environ.get("SPREADSHEET_KEY")
                   or os.environ.get("SHEET_KEY")
                   or os.environ.get("GOOGLE_SHEET_KEY")
                   or "").strip()

GOOGLE_CREDENTIALS_JSON = (os.environ.get("GOOGLE_CREDENTIALS_JSON")
                           or os.environ.get("GOOGLE_CREDENTIALS")
                           or os.environ.get("GOOGLE_CREDENTIALIALS")  # por si lo escribiste así
                           or "").strip()

_gs_client = None
_ws_solicitudes = None
_ws_catalogo = None
_ws_usuarios = None
_ws_almaceneros = None


def now_str():
    return datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M:%S UTC")


def init_gsheets():
    """
    Inicializa el cliente y hojas. Si algo falla, lanza error con mensaje claro.
    """
    global _gs_client, _ws_solicitudes, _ws_catalogo, _ws_usuarios, _ws_almaceneros

    if _gs_client is not None:
        return

    if not SPREADSHEET_KEY:
        raise RuntimeError("FALTA SPREADSHEET_KEY en Render Environment (ID del Sheet).")

    if not GOOGLE_CREDENTIALS_JSON:
        raise RuntimeError("FALTA GOOGLE_CREDENTIALS_JSON en Render Environment (JSON del service account).")

    # Intentar parsear el JSON
    try:
        creds_dict = json.loads(GOOGLE_CREDENTIALS_JSON)
    except Exception as e:
        raise RuntimeError(f"GOOGLE_CREDENTIALS_JSON NO ES JSON VALIDO: {e}")

    # Crear credenciales
    try:
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    except Exception as e:
        raise RuntimeError(f"ERROR creando credenciales: {e}")

    # Autorizar
    _gs_client = gspread.authorize(creds)

    # Abrir por key (NO requiere Drive scope)
    sh = _gs_client.open_by_key(SPREADSHEET_KEY)

    # Cargar hojas exactas
    try:
        _ws_solicitudes = sh.worksheet("Solicitudes")
        _ws_catalogo = sh.worksheet("Catalogo")
        _ws_usuarios = sh.worksheet("Usuarios")
        _ws_almaceneros = sh.worksheet("Almaceneros")
    except Exception as e:
        raise RuntimeError(f"NO ENCUENTRO UNA HOJA (Solicitudes/Catalogo/Usuarios/Almaceneros): {e}")


def get_ws():
    init_gsheets()
    return _ws_solicitudes, _ws_catalogo, _ws_usuarios, _ws_almaceneros


# =========================
# HELPERS
# =========================
def requiere_login():
    return "usuario" not in session


def es_almacenero():
    return session.get("rol") == "almacenero"


def cargar_almaceneros():
    _, _, _, wsA = get_ws()
    rows = wsA.get_all_values()
    if len(rows) < 2:
        return {}

    header = [h.strip().upper() for h in rows[0]]
    data = rows[1:]

    def idx(col, default):
        return header.index(col) if col in header else default

    i_user = idx("USUARIO", 0)
    i_pass = idx("CLAVE", 1)
    i_name = idx("NOMBRE", 2)
    i_act = idx("ACTIVO", 3)

    out = {}
    for r in data:
        if len(r) <= max(i_user, i_pass, i_name, i_act):
            continue
        u = r[i_user].strip().upper()
        p = r[i_pass].strip()
        n = r[i_name].strip().upper()
        a = r[i_act].strip().upper()
        if u and a == "SI":
            out[u] = {"clave": p, "nombre": n}
    return out


def cargar_usuarios():
    _, _, wsU, _ = get_ws()
    rows = wsU.get_all_values()
    if len(rows) < 2:
        return set()

    header = [h.strip().upper() for h in rows[0]]
    data = rows[1:]

    def idx(col, default):
        return header.index(col) if col in header else default

    i_name = idx("NOMBRE", 1)
    i_act = idx("ACTIVO", 4)

    out = set()
    for r in data:
        if len(r) <= max(i_name, i_act):
            continue
        n = r[i_name].strip().upper()
        a = r[i_act].strip().upper()
        if n and a == "SI":
            out.add(n)
    return out


def cargar_catalogo():
    _, wsC, _, _ = get_ws()
    rows = wsC.get_all_values()
    if len(rows) < 2:
        return {}

    header = [h.strip().upper() for h in rows[0]]
    data = rows[1:]

    def idx(col, default):
        return header.index(col) if col in header else default

    i_tipo = idx("TIPO", 0)
    i_desc = idx("DESCRIPCION", 1)
    i_act = header.index("ACTIVO") if "ACTIVO" in header else None

    cat = {}
    for r in data:
        if len(r) <= max(i_tipo, i_desc):
            continue
        tipo = r[i_tipo].strip().upper()
        desc = r[i_desc].strip().upper()
        activo_ok = True
        if i_act is not None and len(r) > i_act:
            activo_ok = (r[i_act].strip().upper() != "NO")

        if tipo and desc and activo_ok:
            cat.setdefault(tipo, []).append(desc)

    for k in cat:
        cat[k] = sorted(list(set(cat[k])))

    # asegurar tipos
    for t in ["EPP", "CONSUMIBLE", "EQUIPOS Y HERRAMIENTAS"]:
        cat.setdefault(t, [])

    return cat


# =========================
# RUTAS (SIN DUPLICADOS)
# =========================
@app.route("/", methods=["GET"])
def home():
    if "usuario" in session:
        return redirect(url_for("bandeja") if es_almacenero() else url_for("solicitar"))
    return redirect(url_for("login"))


@app.route("/health")
def health():
    """
    Útil para ver en el navegador si Render está leyendo variables y hojas.
    """
    try:
        init_gsheets()
        return jsonify({"ok": True, "sheet_key_ok": bool(SPREADSHEET_KEY), "creds_ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "sheet_key_ok": bool(SPREADSHEET_KEY), "creds_len": len(GOOGLE_CREDENTIALS_JSON)}), 500


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = (request.form.get("usuario") or "").strip().upper()
        pwd = (request.form.get("clave") or "").strip()

        if not user:
            flash("Ingrese usuario.", "danger")
            return render_template("login.html", title="Login")

        try:
            almaceneros = cargar_almaceneros()
            if user in almaceneros:
                if pwd == almaceneros[user]["clave"]:
                    session["usuario"] = almaceneros[user]["nombre"]
                    session["rol"] = "almacenero"
                    return redirect(url_for("bandeja"))
                flash("Clave incorrecta.", "danger")
                return render_template("login.html", title="Login")

            usuarios = cargar_usuarios()
            if user in usuarios:
                session["usuario"] = user
                session["rol"] = "usuario"
                return redirect(url_for("solicitar"))

            flash("Usuario no encontrado o inactivo.", "danger")
            return render_template("login.html", title="Login")

        except Exception as e:
            # Muestra error exacto (para que no te frustres adivinando)
            flash(f"ERROR: {e}", "danger")
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
    return render_template("solicitar.html", title="Nueva Solicitud")


@app.route("/api/catalogo", methods=["GET"])
def api_catalogo():
    if requiere_login():
        return jsonify({"ok": False, "error": "No autenticado"}), 401
    try:
        cat = cargar_catalogo()
        return jsonify({"ok": True, "catalogo": cat})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/enviar_solicitud", methods=["POST"])
def enviar_solicitud():
    if requiere_login():
        return jsonify({"ok": False, "error": "No autenticado"}), 401

    payload = request.get_json(silent=True) or {}
    items = payload.get("items", [])

    if not items:
        return jsonify({"ok": False, "error": "No hay items para enviar"}), 400

    fecha = now_str()
    usuario = session.get("usuario", "").upper()

    try:
        wsS, _, _, _ = get_ws()

        for it in items:
            tipo = str(it.get("tipo", "")).strip().upper()
            prod = str(it.get("descripcion", "")).strip().upper()
            cant = str(it.get("cantidad", "")).strip()
            if not tipo or not prod or not cant:
                continue
            wsS.append_row([fecha, usuario, tipo, prod, cant, "PENDIENTE", "", ""],
                           value_input_option="USER_ENTERED")

        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/bandeja", methods=["GET"])
def bandeja():
    if requiere_login():
        return redirect(url_for("login"))
    if not es_almacenero():
        return redirect(url_for("solicitar"))

    try:
        wsS, _, _, _ = get_ws()
        rows = wsS.get_all_values()
        if len(rows) < 2:
            return render_template("bandeja.html", title="Bandeja", solicitudes=[])

        header = [h.strip().upper() for h in rows[0]]
        data = rows[1:]

        def idx(col, default):
            return header.index(col) if col in header else default

        i_fecha = idx("FECHA", 0)
        i_user = idx("USUARIO", 1)
        i_tipo = idx("TIPO", 2)
        i_prod = idx("PRODUCTO", 3)
        i_cant = idx("CANTIDAD", 4)
        i_est = idx("ESTADO", 5)

        solicitudes = []
        for n, r in enumerate(data, start=2):
            solicitudes.append({
                "row": n,
                "fecha": r[i_fecha] if len(r) > i_fecha else "",
                "usuario": r[i_user] if len(r) > i_user else "",
                "tipo": r[i_tipo] if len(r) > i_tipo else "",
                "producto": r[i_prod] if len(r) > i_prod else "",
                "cantidad": r[i_cant] if len(r) > i_cant else "",
                "estado": (r[i_est] if len(r) > i_est else "").upper()
            })

        return render_template("bandeja.html", title="Bandeja", solicitudes=solicitudes)

    except Exception as e:
        return render_template("bandeja.html", title="Bandeja", solicitudes=[], error=str(e))


@app.route("/atender", methods=["POST"])
def atender():
    if requiere_login():
        return redirect(url_for("login"))
    if not es_almacenero():
        return redirect(url_for("solicitar"))

    row = int(request.form.get("row", "0") or "0")
    if row <= 1:
        return redirect(url_for("bandeja"))

    try:
        wsS, _, _, _ = get_ws()
        wsS.update_cell(row, 6, "ATENDIDO")
        wsS.update_cell(row, 7, session.get("usuario", "").upper())
        wsS.update_cell(row, 8, now_str())
        return redirect(url_for("bandeja"))
    except Exception:
        return redirect(url_for("bandeja"))


if __name__ == "__main__":
    app.run(debug=True)