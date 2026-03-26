from datetime import datetime, date, timedelta, timezone
from flask import render_template, request, jsonify
from flask_login import login_required
from sqlalchemy import func, case, and_
from app.blueprints.reports import bp
from app.extensions import db
from app.models import (
    Ticket, Invoice, POSSale, POSSaleItem, StockItem,
    TicketPartUsed, Customer, User,
)


# ---------------------------------------------------------------------------
# Helpers — date range calculation
# ---------------------------------------------------------------------------

def _parse_date_range(period, start_str=None, end_str=None):
    """
    Return (start_date, end_date, period_label) based on the selected period.
    All dates are date objects (not datetimes).
    Supports: today, yesterday, this_week, last_week, this_month,
              last_month, this_year, last_30, last_90, custom.
    """
    today = date.today()

    if period == "today":
        return today, today, "Today"

    elif period == "yesterday":
        yday = today - timedelta(days=1)
        return yday, yday, "Yesterday"

    elif period == "this_week":
        start = today - timedelta(days=today.weekday())  # Monday
        return start, today, "This Week"

    elif period == "last_week":
        this_monday = today - timedelta(days=today.weekday())
        start = this_monday - timedelta(days=7)
        end = this_monday - timedelta(days=1)
        return start, end, "Last Week"

    elif period == "this_month":
        start = today.replace(day=1)
        return start, today, "This Month"

    elif period == "last_month":
        first_this = today.replace(day=1)
        last_day_prev = first_this - timedelta(days=1)
        start = last_day_prev.replace(day=1)
        return start, last_day_prev, "Last Month"

    elif period == "this_year":
        start = today.replace(month=1, day=1)
        return start, today, "This Year"

    elif period == "last_30":
        start = today - timedelta(days=29)
        return start, today, "Last 30 Days"

    elif period == "last_90":
        start = today - timedelta(days=89)
        return start, today, "Last 90 Days"

    elif period == "custom" and start_str and end_str:
        try:
            start = datetime.strptime(start_str, "%Y-%m-%d").date()
            end = datetime.strptime(end_str, "%Y-%m-%d").date()
            if end < start:
                start, end = end, start
            label = f"{start.strftime('%d %b %Y')} – {end.strftime('%d %b %Y')}"
            return start, end, label
        except ValueError:
            pass

    # Default: this month
    start = today.replace(day=1)
    return start, today, "This Month"


def _date_to_dt_range(start_date, end_date):
    """Convert date pair to UTC datetime range (inclusive of end_date)."""
    start_dt = datetime(start_date.year, start_date.month, start_date.day,
                        tzinfo=timezone.utc)
    end_dt = datetime(end_date.year, end_date.month, end_date.day,
                      23, 59, 59, 999999, tzinfo=timezone.utc)
    return start_dt, end_dt


# ---------------------------------------------------------------------------
# 1. MAIN REPORTS DASHBOARD
# ---------------------------------------------------------------------------

