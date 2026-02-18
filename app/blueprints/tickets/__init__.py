from flask import Blueprint

bp = Blueprint("tickets", __name__, template_folder="../../templates/tickets")

from app.blueprints.tickets import routes  # noqa: F401, E402
