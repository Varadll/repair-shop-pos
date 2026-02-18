import re
from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required
from app.blueprints.customers import bp
from app.extensions import db
from app.models import Customer, Device, Ticket


# ---------------------------------------------------------------------------
# Validation helpers (reusable across add & edit, and future API endpoints)
# ---------------------------------------------------------------------------

def _validate_name(value, field_label):
    """Name must contain only letters, spaces, hyphens, apostrophes."""
    if not re.match(r"^[A-Za-zÀ-ÖØ-öø-ÿ' -]+$", value):
        return f"{field_label} must contain only letters (e.g. O'Brien, Mary-Jane)."
    return None


def _normalise_phone(raw_phone):
    """Strip spaces, dashes, dots, brackets — keep only digits and leading +."""
    cleaned = raw_phone.strip()
    if cleaned.startswith("+"):
        return "+" + re.sub(r"[^\d]", "", cleaned[1:])
    return re.sub(r"[^\d]", "", cleaned)


def _validate_phone(normalised_phone):
    """Irish numbers: 10 digits (08X...) or 12-13 digits with +353 prefix."""
    digits_only = normalised_phone.lstrip("+")
    if normalised_phone.startswith("+353"):
        # +353 8X XXX XXXX → 12 digits total after +
        if len(digits_only) < 11 or len(digits_only) > 13:
            return "International number must be a valid +353 format (e.g. +353 89 436 1114)."
    else:
        if len(digits_only) < 10:
            return "Phone number must be at least 10 digits (e.g. 089 436 1114)."
        if len(digits_only) > 15:
            return "Phone number is too long."
    return None


def _validate_customer_form(form, exclude_customer_id=None):
    """Validate customer form data. Returns (cleaned_data, errors)."""
    first_name = form.get("first_name", "").strip()
    last_name = form.get("last_name", "").strip()
    raw_phone = form.get("phone", "").strip()
    email = form.get("email", "").strip()
    address = form.get("address", "").strip()
    notes = form.get("notes", "").strip()

    errors = []

    # Required fields
    if not first_name:
        errors.append("First name is required.")
    elif err := _validate_name(first_name, "First name"):
        errors.append(err)

    if not last_name:
        errors.append("Last name is required.")
    elif err := _validate_name(last_name, "Last name"):
        errors.append(err)

    if not raw_phone:
        errors.append("Phone number is required.")
    else:
        phone = _normalise_phone(raw_phone)
        if err := _validate_phone(phone):
            errors.append(err)
        else:
            # Check duplicate phone
            dup_query = Customer.query.filter(Customer.phone == phone)
            if exclude_customer_id:
                dup_query = dup_query.filter(Customer.id != exclude_customer_id)
            if dup_query.first():
                errors.append("A customer with this phone number already exists.")

    cleaned = {
        "first_name": first_name,
        "last_name": last_name,
        "phone": _normalise_phone(raw_phone) if raw_phone else "",
        "email": email,
        "address": address,
        "notes": notes,
    }
    return cleaned, errors


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@bp.route("/")
@login_required
def index():
    """List customers with search and pagination."""
    page = request.args.get("page", 1, type=int)
    per_page = 20
    search = request.args.get("q", "", type=str).strip()

    query = Customer.query

    if search:
        # Normalise search term for phone matching
        search_digits = re.sub(r"[^\d]", "", search)
        like_term = f"%{search}%"

        filters = [
            Customer.first_name.ilike(like_term),
            Customer.last_name.ilike(like_term),
            Customer.phone.ilike(like_term),
            Customer.email.ilike(like_term),
        ]
        # If the search looks like a phone number, also search normalised digits
        if search_digits and len(search_digits) >= 3:
            filters.append(Customer.phone.ilike(f"%{search_digits}%"))

        query = query.filter(db.or_(*filters))

    query = query.order_by(Customer.created_at.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return render_template(
        "customers/index.html",
        customers=pagination.items,
        pagination=pagination,
        search=search,
    )


@bp.route("/add", methods=["GET", "POST"])
@login_required
def add():
    """Add a new customer."""
    if request.method == "POST":
        cleaned, errors = _validate_customer_form(request.form)

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("customers/add.html", form_data=request.form)

        customer = Customer(**cleaned)
        db.session.add(customer)
        db.session.commit()

        flash(f"Customer {customer.full_name} added successfully.", "success")
        return redirect(url_for("customers.view", customer_id=customer.id))

    return render_template("customers/add.html", form_data={})


@bp.route("/<int:customer_id>")
@login_required
def view(customer_id):
    """View customer profile with devices and tickets."""
    customer = Customer.query.get_or_404(customer_id)
    devices = customer.devices.order_by(Device.created_at.desc()).all()
    tickets = customer.tickets.order_by(Ticket.created_at.desc()).all()

    return render_template(
        "customers/view.html",
        customer=customer,
        devices=devices,
        tickets=tickets,
    )


@bp.route("/<int:customer_id>/edit", methods=["GET", "POST"])
@login_required
def edit(customer_id):
    """Edit an existing customer."""
    customer = Customer.query.get_or_404(customer_id)

    if request.method == "POST":
        cleaned, errors = _validate_customer_form(
            request.form, exclude_customer_id=customer.id
        )

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template(
                "customers/edit.html",
                customer=customer,
                form_data=request.form,
            )

        customer.first_name = cleaned["first_name"]
        customer.last_name = cleaned["last_name"]
        customer.phone = cleaned["phone"]
        customer.email = cleaned["email"]
        customer.address = cleaned["address"]
        customer.notes = cleaned["notes"]
        db.session.commit()

        flash(f"Customer {customer.full_name} updated successfully.", "success")
        return redirect(url_for("customers.view", customer_id=customer.id))

    form_data = {
        "first_name": customer.first_name,
        "last_name": customer.last_name,
        "phone": customer.phone,
        "email": customer.email,
        "address": customer.address,
        "notes": customer.notes,
    }
    return render_template(
        "customers/edit.html",
        customer=customer,
        form_data=form_data,
    )


@bp.route("/<int:customer_id>/delete", methods=["POST"])
@login_required
def delete(customer_id):
    """Delete a customer (only if they have no tickets)."""
    customer = Customer.query.get_or_404(customer_id)

    if customer.tickets.count() > 0:
        flash(
            f"Cannot delete {customer.full_name} — they have {customer.tickets.count()} ticket(s) linked. "
            "Delete or reassign tickets first.",
            "danger",
        )
        return redirect(url_for("customers.view", customer_id=customer.id))

    name = customer.full_name
    db.session.delete(customer)
    db.session.commit()

    flash(f"Customer {name} has been deleted.", "success")
    return redirect(url_for("customers.index"))
