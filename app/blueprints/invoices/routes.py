<<<<<<< HEAD
from flask import render_template
from flask_login import login_required
from app.blueprints.invoices import bp


@bp.route("/")
@login_required
def index():
    return render_template("invoices/index.html")
=======
from flask import (
    render_template, request, redirect, url_for, flash,
    current_app, make_response,
)
from flask_login import login_required, current_user
from app.blueprints.invoices import bp
from app.extensions import db
from app.models import (
    Invoice, Ticket, Customer, Device, TicketPartUsed,
    TicketProgressLog, User,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PAYMENT_METHODS = ["Cash", "Card", "Bank Transfer", "Other"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _calc_parts_cost(ticket):
    """Sum up all parts used on a ticket."""
    parts = TicketPartUsed.query.filter_by(ticket_id=ticket.id).all()
    return round(sum(p.line_total for p in parts), 2)


def _validate_invoice_form(form):
    """Validate invoice create/edit form. Returns (cleaned_data, errors)."""
    errors = []

    # --- Labour cost ---
    try:
        labour_cost = round(float(form.get("labour_cost", "0").strip() or "0"), 2)
        if labour_cost < 0:
            errors.append("Labour cost cannot be negative.")
    except ValueError:
        errors.append("Labour cost must be a valid number.")
        labour_cost = 0.0

    # --- Discount ---
    try:
        discount = round(float(form.get("discount", "0").strip() or "0"), 2)
        if discount < 0:
            errors.append("Discount cannot be negative.")
    except ValueError:
        errors.append("Discount must be a valid number.")
        discount = 0.0

    # --- Deposit paid ---
    try:
        deposit_paid = round(float(form.get("deposit_paid", "0").strip() or "0"), 2)
        if deposit_paid < 0:
            errors.append("Deposit cannot be negative.")
    except ValueError:
        errors.append("Deposit must be a valid number.")
        deposit_paid = 0.0

    # --- Payment method ---
    payment_method = form.get("payment_method", "").strip()

    cleaned = {
        "labour_cost": labour_cost,
        "discount": discount,
        "deposit_paid": deposit_paid,
        "payment_method": payment_method,
    }
    return cleaned, errors


def _get_invoice_context(invoice):
    """Build the full context dict for invoice view/PDF templates."""
    ticket = invoice.ticket
    customer = ticket.customer
    device = ticket.device
    parts = TicketPartUsed.query.filter_by(ticket_id=ticket.id).all()

    return {
        "invoice": invoice,
        "ticket": ticket,
        "customer": customer,
        "device": device,
        "parts": parts,
        "payment_methods": PAYMENT_METHODS,
    }


# ---------------------------------------------------------------------------
# 1. LIST — all invoices with search, filter, pagination
# ---------------------------------------------------------------------------

@bp.route("/")
@login_required
def index():
    """List all invoices with search and paid/unpaid filter."""
    page = request.args.get("page", 1, type=int)
    per_page = 20
    search = request.args.get("q", "", type=str).strip()
    status_filter = request.args.get("status", "", type=str).strip()

    query = Invoice.query.join(Ticket).join(Customer)

    # --- Search (invoice #, ticket #, customer name, customer phone) ---
    if search:
        like = f"%{search}%"
        query = query.filter(
            db.or_(
                Invoice.invoice_number.ilike(like),
                Ticket.ticket_number.ilike(like),
                Customer.first_name.ilike(like),
                Customer.last_name.ilike(like),
                Customer.phone.ilike(like),
            )
        )

    # --- Paid / Unpaid filter ---
    if status_filter == "paid":
        query = query.filter(Invoice.is_paid == True)  # noqa: E712
    elif status_filter == "unpaid":
        query = query.filter(Invoice.is_paid == False)  # noqa: E712

    query = query.order_by(Invoice.created_at.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    # Counts for filter badges
    total_count = Invoice.query.count()
    unpaid_count = Invoice.query.filter(Invoice.is_paid == False).count()  # noqa: E712

    return render_template(
        "invoices/index.html",
        invoices=pagination.items,
        pagination=pagination,
        search=search,
        status_filter=status_filter,
        total_count=total_count,
        unpaid_count=unpaid_count,
    )


# ---------------------------------------------------------------------------
# 2. CREATE — generate invoice from a ticket
# ---------------------------------------------------------------------------

@bp.route("/create/<int:ticket_id>", methods=["GET", "POST"])
@login_required
def create(ticket_id):
    """Create an invoice for a ticket. Auto-pulls parts cost."""
    ticket = Ticket.query.get_or_404(ticket_id)

    # Block if invoice already exists for this ticket
    if ticket.invoice:
        flash(f"Invoice {ticket.invoice.invoice_number} already exists for this ticket.", "warning")
        return redirect(url_for("invoices.view", invoice_id=ticket.invoice.id))

    parts_cost = _calc_parts_cost(ticket)
    customer = ticket.customer
    device = ticket.device
    parts = TicketPartUsed.query.filter_by(ticket_id=ticket.id).all()

    if request.method == "POST":
        cleaned, errors = _validate_invoice_form(request.form)

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template(
                "invoices/create.html",
                ticket=ticket,
                customer=customer,
                device=device,
                parts=parts,
                parts_cost=parts_cost,
                payment_methods=PAYMENT_METHODS,
                form_data=request.form,
            )

        # Create the invoice
        invoice = Invoice(
            invoice_number=Invoice.generate_invoice_number(),
            ticket_id=ticket.id,
            labour_cost=cleaned["labour_cost"],
            parts_cost=parts_cost,
            discount=cleaned["discount"],
            deposit_paid=cleaned["deposit_paid"],
            payment_method=cleaned["payment_method"],
        )
        invoice.recalculate()
        db.session.add(invoice)

        # Log to ticket progress trail
        log = TicketProgressLog(
            ticket_id=ticket.id,
            user_id=current_user.id,
            action="Invoice Created",
            new_value=f"{invoice.invoice_number} \u2014 Total: \u20ac{invoice.total:.2f}",
        )
        db.session.add(log)
        db.session.commit()

        flash(f"Invoice {invoice.invoice_number} created successfully.", "success")
        return redirect(url_for("invoices.view", invoice_id=invoice.id))

    return render_template(
        "invoices/create.html",
        ticket=ticket,
        customer=customer,
        device=device,
        parts=parts,
        parts_cost=parts_cost,
        payment_methods=PAYMENT_METHODS,
        form_data={},
    )


# ---------------------------------------------------------------------------
# 3. VIEW — invoice detail page
# ---------------------------------------------------------------------------

@bp.route("/<int:invoice_id>")
@login_required
def view(invoice_id):
    """View full invoice detail."""
    invoice = Invoice.query.get_or_404(invoice_id)
    ctx = _get_invoice_context(invoice)
    return render_template("invoices/view.html", **ctx)


# ---------------------------------------------------------------------------
# 4. EDIT — update labour, discount, deposit, payment method
# ---------------------------------------------------------------------------

@bp.route("/<int:invoice_id>/edit", methods=["GET", "POST"])
@login_required
def edit(invoice_id):
    """Edit invoice details."""
    invoice = Invoice.query.get_or_404(invoice_id)
    ticket = invoice.ticket
    customer = ticket.customer
    device = ticket.device
    parts = TicketPartUsed.query.filter_by(ticket_id=ticket.id).all()
    parts_cost = _calc_parts_cost(ticket)

    if request.method == "POST":
        cleaned, errors = _validate_invoice_form(request.form)

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template(
                "invoices/edit.html",
                invoice=invoice,
                ticket=ticket,
                customer=customer,
                device=device,
                parts=parts,
                parts_cost=parts_cost,
                payment_methods=PAYMENT_METHODS,
                form_data=request.form,
            )

        # Track changes for audit log
        changes = []
        if invoice.labour_cost != cleaned["labour_cost"]:
            changes.append(f"Labour: \u20ac{invoice.labour_cost:.2f} \u2192 \u20ac{cleaned['labour_cost']:.2f}")
        if invoice.discount != cleaned["discount"]:
            changes.append(f"Discount: \u20ac{invoice.discount:.2f} \u2192 \u20ac{cleaned['discount']:.2f}")
        if invoice.deposit_paid != cleaned["deposit_paid"]:
            changes.append(f"Deposit: \u20ac{invoice.deposit_paid:.2f} \u2192 \u20ac{cleaned['deposit_paid']:.2f}")
        if invoice.payment_method != cleaned["payment_method"]:
            changes.append(f"Payment: {invoice.payment_method or '\u2014'} \u2192 {cleaned['payment_method'] or '\u2014'}")

        # Apply changes
        invoice.labour_cost = cleaned["labour_cost"]
        invoice.parts_cost = parts_cost  # Recalculate in case parts changed
        invoice.discount = cleaned["discount"]
        invoice.deposit_paid = cleaned["deposit_paid"]
        invoice.payment_method = cleaned["payment_method"]
        invoice.recalculate()

        # Log to ticket progress trail if anything changed
        if changes:
            log = TicketProgressLog(
                ticket_id=ticket.id,
                user_id=current_user.id,
                action="Invoice Updated",
                new_value=invoice.invoice_number,
                note="; ".join(changes),
            )
            db.session.add(log)

        db.session.commit()
        flash(f"Invoice {invoice.invoice_number} updated.", "success")
        return redirect(url_for("invoices.view", invoice_id=invoice.id))

    form_data = {
        "labour_cost": str(invoice.labour_cost),
        "discount": str(invoice.discount),
        "deposit_paid": str(invoice.deposit_paid),
        "payment_method": invoice.payment_method,
    }
    return render_template(
        "invoices/edit.html",
        invoice=invoice,
        ticket=ticket,
        customer=customer,
        device=device,
        parts=parts,
        parts_cost=parts_cost,
        payment_methods=PAYMENT_METHODS,
        form_data=form_data,
    )


# ---------------------------------------------------------------------------
# 5. MARK PAID — quick action to settle the full balance
# ---------------------------------------------------------------------------

@bp.route("/<int:invoice_id>/mark-paid", methods=["POST"])
@login_required
def mark_paid(invoice_id):
    """Mark invoice as fully paid."""
    invoice = Invoice.query.get_or_404(invoice_id)

    if invoice.is_paid:
        flash("Invoice is already marked as paid.", "info")
        return redirect(url_for("invoices.view", invoice_id=invoice.id))

    payment_method = request.form.get("payment_method", "").strip()
    if not payment_method:
        flash("Please select a payment method.", "danger")
        return redirect(url_for("invoices.view", invoice_id=invoice.id))

    old_deposit = invoice.deposit_paid
    invoice.deposit_paid = invoice.total
    invoice.payment_method = payment_method
    invoice.recalculate()

    # Log to ticket progress trail
    log = TicketProgressLog(
        ticket_id=invoice.ticket_id,
        user_id=current_user.id,
        action="Invoice Paid",
        old_value=f"Balance was: \u20ac{invoice.total - old_deposit:.2f}",
        new_value=f"{invoice.invoice_number} \u2014 Paid via {payment_method}",
    )
    db.session.add(log)
    db.session.commit()

    flash(f"Invoice {invoice.invoice_number} marked as paid ({payment_method}).", "success")
    return redirect(url_for("invoices.view", invoice_id=invoice.id))


# ---------------------------------------------------------------------------
# 6. ADD PAYMENT — record a partial or full payment
# ---------------------------------------------------------------------------

@bp.route("/<int:invoice_id>/add-payment", methods=["POST"])
@login_required
def add_payment(invoice_id):
    """Record a payment against the invoice balance."""
    invoice = Invoice.query.get_or_404(invoice_id)

    if invoice.is_paid:
        flash("Invoice is already fully paid.", "info")
        return redirect(url_for("invoices.view", invoice_id=invoice.id))

    try:
        amount = round(float(request.form.get("amount", "0").strip() or "0"), 2)
    except ValueError:
        flash("Payment amount must be a valid number.", "danger")
        return redirect(url_for("invoices.view", invoice_id=invoice.id))

    if amount <= 0:
        flash("Payment amount must be greater than zero.", "danger")
        return redirect(url_for("invoices.view", invoice_id=invoice.id))

    payment_method = request.form.get("payment_method", "").strip()
    if not payment_method:
        flash("Please select a payment method.", "danger")
        return redirect(url_for("invoices.view", invoice_id=invoice.id))

    # Cap payment at balance due
    max_payment = invoice.balance_due
    if amount > max_payment:
        amount = max_payment

    old_deposit = invoice.deposit_paid
    invoice.deposit_paid = round(invoice.deposit_paid + amount, 2)
    if payment_method:
        invoice.payment_method = payment_method
    invoice.recalculate()

    # Log to ticket progress trail
    log = TicketProgressLog(
        ticket_id=invoice.ticket_id,
        user_id=current_user.id,
        action="Payment Received",
        old_value=f"Previous paid: \u20ac{old_deposit:.2f}",
        new_value=f"\u20ac{amount:.2f} via {payment_method} \u2014 Balance: \u20ac{invoice.balance_due:.2f}",
    )
    db.session.add(log)
    db.session.commit()

    if invoice.is_paid:
        flash(f"Payment of \u20ac{amount:.2f} received. Invoice is now fully paid.", "success")
    else:
        flash(f"Payment of \u20ac{amount:.2f} received. Remaining balance: \u20ac{invoice.balance_due:.2f}.", "success")

    return redirect(url_for("invoices.view", invoice_id=invoice.id))


# ---------------------------------------------------------------------------
# 7. PDF — generate and download invoice PDF via WeasyPrint
# ---------------------------------------------------------------------------

@bp.route("/<int:invoice_id>/pdf")
@login_required
def download_pdf(invoice_id):
    """Generate PDF invoice using WeasyPrint (HTML to PDF)."""
    invoice = Invoice.query.get_or_404(invoice_id)
    ctx = _get_invoice_context(invoice)

    # Add shop details from config
    ctx["shop_name"] = current_app.config.get("SHOP_NAME", "Repair Shop")
    ctx["shop_address"] = current_app.config.get("SHOP_ADDRESS", "")
    ctx["shop_phone"] = current_app.config.get("SHOP_PHONE", "")
    ctx["shop_email"] = current_app.config.get("SHOP_EMAIL", "")
    ctx["shop_vat"] = current_app.config.get("SHOP_VAT", "")

    # Render the PDF-specific HTML template
    html_string = render_template("invoices/pdf.html", **ctx)

    # Generate PDF with WeasyPrint
    try:
        from weasyprint import HTML
        pdf_bytes = HTML(string=html_string).write_pdf()
    except ImportError:
        flash("WeasyPrint is not installed. Run: pip install weasyprint", "danger")
        return redirect(url_for("invoices.view", invoice_id=invoice.id))
    except Exception as e:
        flash(f"PDF generation failed: {str(e)}", "danger")
        return redirect(url_for("invoices.view", invoice_id=invoice.id))

    # Return PDF as downloadable file
    response = make_response(pdf_bytes)
    response.headers["Content-Type"] = "application/pdf"
    filename = f"{invoice.invoice_number}.pdf"
    response.headers["Content-Disposition"] = f"inline; filename={filename}"
    return response


# ---------------------------------------------------------------------------
# 8. DELETE — admin only, blocked if paid
# ---------------------------------------------------------------------------

@bp.route("/<int:invoice_id>/delete", methods=["POST"])
@login_required
def delete(invoice_id):
    """Delete an invoice (admin only, blocked if paid)."""
    invoice = Invoice.query.get_or_404(invoice_id)

    # Admin only
    if not current_user.is_admin:
        flash("Only administrators can delete invoices.", "danger")
        return redirect(url_for("invoices.view", invoice_id=invoice.id))

    # Block if paid
    if invoice.is_paid:
        flash("Cannot delete a paid invoice.", "danger")
        return redirect(url_for("invoices.view", invoice_id=invoice.id))

    ticket_id = invoice.ticket_id
    inv_number = invoice.invoice_number

    # Log deletion to ticket progress trail
    log = TicketProgressLog(
        ticket_id=ticket_id,
        user_id=current_user.id,
        action="Invoice Deleted",
        old_value=f"{inv_number} \u2014 Total: \u20ac{invoice.total:.2f}",
    )
    db.session.add(log)

    db.session.delete(invoice)
    db.session.commit()

    flash(f"Invoice {inv_number} deleted.", "success")
    return redirect(url_for("invoices.index"))


# ---------------------------------------------------------------------------
# API — JSON endpoint for future AJAX / AI integrations
# ---------------------------------------------------------------------------

@bp.route("/api/summary/<int:invoice_id>")
@login_required
def api_summary(invoice_id):
    """Return invoice summary as JSON for AJAX/AI integrations."""
    from flask import jsonify

    invoice = Invoice.query.get_or_404(invoice_id)
    ticket = invoice.ticket
    customer = ticket.customer
    parts = TicketPartUsed.query.filter_by(ticket_id=ticket.id).all()

    result = {
        "invoice_number": invoice.invoice_number,
        "ticket_number": ticket.ticket_number,
        "customer_name": customer.full_name,
        "customer_phone": customer.phone,
        "labour_cost": invoice.labour_cost,
        "parts_cost": invoice.parts_cost,
        "subtotal": invoice.subtotal,
        "discount": invoice.discount,
        "total": invoice.total,
        "deposit_paid": invoice.deposit_paid,
        "balance_due": invoice.balance_due,
        "is_paid": invoice.is_paid,
        "payment_method": invoice.payment_method,
        "created_at": invoice.created_at.isoformat() if invoice.created_at else None,
        "parts": [
            {
                "name": p.stock_item.name if p.stock_item else "Unknown",
                "quantity": p.quantity,
                "price_charged": p.price_charged,
                "line_total": p.line_total,
            }
            for p in parts
        ],
    }
    return jsonify(result)
>>>>>>> 51e3823 (commit new changes)