@bp.route("/")
@login_required
def index():
    """Main reports page with revenue, tickets, technician stats."""
    period = request.args.get("period", "this_month", type=str).strip()
    start_str = request.args.get("start", "", type=str).strip()
    end_str = request.args.get("end", "", type=str).strip()

    start_date, end_date, period_label = _parse_date_range(period, start_str, end_str)
    start_dt, end_dt = _date_to_dt_range(start_date, end_date)

    # =====================================================================
    # REVENUE SUMMARY
    # =====================================================================

    # Invoice revenue (total of fully/partially paid invoices within range)
    invoice_revenue_q = (
        db.session.query(
            func.coalesce(func.sum(Invoice.total), 0.0).label("total"),
            func.coalesce(func.sum(Invoice.deposit_paid), 0.0).label("collected"),
            func.coalesce(func.sum(Invoice.balance_due), 0.0).label("outstanding"),
            func.count(Invoice.id).label("count"),
        )
        .filter(Invoice.created_at >= start_dt)
        .filter(Invoice.created_at <= end_dt)
        .first()
    )

    invoice_total = round(invoice_revenue_q.total or 0, 2)
    invoice_collected = round(invoice_revenue_q.collected or 0, 2)
    invoice_outstanding = round(invoice_revenue_q.outstanding or 0, 2)
    invoice_count = invoice_revenue_q.count or 0

    # Invoice revenue by payment method
    invoice_by_method = (
        db.session.query(
            Invoice.payment_method,
            func.count(Invoice.id).label("count"),
            func.coalesce(func.sum(Invoice.total), 0.0).label("total"),
        )
        .filter(Invoice.created_at >= start_dt)
        .filter(Invoice.created_at <= end_dt)
        .filter(Invoice.payment_method != "")
        .group_by(Invoice.payment_method)
        .order_by(func.sum(Invoice.total).desc())
        .all()
    )

    # POS sales revenue
    pos_revenue_q = (
        db.session.query(
            func.coalesce(func.sum(POSSale.total), 0.0).label("total"),
            func.count(POSSale.id).label("count"),
        )
        .filter(POSSale.created_at >= start_dt)
        .filter(POSSale.created_at <= end_dt)
        .first()
    )

    pos_total = round(pos_revenue_q.total or 0, 2)
    pos_count = pos_revenue_q.count or 0

    # POS revenue by payment method
    pos_by_method = (
        db.session.query(
            POSSale.payment_method,
            func.count(POSSale.id).label("count"),
            func.coalesce(func.sum(POSSale.total), 0.0).label("total"),
        )
        .filter(POSSale.created_at >= start_dt)
        .filter(POSSale.created_at <= end_dt)
        .group_by(POSSale.payment_method)
        .order_by(func.sum(POSSale.total).desc())
        .all()
    )

    combined_revenue = round(invoice_total + pos_total, 2)

    # =====================================================================
    # PROFIT ESTIMATION
    # =====================================================================

    # Parts cost on tickets (cost_price × quantity for parts used in the period)
    ticket_parts_cost = (
        db.session.query(
            func.coalesce(
                func.sum(TicketPartUsed.quantity * StockItem.cost_price), 0.0
            )
        )
        .join(StockItem, TicketPartUsed.stock_item_id == StockItem.id)
        .filter(TicketPartUsed.created_at >= start_dt)
        .filter(TicketPartUsed.created_at <= end_dt)
        .scalar()
    )
    ticket_parts_cost = round(ticket_parts_cost or 0, 2)

    # Parts cost on POS sales
    pos_parts_cost = (
        db.session.query(
            func.coalesce(
                func.sum(POSSaleItem.quantity * StockItem.cost_price), 0.0
            )
        )
        .join(StockItem, POSSaleItem.stock_item_id == StockItem.id)
        .join(POSSale, POSSaleItem.sale_id == POSSale.id)
        .filter(POSSale.created_at >= start_dt)
        .filter(POSSale.created_at <= end_dt)
        .scalar()
    )
    pos_parts_cost = round(pos_parts_cost or 0, 2)

    total_parts_cost = round(ticket_parts_cost + pos_parts_cost, 2)

    # Labour revenue (from invoices)
    labour_revenue = (
        db.session.query(
            func.coalesce(func.sum(Invoice.labour_cost), 0.0)
        )
        .filter(Invoice.created_at >= start_dt)
        .filter(Invoice.created_at <= end_dt)
        .scalar()
    )
    labour_revenue = round(labour_revenue or 0, 2)

    # Estimated gross profit = combined revenue - total parts cost
    estimated_profit = round(combined_revenue - total_parts_cost, 2)
    profit_margin = round((estimated_profit / combined_revenue * 100), 1) if combined_revenue > 0 else 0.0

    # =====================================================================
    # TICKET STATISTICS
    # =====================================================================

    # Tickets created in period
    tickets_created = (
        Ticket.query
        .filter(Ticket.created_at >= start_dt)
        .filter(Ticket.created_at <= end_dt)
        .count()
    )

    # Tickets by status (current status, regardless of creation date)
    tickets_by_status = (
        db.session.query(
            Ticket.status,
            func.count(Ticket.id).label("count"),
        )
        .group_by(Ticket.status)
        .order_by(func.count(Ticket.id).desc())
        .all()
    )

    # Tickets created in period grouped by status
    tickets_period_by_status = (
        db.session.query(
            Ticket.status,
            func.count(Ticket.id).label("count"),
        )
        .filter(Ticket.created_at >= start_dt)
        .filter(Ticket.created_at <= end_dt)
        .group_by(Ticket.status)
        .order_by(func.count(Ticket.id).desc())
        .all()
    )

    # Tickets by priority (created in period)
    tickets_by_priority = (
        db.session.query(
            Ticket.priority,
            func.count(Ticket.id).label("count"),
        )
        .filter(Ticket.created_at >= start_dt)
        .filter(Ticket.created_at <= end_dt)
        .group_by(Ticket.priority)
        .order_by(func.count(Ticket.id).desc())
        .all()
    )

    # =====================================================================
    # TECHNICIAN PERFORMANCE
    # =====================================================================

    technician_stats = (
        db.session.query(
            User.id,
            User.full_name,
            func.count(Ticket.id).label("total_tickets"),
            func.sum(case((Ticket.status == "Collected", 1), else_=0)).label("completed"),
            func.sum(case((Ticket.status.in_(["Waiting", "Diagnosed", "In Progress"]), 1), else_=0)).label("open"),
        )
        .outerjoin(Ticket, and_(
            Ticket.technician_id == User.id,
            Ticket.created_at >= start_dt,
            Ticket.created_at <= end_dt,
        ))
        .filter(User.is_active == True)
        .group_by(User.id, User.full_name)
        .order_by(func.count(Ticket.id).desc())
        .all()
    )

    # Revenue per technician (via invoices on their tickets)
    tech_revenue = (
        db.session.query(
            Ticket.technician_id,
            func.coalesce(func.sum(Invoice.total), 0.0).label("revenue"),
        )
        .join(Invoice, Invoice.ticket_id == Ticket.id)
        .filter(Invoice.created_at >= start_dt)
        .filter(Invoice.created_at <= end_dt)
        .group_by(Ticket.technician_id)
        .all()
    )
    tech_revenue_map = {tr.technician_id: round(tr.revenue or 0, 2) for tr in tech_revenue}

    # =====================================================================
    # STOCK VALUATION SUMMARY
    # =====================================================================

    stock_summary = (
        db.session.query(
            func.count(StockItem.id).label("total_items"),
            func.coalesce(func.sum(StockItem.quantity), 0).label("total_units"),
            func.coalesce(
                func.sum(StockItem.quantity * StockItem.cost_price), 0.0
            ).label("cost_value"),
            func.coalesce(
                func.sum(StockItem.quantity * StockItem.sell_price), 0.0
            ).label("sell_value"),
        )
        .first()
    )

    low_stock_count = (
        StockItem.query
        .filter(StockItem.quantity <= StockItem.low_stock_threshold)
        .count()
    )

    out_of_stock_count = (
        StockItem.query
        .filter(StockItem.quantity <= 0)
        .count()
    )

    # Top selling parts (by quantity used in period — tickets + POS)
    top_parts_tickets = (
        db.session.query(
            StockItem.id,
            StockItem.name,
            func.coalesce(func.sum(TicketPartUsed.quantity), 0).label("qty"),
            func.coalesce(func.sum(TicketPartUsed.quantity * TicketPartUsed.price_charged), 0.0).label("revenue"),
        )
        .join(TicketPartUsed, TicketPartUsed.stock_item_id == StockItem.id)
        .filter(TicketPartUsed.created_at >= start_dt)
        .filter(TicketPartUsed.created_at <= end_dt)
        .group_by(StockItem.id, StockItem.name)
    )

    top_parts_pos = (
        db.session.query(
            StockItem.id,
            StockItem.name,
            func.coalesce(func.sum(POSSaleItem.quantity), 0).label("qty"),
            func.coalesce(func.sum(POSSaleItem.quantity * POSSaleItem.price_charged), 0.0).label("revenue"),
        )
        .join(POSSaleItem, POSSaleItem.stock_item_id == StockItem.id)
        .join(POSSale, POSSaleItem.sale_id == POSSale.id)
        .filter(POSSale.created_at >= start_dt)
        .filter(POSSale.created_at <= end_dt)
        .group_by(StockItem.id, StockItem.name)
    )

    # Combine top parts from both sources
    parts_combined = {}
    for row in top_parts_tickets.all():
        parts_combined[row.id] = {
            "id": row.id, "name": row.name,
            "qty": row.qty, "revenue": round(row.revenue, 2),
        }
    for row in top_parts_pos.all():
        if row.id in parts_combined:
            parts_combined[row.id]["qty"] += row.qty
            parts_combined[row.id]["revenue"] = round(
                parts_combined[row.id]["revenue"] + row.revenue, 2
            )
        else:
            parts_combined[row.id] = {
                "id": row.id, "name": row.name,
                "qty": row.qty, "revenue": round(row.revenue, 2),
            }

    top_parts = sorted(parts_combined.values(), key=lambda x: x["qty"], reverse=True)[:10]

    # =====================================================================
    # DAILY REVENUE BREAKDOWN (for chart data)
    # =====================================================================

    daily_revenue = _get_daily_revenue(start_dt, end_dt)

    # =====================================================================
    # CUSTOMER STATS
    # =====================================================================

    new_customers = (
        Customer.query
        .filter(Customer.created_at >= start_dt)
        .filter(Customer.created_at <= end_dt)
        .count()
    )

    total_customers = Customer.query.count()

    # =====================================================================
    # STATUS COLOUR MAP (reuse from tickets)
    # =====================================================================

    status_colours = {
        "Waiting": "warning",
        "Diagnosed": "info",
        "In Progress": "primary",
        "Ready": "success",
        "Collected": "secondary",
        "Cancelled": "danger",
    }

    priority_colours = {
        "Low": "secondary",
        "Normal": "primary",
        "High": "warning",
        "Urgent": "danger",
    }

    return render_template(
        "reports/index.html",
        # Period
        period=period,
        period_label=period_label,
        start_date=start_date,
        end_date=end_date,
        # Revenue
        invoice_total=invoice_total,
        invoice_collected=invoice_collected,
        invoice_outstanding=invoice_outstanding,
        invoice_count=invoice_count,
        invoice_by_method=invoice_by_method,
        pos_total=pos_total,
        pos_count=pos_count,
        pos_by_method=pos_by_method,
        combined_revenue=combined_revenue,
        # Profit
        labour_revenue=labour_revenue,
        total_parts_cost=total_parts_cost,
        ticket_parts_cost=ticket_parts_cost,
        pos_parts_cost=pos_parts_cost,
        estimated_profit=estimated_profit,
        profit_margin=profit_margin,
        # Tickets
        tickets_created=tickets_created,
        tickets_by_status=tickets_by_status,
        tickets_period_by_status=tickets_period_by_status,
        tickets_by_priority=tickets_by_priority,
        # Technicians
        technician_stats=technician_stats,
        tech_revenue_map=tech_revenue_map,
        # Stock
        stock_summary=stock_summary,
        low_stock_count=low_stock_count,
        out_of_stock_count=out_of_stock_count,
        top_parts=top_parts,
        # Daily chart
        daily_revenue=daily_revenue,
        # Customers
        new_customers=new_customers,
        total_customers=total_customers,
        # Colours
        status_colours=status_colours,
        priority_colours=priority_colours,
    )


