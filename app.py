from flask import Flask, render_template, request, redirect, url_for, session, flash
import os
import json

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "xylem-secret")

# ===============================
# RUTAS PRINCIPALES
# ===============================

@app.route("/", methods=["GET"])
def root():
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":

        # --- PERSONAL ---
        codigo_personal = request.form.get("codigo_personal", "").strip()
        nombre_personal = request.form.get("nombre_personal", "").strip()

        # --- ALMACENERO ---
        almacenero = request.form.get("almacenero", "").strip()
        password = request.form.get("password", "").strip()

        # ========= VALIDACIÓN =========

        # Almacenero
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

        # Personal
        if codigo_personal or nombre_personal:
            session["rol"] = "PERSONAL"
            session["nombre"] = nombre_personal if nombre_personal else f"Código {codigo_personal}"
            return redirect(url_for("inicio"))

        return render_template("login.html", error="Complete los datos de ingreso")

    return render_template("login.html")


@app.route("/inicio")
def inicio():
    if "nombre" not in session:
        return redirect(url_for("login"))
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

    items_json = request.form.get("items_json", "")
    if not items_json:
        flash("No hay ítems en la solicitud", "danger")
        return redirect(url_for("solicitar"))

    items = json.loads(items_json)
    flash("Solicitud enviada correctamente", "success")
    return redirect(url_for("solicitar"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))