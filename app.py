from flask import Flask, render_template, request, redirect, url_for, session
import gspread
from google.oauth2.service_account import Credentials
import os

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "xylem-secret")

# ===============================
# GOOGLE SHEETS
# ===============================
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

creds_info = eval(os.environ["GOOGLE_SERVICE_ACCOUNT"])
creds = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
client = gspread.authorize(creds)

SPREADSHEET_ID = os.environ["SPREADSHEET_ID"]
sheet = client.open_by_key(SPREADSHEET_ID)

sheet_usuarios = sheet.worksheet("Usuarios")
sheet_almaceneros = sheet.worksheet("Almaceneros")
sheet_catalogo = sheet.worksheet("Catalogo")
sheet_solicitudes = sheet.worksheet("Solicitudes")

# ===============================
# LOGIN
# ===============================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        mode = request.form.get("mode")

        # -------- PERSONAL --------
        if mode == "personal":
            texto = request.form.get("usuario_personal", "").strip().upper()
            usuarios = sheet_usuarios.get_all_records()

            for u in usuarios:
                if (
                    str(u["CODIGO"]).strip() == texto
                    or texto in u["NOMBRE"].upper()
                ) and u.get("ACTIVO", "SI") == "SI":
                    session.clear()
                    session["rol"] = "personal"
                    session["nombre"] = u["NOMBRE"]
                    return redirect(url_for("solicitar"))

            return render_template("login.html", error="Personal no encontrado")

        # -------- ALMACENERO --------
        if mode == "almacenero":
            user = request.form.get("user_alm", "").strip().upper()
            pwd = request.form.get("pass_alm", "").strip()
            almaceneros = sheet_almaceneros.get_all_records()

            for a in almaceneros:
                if (
                    a["USUARIO"].strip().upper() == user
                    and str(a["CLAVE"]).strip() == pwd
                    and a.get("ACTIVO", "SI") == "SI"
                ):
                    session.clear()
                    session["rol"] = "almacenero"
                    session["nombre"] = a["NOMBRE"]
                    return redirect(url_for("bandeja"))

            return render_template("login.html", error="Credenciales inválidas")

    return render_template("login.html")


# ===============================
# INICIO
# ===============================
@app.route("/")
def inicio():
    if "rol" not in session:
        return redirect(url_for("login"))
    return render_template("inicio.html")


# ===============================
# SOLICITAR
# ===============================
@app.route("/solicitar", methods=["GET", "POST"])
def solicitar():
    if session.get("rol") != "personal":
        return redirect(url_for("login"))

    catalogo = sheet_catalogo.get_all_records()

    if request.method == "POST":
        codigo = request.form["codigo"]
        cantidad = int(request.form["cantidad"])

        for c in catalogo:
            if c["CODIGO"] == codigo:
                sheet_solicitudes.append_row([
                    "",
                    "",
                    codigo,
                    session["nombre"],
                    c["TIPO"],
                    c["DESCRIPCION"],
                    cantidad,
                    "PENDIENTE",
                    session["nombre"]
                ])
                return redirect(url_for("inicio"))

    return render_template("solicitar.html", catalogo=catalogo)


# ===============================
# BANDEJA ALMACENERO
# ===============================
@app.route("/bandeja")
def bandeja():
    if session.get("rol") != "almacenero":
        return redirect(url_for("login"))

    solicitudes = sheet_solicitudes.get_all_records()
    return render_template("bandeja.html", solicitudes=solicitudes)


# ===============================
# LOGOUT
# ===============================
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


if __name__ == "__main__":
    app.run(debug=True)