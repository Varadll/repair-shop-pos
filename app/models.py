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
    barcodes = db.relationship("Barcode", backref="stock_item", lazy="dynamic",
                               cascade="all, delete-orphan")

    @property
    def is_low_stock(self):
        return self.quantity <= self.low_stock_threshold

    def sync_barcode_quantity(self):
        """Update quantity to match active barcode count (if item uses barcodes)."""
        total_barcodes = self.barcodes.count()
        if total_barcodes > 0:
            self.quantity = self.barcodes.filter_by(is_active=True).count()

    def __repr__(self):
        return f"<StockItem {self.name} (qty: {self.quantity})>"


# ---------------------------------------------------------------------------
# Table 8 — Barcodes (individual unit tracking for stock items)
# ---------------------------------------------------------------------------
class Barcode(db.Model):
    __tablename__ = "barcodes"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(100), unique=True, nullable=False, index=True)
    stock_item_id = db.Column(db.Integer, db.ForeignKey("stock_items.id"), nullable=False, index=True)
    is_active = db.Column(db.Boolean, default=True, index=True)
    created_at = db.Column(db.DateTime, default=utcnow)
    used_at = db.Column(db.DateTime, nullable=True)

    def __repr__(self):
        return f"<Barcode {self.code} (active={self.is_active})>"


# ---------------------------------------------------------------------------
# Table 9 — Ticket Parts Used
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
