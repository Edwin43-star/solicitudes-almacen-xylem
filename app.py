from flask import Flask, render_template, request, redirect, url_for, session
import os

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "dev")

@app.route("/")
def inicio():
    if "usuario" not in session:
        return redirect(url_for("login"))
    return render_template("inicio.html", usuario=session["usuario"])

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = request.form.get("usuario")
        if usuario:
            session["usuario"] = usuario
            return redirect(url_for("inicio"))
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/solicitar")
def solicitar():
    if "usuario" not in session:
        return redirect(url_for("login"))
    return render_template("solicitar.html")

@app.route("/bandeja")
def bandeja():
    if "usuario" not in session:
        return redirect(url_for("login"))
    return render_template("bandeja.html")

if __name__ == "__main__":
    app.run()
