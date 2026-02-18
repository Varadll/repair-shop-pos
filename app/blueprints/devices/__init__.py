from flask import Blueprint

bp = Blueprint("devices", __name__, template_folder="../../templates/devices")

from app.blueprints.devices import routes  # noqa: F401, E402
