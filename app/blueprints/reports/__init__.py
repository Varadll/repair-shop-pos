from flask import Blueprint

bp = Blueprint("reports", __name__, template_folder="../../templates/reports")

from app.blueprints.reports import routes  # noqa: F401, E402
