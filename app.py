from flask import Flask, render_template, request, redirect, session, jsonify
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

app = Flask(__name__)
app.secret_key = "xylem-secret-key"

# ===============================
# GOOGLE SHEETS
# ===============================
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

service_account_info = json.loads(
    os.environ.get("GOOGLE_SERVICE_ACCOUNT")
)

creds = Credentials.from_service_account_info(
    service_account_info,
    scopes=SCOPES
)

client = gspread.authorize(creds)

SPREADSHEET = client.open("Solicitudes_Almacen_App")
SHEET_SOLICITUDES = SPREADSHEET.worksheet("Solicitudes")
SHEET_USUARIOS = SPREADSHEET.worksheet("Usuarios")
SHEET_ALMACENEROS = SPREADSHEET.worksheet("Almaceneros")
SHEET_CATALOGO = SPREADSHEET.worksheet("Catalogo")

# ===============================
# LOGIN
# ===============================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":

        # ---- PERSONAL ----
        if "personal_nombre" in request.form:
            nombre = request.form["personal_nombre"].strip()
            if nombre == "":
                return redirect("/login")

            session.clear()
            session["rol"] = "personal"
            session["nombre"] = nombre
            session["carrito"] = []

            return redirect("/inicio")

        # ---- ALMACENERO ----
        if "usuario" in request.form:
            usuario = request.form["usuario"].upper()
            clave = request.form["clave"]

            almaceneros = SHEET_ALMACENEROS.get_all_records()
            for a in almaceneros:
                if (
                    a["USUARIO"].upper() == usuario
                    and str(a["CLAVE"]) == clave
                    and a["ACTIVO"] == "SI"
                ):
                    session.clear()
                    session["rol"] = "almacenero"
                    session["usuario"] = usuario
                    return redirect("/bandeja")

            return redirect("/login")

    return render_template("login.html")

# ===============================
# INICIO
# ===============================
@app.route("/")
@app.route("/inicio")
def inicio():
    if "rol" not in session:
        return redirect("/login")
    return render_template("inicio.html")

# ===============================
# SOLICITAR
# ===============================
@app.route("/solicitar")
def solicitar():
    if session.get("rol") != "personal":
        return redirect("/login")

    return render_template("solicitar.html")

# ===============================
# API CATALOGO POR TIPO
# ===============================
@app.route("/api/catalogo/<tipo>")
def api_catalogo(tipo):
    items = SHEET_CATALOGO.get_all_records()
    filtrado = []

    for i in items:
        if i["TIPO"].upper() == tipo.upper():
            filtrado.append({
                "codigo": i["CODIGO"],
                "descripcion": i["DESCRIPCION"],
                "stock": i["STOCK"]
            })

    return jsonify(filtrado)

# ===============================
# AGREGAR ITEM (CARRITO)
# ===============================
@app.route("/agregar", methods=["POST"])
def agregar():
    if session.get("rol") != "personal":
        return redirect("/login")

    codigo = request.form["codigo"]
    descripcion = request.form["descripcion"]
    cantidad = int(request.form["cantidad"])

    session["carrito"].append({
        "codigo": codigo,
        "descripcion": descripcion,
        "cantidad": cantidad
    })

    return redirect("/solicitar")

# ===============================
# ELIMINAR ITEM
# ===============================
@app.route("/eliminar/<int:index>")
def eliminar(index):
    if session.get("rol") != "personal":
        return redirect("/login")

    session["carrito"].pop(index)
    return redirect("/solicitar")

# ===============================
# ENVIAR SOLICITUD
# ===============================
@app.route("/enviar", methods=["POST"])
def enviar():
    if session.get("rol") != "personal":
        return redirect("/login")

    fecha = datetime.now().strftime("%d/%m/%Y")
    hora = datetime.now().strftime("%H:%M:%S")
    nombre = session["nombre"]

    for item in session["carrito"]:
        SHEET_SOLICITUDES.append_row([
            fecha,
            hora,
            item["codigo"],
            nombre,
            "SOLICITUD",
            item["descripcion"],
            item["cantidad"],
            "PENDIENTE",
            nombre
        ])

    session["carrito"] = []
    return redirect("/inicio")

# ===============================
# BANDEJA ALMACENERO
# ===============================
@app.route("/bandeja")
def bandeja():
    if session.get("rol") != "almacenero":
        return redirect("/login")

    solicitudes = SHEET_SOLICITUDES.get_all_records()
    pendientes = [s for s in solicitudes if s["ESTADO"] == "PENDIENTE"]

    return render_template("bandeja.html", solicitudes=pendientes)

# ===============================
# LOGOUT
# ===============================
@app.route("/salir")
def salir():
    session.clear()
    return redirect("/login")

if __name__ == "__main__":
    app.run(debug=True)