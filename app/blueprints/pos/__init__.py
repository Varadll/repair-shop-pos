from flask import Blueprint

bp = Blueprint("pos", __name__, template_folder="../../templates/pos")

from app.blueprints.pos import routes  # noqa: F401, E402
