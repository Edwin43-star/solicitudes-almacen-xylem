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
    # Abre directo la pestaña VALE_SALIDA por gid
    return f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit#gid={VALE_GID}"


def ws_set(ws, a1, value):
    """Escritura segura (gspread espera matriz)."""
    ws.update(a1, [[value]], value_input_option="USER_ENTERED")


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
                # Code39
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
                        {"type": "text", "text": str(cantidad)},
                    ],
                }
            ],
        },
    }

    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
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
            lista_items.append(f"✅{idx}) {descripcion} (x{cantidad})")

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

            ws.append_row(
                [
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
                    "",
                ]
            )

        enviar_whatsapp(solicitante, tipo_general, descripcion_lista, cantidad_total)

        flash("✅ Solicitud registrada. El almacén la atenderá en breve.", "success")
        return redirect(url_for("solicitar"))

    except Exception as e:
        print("ERROR guardar_solicitud:", e)
        flash(f"Error al guardar solicitud: {e}", "danger")
        return redirect(url_for("solicitar"))


# ===============================
# BANDEJA
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

        grupos[id_solicitud].append(
            {
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
            }
        )

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

        solicitudes_agrupadas.append(
            {
                "id_solicitud": id_s,
                "fecha": cab.get("fecha", ""),
                "solicitante": cab.get("solicitante", ""),
                "tipo": cab.get("tipo", ""),
                "estado": estado_cab,
                "almacenero": alm_cab,
                "detalle": detalle,
            }
        )

    solicitudes_agrupadas = sorted(solicitudes_agrupadas, key=lambda x: x["id_solicitud"], reverse=True)

    return render_template(
        "bandeja.html",
        solicitudes=solicitudes_agrupadas,
        spreadsheet_id=SPREADSHEET_ID,
        vale_gid=VALE_GID,
        vale_url=url_vale_sheets(),
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
                        "tipo": fila[3],
                    }

                items.append(
                    {
                        "codigo_sap": fila[4],
                        "codigo_barras": fila[5],
                        "descripcion": fila[6],
                        "um": fila[7],
                        "cantidad": fila[8],
                    }
                )

                filas_a_actualizar.append(idx)

        if not items or cabecera is None:
            msg = "❌ No se encontraron items para esta solicitud"
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return jsonify({"ok": False, "error": msg}), 400
            flash(msg, "danger")
            return redirect(url_for("bandeja"))

        almacenero = session.get("nombre", "").strip()

        # ==========================================
        # 1) LIMPIAR DETALLE (sin tocar etiquetas)
        #    (OJO: en combinadas, limpiar la celda "arriba-izq" es suficiente)
        # ==========================================
        clear_ranges = [
            "A8:A22",  # N°
            "B8:B22",  # CODIGO
            "C8:C22",  # COD BARRAS
            "D8:D22",  # DESCRIPCION (D-E-F combinadas -> se escribe/limpia en D)
            "G8:G22",  # CANT
            "H8:H22",  # UM
            "I8:I22",  # NUEVO
            "J8:J22",  # CAMBIO
            "K8:K22",  # (por si existe una 3ra col en motivo)
        ]
        wsVale.batch_clear(clear_ranges)

        # ==========================================
        # 2) CABECERA (ajusta aquí si tu plantilla usa otras celdas)
        #    - En combinadas escribe en la 1ra celda (arriba-izq)
        # ==========================================
        fecha_vale = datetime.now(ZoneInfo("America/Lima")).strftime("%d/%m/%Y %H:%M")
        solicitante = cabecera.get("solicitante", "")

        codigo_trab, area, cargo = buscar_datos_usuario_por_nombre(solicitante)

        # FECHA (J-K-L combinadas -> J3)
        ws_set(wsVale, "J3", fecha_vale)

        # CODIGO trabajador (si tu CODIGO está en B5)
        ws_set(wsVale, "B5", codigo_trab)

        # TRABAJADOR (D-E-F combinadas -> D5)
        ws_set(wsVale, "D5", solicitante)

        # CARGO (B-C-D combinadas -> B6)
        ws_set(wsVale, "B6", cargo)

        # AREA (si está combinada en E-F -> E6)
        ws_set(wsVale, "E6", area)

        # ALMACENERO (IMPORTANTE: NO escribir donde dice "ALMACENERO")
        # En tu plantilla normalmente el nombre está a la derecha/abajo del rótulo.
        # Prueba con H6. Si tu nombre va en otra celda, cámbiala aquí.
        ws_set(wsVale, "H6", almacenero)

        # ==========================================
        # 3) ITEMS (escribimos por celda para no romper combinadas)
        # ==========================================
        updates = []
        fila_inicio = 8

        for n, it in enumerate(items, start=1):
            r = fila_inicio + (n - 1)

            cb = str(it.get("codigo_barras", "")).strip()
            if cb and not (cb.startswith("*") and cb.endswith("*")):
                cb = f"*{cb}*"

            codigo_sap = str(it.get("codigo_sap", "")).strip()
            desc = str(it.get("descripcion", "")).strip()
            cant = str(it.get("cantidad", "")).strip()
            um = str(it.get("um", "")).strip()

            # A: N°
            updates.append({"range": f"A{r}", "values": [[n]]})

            # B: CODIGO
            updates.append({"range": f"B{r}", "values": [[codigo_sap]]})

            # C: COD BARRAS
            updates.append({"range": f"C{r}", "values": [[cb]]})

            # D (D-E-F combinadas): DESCRIPCION
            updates.append({"range": f"D{r}", "values": [[desc]]})

            # G: CANT
            updates.append({"range": f"G{r}", "values": [[cant]]})

            # H: UM
            updates.append({"range": f"H{r}", "values": [[um]]})

            # MOTIVO (texto para marcar a mano)
            updates.append({"range": f"I{r}", "values": [["NUEVO"]]})
            updates.append({"range": f"J{r}", "values": [["CAMBIO"]]})

        if updates:
            wsVale.batch_update(updates, value_input_option="USER_ENTERED")

        # ==========================================
        # 4) MARCAR ATENDIDO EN SOLICITUDES (todas filas del ID)
        # ==========================================
        batch_updates = []
        for rr in filas_a_actualizar:
            batch_updates.append({"range": f"J{rr}", "values": [["ATENDIDO"]]})
            batch_updates.append({"range": f"K{rr}", "values": [[almacenero]]})

        wsSol.batch_update(batch_updates, value_input_option="USER_ENTERED")

        vale_url = url_vale_sheets()

        # AJAX
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"ok": True, "vale_url": vale_url})

        flash("✅ VALE generado y solicitud marcada como ATENDIDO", "success")
        return redirect(url_for("bandeja"))

    except Exception as e:
        err = f"❌ Error al generar vale: {e}"
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"ok": False, "error": err}), 500
        flash(err, "danger")
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
                items.append(
                    {
                        "codigo_sap": fila.get("CODIGO", ""),
                        "tipo": fila.get("TIPO", ""),
                        "descripcion": fila.get("DESCRIPCION", ""),
                        "um": fila.get("U.M", ""),
                        "stock": fila.get("STOCK", ""),
                        "codigo_barras": fila.get("CODIGO_BARRAS", ""),
                    }
                )

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
✅ bandeja.html (copia y pega completo)
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Bandeja - Solicitudes</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">

  <style>
    body { background: #f4f6f9; }
    .hdr-dark { background:#212529; color:#fff; border-radius:10px 10px 0 0; }
    .card { border:0; border-radius: 12px; overflow:hidden; }
    .badge-estado { font-size: .85rem; padding: .5rem .75rem; border-radius: .6rem; }
    .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace; }
    .btn { border-radius: 10px; }
    .table thead th { background:#e9ecef; }
  </style>
</head>

<body class="py-4">
<div class="container">

  <div class="d-flex justify-content-between align-items-center mb-3">
    <h2 class="m-0">📥 Bandeja de Solicitudes</h2>
    <a class="btn btn-outline-danger" href="{{ url_for('logout') }}">Cerrar sesión</a>
  </div>

  {% with messages = get_flashed_messages(with_categories=true) %}
    {% if messages %}
      {% for cat, msg in messages %}
        <div class="alert alert-{{ cat }} alert-dismissible fade show" role="alert">
          {{ msg }}
          <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
        </div>
      {% endfor %}
    {% endif %}
  {% endwith %}

  {% if not solicitudes %}
    <div class="alert alert-info">No hay solicitudes registradas.</div>
  {% endif %}

  {% for sol in solicitudes %}
    {% set est = (sol.estado or "")|upper %}

    <div class="card shadow-sm mb-4">
      <div class="card-header hdr-dark d-flex justify-content-between align-items-center flex-wrap gap-2">
        <div class="d-flex align-items-center flex-wrap gap-3">
          <span class="badge bg-primary">ID</span>
          <div class="fw-bold mono">ID: {{ sol.id_solicitud }}</div>
          <div class="text-white-50">({{ sol.detalle|length }} items)</div>

          <div class="text-white-50">📅 {{ sol.fecha }}</div>
          <div class="text-white-50">👤 {{ sol.solicitante }}</div>
          <div class="text-white-50">📦 {{ sol.tipo }}</div>
        </div>

        <div class="d-flex align-items-center gap-2">
          {% if est == "ATENDIDO" %}
            <a class="btn btn-primary btn-sm"
               href="{{ vale_url }}"
               target="_blank">📄 VER VALE</a>

            <button class="btn btn-secondary btn-sm" disabled title="Esta solicitud ya fue atendida">
              ✅ YA ATENDIDO
            </button>
          {% else %}
            <button class="btn btn-warning btn-sm"
                    id="btnGen{{ sol.id_solicitud }}"
                    onclick="generarVale('{{ sol.id_solicitud }}')">
              🧾 GENERAR VALE
            </button>
          {% endif %}

          <!-- BADGE ESTADO -->
          {% if est == "PENDIENTE" %}
            <span class="badge bg-warning text-dark badge-estado">PENDIENTE</span>
          {% elif est == "ATENDIDO" %}
            <span class="badge bg-success badge-estado">ATENDIDO</span>
          {% elif est == "ANULADO" %}
            <span class="badge bg-danger badge-estado">ANULADO</span>
          {% else %}
            <span class="badge bg-info badge-estado">{{ sol.estado }}</span>
          {% endif %}
        </div>
      </div>

      <div class="card-body">
        <div class="table-responsive">
          <table class="table table-bordered align-middle">
            <thead>
              <tr>
                <th style="width:160px">COD SAP</th>
                <th style="width:200px">COD BARRAS</th>
                <th>DESCRIPCIÓN</th>
                <th style="width:90px" class="text-center">U.M</th>
                <th style="width:90px" class="text-center">CANT</th>
                <th style="width:110px" class="text-center">ESTADO</th>
              </tr>
            </thead>
            <tbody>
              {% for it in sol.detalle %}
                {% set ei = (it.estado or "")|upper %}
                <tr>
                  <td class="mono">{{ it.codigo_sap }}</td>
                  <td class="mono">{{ it.codigo_barras }}</td>
                  <td>{{ it.descripcion }}</td>
                  <td class="text-center">{{ it.um }}</td>
                  <td class="text-center fw-bold">{{ it.cantidad }}</td>
                  <td class="text-center">
                    {% if ei == "PENDIENTE" %}
                      <span class="badge bg-warning text-dark">PENDIENTE</span>
                    {% elif ei == "ATENDIDO" %}
                      <span class="badge bg-success">ATENDIDO</span>
                    {% elif ei == "ANULADO" %}
                      <span class="badge bg-danger">ANULADO</span>
                    {% else %}
                      <span class="badge bg-secondary">{{ it.estado }}</span>
                    {% endif %}
                  </td>
                </tr>
              {% endfor %}
            </tbody>
          </table>
        </div>

        <div class="text-end small text-muted">
          🧑‍💼 Almacenero: <span class="fw-semibold">{{ sol.almacenero or "-" }}</span>
        </div>
      </div>
    </div>
  {% endfor %}

</div>

<script>
async function generarVale(idSolicitud) {
  const ok = confirm("¿Generar VALE para la solicitud: " + idSolicitud + " ?");
  if (!ok) return;

  const btn = document.getElementById("btnGen" + idSolicitud);
  if (btn) { btn.disabled = true; btn.innerText = "Generando..."; }

  try {
    const res = await fetch("/generar_vale/" + idSolicitud, {
      method: "POST",
      headers: {"X-Requested-With": "XMLHttpRequest"}
    });

    const data = await res.json().catch(() => ({ok:false, error:"Respuesta inválida del servidor"}));

    if (!res.ok || !data.ok) {
      alert(data.error || "Error al generar vale");
      if (btn) { btn.disabled = false; btn.innerText = "🧾 GENERAR VALE"; }
      return;
    }

    // Abre el VALE directo en otra pestaña
    window.open(data.vale_url, "_blank");

    // Recarga para que cambie a ATENDIDO y aparezca VER VALE
    window.location.reload();

  } catch (e) {
    alert("Error: " + e);
    if (btn) { btn.disabled = false; btn.innerText = "🧾 GENERAR VALE"; }
  }
}
</script>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>