# NovaMart

NovaMart is a multi-role e-commerce platform built with Flask. It supports a
unified checkout, after-sales flows, messaging, and personalized discovery for
customers, merchants, and administrators.

## Highlights

- Customer, merchant, and admin roles with scoped dashboards
- Unified checkout (one payment, split by merchant orders)
- After-sales handling for returns/refunds
- Real-time-style messaging with images and product links
- Personalized recommendations and custom search

## Quick Start

```bash
pip install -r requirements.txt
flask db upgrade
python run.py
```

Default database: `sqlite:///ecommerce.db`


## Tech Stack

- Flask 3
- SQLAlchemy + Flask-Migrate
- Flask-Login
- SQLite (default)
