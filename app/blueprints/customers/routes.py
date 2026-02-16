from flask import render_template
from flask_login import login_required
from app.blueprints.customers import bp


@bp.route("/")
@login_required
def index():
    return render_template("customers/index.html")
