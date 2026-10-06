# Newspaper Delivery V5

Flask + SQLite testing version.

Features: one global Goods Received button; duplicate protection per customer/day; multiple papers; historical paper price snapshots; daily delivery charge; customer accounts; payment recording; advance credit; coupon records; collection cycles; ledger; Render deployment files.

## Local
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py

Open http://127.0.0.1:5000

## Render
Build: pip install -r requirements.txt
Start: gunicorn app:app

SQLite on Render Free is for testing only because the filesystem is not persistent. Use PostgreSQL for production data.
