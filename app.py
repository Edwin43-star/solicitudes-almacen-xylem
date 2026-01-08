from flask import Flask, render_template, request, redirect, url_for

# ==================================================
# APP FLASK (IMPORTANTE: debe llamarse "app")
# ==================================================
app = Flask(__name__)

# ==================================================
# RUTAS PRINCIPALES
# ==================================================

@app.route("/")
def inicio():
    return render_template("inicio.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        # Aquí luego validaremos usuario/clave
        return redirect(url_for("bandeja"))
    return render_template("login.html")


@app.route("/bandeja")
def bandeja():
    return render_template("bandeja.html")


@app.route("/solicitar", methods=["GET", "POST"])
def solicitar():
    if request.method == "POST":
        # Aquí luego guardaremos la solicitud
        return redirect(url_for("bandeja"))
    return render_template("solicitar.html")


# ==================================================
# EJECUCIÓN LOCAL (Render lo ignora, pero es correcto)
# ==================================================
if __name__ == "__main__":
    app.run(debug=True)