from datetime import datetime, timezone, timedelta
from flask import render_template
from flask_login import login_required
from sqlalchemy import func
from app.blueprints.dashboard import bp
from app.extensions import db
from app.models import Ticket, Invoice, StockItem, POSSale


def _today_range():
    """Return (start, end) datetimes for today in UTC."""
    now = datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return start, end


@bp.route("/")
@login_required
def index():
    # ---- Stat card 1: Open Tickets (Waiting + Diagnosed + In Progress) ----
    open_statuses = ["Waiting", "Diagnosed", "In Progress"]
    open_tickets = Ticket.query.filter(Ticket.status.in_(open_statuses)).count()

    # ---- Stat card 2: Ready for Collection ----
    ready_tickets = Ticket.query.filter_by(status="Ready").count()

    # ---- Stat card 3: Low Stock Items ----
    low_stock_count = (
        StockItem.query
        .filter(StockItem.quantity <= StockItem.low_stock_threshold)
        .count()
    )

    # ---- Stat card 4: Today's Revenue ----
    today_start, today_end = _today_range()

    # Invoice payments received today (deposit_paid on invoices created/updated today)
    invoice_revenue = (
        db.session.query(func.coalesce(func.sum(Invoice.deposit_paid), 0.0))
        .filter(Invoice.is_paid == True)
        .filter(Invoice.updated_at >= today_start)
        .filter(Invoice.updated_at < today_end)
        .scalar()
    )

    # POS sales today
    pos_revenue = (
        db.session.query(func.coalesce(func.sum(POSSale.total), 0.0))
        .filter(POSSale.created_at >= today_start)
        .filter(POSSale.created_at < today_end)
        .scalar()
    )

    todays_revenue = round((invoice_revenue or 0) + (pos_revenue or 0), 2)

    # ---- Recent active tickets (last 10, excluding Collected/Cancelled) ----
    active_statuses = ["Waiting", "Diagnosed", "In Progress", "Ready"]
    recent_tickets = (
        Ticket.query
        .filter(Ticket.status.in_(active_statuses))
        .order_by(Ticket.created_at.desc())
        .limit(10)
        .all()
    )

    return render_template(
        "dashboard.html",
        open_tickets=open_tickets,
        ready_tickets=ready_tickets,
        low_stock_count=low_stock_count,
        todays_revenue=todays_revenue,
        recent_tickets=recent_tickets,
    )
