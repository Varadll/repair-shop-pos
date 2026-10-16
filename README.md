# Repair Shop POS

A web-based point-of-sale and repair management system for phone and electronics repair shops. Built with Flask and SQLite, it handles the whole repair workflow: customer check-in, repair tickets, parts stock, invoicing, counter sales, and reporting.

## Features

**Customers and devices**
- Customer records with contact details and notes
- Track multiple devices per customer (type, brand, model, IMEI/serial, passcode, condition notes)
- Full repair and purchase history per customer

**Repair tickets**
- Auto-numbered tickets (`TK-0001`) linked to a customer and device
- Status workflow: Waiting → Diagnosed → In Progress → Ready → Collected (or Cancelled)
- Priority levels, due dates, and technician assignment
- Separate customer-facing and internal notes
- Progress log that records every status change, note, and assignment
- Add parts from stock to a ticket, by search or barcode scan

**Invoicing**
- Create an invoice from a ticket, with labour, parts, and discount
- Deposits and part payments, with the outstanding balance tracked
- Payment method recording and mark-as-paid
- Printable PDF invoices with shop details and VAT number

**Stock / parts inventory**
- Parts catalogue with category, SKU, compatible devices, supplier, and cost/sell prices
- Low-stock thresholds and alerts
- Per-unit barcode tracking: quantity syncs with active barcodes
- Manual stock adjustments

**Point of sale**
- Quick counter sales for accessories and parts (`POS-0001`)
- Barcode scanner support (detects fast keyboard-wedge input)
- Optional customer lookup on each sale
- PDF receipts

**Dashboard and reports**
- Dashboard: open tickets, ready-for-collection count, low-stock items, today's revenue
- Reports for any period (today, this week, this month, last 30/90 days, custom range, and more)
- Revenue split by invoices vs POS and by payment method
- Estimated profit and margin (labour + sales minus parts cost)
- Ticket and technician statistics, with a daily revenue chart

**Staff accounts**
- Login with hashed passwords (Flask-Login)
- Admin and technician roles

## Tech stack

- **Backend:** Python, Flask 3, Flask-SQLAlchemy, Flask-Migrate (Alembic), Flask-Login
- **Database:** SQLite by default (any SQLAlchemy-supported DB via `DATABASE_URL`)
- **Frontend:** Jinja2 templates, Bootstrap 5, Bootstrap Icons, Chart.js
- **PDFs:** WeasyPrint
- **Deployment:** Gunicorn

## Getting started

### Prerequisites
- Python 3.10+
- (Optional) [WeasyPrint system dependencies](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html) for PDF invoices and receipts

### Installation

```bash
git clone https://github.com/Varadll/repair-shop-pos.git
cd repair-shop-pos

python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt
pip install weasyprint          # optional, needed for PDF export
```

### Create the admin user

```bash
flask --app run.py create-admin
```

This creates a default admin account (`admin` / `admin123`). **Change the password after first login.**

### Run the app

```bash
flask --app run.py run --debug
```

Then open http://127.0.0.1:5000.

The database tables are created automatically on first run in `instance/repairshop.db`.

## Configuration

Settings are read from environment variables (see `config.py`):

| Variable        | Description                              | Default                            |
|-----------------|------------------------------------------|------------------------------------|
| `SECRET_KEY`    | Flask session secret. **Set this in production.** | `dev-secret-change-in-production` |
| `DATABASE_URL`  | SQLAlchemy database URL                  | `sqlite:///instance/repairshop.db` |
| `SHOP_NAME`     | Shop name shown on invoices and receipts | `Repair Shop`                      |
| `SHOP_ADDRESS`  | Shop address                             | `123 Main Street`                  |
| `SHOP_PHONE`    | Shop phone number                        | `+353 1 234 5678`                  |
| `SHOP_EMAIL`    | Shop email                               | `info@repairshop.com`              |
| `SHOP_VAT`      | VAT number (shown on invoices/receipts if set) | *(empty)*                    |

## Production

```bash
export SECRET_KEY="your-long-random-secret"
gunicorn -w 4 -b 0.0.0.0:8000 run:app
```

## Project structure

```
repair-shop-pos/
├── app/
│   ├── __init__.py          # App factory, blueprint registration
│   ├── extensions.py        # db, migrate, login_manager
│   ├── models.py            # SQLAlchemy models
│   ├── blueprints/
│   │   ├── auth/            # Login, logout, create-admin CLI
│   │   ├── dashboard/       # Home dashboard
│   │   ├── customers/       # Customer CRUD
│   │   ├── devices/         # Device CRUD
│   │   ├── tickets/         # Repair tickets, progress log, parts used
│   │   ├── invoices/        # Invoices, payments, PDF export
│   │   ├── stock/           # Inventory and barcodes
│   │   ├── pos/             # Counter sales and receipts
│   │   └── reports/         # Revenue, profit, ticket stats
│   └── templates/           # Jinja2 templates per module
├── migrations/              # Alembic migrations
├── config.py                # Configuration
├── run.py                   # Entry point
└── requirements.txt
```

## Data model

`User` · `Customer` · `Device` · `Ticket` · `TicketProgressLog` · `TicketPartUsed` · `Invoice` · `StockItem` · `Barcode` · `POSSale` · `POSSaleItem`

A customer has many devices; each ticket links a customer, a device, and an optional technician. A ticket can have one invoice and many parts used. Stock items can be tracked per unit with barcodes and are used by both tickets and POS sales.

## Author

**Varad Kanade** · [@Varadll](https://github.com/Varadll)
