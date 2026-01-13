from flask import Flask, render_template, request, redirect, session, url_for

app = Flask(__name__)
app.secret_key = "xylem-secret-key"

# ===============================
# ROOT
# ===============================
@app.route("/")
def root():
    return redirect("/login")

# =============================
# LOGIN
# =============================
@app.route("/", methods=["GET"])
@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        # -------- PERSONAL --------
        if "nombre" in request.form:
            nombre = request.form["nombre"].strip()
            if nombre:
                session.clear()
                session["rol"] = "personal"
                session["usuario"] = nombre.upper()
                return redirect("/solicitar")

        # -------- ALMACENERO --------
if "usuario" in request.form and "password" in request.form:
    usuario = request.form["usuario"].strip().upper()
    password = request.form["password"].strip()

    if (
        (usuario == "EDWIN" and password == "6982") or
        (usuario == "EDGAR GARCIA" and password == "1234")
    ):
        session.clear()
        session["rol"] = "almacenero"
        session["usuario"] = usuario
        return redirect("/bandeja")

    return render_template("login.html")


# =============================
# INICIO (solo almacenero)
# =============================
@app.route("/inicio")
def inicio():
    if session.get("rol") != "almacenero":
        return redirect("/login")
    return render_template("inicio.html")


# =============================
# SOLICITUD (personal)
# =============================
@app.route("/solicitar")
def solicitar():
    if session.get("rol") != "personal":
        return redirect("/login")

    # catálogo simulado (luego Excel / Sheets)
    catalogo = {
        "EPP": [
            "CASCO DE SEGURIDAD",
            "GUANTES NITRILO",
            "LENTES DE SEGURIDAD"
        ],
        "CONSUMIBLE": [
            "CINTA AISLANTE",
            "TRAPO INDUSTRIAL",
            "ACEITE"
        ]
    }

    return render_template(
        "solicitar.html",
        usuario=session.get("usuario"),
        catalogo=catalogo
    )


# =============================
# BANDEJA (almacenero)
# =============================
@app.route("/bandeja")
def bandeja():
    if session.get("rol") != "almacenero":
        return redirect("/login")

    return render_template(
        "bandeja.html",
        usuario=session.get("usuario")
    )

# ======================
# CATALOGO DINAMICO
# ======================
CATALOGO = {
    "EPP": [
        {"codigo": "EPP001", "descripcion": "CASCO SEGURIDAD"},
        {"codigo": "EPP002", "descripcion": "LENTES SEGURIDAD"}
    ],
    "CONSUMIBLE": [
        {"codigo": "CON001", "descripcion": "GUANTES NITRILO"},
        {"codigo": "CON002", "descripcion": "CINTA AISLANTE"}
    ]
}

@app.route("/catalogo/<tipo>")
def catalogo(tipo):
    return CATALOGO.get(tipo.upper(), [])

# =============================
# LOGOUT
# =============================
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


if __name__ == "__main__":
    app.run(debug=True)