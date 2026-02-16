from flask import Blueprint

bp = Blueprint("customers", __name__, template_folder="../../templates/customers")

from app.blueprints.customers import routes  # noqa: F401, E402
