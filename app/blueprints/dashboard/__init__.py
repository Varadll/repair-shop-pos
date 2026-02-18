from flask import Blueprint

bp = Blueprint("dashboard", __name__, template_folder="../../templates")

from app.blueprints.dashboard import routes  # noqa: F401, E402
