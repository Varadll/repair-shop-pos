from app.models import Invoice


def make_invoice(labour, parts, discount=0.0, deposit=0.0):
    return Invoice(
        labour_cost=labour,
        parts_cost=parts,
        discount=discount,
        deposit_paid=deposit,
    )


def test_recalculate_with_partial_deposit_leaves_balance_due():
    invoice = make_invoice(labour=50.0, parts=30.0, discount=10.0, deposit=20.0)

    invoice.recalculate()

    assert invoice.subtotal == 80.0
    assert invoice.total == 70.0
    assert invoice.balance_due == 50.0
    assert invoice.is_paid is False


def test_recalculate_marks_invoice_paid_when_deposit_covers_total():
    invoice = make_invoice(labour=50.0, parts=30.0, deposit=80.0)

    invoice.recalculate()

    assert invoice.balance_due == 0.0
    assert invoice.is_paid is True
