from flask import Flask, render_template, redirect, url_for, request

# =========================================================
# CREAR APP FLASK (ESTO ES CLAVE PARA GUNICORN)
# =========================================================
app = Flask(__name__)

# =========================================================
# RUTAS
# =========================================================

@app.route("/")
def home():
    return redirect(url_for("inicio"))


@app.route("/inicio")
def inicio():
    return render_template("inicio.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        # aquí luego validaremos usuario
        return redirect(url_for("bandeja"))
    return render_template("login.html")


@app.route("/bandeja")
def bandeja():
    return render_template("bandeja.html")


@app.route("/solicitar")
def solicitar():
    return render_template("solicitar.html")


# =========================================================
# EJECUCIÓN LOCAL (NO AFECTA A RENDER)
# =========================================================
if __name__ == "__main__":
    app.run(debug=True)