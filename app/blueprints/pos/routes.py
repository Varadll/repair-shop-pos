from flask import (
    render_template, request, redirect, url_for, flash,
    current_app, make_response, jsonify,
)
from flask_login import login_required, current_user
from app.blueprints.pos import bp
from app.extensions import db
from app.models import POSSale, POSSaleItem, StockItem, Customer, Barcode


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PAYMENT_METHODS = ["Cash", "Card", "Bank Transfer", "Other"]


# ---------------------------------------------------------------------------
# 1. LIST — all POS sales with search, date filter, pagination
# ---------------------------------------------------------------------------

@bp.route("/")
@login_required
def index():
    """List all POS sales with search and filters."""
    page = request.args.get("page", 1, type=int)
    per_page = 20
    search = request.args.get("q", "", type=str).strip()
    date_filter = request.args.get("date", "", type=str).strip()  # today / week / month

    query = POSSale.query

    # --- Search (sale #, customer name, customer phone) ---
    if search:
        like = f"%{search}%"
        query = query.outerjoin(Customer).filter(
            db.or_(
                POSSale.sale_number.ilike(like),
                Customer.first_name.ilike(like),
                Customer.last_name.ilike(like),
                Customer.phone.ilike(like),
                POSSale.notes.ilike(like),
            )
        )

    # --- Date filter ---
    if date_filter:
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)
        if date_filter == "today":
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            query = query.filter(POSSale.created_at >= start)
        elif date_filter == "week":
            start = (now - timedelta(days=now.weekday())).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            query = query.filter(POSSale.created_at >= start)
        elif date_filter == "month":
            start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            query = query.filter(POSSale.created_at >= start)

    query = query.order_by(POSSale.created_at.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    # Today's summary for top cards
    from datetime import datetime, timezone
    today_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    today_sales = POSSale.query.filter(POSSale.created_at >= today_start).all()
    today_count = len(today_sales)
    today_revenue = round(sum(s.total for s in today_sales), 2)

    return render_template(
        "pos/index.html",
        sales=pagination.items,
        pagination=pagination,
        search=search,
        date_filter=date_filter,
        today_count=today_count,
        today_revenue=today_revenue,
    )


# ---------------------------------------------------------------------------
# 2. CREATE — quick counter sale with AJAX item search
# ---------------------------------------------------------------------------

@bp.route("/create", methods=["GET", "POST"])
@login_required
def create():
    """Create a new POS sale. Items are added via hidden fields populated by JS."""
    if request.method == "POST":
        # --- Parse cart items from hidden fields ---
        item_ids = request.form.getlist("item_id[]")
        item_qtys = request.form.getlist("item_qty[]")
        item_prices = request.form.getlist("item_price[]")

        if not item_ids:
            flash("Please add at least one item to the sale.", "danger")
            return redirect(url_for("pos.create"))

        # --- Optional customer ---
        customer_id = request.form.get("customer_id", "", type=str).strip()
        customer = None
        if customer_id:
            try:
                customer = Customer.query.get(int(customer_id))
            except (ValueError, TypeError):
                customer = None

        # --- Payment method ---
        payment_method = request.form.get("payment_method", "Cash").strip()
        if payment_method not in PAYMENT_METHODS:
            payment_method = "Cash"

        notes = request.form.get("notes", "").strip()

        # --- Build sale items, validate stock ---
        errors = []
        sale_items = []
        sale_total = 0.0

        for i, raw_id in enumerate(item_ids):
            try:
                stock_id = int(raw_id)
                qty = int(item_qtys[i]) if i < len(item_qtys) else 1
                price = round(float(item_prices[i]), 2) if i < len(item_prices) else 0.0
            except (ValueError, IndexError):
                errors.append(f"Invalid data for item row {i + 1}.")
                continue

            if qty <= 0:
                errors.append(f"Quantity must be at least 1 for row {i + 1}.")
                continue
            if price < 0:
                errors.append(f"Price cannot be negative for row {i + 1}.")
                continue

            stock_item = StockItem.query.get(stock_id)
            if not stock_item:
                errors.append(f"Stock item #{stock_id} not found.")
                continue
            if stock_item.quantity < qty:
                errors.append(
                    f"Not enough stock for '{stock_item.name}'. "
                    f"Available: {stock_item.quantity}, Requested: {qty}."
                )
                continue

            sale_items.append({
                "stock_item": stock_item,
                "quantity": qty,
                "price_charged": price,
            })
            sale_total += round(qty * price, 2)

        if errors:
            for e in errors:
                flash(e, "danger")
            return redirect(url_for("pos.create"))

        # --- Create the sale ---
        sale = POSSale(
            sale_number=POSSale.generate_sale_number(),
            served_by=current_user.id,
            customer_id=customer.id if customer else None,
            total=round(sale_total, 2),
            payment_method=payment_method,
            notes=notes,
        )
        db.session.add(sale)
        db.session.flush()  # Get sale.id before creating items

        # --- Create sale items + deduct stock + deactivate barcodes ---
        from datetime import datetime, timezone as tz
        now = datetime.now(tz.utc)

        for si in sale_items:
            pos_item = POSSaleItem(
                sale_id=sale.id,
                stock_item_id=si["stock_item"].id,
                quantity=si["quantity"],
                price_charged=si["price_charged"],
            )
            db.session.add(pos_item)

            # Deactivate barcodes for sold quantity (if item has barcodes)
            active_barcodes = (
                Barcode.query
                .filter_by(stock_item_id=si["stock_item"].id, is_active=True)
                .order_by(Barcode.created_at.asc())
                .limit(si["quantity"])
                .all()
            )
            for bc in active_barcodes:
                bc.is_active = False
                bc.used_at = now

            # Auto-deduct stock
            si["stock_item"].quantity -= si["quantity"]

        db.session.commit()

        flash(f"Sale {sale.sale_number} completed — €{sale.total:.2f} ({payment_method}).", "success")
        return redirect(url_for("pos.view", sale_id=sale.id))

    # GET — render the create page
    return render_template(
        "pos/create.html",
        payment_methods=PAYMENT_METHODS,
    )


# ---------------------------------------------------------------------------
# 3. VIEW — sale detail page
# ---------------------------------------------------------------------------

@bp.route("/<int:sale_id>")
@login_required
def view(sale_id):
    """View POS sale detail."""
    sale = POSSale.query.get_or_404(sale_id)
    items = POSSaleItem.query.filter_by(sale_id=sale.id).all()

    return render_template(
        "pos/view.html",
        sale=sale,
        items=items,
    )


# ---------------------------------------------------------------------------
# 4. RECEIPT PDF — compact receipt via WeasyPrint
# ---------------------------------------------------------------------------

@bp.route("/<int:sale_id>/receipt")
@login_required
def receipt_pdf(sale_id):
    """Generate a compact receipt PDF."""
    sale = POSSale.query.get_or_404(sale_id)
    items = POSSaleItem.query.filter_by(sale_id=sale.id).all()

    ctx = {
        "sale": sale,
        "items": items,
        "shop_name": current_app.config.get("SHOP_NAME", "Repair Shop"),
        "shop_address": current_app.config.get("SHOP_ADDRESS", ""),
        "shop_phone": current_app.config.get("SHOP_PHONE", ""),
        "shop_email": current_app.config.get("SHOP_EMAIL", ""),
        "shop_vat": current_app.config.get("SHOP_VAT", ""),
    }

    html_string = render_template("pos/receipt_pdf.html", **ctx)

    try:
        from weasyprint import HTML
        pdf_bytes = HTML(string=html_string).write_pdf()
    except ImportError:
        flash("WeasyPrint is not installed. Run: pip install weasyprint", "danger")
        return redirect(url_for("pos.view", sale_id=sale.id))
    except Exception as e:
        flash(f"Receipt generation failed: {str(e)}", "danger")
        return redirect(url_for("pos.view", sale_id=sale.id))

    response = make_response(pdf_bytes)
    response.headers["Content-Type"] = "application/pdf"
    filename = f"{sale.sale_number}-receipt.pdf"
    response.headers["Content-Disposition"] = f"inline; filename={filename}"
    return response


# ---------------------------------------------------------------------------
# 5. DELETE — admin only
# ---------------------------------------------------------------------------

@bp.route("/<int:sale_id>/delete", methods=["POST"])
@login_required
def delete(sale_id):
    """Delete a POS sale and restore stock (admin only)."""
    sale = POSSale.query.get_or_404(sale_id)

    if not current_user.is_admin:
        flash("Only administrators can delete POS sales.", "danger")
        return redirect(url_for("pos.view", sale_id=sale.id))

    sale_number = sale.sale_number

    # Restore stock for each item
    items = POSSaleItem.query.filter_by(sale_id=sale.id).all()
    for item in items:
        stock = StockItem.query.get(item.stock_item_id)
        if stock:
            stock.quantity += item.quantity

    db.session.delete(sale)
    db.session.commit()

    flash(f"Sale {sale_number} deleted and stock restored.", "success")
    return redirect(url_for("pos.index"))


# ---------------------------------------------------------------------------
# 6. API — customer search for optional customer linking
# ---------------------------------------------------------------------------

@bp.route("/api/customer-search")
@login_required
def api_customer_search():
    """Return customers as JSON for AJAX typeahead on POS create page."""
    search = request.args.get("q", "", type=str).strip()
    limit = request.args.get("limit", 10, type=int)

    if not search:
        return jsonify([])

    like = f"%{search}%"
    customers = (
        Customer.query
        .filter(
            db.or_(
                Customer.first_name.ilike(like),
                Customer.last_name.ilike(like),
                Customer.phone.ilike(like),
            )
        )
        .order_by(Customer.first_name)
        .limit(limit)
        .all()
    )

    return jsonify([
        {
            "id": c.id,
            "name": c.full_name,
            "phone": c.phone,
        }
        for c in customers
    ])


# ---------------------------------------------------------------------------
# 7. API — sale summary JSON
# ---------------------------------------------------------------------------

@bp.route("/api/summary/<int:sale_id>")
@login_required
def api_summary(sale_id):
    """Return POS sale summary as JSON."""
    sale = POSSale.query.get_or_404(sale_id)
    items = POSSaleItem.query.filter_by(sale_id=sale.id).all()

    return jsonify({
        "sale_number": sale.sale_number,
        "total": sale.total,
        "payment_method": sale.payment_method,
        "served_by": sale.served_by_user.full_name if sale.served_by_user else "Unknown",
        "customer": sale.customer.full_name if sale.customer else None,
        "notes": sale.notes,
        "created_at": sale.created_at.isoformat() if sale.created_at else None,
        "items": [
            {
                "name": i.stock_item.name if i.stock_item else "Unknown",
                "quantity": i.quantity,
                "price_charged": i.price_charged,
                "line_total": i.line_total,
            }
            for i in items
        ],
    })
