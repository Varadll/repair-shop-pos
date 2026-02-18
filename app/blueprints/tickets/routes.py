from datetime import datetime, date
from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.blueprints.tickets import bp
from app.extensions import db
from app.models import (
    Ticket, Customer, Device, User, TicketProgressLog,
<<<<<<< HEAD
=======
    StockItem, TicketPartUsed,
>>>>>>> 51e3823 (commit new changes)
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STATUS_CHOICES = Ticket.STATUSES          # ["Waiting", "Diagnosed", ...]
PRIORITY_CHOICES = Ticket.PRIORITIES      # ["Low", "Normal", "High", "Urgent"]

STATUS_COLOURS = {
    "Waiting": "warning",
    "Diagnosed": "info",
    "In Progress": "primary",
    "Ready": "success",
    "Collected": "secondary",
    "Cancelled": "danger",
}

PRIORITY_COLOURS = {
    "Low": "secondary",
    "Normal": "primary",
    "High": "warning",
    "Urgent": "danger",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_technicians():
    """Return all active users (both admin and technician) for assignment."""
    return User.query.filter_by(is_active=True).order_by(User.full_name).all()


def _log_progress(ticket, action, old_value="", new_value="", note=""):
    """Write one row to the audit trail."""
    entry = TicketProgressLog(
        ticket_id=ticket.id,
        user_id=current_user.id,
        action=action,
        old_value=str(old_value),
        new_value=str(new_value),
        note=note,
    )
    db.session.add(entry)


def _validate_ticket_form(form, is_edit=False):
    """Validate ticket creation / edit form. Returns (cleaned, errors)."""
    errors = []

    fault_description = form.get("fault_description", "").strip()
    priority = form.get("priority", "Normal").strip()
    due_date_str = form.get("due_date", "").strip()
    technician_id = form.get("technician_id", "").strip()
    customer_notes = form.get("customer_notes", "").strip()
    internal_notes = form.get("internal_notes", "").strip()

    if not fault_description:
        errors.append("Fault description is required.")
    elif len(fault_description) < 5:
        errors.append("Fault description must be at least 5 characters.")

    if priority not in PRIORITY_CHOICES:
        errors.append("Invalid priority selected.")

    due_date = None
    if due_date_str:
        try:
            due_date = datetime.strptime(due_date_str, "%Y-%m-%d").date()
        except ValueError:
            errors.append("Due date must be a valid date (YYYY-MM-DD).")

    tech_id = None
    if technician_id:
        try:
            tech_id = int(technician_id)
            if not User.query.get(tech_id):
                errors.append("Selected technician does not exist.")
        except ValueError:
            errors.append("Invalid technician selection.")

    # Creation-only validations
    if not is_edit:
        device_id = form.get("device_id", "").strip()
        disclaimer = form.get("disclaimer_accepted")

        if not device_id:
            errors.append("Please select a device.")
        else:
            try:
                device_id = int(device_id)
            except ValueError:
                errors.append("Invalid device selection.")
                device_id = None

        if not disclaimer:
            errors.append("Customer must accept the disclaimer before creating a ticket.")
    else:
        device_id = None
        disclaimer = None

    cleaned = {
        "fault_description": fault_description,
        "priority": priority,
        "due_date": due_date,
        "technician_id": tech_id,
        "customer_notes": customer_notes,
        "internal_notes": internal_notes,
        "device_id": device_id,
        "disclaimer_accepted": bool(disclaimer),
    }
    return cleaned, errors


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@bp.route("/")
@login_required
def index():
    """List all tickets with search, filters, and pagination."""
    page = request.args.get("page", 1, type=int)
    per_page = 20
    search = request.args.get("q", "", type=str).strip()
    status_filter = request.args.get("status", "", type=str).strip()
    priority_filter = request.args.get("priority", "", type=str).strip()
    technician_filter = request.args.get("technician", "", type=str).strip()

    query = Ticket.query

    # --- Filters ---
    if status_filter and status_filter in STATUS_CHOICES:
        query = query.filter(Ticket.status == status_filter)

    if priority_filter and priority_filter in PRIORITY_CHOICES:
        query = query.filter(Ticket.priority == priority_filter)

    if technician_filter:
        try:
            tech_id = int(technician_filter)
            query = query.filter(Ticket.technician_id == tech_id)
        except ValueError:
            pass  # ignore bad value

    # --- Search (ticket number, customer name, device, fault) ---
    if search:
        like = f"%{search}%"
        query = query.join(Customer, Ticket.customer_id == Customer.id)\
                     .outerjoin(Device, Ticket.device_id == Device.id)\
                     .filter(
                         db.or_(
                             Ticket.ticket_number.ilike(like),
                             Customer.first_name.ilike(like),
                             Customer.last_name.ilike(like),
                             Customer.phone.ilike(like),
                             Device.brand.ilike(like),
                             Device.model.ilike(like),
                             Ticket.fault_description.ilike(like),
                         )
                     )

    query = query.order_by(Ticket.created_at.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return render_template(
        "tickets/index.html",
        tickets=pagination.items,
        pagination=pagination,
        search=search,
        status_filter=status_filter,
        priority_filter=priority_filter,
        technician_filter=technician_filter,
        status_choices=STATUS_CHOICES,
        priority_choices=PRIORITY_CHOICES,
        status_colours=STATUS_COLOURS,
        priority_colours=PRIORITY_COLOURS,
        technicians=_get_technicians(),
    )


@bp.route("/create/<int:customer_id>", methods=["GET", "POST"])
@login_required
def create(customer_id):
    """Create a new ticket for a customer."""
    customer = Customer.query.get_or_404(customer_id)
    devices = customer.devices.order_by(Device.created_at.desc()).all()

    if not devices:
        flash("This customer has no devices. Add a device first.", "warning")
        return redirect(url_for("customers.view", customer_id=customer.id))

    if request.method == "POST":
        cleaned, errors = _validate_ticket_form(request.form, is_edit=False)

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template(
                "tickets/create.html",
                customer=customer,
                devices=devices,
                technicians=_get_technicians(),
                priority_choices=PRIORITY_CHOICES,
                form_data=request.form,
            )

        # Verify device belongs to this customer
        device = Device.query.get(cleaned["device_id"])
        if not device or device.customer_id != customer.id:
            flash("Selected device does not belong to this customer.", "danger")
            return redirect(url_for("tickets.create", customer_id=customer.id))

        ticket = Ticket(
            ticket_number=Ticket.generate_ticket_number(),
            customer_id=customer.id,
            device_id=cleaned["device_id"],
            technician_id=cleaned["technician_id"],
            fault_description=cleaned["fault_description"],
            priority=cleaned["priority"],
            due_date=cleaned["due_date"],
            customer_notes=cleaned["customer_notes"],
            internal_notes=cleaned["internal_notes"],
            disclaimer_accepted=cleaned["disclaimer_accepted"],
            status="Waiting",
        )
        db.session.add(ticket)
        db.session.flush()  # get ticket.id before logging

        # Log creation
        _log_progress(ticket, "Ticket Created", note=f"Fault: {ticket.fault_description[:100]}")

        if ticket.technician_id:
            tech = User.query.get(ticket.technician_id)
            _log_progress(ticket, "Technician Assigned", new_value=tech.full_name)

        db.session.commit()

        flash(f"Ticket {ticket.ticket_number} created successfully.", "success")
        return redirect(url_for("tickets.view", ticket_id=ticket.id))

    return render_template(
        "tickets/create.html",
        customer=customer,
        devices=devices,
        technicians=_get_technicians(),
        priority_choices=PRIORITY_CHOICES,
        form_data={},
    )


@bp.route("/<int:ticket_id>")
@login_required
def view(ticket_id):
    """View ticket detail page with progress log, notes, and parts used."""
    ticket = Ticket.query.get_or_404(ticket_id)
    customer = ticket.customer
    device = ticket.device
    technician = ticket.technician
    progress_logs = ticket.progress_logs.order_by(TicketProgressLog.created_at.desc()).all()
    parts_used = ticket.parts_used.all()

<<<<<<< HEAD
=======
    # Stock items for the "Add Part" dropdown
    stock_items = StockItem.query.filter(StockItem.quantity > 0).order_by(StockItem.name).all()

>>>>>>> 51e3823 (commit new changes)
    return render_template(
        "tickets/view.html",
        ticket=ticket,
        customer=customer,
        device=device,
        technician=technician,
        progress_logs=progress_logs,
        parts_used=parts_used,
<<<<<<< HEAD
=======
        stock_items=stock_items,
>>>>>>> 51e3823 (commit new changes)
        status_choices=STATUS_CHOICES,
        status_colours=STATUS_COLOURS,
        priority_colours=PRIORITY_COLOURS,
        technicians=_get_technicians(),
    )


@bp.route("/<int:ticket_id>/edit", methods=["GET", "POST"])
@login_required
def edit(ticket_id):
    """Edit ticket details (fault, priority, due date, technician, notes)."""
    ticket = Ticket.query.get_or_404(ticket_id)
    customer = ticket.customer

    if request.method == "POST":
        cleaned, errors = _validate_ticket_form(request.form, is_edit=True)

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template(
                "tickets/edit.html",
                ticket=ticket,
                customer=customer,
                technicians=_get_technicians(),
                priority_choices=PRIORITY_CHOICES,
                form_data=request.form,
            )

        changes = []

        # Track changes for audit log
        if ticket.fault_description != cleaned["fault_description"]:
            changes.append(("Fault Updated", ticket.fault_description[:50], cleaned["fault_description"][:50]))
            ticket.fault_description = cleaned["fault_description"]

        if ticket.priority != cleaned["priority"]:
            changes.append(("Priority Changed", ticket.priority, cleaned["priority"]))
            ticket.priority = cleaned["priority"]

        old_due = ticket.due_date.isoformat() if ticket.due_date else "None"
        new_due = cleaned["due_date"].isoformat() if cleaned["due_date"] else "None"
        if old_due != new_due:
            changes.append(("Due Date Changed", old_due, new_due))
            ticket.due_date = cleaned["due_date"]

        if ticket.technician_id != cleaned["technician_id"]:
            old_tech = ticket.technician.full_name if ticket.technician else "Unassigned"
            new_tech_user = User.query.get(cleaned["technician_id"]) if cleaned["technician_id"] else None
            new_tech = new_tech_user.full_name if new_tech_user else "Unassigned"
            changes.append(("Technician Changed", old_tech, new_tech))
            ticket.technician_id = cleaned["technician_id"]

        if ticket.customer_notes != cleaned["customer_notes"]:
            ticket.customer_notes = cleaned["customer_notes"]
            changes.append(("Customer Notes Updated", "", ""))

        if ticket.internal_notes != cleaned["internal_notes"]:
            ticket.internal_notes = cleaned["internal_notes"]
            changes.append(("Internal Notes Updated", "", ""))

        # Log all changes
        for action, old_val, new_val in changes:
            _log_progress(ticket, action, old_value=old_val, new_value=new_val)

        if not changes:
            flash("No changes were made.", "info")
            return redirect(url_for("tickets.view", ticket_id=ticket.id))

        db.session.commit()
        flash(f"Ticket {ticket.ticket_number} updated.", "success")
        return redirect(url_for("tickets.view", ticket_id=ticket.id))

    form_data = {
        "fault_description": ticket.fault_description,
        "priority": ticket.priority,
        "due_date": ticket.due_date.isoformat() if ticket.due_date else "",
        "technician_id": str(ticket.technician_id) if ticket.technician_id else "",
        "customer_notes": ticket.customer_notes,
        "internal_notes": ticket.internal_notes,
    }
    return render_template(
        "tickets/edit.html",
        ticket=ticket,
        customer=customer,
        technicians=_get_technicians(),
        priority_choices=PRIORITY_CHOICES,
        form_data=form_data,
    )


@bp.route("/<int:ticket_id>/status", methods=["POST"])
@login_required
def update_status(ticket_id):
    """Update ticket status with a required note."""
    ticket = Ticket.query.get_or_404(ticket_id)
    new_status = request.form.get("status", "").strip()
    note = request.form.get("note", "").strip()

    if new_status not in STATUS_CHOICES:
        flash("Invalid status selected.", "danger")
        return redirect(url_for("tickets.view", ticket_id=ticket.id))

    if new_status == ticket.status:
        flash("Status is already set to that value.", "info")
        return redirect(url_for("tickets.view", ticket_id=ticket.id))

    if not note:
        flash("Please add a note when changing status.", "danger")
        return redirect(url_for("tickets.view", ticket_id=ticket.id))

    old_status = ticket.status
    ticket.status = new_status

    _log_progress(
        ticket,
        action="Status Changed",
        old_value=old_status,
        new_value=new_status,
        note=note,
    )

    db.session.commit()
    flash(f"Status changed from {old_status} to {new_status}.", "success")
    return redirect(url_for("tickets.view", ticket_id=ticket.id))


@bp.route("/<int:ticket_id>/note", methods=["POST"])
@login_required
def add_note(ticket_id):
    """Add an internal or customer-facing note to the ticket."""
    ticket = Ticket.query.get_or_404(ticket_id)
    note_text = request.form.get("note", "").strip()
    note_type = request.form.get("note_type", "internal").strip()

    if not note_text:
        flash("Note cannot be empty.", "danger")
        return redirect(url_for("tickets.view", ticket_id=ticket.id))

    if note_type not in ("internal", "customer"):
        note_type = "internal"

    action_label = "Internal Note Added" if note_type == "internal" else "Customer Note Added"

    _log_progress(
        ticket,
        action=action_label,
        note=note_text,
    )

    db.session.commit()
    flash(f"{action_label.replace(' Added', '')} added.", "success")
    return redirect(url_for("tickets.view", ticket_id=ticket.id))


@bp.route("/<int:ticket_id>/assign", methods=["POST"])
@login_required
def assign(ticket_id):
    """Reassign ticket to a different technician."""
    ticket = Ticket.query.get_or_404(ticket_id)
    new_tech_id = request.form.get("technician_id", "").strip()

    old_tech = ticket.technician.full_name if ticket.technician else "Unassigned"

    if not new_tech_id:
        ticket.technician_id = None
        new_tech = "Unassigned"
    else:
        try:
            new_tech_id = int(new_tech_id)
            tech = User.query.get(new_tech_id)
            if not tech:
                flash("Selected technician does not exist.", "danger")
                return redirect(url_for("tickets.view", ticket_id=ticket.id))
            ticket.technician_id = new_tech_id
            new_tech = tech.full_name
        except ValueError:
            flash("Invalid technician selection.", "danger")
            return redirect(url_for("tickets.view", ticket_id=ticket.id))

    if old_tech == new_tech:
        flash("Technician is already assigned.", "info")
        return redirect(url_for("tickets.view", ticket_id=ticket.id))

    _log_progress(
        ticket,
        action="Technician Reassigned",
        old_value=old_tech,
        new_value=new_tech,
    )

    db.session.commit()
    flash(f"Ticket reassigned to {new_tech}.", "success")
    return redirect(url_for("tickets.view", ticket_id=ticket.id))
<<<<<<< HEAD
=======


# ---------------------------------------------------------------------------
# Phase 4: Parts Management on Tickets
# ---------------------------------------------------------------------------

@bp.route("/<int:ticket_id>/add-part", methods=["POST"])
@login_required
def add_part(ticket_id):
    """Add a stock part to this ticket. Auto-deducts from stock quantity."""
    ticket = Ticket.query.get_or_404(ticket_id)

    stock_item_id_str = request.form.get("stock_item_id", "").strip()
    quantity_str = request.form.get("part_quantity", "1").strip()
    price_str = request.form.get("part_price", "").strip()

    # Validate stock item
    if not stock_item_id_str:
        flash("Please select a part.", "danger")
        return redirect(url_for("tickets.view", ticket_id=ticket.id))

    try:
        stock_item_id = int(stock_item_id_str)
    except ValueError:
        flash("Invalid part selection.", "danger")
        return redirect(url_for("tickets.view", ticket_id=ticket.id))

    stock_item = StockItem.query.get(stock_item_id)
    if not stock_item:
        flash("Selected part does not exist.", "danger")
        return redirect(url_for("tickets.view", ticket_id=ticket.id))

    # Validate quantity
    try:
        quantity = int(quantity_str)
        if quantity < 1:
            flash("Quantity must be at least 1.", "danger")
            return redirect(url_for("tickets.view", ticket_id=ticket.id))
    except ValueError:
        flash("Quantity must be a whole number.", "danger")
        return redirect(url_for("tickets.view", ticket_id=ticket.id))

    # Check stock availability
    if stock_item.quantity < quantity:
        flash(
            f"Insufficient stock for '{stock_item.name}'. "
            f"Available: {stock_item.quantity}, Requested: {quantity}.",
            "danger",
        )
        return redirect(url_for("tickets.view", ticket_id=ticket.id))

    # Validate price (default to sell price if empty)
    if not price_str:
        price_charged = stock_item.sell_price
    else:
        try:
            price_charged = round(float(price_str), 2)
            if price_charged < 0:
                flash("Price cannot be negative.", "danger")
                return redirect(url_for("tickets.view", ticket_id=ticket.id))
        except ValueError:
            flash("Price must be a valid number.", "danger")
            return redirect(url_for("tickets.view", ticket_id=ticket.id))

    # Create the TicketPartUsed record
    part_used = TicketPartUsed(
        ticket_id=ticket.id,
        stock_item_id=stock_item.id,
        quantity=quantity,
        price_charged=price_charged,
    )
    db.session.add(part_used)

    # Deduct from stock
    stock_item.quantity -= quantity

    # Log to audit trail
    _log_progress(
        ticket,
        action="Part Added",
        new_value=f"{stock_item.name} x{quantity} @ €{price_charged:.2f}",
        note=f"Stock deducted: {stock_item.quantity + quantity} → {stock_item.quantity}",
    )

    db.session.commit()
    flash(
        f"Added {stock_item.name} x{quantity} @ €{price_charged:.2f} to ticket.",
        "success",
    )
    return redirect(url_for("tickets.view", ticket_id=ticket.id))


@bp.route("/<int:ticket_id>/remove-part/<int:part_id>", methods=["POST"])
@login_required
def remove_part(ticket_id, part_id):
    """Remove a part from ticket and restore stock quantity."""
    ticket = Ticket.query.get_or_404(ticket_id)
    part_used = TicketPartUsed.query.get_or_404(part_id)

    # Security: ensure this part belongs to this ticket
    if part_used.ticket_id != ticket.id:
        flash("Invalid operation.", "danger")
        return redirect(url_for("tickets.view", ticket_id=ticket.id))

    stock_item = part_used.stock_item
    restored_qty = part_used.quantity
    part_name = stock_item.name if stock_item else "Unknown Part"

    # Restore stock quantity
    if stock_item:
        stock_item.quantity += restored_qty

    # Log to audit trail
    _log_progress(
        ticket,
        action="Part Removed",
        old_value=f"{part_name} x{restored_qty}",
        note=f"Stock restored: {stock_item.quantity - restored_qty} → {stock_item.quantity}" if stock_item else "",
    )

    db.session.delete(part_used)
    db.session.commit()

    flash(f"Removed {part_name} x{restored_qty} from ticket. Stock restored.", "success")
    return redirect(url_for("tickets.view", ticket_id=ticket.id))
>>>>>>> 51e3823 (commit new changes)
