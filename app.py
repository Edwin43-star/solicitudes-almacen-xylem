import os
import json
from datetime import datetime
from flask import Flask, render_template, request, redirect, session, url_for, jsonify, abort

import gspread
from google.oauth2.service_account import Credentials

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "xylem-secret-key")

# ============================================================
# GOOGLE SHEETS (UN SOLO ARCHIVO)
# ============================================================
# ID de tu Google Sheet (de tu URL):
SHEET_ID = os.environ.get("SHEET_ID", "1asHBISZ2xwhcJ7sRocVqZ-7oLoj7iscF9Rc-xXJWpy")

# Nombres de hojas EXACTAS (según tus capturas)
WS_SOLICITUDES = os.environ.get("WS_SOLICITUDES", "Solicitudes")
WS_CATALOGO    = os.environ.get("WS_CATALOGO", "Catalogo")
WS_USUARIOS    = os.environ.get("WS_USUARIOS", "Usuarios")       # personal (CODIGO, NOMBRE, AREA, CARGO, ACTIVO)
WS_ALMACENEROS = os.environ.get("WS_ALMACENEROS", "Almaceneros")  # credenciales almaceneros (USUARIO, CLAVE, NOMBRE, ACTIVO)

# Scopes correctos para evitar 403 (Drive + Sheets)
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

_gc = None
_sh = None


def _get_gspread_client() -> gspread.Client:
    """
    Crea cliente gspread desde GOOGLE_CREDENTIALS (JSON completo del service account).
    IMPORTANTE en Render: debe existir env var GOOGLE_CREDENTIALS.
    """
    global _gc

    if _gc is not None:
        return _gc

    raw = os.environ.get("GOOGLE_CREDENTIALS")
    if not raw:
        raise RuntimeError(
            "Falta la variable de entorno GOOGLE_CREDENTIALS (JSON del Service Account). "
            "En Render > Environment, crea GOOGLE_CREDENTIALS y pega el JSON completo."
        )

    try:
        info = json.loads(raw)
    except Exception as e:
        raise RuntimeError("GOOGLE_CREDENTIALS no es JSON válido. Revisa comillas/pegado.") from e

    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    _gc = gspread.authorize(creds)
    return _gc


def _get_sheet():
    """Abre el Spreadsheet por ID (mejor que por nombre, evita errores de scope/listado)."""
    global _sh
    if _sh is not None:
        return _sh
    gc = _get_gspread_client()
    _sh = gc.open_by_key(SHEET_ID)
    return _sh


def _ws(name: str):
    """Obtiene worksheet por nombre."""
    return _get_sheet().worksheet(name)


def _normalize(s: str) -> str:
    return (s or "").strip().upper()


def _find_col(headers, *candidates):
    """
    Busca una columna por nombre (case-insensitive).
    candidates: posibles nombres (ej: 'DESCRIPCION', 'PRODUCTO')
    """
    h = [_normalize(x) for x in headers]
    for cand in candidates:
        cand_u = _normalize(cand)
        if cand_u in h:
            return h.index(cand_u)
    return None


def _safe_cell(row, idx, default=""):
    try:
        return row[idx]
    except Exception:
        return default


# ============================================================
# AUTH / LOGIN
# ============================================================
def _is_logged_in():
    return bool(session.get("user_name"))


def _is_almacenero():
    return session.get("role") == "almacenero"


