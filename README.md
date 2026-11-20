# MediCore — Hospital Emergency Management System

A Django + Django Templates starter application for managing emergency patient flow,
triage, staff, beds, ambulances and operational reporting.

## 1. Requirements
- Python 3.10+
- pip

## 2. Setup
```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py seed_demo
python manage.py runserver
```
Open http://127.0.0.1:8000/

The demo command creates a demo login:
- Username: `admin`
- Password: `Admin@12345`

Change this password immediately. The demo data is fictional.

## 3. Main modules
- Separate sign-in portals: Admin `/admin/`, Doctor `/doctor/`, Pharmacist `/pharmacist/`, Lab `/lab/`, Staff `/staff/` (reception, nurses and other staff). Only the admin creates doctor and staff accounts; there is no self sign-up and no patient portal.
- Emergency patient registration and case tracking
- Triage severity and priority queue
- Staff directory and availability
- Bed and ward allocation
- Ambulance status and dispatch details
- Dashboard and operational reports
- Django data admin at `/django-admin/`

## 4. Notes
This is an educational/basic operational prototype, not a certified clinical system.
It does not replace clinical judgement, emergency protocols, access auditing, backups,
encryption/key management, or integration with hospital devices and systems.
Before real deployment, add HTTPS, secure production settings, granular permissions,
audit logs, database backups, privacy/legal review, and clinical validation.

SQLite is used for easy local setup. For production, configure PostgreSQL in
`config/settings.py`.
