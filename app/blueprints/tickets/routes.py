from flask import render_template
from flask_login import login_required
from app.blueprints.tickets import bp


@bp.route("/")
@login_required
def index():
    return render_template("tickets/index.html")
