from app.extensions import db
from app.models import POSSale, StockItem


def submit_sale(client, item, qty, price):
    # The POS page builds these hidden fields in JavaScript; the test posts them directly
    return client.post("/pos/create", data={
        "item_id[]": [str(item.id)],
        "item_qty[]": [str(qty)],
        "item_price[]": [str(price)],
        "payment_method": "Card",
    })


def test_sale_deducts_stock_and_records_total(logged_in_client, screen_protector):
    response = submit_sale(logged_in_client, screen_protector, qty=3, price=15.0)

    assert response.status_code == 302  # redirected to the sale view page

    sale = POSSale.query.one()
    assert sale.total == 45.0
    assert sale.payment_method == "Card"
    assert sale.items.count() == 1

    assert db.session.get(StockItem, screen_protector.id).quantity == 7


def test_sale_rejected_when_not_enough_stock(logged_in_client, screen_protector):
    submit_sale(logged_in_client, screen_protector, qty=11, price=15.0)

    assert POSSale.query.count() == 0
    assert db.session.get(StockItem, screen_protector.id).quantity == 10


def test_pos_requires_login(client, screen_protector):
    response = submit_sale(client, screen_protector, qty=1, price=15.0)

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
    assert POSSale.query.count() == 0
