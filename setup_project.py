"""
REPAIR SHOP POS — Project Setup Script
=======================================
Run this script ONCE to create the entire project structure.

Usage:
  1. Create an empty folder called "repair-shop-pos" anywhere on your computer
  2. Save this file inside that folder as "setup_project.py"
  3. Open a terminal in that folder and run:  python setup_project.py
  4. The entire project will be created around it
  5. Then follow the instructions printed at the end
"""

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def write_file(relative_path, content):
    """Create a file at the given path relative to BASE_DIR."""
    full_path = os.path.join(BASE_DIR, relative_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  ✓ {relative_path}")


# ============================================================================
# FILE CONTENTS
# ============================================================================

CONFIG_PY = '''\
import os

basedir = os.path.abspath(os.path.dirname(__file__))
instance_path = os.path.join(basedir, "instance")
os.makedirs(instance_path, exist_ok=True)


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{os.path.join(instance_path, \'repairshop.db\')}"
    )
    # Shop details (used on invoices/receipts)
    SHOP_NAME = os.environ.get("SHOP_NAME", "Repair Shop")
    SHOP_ADDRESS = os.environ.get("SHOP_ADDRESS", "123 Main Street")
    SHOP_PHONE = os.environ.get("SHOP_PHONE", "+353 1 234 5678")
    SHOP_EMAIL = os.environ.get("SHOP_EMAIL", "info@repairshop.com")
    SHOP_VAT = os.environ.get("SHOP_VAT", "")
    LOW_STOCK_DEFAULT = 5
'''

RUN_PY = '''\
from app import create_app

app = create_app()
'''

REQUIREMENTS_TXT = '''\
Flask==3.1.0
Flask-SQLAlchemy==3.1.1
Flask-Migrate==4.1.0
Flask-Login==0.6.3
Werkzeug==3.1.3
gunicorn==23.0.0
'''

FLASKENV = '''\
FLASK_APP=run.py
FLASK_DEBUG=1
'''

APP_INIT_PY = '''\
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
'''

EXTENSIONS_PY = '''\
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
'''

MODELS_PY = '''\
from datetime import datetime, timezone
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from app.extensions import db, login_manager


def utcnow():
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Table 1 — Users (staff accounts)
# ---------------------------------------------------------------------------
class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="technician")
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=utcnow)

    assigned_tickets = db.relationship("Ticket", backref="technician", lazy="dynamic",
                                       foreign_keys="Ticket.technician_id")
    progress_logs = db.relationship("TicketProgressLog", backref="user", lazy="dynamic")
    pos_sales = db.relationship("POSSale", backref="served_by_user", lazy="dynamic")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self):
        return self.role == "admin"

    def __repr__(self):
        return f"<User {self.username}>"


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# ---------------------------------------------------------------------------
# Table 2 — Customers
# ---------------------------------------------------------------------------
class Customer(db.Model):
    __tablename__ = "customers"

    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(80), nullable=False)
    last_name = db.Column(db.String(80), nullable=False)
    phone = db.Column(db.String(30), nullable=False, index=True)
    email = db.Column(db.String(120), default="")
    address = db.Column(db.Text, default="")
    notes = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    devices = db.relationship("Device", backref="customer", lazy="dynamic",
                              cascade="all, delete-orphan")
    tickets = db.relationship("Ticket", backref="customer", lazy="dynamic")
    pos_sales = db.relationship("POSSale", backref="customer", lazy="dynamic")

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    def __repr__(self):
        return f"<Customer {self.full_name}>"


# ---------------------------------------------------------------------------
# Table 3 — Devices
# ---------------------------------------------------------------------------
class Device(db.Model):
    __tablename__ = "devices"

    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=False, index=True)
    device_type = db.Column(db.String(30), nullable=False)
    brand = db.Column(db.String(60), nullable=False)
    model = db.Column(db.String(100), nullable=False)
    colour = db.Column(db.String(40), default="")
    imei_serial = db.Column(db.String(60), default="", index=True)
    passcode = db.Column(db.String(40), default="")
    condition_notes = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=utcnow)

    tickets = db.relationship("Ticket", backref="device", lazy="dynamic")

    @property
    def display_name(self):
        return f"{self.brand} {self.model}"

    def __repr__(self):
        return f"<Device {self.display_name}>"


# ---------------------------------------------------------------------------
# Table 4 — Tickets (core table)
# ---------------------------------------------------------------------------
class Ticket(db.Model):
    __tablename__ = "tickets"

    STATUSES = ["Waiting", "Diagnosed", "In Progress", "Ready", "Collected", "Cancelled"]
    PRIORITIES = ["Low", "Normal", "High", "Urgent"]

    id = db.Column(db.Integer, primary_key=True)
    ticket_number = db.Column(db.String(20), unique=True, nullable=False, index=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=False, index=True)
    device_id = db.Column(db.Integer, db.ForeignKey("devices.id"), nullable=False)
    technician_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    fault_description = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="Waiting", index=True)
    priority = db.Column(db.String(10), nullable=False, default="Normal")
    due_date = db.Column(db.Date, nullable=True)
    customer_notes = db.Column(db.Text, default="")
    internal_notes = db.Column(db.Text, default="")
    disclaimer_accepted = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    progress_logs = db.relationship("TicketProgressLog", backref="ticket",
                                     lazy="dynamic", order_by="TicketProgressLog.created_at.desc()",
                                     cascade="all, delete-orphan")
    invoice = db.relationship("Invoice", backref="ticket", uselist=False,
                              cascade="all, delete-orphan")
    parts_used = db.relationship("TicketPartUsed", backref="ticket", lazy="dynamic",
                                  cascade="all, delete-orphan")

    @staticmethod
    def generate_ticket_number():
        last = Ticket.query.order_by(Ticket.id.desc()).first()
        next_num = (last.id + 1) if last else 1
        return f"TK-{next_num:04d}"

    def __repr__(self):
        return f"<Ticket {self.ticket_number}>"


# ---------------------------------------------------------------------------
# Table 5 — Ticket Progress Log (audit trail)
# ---------------------------------------------------------------------------
class TicketProgressLog(db.Model):
    __tablename__ = "ticket_progress_log"

    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey("tickets.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    action = db.Column(db.String(50), nullable=False)
    old_value = db.Column(db.String(200), default="")
    new_value = db.Column(db.String(200), default="")
    note = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=utcnow)

    def __repr__(self):
        return f"<ProgressLog Ticket#{self.ticket_id} — {self.action}>"


# ---------------------------------------------------------------------------
# Table 6 — Invoices
# ---------------------------------------------------------------------------
class Invoice(db.Model):
    __tablename__ = "invoices"

    id = db.Column(db.Integer, primary_key=True)
    invoice_number = db.Column(db.String(20), unique=True, nullable=False, index=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey("tickets.id"), nullable=False, unique=True)
    labour_cost = db.Column(db.Float, default=0.0)
    parts_cost = db.Column(db.Float, default=0.0)
    subtotal = db.Column(db.Float, default=0.0)
    discount = db.Column(db.Float, default=0.0)
    total = db.Column(db.Float, default=0.0)
    deposit_paid = db.Column(db.Float, default=0.0)
    balance_due = db.Column(db.Float, default=0.0)
    payment_method = db.Column(db.String(20), default="")
    is_paid = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    @staticmethod
    def generate_invoice_number():
        last = Invoice.query.order_by(Invoice.id.desc()).first()
        next_num = (last.id + 1) if last else 1
        return f"INV-{next_num:04d}"

    def recalculate(self):
        self.subtotal = self.labour_cost + self.parts_cost
        self.total = self.subtotal - self.discount
        self.balance_due = self.total - self.deposit_paid
        self.is_paid = self.balance_due <= 0

    def __repr__(self):
        return f"<Invoice {self.invoice_number}>"


# ---------------------------------------------------------------------------
# Table 7 — Stock / Parts
# ---------------------------------------------------------------------------
class StockItem(db.Model):
    __tablename__ = "stock_items"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False, index=True)
    category = db.Column(db.String(60), default="General")
    compatible_devices = db.Column(db.Text, default="")
    sku = db.Column(db.String(60), default="", index=True)
    quantity = db.Column(db.Integer, default=0)
    low_stock_threshold = db.Column(db.Integer, default=5)
    cost_price = db.Column(db.Float, default=0.0)
    sell_price = db.Column(db.Float, default=0.0)
    supplier = db.Column(db.String(120), default="")
    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    ticket_uses = db.relationship("TicketPartUsed", backref="stock_item", lazy="dynamic")
    pos_sale_items = db.relationship("POSSaleItem", backref="stock_item", lazy="dynamic")

    @property
    def is_low_stock(self):
        return self.quantity <= self.low_stock_threshold

    def __repr__(self):
        return f"<StockItem {self.name} (qty: {self.quantity})>"


# ---------------------------------------------------------------------------
# Table 8 — Ticket Parts Used
# ---------------------------------------------------------------------------
class TicketPartUsed(db.Model):
    __tablename__ = "ticket_parts_used"

    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey("tickets.id"), nullable=False, index=True)
    stock_item_id = db.Column(db.Integer, db.ForeignKey("stock_items.id"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    price_charged = db.Column(db.Float, nullable=False, default=0.0)
    created_at = db.Column(db.DateTime, default=utcnow)

    @property
    def line_total(self):
        return self.quantity * self.price_charged

    def __repr__(self):
        return f"<TicketPartUsed ticket={self.ticket_id} part={self.stock_item_id}>"


# ---------------------------------------------------------------------------
# Table 9 — POS Sales
# ---------------------------------------------------------------------------
class POSSale(db.Model):
    __tablename__ = "pos_sales"

    id = db.Column(db.Integer, primary_key=True)
    sale_number = db.Column(db.String(20), unique=True, nullable=False, index=True)
    served_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=True)
    total = db.Column(db.Float, nullable=False, default=0.0)
    payment_method = db.Column(db.String(20), nullable=False, default="Cash")
    notes = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=utcnow)

    items = db.relationship("POSSaleItem", backref="sale", lazy="dynamic",
                            cascade="all, delete-orphan")

    @staticmethod
    def generate_sale_number():
        last = POSSale.query.order_by(POSSale.id.desc()).first()
        next_num = (last.id + 1) if last else 1
        return f"POS-{next_num:04d}"

    def __repr__(self):
        return f"<POSSale {self.sale_number}>"


# ---------------------------------------------------------------------------
# Table 10 — POS Sale Items
# ---------------------------------------------------------------------------
class POSSaleItem(db.Model):
    __tablename__ = "pos_sale_items"

    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey("pos_sales.id"), nullable=False, index=True)
    stock_item_id = db.Column(db.Integer, db.ForeignKey("stock_items.id"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    price_charged = db.Column(db.Float, nullable=False, default=0.0)
    created_at = db.Column(db.DateTime, default=utcnow)

    @property
    def line_total(self):
        return self.quantity * self.price_charged

    def __repr__(self):
        return f"<POSSaleItem sale={self.sale_id} item={self.stock_item_id}>"
'''

# ---------------------------------------------------------------------------
# Auth blueprint
# ---------------------------------------------------------------------------
AUTH_INIT = '''\
from flask import Blueprint

bp = Blueprint("auth", __name__, template_folder="../../templates/auth")

from app.blueprints.auth import routes  # noqa: F401, E402
'''

AUTH_ROUTES = '''\
from flask import render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from app.blueprints.auth import bp
from app.extensions import db
from app.models import User


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password) and user.is_active:
            login_user(user, remember=True)
            next_page = request.args.get("next")
            flash("Logged in successfully.", "success")
            return redirect(next_page or url_for("dashboard.index"))

        flash("Invalid username or password.", "danger")

    return render_template("auth/login.html")


@bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Logged out.", "info")
    return redirect(url_for("auth.login"))


@bp.cli.command("create-admin")
def create_admin():
    """Create default admin user: admin / admin123"""
    if User.query.filter_by(username="admin").first():
        print("Admin user already exists.")
        return
    admin = User(
        username="admin",
        email="admin@repairshop.com",
        full_name="Admin",
        role="admin",
    )
    admin.set_password("admin123")
    db.session.add(admin)
    db.session.commit()
    print("Admin user created (admin / admin123). Change the password after first login.")
'''

# ---------------------------------------------------------------------------
# Dashboard blueprint
# ---------------------------------------------------------------------------
DASHBOARD_INIT = '''\
from flask import Blueprint

bp = Blueprint("dashboard", __name__, template_folder="../../templates")

from app.blueprints.dashboard import routes  # noqa: F401, E402
'''

DASHBOARD_ROUTES = '''\
from flask import render_template
from flask_login import login_required
from app.blueprints.dashboard import bp


@bp.route("/")
@login_required
def index():
    return render_template("dashboard.html")
'''

# ---------------------------------------------------------------------------
# Stub blueprint template — used for modules not yet built
# ---------------------------------------------------------------------------
def make_stub_init(name):
    return f'''\
from flask import Blueprint

bp = Blueprint("{name}", __name__, template_folder="../../templates/{name}")

from app.blueprints.{name} import routes  # noqa: F401, E402
'''

def make_stub_routes(name):
    return f'''\
from flask import render_template
from flask_login import login_required
from app.blueprints.{name} import bp


@bp.route("/")
@login_required
def index():
    return render_template("{name}/index.html")
'''

def make_stub_template(name, title):
    return f'''\
{{% extends "base.html" %}}
{{% block title %}}{title} — {{{{ shop_name }}}}{{% endblock %}}

{{% block content %}}
<h4 class="mb-4">{title}</h4>
<p class="text-muted">This module will be built next.</p>
{{% endblock %}}
'''

# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------
BASE_HTML = '''\
<!DOCTYPE html>
<html lang="en" data-bs-theme="light">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}{{ shop_name }}{% endblock %}</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css" rel="stylesheet">
  <style>
    :root { --sidebar-width: 230px; }
    body { min-height: 100vh; }
    .sidebar {
      width: var(--sidebar-width);
      min-height: 100vh;
      background: #212529;
      position: fixed;
      top: 0; left: 0;
      z-index: 1030;
      transition: transform .2s;
    }
    .sidebar .nav-link { color: #adb5bd; padding: .6rem 1rem; font-size: .9rem; }
    .sidebar .nav-link:hover,
    .sidebar .nav-link.active { color: #fff; background: rgba(255,255,255,.08); }
    .sidebar .nav-link i { width: 22px; text-align: center; margin-right: .5rem; }
    .main-content { margin-left: var(--sidebar-width); padding: 1.25rem; }
    @media (max-width: 768px) {
      .sidebar { transform: translateX(-100%); }
      .sidebar.show { transform: translateX(0); }
      .main-content { margin-left: 0; }
    }
    .sidebar-brand { padding: 1rem; font-weight: 700; font-size: 1.1rem; color: #fff; border-bottom: 1px solid rgba(255,255,255,.1); }
  </style>
  {% block extra_css %}{% endblock %}
</head>
<body>
  {% if current_user.is_authenticated %}
  <nav class="sidebar d-flex flex-column" id="sidebar">
    <div class="sidebar-brand">
      <i class="bi bi-tools"></i> {{ shop_name }}
    </div>
    <ul class="nav flex-column mt-2 flex-grow-1">
      <li class="nav-item">
        <a class="nav-link {% if request.endpoint == 'dashboard.index' %}active{% endif %}" href="{{ url_for('dashboard.index') }}">
          <i class="bi bi-speedometer2"></i> Dashboard
        </a>
      </li>
      <li class="nav-item">
        <a class="nav-link {% if 'customers' in request.endpoint|default('') %}active{% endif %}" href="{{ url_for('customers.index') }}">
          <i class="bi bi-people"></i> Customers
        </a>
      </li>
      <li class="nav-item">
        <a class="nav-link {% if 'tickets' in request.endpoint|default('') %}active{% endif %}" href="{{ url_for('tickets.index') }}">
          <i class="bi bi-clipboard-check"></i> Tickets
        </a>
      </li>
      <li class="nav-item">
        <a class="nav-link {% if 'invoices' in request.endpoint|default('') %}active{% endif %}" href="{{ url_for('invoices.index') }}">
          <i class="bi bi-receipt"></i> Invoices
        </a>
      </li>
      <li class="nav-item">
        <a class="nav-link {% if 'stock' in request.endpoint|default('') %}active{% endif %}" href="{{ url_for('stock.index') }}">
          <i class="bi bi-box-seam"></i> Stock
        </a>
      </li>
      <li class="nav-item">
        <a class="nav-link {% if 'pos' in request.endpoint|default('') %}active{% endif %}" href="{{ url_for('pos.index') }}">
          <i class="bi bi-cart3"></i> POS Sales
        </a>
      </li>
      <li class="nav-item">
        <a class="nav-link {% if 'reports' in request.endpoint|default('') %}active{% endif %}" href="{{ url_for('reports.index') }}">
          <i class="bi bi-graph-up"></i> Reports
        </a>
      </li>
    </ul>
    <div class="p-3 border-top border-secondary small text-secondary">
      <i class="bi bi-person-circle"></i> {{ current_user.full_name }}
      <br>
      <a href="{{ url_for('auth.logout') }}" class="text-secondary text-decoration-none">
        <i class="bi bi-box-arrow-left"></i> Logout
      </a>
    </div>
  </nav>

  <div class="main-content">
    <button class="btn btn-dark d-md-none mb-3" onclick="document.getElementById('sidebar').classList.toggle('show')">
      <i class="bi bi-list"></i> Menu
    </button>

    {% with messages = get_flashed_messages(with_categories=true) %}
      {% if messages %}
        {% for cat, msg in messages %}
          <div class="alert alert-{{ cat }} alert-dismissible fade show" role="alert">
            {{ msg }}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
          </div>
        {% endfor %}
      {% endif %}
    {% endwith %}

    {% block content %}{% endblock %}
  </div>

  {% else %}
  <div class="container">
    {% with messages = get_flashed_messages(with_categories=true) %}
      {% if messages %}
        {% for cat, msg in messages %}
          <div class="alert alert-{{ cat }} alert-dismissible fade show mt-3" role="alert">
            {{ msg }}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
          </div>
        {% endfor %}
      {% endif %}
    {% endwith %}

    {% block content_public %}{% endblock %}
  </div>
  {% endif %}

  <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
  {% block extra_js %}{% endblock %}
</body>
</html>
'''

LOGIN_HTML = '''\
{% extends "base.html" %}
{% block title %}Login — {{ shop_name }}{% endblock %}

{% block content_public %}
<div class="row justify-content-center mt-5">
  <div class="col-sm-8 col-md-5 col-lg-4">
    <div class="card shadow-sm">
      <div class="card-body p-4">
        <h4 class="text-center mb-4"><i class="bi bi-tools"></i> {{ shop_name }}</h4>
        <form method="POST">
          <div class="mb-3">
            <label for="username" class="form-label">Username</label>
            <input type="text" class="form-control" id="username" name="username" required autofocus>
          </div>
          <div class="mb-3">
            <label for="password" class="form-label">Password</label>
            <input type="password" class="form-control" id="password" name="password" required>
          </div>
          <button type="submit" class="btn btn-primary w-100">Log In</button>
        </form>
      </div>
    </div>
  </div>
</div>
{% endblock %}
'''

DASHBOARD_HTML = '''\
{% extends "base.html" %}
{% block title %}Dashboard — {{ shop_name }}{% endblock %}

{% block content %}
<h4 class="mb-4">Dashboard</h4>
<div class="row g-3">
  <div class="col-sm-6 col-lg-3">
    <div class="card text-bg-primary">
      <div class="card-body">
        <div class="d-flex justify-content-between align-items-center">
          <div>
            <div class="small text-white-50">Open Tickets</div>
            <div class="fs-3 fw-bold">&mdash;</div>
          </div>
          <i class="bi bi-clipboard-check fs-1 text-white-50"></i>
        </div>
      </div>
    </div>
  </div>
  <div class="col-sm-6 col-lg-3">
    <div class="card text-bg-success">
      <div class="card-body">
        <div class="d-flex justify-content-between align-items-center">
          <div>
            <div class="small text-white-50">Ready for Collection</div>
            <div class="fs-3 fw-bold">&mdash;</div>
          </div>
          <i class="bi bi-check-circle fs-1 text-white-50"></i>
        </div>
      </div>
    </div>
  </div>
  <div class="col-sm-6 col-lg-3">
    <div class="card text-bg-warning">
      <div class="card-body">
        <div class="d-flex justify-content-between align-items-center">
          <div>
            <div class="small text-white-50">Low Stock Items</div>
            <div class="fs-3 fw-bold">&mdash;</div>
          </div>
          <i class="bi bi-exclamation-triangle fs-1 text-dark-50"></i>
        </div>
      </div>
    </div>
  </div>
  <div class="col-sm-6 col-lg-3">
    <div class="card text-bg-info">
      <div class="card-body">
        <div class="d-flex justify-content-between align-items-center">
          <div>
            <div class="small text-white-50">Today\\'s Revenue</div>
            <div class="fs-3 fw-bold">&mdash;</div>
          </div>
          <i class="bi bi-currency-euro fs-1 text-white-50"></i>
        </div>
      </div>
    </div>
  </div>
</div>

<div class="mt-4 text-muted">
  <p>Dashboard stats will be wired up once tickets, invoices, and stock modules are built.</p>
</div>
{% endblock %}
'''


# ============================================================================
# BUILD THE PROJECT
# ============================================================================

def main():
    print("=" * 60)
    print("  REPAIR SHOP POS — Project Setup")
    print("=" * 60)
    print(f"\nCreating project in: {BASE_DIR}\n")

    # --- Root files ---
    write_file("config.py", CONFIG_PY)
    write_file("run.py", RUN_PY)
    write_file("requirements.txt", REQUIREMENTS_TXT)
    write_file(".flaskenv", FLASKENV)

    # --- App core ---
    write_file("app/__init__.py", APP_INIT_PY)
    write_file("app/extensions.py", EXTENSIONS_PY)
    write_file("app/models.py", MODELS_PY)

    # --- Auth blueprint ---
    write_file("app/blueprints/auth/__init__.py", AUTH_INIT)
    write_file("app/blueprints/auth/routes.py", AUTH_ROUTES)

    # --- Dashboard blueprint ---
    write_file("app/blueprints/dashboard/__init__.py", DASHBOARD_INIT)
    write_file("app/blueprints/dashboard/routes.py", DASHBOARD_ROUTES)

    # --- Stub blueprints (modules to be built later) ---
    stubs = {
        "customers": "Customers",
        "devices": "Devices",
        "tickets": "Tickets",
        "invoices": "Invoices",
        "stock": "Stock",
        "pos": "POS Sales",
        "reports": "Reports",
    }
    for name, title in stubs.items():
        write_file(f"app/blueprints/{name}/__init__.py", make_stub_init(name))
        write_file(f"app/blueprints/{name}/routes.py", make_stub_routes(name))
        write_file(f"app/templates/{name}/index.html", make_stub_template(name, title))

    # --- Templates ---
    write_file("app/templates/base.html", BASE_HTML)
    write_file("app/templates/auth/login.html", LOGIN_HTML)
    write_file("app/templates/dashboard.html", DASHBOARD_HTML)

    # --- Empty dirs ---
    for d in ["app/static/css", "app/static/js", "app/static/img", "instance", "migrations"]:
        os.makedirs(os.path.join(BASE_DIR, d), exist_ok=True)

    print("\n" + "=" * 60)
    print("  ✓ PROJECT CREATED SUCCESSFULLY")
    print("=" * 60)
    print("""
NEXT STEPS — run these commands one at a time:

  1. Create virtual environment:
     python -m venv venv

  2. Activate it:
     Windows:   venv\\Scripts\\activate
     Mac/Linux: source venv/bin/activate

  3. Install dependencies:
     pip install -r requirements.txt

  4. Create the admin user:
     flask --app run.py create-admin

  5. Run the app:
     flask --app run.py run --debug

  6. Open browser:
     http://127.0.0.1:5000

  7. Login:
     Username: admin
     Password: admin123

You can delete this setup_project.py file after running it.
""")


if __name__ == "__main__":
    main()