@app.route("/")
def home():
    # Si ya está logueado
    if _is_logged_in():
        return redirect(url_for("bandeja" if _is_almacenero() else "solicitar"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None

    if request.method == "POST":
        usuario = (request.form.get("usuario") or "").strip()
        clave   = (request.form.get("clave") or "").strip()

        if not usuario:
            error = "Ingrese usuario."
            return render_template("login.html", error=error)

        # 1) Intentar como almacenero (USUARIO/CLAVE)
        try:
            wsA = _ws(WS_ALMACENEROS)
            data = wsA.get_all_values()
            if len(data) >= 2:
                headers = data[0]
                rows = data[1:]

                i_user = _find_col(headers, "USUARIO")
                i_pass = _find_col(headers, "CLAVE")
                i_name = _find_col(headers, "NOMBRE")
                i_act  = _find_col(headers, "ACTIVO")

                for r in rows:
                    u = _normalize(_safe_cell(r, i_user))
                    p = str(_safe_cell(r, i_pass)).strip()
                    activo = _normalize(_safe_cell(r, i_act, "SI"))

                    if u == _normalize(usuario) and activo == "SI" and clave and clave == p:
                        session["role"] = "almacenero"
                        session["user_name"] = _safe_cell(r, i_name, usuario).strip() or usuario
                        return redirect(url_for("bandeja"))
        except Exception as e:
            # Si falla Google, mostramos error claro
            error = f"Error conectando a Google Sheets (Almaceneros). {e}"
            return render_template("login.html", error=error)

        # 2) Si no pasó como almacenero, intentar como PERSONAL por CODIGO (sin clave obligatoria)
        #    (Tu hoja Usuarios es personal: CODIGO, NOMBRE, AREA, CARGO, ACTIVO)
        try:
            wsU = _ws(WS_USUARIOS)
            data = wsU.get_all_values()
            if len(data) >= 2:
                headers = data[0]
                rows = data[1:]

                i_cod = _find_col(headers, "CODIGO")
                i_nom = _find_col(headers, "NOMBRE")
                i_act = _find_col(headers, "ACTIVO")

                for r in rows:
                    cod = str(_safe_cell(r, i_cod)).strip()
                    activo = _normalize(_safe_cell(r, i_act, "SI"))
                    if cod == usuario and activo == "SI":
                        session["role"] = "usuario"
                        session["user_name"] = _safe_cell(r, i_nom, usuario).strip() or usuario
                        session["user_code"] = cod
                        return redirect(url_for("solicitar"))
        except Exception as e:
            error = f"Error conectando a Google Sheets (Usuarios). {e}"
            return render_template("login.html", error=error)

        error = "Usuario/clave incorrectos o usuario no activo."

    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ============================================================
# CATALOGO API
# ============================================================
@app.route("/api/catalogo", methods=["GET"])
def api_catalogo():
    if not _is_logged_in():
        return jsonify({"ok": False, "error": "No autorizado"}), 401

    try:
        wsC = _ws(WS_CATALOGO)
        data = wsC.get_all_values()
        if len(data) < 2:
            return jsonify({"ok": True, "items": []})

        headers = data[0]
        rows = data[1:]

        i_tipo = _find_col(headers, "TIPO")
        i_desc = _find_col(headers, "DESCRIPCION", "PRODUCTO", "ITEM")
        i_act  = _find_col(headers, "ACTIVO")

        items = []
        for r in rows:
            tipo = _normalize(_safe_cell(r, i_tipo))
            desc = (_safe_cell(r, i_desc) or "").strip()
            activo = _normalize(_safe_cell(r, i_act, "SI"))

            if not desc:
                continue
            if activo != "SI":
                continue

            # Normalizamos tipos permitidos
            if tipo not in ["EPP", "CONSUMIBLE", "EQUIPO", "HERRAMIENTA"]:
                # si viene vacío, lo dejamos como "EPP" por defecto
                if not tipo:
                    tipo = "EPP"
                else:
                    # lo guardamos igual pero no rompe
                    pass

            items.append({"tipo": tipo, "descripcion": desc})

        return jsonify({"ok": True, "items": items})

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ============================================================
# SOLICITAR
# ============================================================
@app.route("/solicitar", methods=["GET"])
def solicitar():
    if not _is_logged_in():
        return redirect(url_for("login"))
    # almacenero no debe solicitar
    if _is_almacenero():
        return redirect(url_for("bandeja"))

    return render_template("solicitar.html", user_name=session.get("user_name", ""))


@app.route("/api/guardar_solicitud", methods=["POST"])
def api_guardar_solicitud():
    if not _is_logged_in():
        return jsonify({"ok": False, "error": "No autorizado"}), 401
    if _is_almacenero():
        return jsonify({"ok": False, "error": "Un almacenero no registra solicitudes aquí."}), 403

    payload = request.get_json(silent=True) or {}
    items = payload.get("items", [])

    if not isinstance(items, list) or len(items) == 0:
        return jsonify({"ok": False, "error": "No hay ítems para enviar."}), 400

    try:
        wsS = _ws(WS_SOLICITUDES)

        fecha = datetime.now().strftime("%d/%m/%Y %H:%M")
        usuario = session.get("user_name", "").strip() or "SIN NOMBRE"

        # Guardamos 1 fila por item (simple y robusto)
        # Columnas recomendadas:
        # FECHA | USUARIO | TIPO | PRODUCTO | CANTIDAD | ESTADO
        for it in items:
            tipo = (it.get("tipo") or "").strip().upper()
            desc = (it.get("descripcion") or "").strip()
            cant = it.get("cantidad")

            try:
                cant = int(cant)
            except Exception:
                cant = 1

            if not desc:
                continue

            estado = "PENDIENTE"
            wsS.append_row([fecha, usuario, tipo, desc, cant, estado], value_input_option="USER_ENTERED")

        return jsonify({"ok": True})

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ============================================================
# BANDEJA (ALMACENERO)
# ============================================================
@app.route("/bandeja", methods=["GET"])
def bandeja():
    if not _is_logged_in():
        return redirect(url_for("login"))
    if not _is_almacenero():
        return redirect(url_for("solicitar"))

    try:
        wsS = _ws(WS_SOLICITUDES)
        data = wsS.get_all_values()
        if len(data) < 2:
            solicitudes = []
        else:
            # Asumimos:
            # 0 FECHA | 1 USUARIO | 2 TIPO | 3 PRODUCTO | 4 CANTIDAD | 5 ESTADO
            rows = data[1:]
            solicitudes = []
            for i, r in enumerate(rows, start=2):  # fila real en sheet
                solicitudes.append({
                    "row": i,
                    "fecha": _safe_cell(r, 0),
                    "usuario": _safe_cell(r, 1),
                    "tipo": _safe_cell(r, 2),
                    "producto": _safe_cell(r, 3),
                    "cantidad": _safe_cell(r, 4),
                    "estado": _safe_cell(r, 5, "PENDIENTE"),
                })

        return render_template(
            "bandeja.html",
            user_name=session.get("user_name", ""),
            solicitudes=solicitudes
        )

    except Exception as e:
        # Error visible (para que no te salga “Internal Server Error” sin explicación)
        return f"<h2>Error cargando bandeja:</h2><pre>{e}</pre>", 500


@app.route("/api/cambiar_estado", methods=["POST"])
def api_cambiar_estado():
    if not _is_logged_in():
        return jsonify({"ok": False, "error": "No autorizado"}), 401
    if not _is_almacenero():
        return jsonify({"ok": False, "error": "Solo almaceneros"}), 403

    payload = request.get_json(silent=True) or {}
    row = payload.get("row")
    estado = (payload.get("estado") or "").strip().upper()

    if estado not in ["PENDIENTE", "ATENDIDO"]:
        return jsonify({"ok": False, "error": "Estado inválido"}), 400

    try:
        row = int(row)
        wsS = _ws(WS_SOLICITUDES)
        # ESTADO está en columna 6 => F (1-index)
        wsS.update_cell(row, 6, estado)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    app.run(debug=True)