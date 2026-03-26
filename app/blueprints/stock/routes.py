from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.blueprints.stock import bp
from app.extensions import db
from app.models import StockItem, Barcode, TicketPartUsed, POSSaleItem


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Default categories — easily extendable; kept as a list so future phases
# can pull distinct categories from the DB and merge with these defaults.
DEFAULT_CATEGORIES = [
    "General",
    "Screens",
    "Batteries",
    "Charging Ports",
    "Cameras",
    "Housings & Frames",
    "Flex Cables",
    "Connectors",
    "Logic Boards",
    "Accessories",
    "Tools",
    "Other",
]


def _get_all_categories():
    """Return sorted unique categories (DB values merged with defaults)."""
    db_cats = (
        db.session.query(StockItem.category)
        .distinct()
        .order_by(StockItem.category)
        .all()
    )
    db_set = {c[0] for c in db_cats if c[0]}
    merged = sorted(db_set | set(DEFAULT_CATEGORIES))
    return merged


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _validate_stock_form(form, is_edit=False, current_item=None):
    """Validate stock item form. Returns (cleaned_data, errors)."""
    errors = []

    name = form.get("name", "").strip()
    category = form.get("category", "General").strip()
    sku = form.get("sku", "").strip()
    compatible_devices = form.get("compatible_devices", "").strip()
    supplier = form.get("supplier", "").strip()

    # Numeric fields
    quantity_str = form.get("quantity", "0").strip()
    low_stock_threshold_str = form.get("low_stock_threshold", "5").strip()
    cost_price_str = form.get("cost_price", "0").strip()
    sell_price_str = form.get("sell_price", "0").strip()

    # --- Name ---
    if not name:
        errors.append("Part name is required.")
    elif len(name) < 2:
        errors.append("Part name must be at least 2 characters.")

    # --- SKU uniqueness (only if provided) ---
    if sku:
        sku_query = StockItem.query.filter(
            db.func.lower(StockItem.sku) == sku.lower()
        )
        if is_edit and current_item:
            sku_query = sku_query.filter(StockItem.id != current_item.id)
        if sku_query.first():
            errors.append(f"SKU '{sku}' is already in use.")

    # --- Quantity ---
    try:
        quantity = int(quantity_str)
        if quantity < 0:
            errors.append("Quantity cannot be negative.")
    except ValueError:
        errors.append("Quantity must be a whole number.")
        quantity = 0

    # --- Low stock threshold ---
    try:
        low_stock_threshold = int(low_stock_threshold_str)
        if low_stock_threshold < 0:
            errors.append("Low stock threshold cannot be negative.")
    except ValueError:
        errors.append("Low stock threshold must be a whole number.")
        low_stock_threshold = 5

    # --- Cost price ---
    try:
        cost_price = round(float(cost_price_str), 2)
        if cost_price < 0:
            errors.append("Cost price cannot be negative.")
    except ValueError:
        errors.append("Cost price must be a valid number.")
        cost_price = 0.0

    # --- Sell price ---
    try:
        sell_price = round(float(sell_price_str), 2)
        if sell_price < 0:
            errors.append("Sell price cannot be negative.")
    except ValueError:
        errors.append("Sell price must be a valid number.")
        sell_price = 0.0

    cleaned = {
        "name": name,
        "category": category if category else "General",
        "sku": sku,
        "compatible_devices": compatible_devices,
        "quantity": quantity,
        "low_stock_threshold": low_stock_threshold,
        "cost_price": cost_price,
        "sell_price": sell_price,
        "supplier": supplier,
    }
    return cleaned, errors


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@bp.route("/")
@login_required
def index():
    """List all stock items with search, category filter, low-stock filter, pagination."""
    page = request.args.get("page", 1, type=int)
    per_page = 20
    search = request.args.get("q", "", type=str).strip()
    category_filter = request.args.get("category", "", type=str).strip()
    low_stock_only = request.args.get("low_stock", "", type=str).strip()

    query = StockItem.query

    # --- Search (name, SKU, compatible devices, supplier) ---
    if search:
        like = f"%{search}%"
        query = query.filter(
            db.or_(
                StockItem.name.ilike(like),
                StockItem.sku.ilike(like),
                StockItem.compatible_devices.ilike(like),
                StockItem.supplier.ilike(like),
            )
        )

    # --- Category filter ---
    if category_filter:
        query = query.filter(StockItem.category == category_filter)

    # --- Low stock filter ---
    if low_stock_only == "1":
        query = query.filter(StockItem.quantity <= StockItem.low_stock_threshold)

    query = query.order_by(StockItem.name.asc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    # Count low-stock items for badge display
    low_stock_count = StockItem.query.filter(
        StockItem.quantity <= StockItem.low_stock_threshold
    ).count()

    return render_template(
        "stock/index.html",
        items=pagination.items,
        pagination=pagination,
        search=search,
        category_filter=category_filter,
        low_stock_only=low_stock_only,
        categories=_get_all_categories(),
        low_stock_count=low_stock_count,
    )


@bp.route("/add", methods=["GET", "POST"])
@login_required
def add():
    """Add a new stock item."""
    if request.method == "POST":
        cleaned, errors = _validate_stock_form(request.form)

        # Validate new barcodes
        new_barcodes = request.form.getlist("new_barcodes[]")
        new_barcodes = [b.strip() for b in new_barcodes if b.strip()]
        for code in new_barcodes:
            existing = Barcode.query.filter(db.func.lower(Barcode.code) == code.lower()).first()
            if existing:
                errors.append(f"Barcode '{code}' is already assigned to '{existing.stock_item.name}'.")

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template(
                "stock/add.html",
                categories=_get_all_categories(),
                form_data=request.form,
            )

        item = StockItem(**cleaned)
        db.session.add(item)
        db.session.flush()  # Get item.id before adding barcodes

        # Create barcode records
        for code in new_barcodes:
            db.session.add(Barcode(code=code, stock_item_id=item.id))

        # If barcodes were scanned, quantity = barcode count
        if new_barcodes:
            item.quantity = len(new_barcodes)

        db.session.commit()

        flash(f"Stock item '{item.name}' added successfully.", "success")
        return redirect(url_for("stock.view", item_id=item.id))

    return render_template(
        "stock/add.html",
        categories=_get_all_categories(),
        form_data={},
    )


@bp.route("/<int:item_id>")
@login_required
def view(item_id):
    """View stock item detail with usage history."""
    item = StockItem.query.get_or_404(item_id)

    # Fetch usage in tickets (most recent first)
    ticket_uses = (
        TicketPartUsed.query
        .filter_by(stock_item_id=item.id)
        .order_by(TicketPartUsed.created_at.desc())
        .limit(50)
        .all()
    )

    # Fetch usage in POS sales (most recent first)
    pos_uses = (
        POSSaleItem.query
        .filter_by(stock_item_id=item.id)
        .order_by(POSSaleItem.created_at.desc())
        .limit(50)
        .all()
    )

    active_barcodes = item.barcodes.filter_by(is_active=True).order_by(Barcode.created_at.desc()).all()
    used_barcodes = item.barcodes.filter_by(is_active=False).order_by(Barcode.used_at.desc()).limit(20).all()

    return render_template(
        "stock/view.html",
        item=item,
        ticket_uses=ticket_uses,
        pos_uses=pos_uses,
        active_barcodes=active_barcodes,
        used_barcodes=used_barcodes,
    )


@bp.route("/<int:item_id>/edit", methods=["GET", "POST"])
@login_required
def edit(item_id):
    """Edit an existing stock item."""
    item = StockItem.query.get_or_404(item_id)

    if request.method == "POST":
        cleaned, errors = _validate_stock_form(
            request.form, is_edit=True, current_item=item
        )

        # Validate new barcodes
        new_barcodes = request.form.getlist("new_barcodes[]")
        new_barcodes = [b.strip() for b in new_barcodes if b.strip()]
        for code in new_barcodes:
            existing = Barcode.query.filter(db.func.lower(Barcode.code) == code.lower()).first()
            if existing:
                errors.append(f"Barcode '{code}' is already assigned to '{existing.stock_item.name}'.")

        if errors:
            for e in errors:
                flash(e, "danger")
            existing_barcodes = item.barcodes.filter_by(is_active=True).all()
            return render_template(
                "stock/edit.html",
                item=item,
                categories=_get_all_categories(),
                form_data=request.form,
                existing_barcodes=existing_barcodes,
            )

        # Apply changes
        for key, value in cleaned.items():
            setattr(item, key, value)

        # Handle barcode removals (barcodes in DB but not in submitted existing_barcodes[])
        kept_codes = set(b.strip().lower() for b in request.form.getlist("existing_barcodes[]") if b.strip())
        for bc in item.barcodes.filter_by(is_active=True).all():
            if bc.code.lower() not in kept_codes:
                db.session.delete(bc)

        # Add new barcodes
        for code in new_barcodes:
            db.session.add(Barcode(code=code, stock_item_id=item.id))

        # Sync quantity if item uses barcodes
        db.session.flush()
        item.sync_barcode_quantity()

        db.session.commit()
        flash(f"Stock item '{item.name}' updated.", "success")
        return redirect(url_for("stock.view", item_id=item.id))

    existing_barcodes = item.barcodes.filter_by(is_active=True).all()
    form_data = {
        "name": item.name,
        "category": item.category,
        "sku": item.sku,
        "compatible_devices": item.compatible_devices,
        "quantity": str(item.quantity),
        "low_stock_threshold": str(item.low_stock_threshold),
        "cost_price": str(item.cost_price),
        "sell_price": str(item.sell_price),
        "supplier": item.supplier,
    }
    return render_template(
        "stock/edit.html",
        item=item,
        categories=_get_all_categories(),
        form_data=form_data,
        existing_barcodes=existing_barcodes,
    )


@bp.route("/<int:item_id>/adjust", methods=["POST"])
@login_required
def adjust_quantity(item_id):
    """Quick quantity adjustment (receive stock / correct errors)."""
    item = StockItem.query.get_or_404(item_id)

    adjustment_str = request.form.get("adjustment", "0").strip()
    reason = request.form.get("reason", "").strip()

    try:
        adjustment = int(adjustment_str)
    except ValueError:
        flash("Adjustment must be a whole number.", "danger")
        return redirect(url_for("stock.view", item_id=item.id))

    if adjustment == 0:
        flash("Adjustment cannot be zero.", "warning")
        return redirect(url_for("stock.view", item_id=item.id))

    new_quantity = item.quantity + adjustment
    if new_quantity < 0:
        flash(f"Cannot reduce stock below zero. Current: {item.quantity}, Adjustment: {adjustment}.", "danger")
        return redirect(url_for("stock.view", item_id=item.id))

    if not reason:
        flash("Please provide a reason for the stock adjustment.", "danger")
        return redirect(url_for("stock.view", item_id=item.id))

    old_qty = item.quantity
    item.quantity = new_quantity
    db.session.commit()

    direction = "increased" if adjustment > 0 else "decreased"
    flash(
        f"Stock {direction} by {abs(adjustment)}. "
        f"{old_qty} → {new_quantity}. Reason: {reason}",
        "success",
    )
    return redirect(url_for("stock.view", item_id=item.id))


@bp.route("/<int:item_id>/delete", methods=["POST"])
@login_required
def delete(item_id):
    """Delete a stock item (blocked if used in tickets or POS sales)."""
    item = StockItem.query.get_or_404(item_id)

    # Check if part has been used in any ticket
    ticket_use_count = TicketPartUsed.query.filter_by(stock_item_id=item.id).count()
    if ticket_use_count > 0:
        flash(
            f"Cannot delete '{item.name}' — it has been used in {ticket_use_count} ticket(s).",
            "danger",
        )
        return redirect(url_for("stock.view", item_id=item.id))

    # Check if part has been used in any POS sale
    pos_use_count = POSSaleItem.query.filter_by(stock_item_id=item.id).count()
    if pos_use_count > 0:
        flash(
            f"Cannot delete '{item.name}' — it has been used in {pos_use_count} POS sale(s).",
            "danger",
        )
        return redirect(url_for("stock.view", item_id=item.id))

    name = item.name
    db.session.delete(item)
    db.session.commit()

    flash(f"Stock item '{name}' deleted.", "success")
    return redirect(url_for("stock.index"))


# ---------------------------------------------------------------------------
# API-style endpoint for AJAX (future-proof for JS/AI integrations)
# ---------------------------------------------------------------------------

@bp.route("/api/search")
@login_required
def api_search():
    """Return stock items as JSON for AJAX dropdowns.
    Query param: q (search term), limit (max results, default 10).
    Supports barcode exact match (priority) and fuzzy text search.
    """
    from flask import jsonify

    search = request.args.get("q", "", type=str).strip()
    limit = request.args.get("limit", 10, type=int)

    if not search or len(search) < 1:
        return jsonify([])

    # Phase 1: Exact barcode match (highest priority)
    barcode_hit = Barcode.query.filter(
        db.func.lower(Barcode.code) == search.lower(),
        Barcode.is_active == True,
    ).first()

    if barcode_hit:
        item = barcode_hit.stock_item
        return jsonify([{
            "id": item.id,
            "name": item.name,
            "sku": item.sku,
            "category": item.category,
            "quantity": item.quantity,
            "sell_price": item.sell_price,
            "is_low_stock": item.is_low_stock,
            "barcode_match": True,
        }])

    # Phase 2: Fuzzy text search by name, SKU, compatible devices
    like = f"%{search}%"
    items = (
        StockItem.query
        .filter(
            db.or_(
                StockItem.name.ilike(like),
                StockItem.sku.ilike(like),
                StockItem.compatible_devices.ilike(like),
            )
        )
        .order_by(StockItem.name)
        .limit(limit)
        .all()
    )

    result = [
        {
            "id": item.id,
            "name": item.name,
            "sku": item.sku,
            "category": item.category,
            "quantity": item.quantity,
            "sell_price": item.sell_price,
            "is_low_stock": item.is_low_stock,
            "barcode_match": False,
        }
        for item in items
    ]
    return jsonify(result)


@bp.route("/<int:item_id>/remove-barcode", methods=["POST"])
@login_required
def remove_barcode(item_id):
    """Remove (delete) an active barcode from a stock item."""
    from flask import jsonify

    item = StockItem.query.get_or_404(item_id)
    barcode_id = request.form.get("barcode_id", type=int)

    if not barcode_id:
        flash("No barcode specified.", "danger")
        return redirect(url_for("stock.view", item_id=item.id))

    barcode = Barcode.query.filter_by(id=barcode_id, stock_item_id=item.id, is_active=True).first()
    if not barcode:
        flash("Barcode not found or already used.", "danger")
        return redirect(url_for("stock.view", item_id=item.id))

    db.session.delete(barcode)
    item.sync_barcode_quantity()
    db.session.commit()

    flash(f"Barcode '{barcode.code}' removed.", "success")
    return redirect(url_for("stock.view", item_id=item.id))
