import re
from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required
from app.blueprints.devices import bp
from app.extensions import db
from app.models import Customer, Device, Ticket


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEVICE_TYPES = ["Phone", "Tablet", "Laptop", "Games Console"]


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def _validate_device_form(form):
    """Validate device form data. Returns (cleaned_data, errors)."""
    device_type = form.get("device_type", "").strip()
    brand = form.get("brand", "").strip()
    model = form.get("model", "").strip()
    colour = form.get("colour", "").strip()
    imei_serial = form.get("imei_serial", "").strip()
    passcode = form.get("passcode", "").strip()
    condition_notes = form.get("condition_notes", "").strip()

    errors = []

    if not device_type or device_type not in DEVICE_TYPES:
        errors.append("Please select a valid device type.")

    if not brand:
        errors.append("Brand is required.")
    elif len(brand) < 2:
        errors.append("Brand must be at least 2 characters.")

    if not model:
        errors.append("Model is required.")
    elif len(model) < 1:
        errors.append("Model must be at least 1 character.")

    if imei_serial and len(imei_serial) < 8:
        errors.append("IMEI / Serial must be at least 8 characters if provided.")

    cleaned = {
        "device_type": device_type,
        "brand": brand,
        "model": model,
        "colour": colour,
        "imei_serial": imei_serial,
        "passcode": passcode,
        "condition_notes": condition_notes,
    }
    return cleaned, errors


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@bp.route("/add/<int:customer_id>", methods=["GET", "POST"])
@login_required
def add(customer_id):
    """Add a new device to a customer."""
    customer = Customer.query.get_or_404(customer_id)

    if request.method == "POST":
        cleaned, errors = _validate_device_form(request.form)

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template(
                "devices/add.html",
                customer=customer,
                form_data=request.form,
                device_types=DEVICE_TYPES,
            )

        device = Device(customer_id=customer.id, **cleaned)
        db.session.add(device)
        db.session.commit()

        flash(f"{device.display_name} added to {customer.full_name}.", "success")
        return redirect(url_for("devices.view", device_id=device.id))

    return render_template(
        "devices/add.html",
        customer=customer,
        form_data={},
        device_types=DEVICE_TYPES,
    )


@bp.route("/<int:device_id>")
@login_required
def view(device_id):
    """View device details and repair history."""
    device = Device.query.get_or_404(device_id)
    customer = device.customer
    tickets = device.tickets.order_by(Ticket.created_at.desc()).all()

    return render_template(
        "devices/view.html",
        device=device,
        customer=customer,
        tickets=tickets,
    )


@bp.route("/<int:device_id>/edit", methods=["GET", "POST"])
@login_required
def edit(device_id):
    """Edit device details."""
    device = Device.query.get_or_404(device_id)
    customer = device.customer

    if request.method == "POST":
        cleaned, errors = _validate_device_form(request.form)

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template(
                "devices/edit.html",
                device=device,
                customer=customer,
                form_data=request.form,
                device_types=DEVICE_TYPES,
            )

        device.device_type = cleaned["device_type"]
        device.brand = cleaned["brand"]
        device.model = cleaned["model"]
        device.colour = cleaned["colour"]
        device.imei_serial = cleaned["imei_serial"]
        device.passcode = cleaned["passcode"]
        device.condition_notes = cleaned["condition_notes"]
        db.session.commit()

        flash(f"{device.display_name} updated successfully.", "success")
        return redirect(url_for("devices.view", device_id=device.id))

    form_data = {
        "device_type": device.device_type,
        "brand": device.brand,
        "model": device.model,
        "colour": device.colour,
        "imei_serial": device.imei_serial,
        "passcode": device.passcode,
        "condition_notes": device.condition_notes,
    }
    return render_template(
        "devices/edit.html",
        device=device,
        customer=customer,
        form_data=form_data,
        device_types=DEVICE_TYPES,
    )


@bp.route("/<int:device_id>/delete", methods=["POST"])
@login_required
def delete(device_id):
    """Delete a device (only if no tickets linked)."""
    device = Device.query.get_or_404(device_id)
    customer_id = device.customer_id

    if device.tickets.count() > 0:
        flash(
            f"Cannot delete {device.display_name} — it has {device.tickets.count()} ticket(s) linked. "
            "Delete or close tickets first.",
            "danger",
        )
        return redirect(url_for("devices.view", device_id=device.id))

    name = device.display_name
    db.session.delete(device)
    db.session.commit()

    flash(f"{name} has been deleted.", "success")
    return redirect(url_for("customers.view", customer_id=customer_id))
