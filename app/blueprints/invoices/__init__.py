from flask import Blueprint

bp = Blueprint("invoices", __name__, template_folder="../../templates/invoices")

from app.blueprints.invoices import routes  # noqa: F401, E402