# ---------------------------------------------------------------------------
# 2. DAILY REVENUE HELPER (for chart)
# ---------------------------------------------------------------------------

def _get_daily_revenue(start_dt, end_dt):
    """Return list of dicts: [{date, invoices, pos, total}, ...] for charting."""
    # Generate all dates in range
    start_d = start_dt.date() if hasattr(start_dt, 'date') else start_dt
    end_d = end_dt.date() if hasattr(end_dt, 'date') else end_dt
    num_days = (end_d - start_d).days + 1

    # Cap at 366 days to prevent huge queries
    if num_days > 366:
        start_d = end_d - timedelta(days=365)
        num_days = 366

    date_map = {}
    for i in range(num_days):
        d = start_d + timedelta(days=i)
        date_map[d.isoformat()] = {"date": d.isoformat(), "invoices": 0.0, "pos": 0.0, "total": 0.0}

    # Invoice revenue by day (using created_at date)
    inv_daily = (
        db.session.query(
            func.date(Invoice.created_at).label("day"),
            func.coalesce(func.sum(Invoice.total), 0.0).label("total"),
        )
        .filter(Invoice.created_at >= start_dt)
        .filter(Invoice.created_at <= end_dt)
        .group_by(func.date(Invoice.created_at))
        .all()
    )
    for row in inv_daily:
        day_key = str(row.day)
        if day_key in date_map:
            date_map[day_key]["invoices"] = round(float(row.total), 2)

    # POS revenue by day
    pos_daily = (
        db.session.query(
            func.date(POSSale.created_at).label("day"),
            func.coalesce(func.sum(POSSale.total), 0.0).label("total"),
        )
        .filter(POSSale.created_at >= start_dt)
        .filter(POSSale.created_at <= end_dt)
        .group_by(func.date(POSSale.created_at))
        .all()
    )
    for row in pos_daily:
        day_key = str(row.day)
        if day_key in date_map:
            date_map[day_key]["pos"] = round(float(row.total), 2)

    # Calculate totals
    result = []
    for d_key in sorted(date_map.keys()):
        entry = date_map[d_key]
        entry["total"] = round(entry["invoices"] + entry["pos"], 2)
        result.append(entry)

    return result


