from flask import render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from app.blueprints.auth import bp
from app.extensions import db
from app.models import User


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password) and user.is_active:
            login_user(user, remember=True)
            next_page = request.args.get("next")
            flash("Logged in successfully.", "success")
            return redirect(next_page or url_for("dashboard.index"))

        flash("Invalid username or password.", "danger")

    return render_template("auth/login.html")


@bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Logged out.", "info")
    return redirect(url_for("auth.login"))


@bp.cli.command("create-admin")
def create_admin():
    """Create default admin user: admin / admin123"""
    if User.query.filter_by(username="admin").first():
        print("Admin user already exists.")
        return
    admin = User(
        username="admin",
        email="admin@repairshop.com",
        full_name="Admin",
        role="admin",
    )
    admin.set_password("admin123")
    db.session.add(admin)
    db.session.commit()
    print("Admin user created (admin / admin123). Change the password after first login.")
