from flask import Flask
from config import Config


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # --- Initialise extensions ---
    from app.extensions import db, migrate, login_manager

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message_category = "warning"

    # --- Register blueprints ---
    from app.blueprints.auth import bp as auth_bp
    from app.blueprints.customers import bp as customers_bp
    from app.blueprints.devices import bp as devices_bp
    from app.blueprints.tickets import bp as tickets_bp
    from app.blueprints.invoices import bp as invoices_bp
    from app.blueprints.stock import bp as stock_bp
    from app.blueprints.pos import bp as pos_bp
    from app.blueprints.reports import bp as reports_bp
    from app.blueprints.dashboard import bp as dashboard_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(customers_bp, url_prefix="/customers")
    app.register_blueprint(devices_bp, url_prefix="/devices")
    app.register_blueprint(tickets_bp, url_prefix="/tickets")
    app.register_blueprint(invoices_bp, url_prefix="/invoices")
    app.register_blueprint(stock_bp, url_prefix="/stock")
    app.register_blueprint(pos_bp, url_prefix="/pos")
    app.register_blueprint(reports_bp, url_prefix="/reports")

    # --- Create tables on first run ---
    with app.app_context():
        from app import models  # noqa: F401
        db.create_all()

    # --- Template context processors ---
    @app.context_processor
    def inject_shop():
        return dict(
            shop_name=app.config["SHOP_NAME"],
            shop_phone=app.config["SHOP_PHONE"],
            shop_email=app.config["SHOP_EMAIL"],
        )

    return app
