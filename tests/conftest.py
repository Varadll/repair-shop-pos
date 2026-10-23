import pytest
from app import create_app
from app.extensions import db
from app.models import User, StockItem
from config import Config


class TestConfig(Config):
    TESTING = True
    # Fresh in-memory database for every test, so tests never touch instance/repairshop.db
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"


@pytest.fixture
def app():
    app = create_app(TestConfig)
    with app.app_context():
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def staff_user(app):
    user = User(username="tech", email="tech@example.com", full_name="Test Tech")
    user.set_password("password")
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def logged_in_client(client, staff_user):
    client.post("/login", data={"username": "tech", "password": "password"})
    return client


@pytest.fixture
def screen_protector(app):
    item = StockItem(name="iPhone 13 Screen Protector", quantity=10, sell_price=15.0)
    db.session.add(item)
    db.session.commit()
    return item
