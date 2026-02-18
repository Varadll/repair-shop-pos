from flask import Blueprint

bp = Blueprint("stock", __name__, template_folder="../../templates/stock")

from app.blueprints.stock import routes  # noqa: F401, E402
