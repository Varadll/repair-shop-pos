import os

basedir = os.path.abspath(os.path.dirname(__file__))
instance_path = os.path.join(basedir, "instance")
os.makedirs(instance_path, exist_ok=True)


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{os.path.join(instance_path, 'repairshop.db')}"
    )
    # Shop details (used on invoices/receipts)
    SHOP_NAME = os.environ.get("SHOP_NAME", "Repair Shop")
    SHOP_ADDRESS = os.environ.get("SHOP_ADDRESS", "123 Main Street")
    SHOP_PHONE = os.environ.get("SHOP_PHONE", "+353 1 234 5678")
    SHOP_EMAIL = os.environ.get("SHOP_EMAIL", "info@repairshop.com")
    SHOP_VAT = os.environ.get("SHOP_VAT", "")
    LOW_STOCK_DEFAULT = 5