# ---------------------------------------------------------------------------
# 3. API — JSON endpoint for reports data (AI/AJAX integrations)
# ---------------------------------------------------------------------------

@bp.route("/api/summary")
@login_required
def api_summary():
    """Return reports summary as JSON for AJAX/AI integrations."""
    period = request.args.get("period", "this_month", type=str).strip()
    start_str = request.args.get("start", "", type=str).strip()
    end_str = request.args.get("end", "", type=str).strip()

    start_date, end_date, period_label = _parse_date_range(period, start_str, end_str)
    start_dt, end_dt = _date_to_dt_range(start_date, end_date)

    # Revenue
    inv_total = db.session.query(
        func.coalesce(func.sum(Invoice.total), 0.0)
    ).filter(Invoice.created_at >= start_dt, Invoice.created_at <= end_dt).scalar()

    pos_total = db.session.query(
        func.coalesce(func.sum(POSSale.total), 0.0)
    ).filter(POSSale.created_at >= start_dt, POSSale.created_at <= end_dt).scalar()

    # Parts cost
    parts_cost = db.session.query(
        func.coalesce(func.sum(TicketPartUsed.quantity * StockItem.cost_price), 0.0)
    ).join(StockItem).filter(
        TicketPartUsed.created_at >= start_dt, TicketPartUsed.created_at <= end_dt
    ).scalar()

    pos_cost = db.session.query(
        func.coalesce(func.sum(POSSaleItem.quantity * StockItem.cost_price), 0.0)
    ).join(StockItem).join(POSSale).filter(
        POSSale.created_at >= start_dt, POSSale.created_at <= end_dt
    ).scalar()

    combined = round((inv_total or 0) + (pos_total or 0), 2)
    total_cost = round((parts_cost or 0) + (pos_cost or 0), 2)
    profit = round(combined - total_cost, 2)

    # Tickets
    tickets_created = Ticket.query.filter(
        Ticket.created_at >= start_dt, Ticket.created_at <= end_dt
    ).count()

    return jsonify({
        "period": period_label,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "revenue": {
            "invoices": round(inv_total or 0, 2),
            "pos_sales": round(pos_total or 0, 2),
            "combined": combined,
        },
        "costs": {
            "ticket_parts": round(parts_cost or 0, 2),
            "pos_parts": round(pos_cost or 0, 2),
            "total": total_cost,
        },
        "profit": {
            "estimated": profit,
            "margin_percent": round((profit / combined * 100), 1) if combined > 0 else 0,
        },
        "tickets_created": tickets_created,
        "daily_revenue": _get_daily_revenue(start_dt, end_dt),
    })


# ---------------------------------------------------------------------------
# 4. API — Daily revenue chart data
# ---------------------------------------------------------------------------

@bp.route("/api/daily-revenue")
@login_required
def api_daily_revenue():
    """Return daily revenue breakdown as JSON for charting."""
    period = request.args.get("period", "this_month", type=str).strip()
    start_str = request.args.get("start", "", type=str).strip()
    end_str = request.args.get("end", "", type=str).strip()

    start_date, end_date, period_label = _parse_date_range(period, start_str, end_str)
    start_dt, end_dt = _date_to_dt_range(start_date, end_date)

    return jsonify({
        "period": period_label,
        "data": _get_daily_revenue(start_dt, end_dt),
    })
