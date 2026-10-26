# MARIS: offshore fleet ERP for SEAMEC

**MARIS** (Latin, "of the sea") is a web-based ERP for an offshore fleet of diving support vessels (DSVs), a support
vessel, an accommodation barge and bulk carriers, modelled on how [SEAMEC Ltd](https://seamec.in/) operates:
vessels are chartered by the day to oil and gas companies, and every hour of every day decides what is billed.

It brings the fleet, its certificates, crew, maintenance, daily reports, contracts and charter-hire billing into one
place, and answers the question that matters most each morning: **which vessels are fit to work, and what is
stopping the others?**

> **Demo data.** Vessel names, IMO numbers, MMSIs and flags come from public AIS ship directories (checked
> October 2026; blank where not found; verify against the registry before relying on them). Clients, rates, crew,
> positions, equipment intervals and dates are invented demo values.

---

## Features

| Area | What it does |
|---|---|
| **Control tower** | Fleet at a glance: vessels on hire, utilisation, hire revenue and profit this month, receivables, reports to approve, certificate warnings, one card per vessel |
| **Hire readiness** | Ready / not ready for every vessel, with the exact reasons: dry dock, certificates and surveys, bottom survey, minimum crew, crew certificates and MLC limits, critical equipment |
| **Planner** | 12-month timeline per vessel: contracts, bottom-survey deadline, certificate expiries, idle days and their cost, with suggestions where timing clashes |
| **Vessels and map** | Live fleet map (daily report, VSAT or AIS position, whichever is newest), vessel details and a 30-day track |
| **Certificates** | Statutory and class certificates with expiry and annual-survey windows; record a survey or a renewal |
| **Maintenance** | Planned jobs by calendar or running hours; a breakdown in a daily report opens a defect automatically; repeat failures flagged |
| **Crew** | Who is on board, reliefs due, certificates, minimum-crew gaps; assignments refused if they would break the rules |
| **Daily reports** | The vessel's 24-hour split (operating, standby, weather, breakdown, transit), work, diving, fuel and position; works offline |
| **Contracts** | Day rates, maintenance allowance, weather billing, tax, fees and bank guarantees; no double booking, no hire with invalid papers |
| **Hire invoices** | Drafted from approved reports with a full breakdown; approve and record payment |
| **Client portal** | The charterer's representative sees only their own contracts and signs or disputes each month's timesheet before invoicing |
| **Assistant** | Plain-language questions ("Is Princess ready for hire?", "Any open defects?") answered only from MARIS's own data |
| **Users and audit log** | Role-based access (vessel/ops, ops manager, admin, client) and a record of every important action |

## The business rules and their sources

Every rule that decides money or safety follows a published industry source, not a guess:

| Rule | Source |
|---|---|
| Maintenance allowance of so many hours a month, pro rata for part months; unused hours carry forward (per contract) | BIMCO SUPPLYTIME 2017, clause 13 |
| Weather hours billed at the operating or standby rate, set per contract | Charters differ, so it is a contract term |
| Tax label and rate set per contract | The GST rate on a vessel charter depends on its classification; confirm with a tax adviser |
| Certificates run 5 years; annual survey within 3 months either side of each anniversary of the expiry date; a missed survey makes the certificate invalid | IMO Harmonized System of Survey and Certification (HSSC) |
| Bottom inspection at most 36 months apart | HSSC |
| Critical equipment: an open defect or overdue job blocks hire readiness | ISM Code 10.3 |
| Diving plant examination intervals set per job | IMCA D 018 |
| At most 11 months on board without leave | MLC 2006, Standard A2.5 |
| Diver medical up to 12 months; STCW medical up to 2 years; certificate of competency revalidated every 5 years | IMCA D 014; STCW I/9, I/11 |

## Tech stack

- **Backend:** Python 3.12+, FastAPI, SQLAlchemy 2, SQLite (one file), pytest
- **Frontend:** React 18, TypeScript, Ant Design 5, TanStack Query, React Router, Leaflet (OpenStreetMap), Vite
- **Security:** PBKDF2 password hashing, HttpOnly SameSite=Strict session cookies, role checks on every route, audit log

## Getting started

Requirements: Python 3.12 or newer, Node.js 20 or newer.

```powershell
# Backend (from backend/)
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m scripts.seed --reset          # load demo data (wipes the database)

# Frontend (from frontend/)
npm install
npm run build

# Run (from backend/)
.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
```

Open http://127.0.0.1:8000. For frontend development, also run `npm run dev` in `frontend/` and open
http://localhost:5180 (API calls are forwarded to port 8000).

On macOS or Linux use `.venv/bin/python` instead of `.\.venv\Scripts\python.exe`.

### Demo accounts

Listed in [`setup/logins.json`](setup/logins.json): `admin`, `manager`, `ops` and `woc.rep` (a client
representative, who only sees the client portal). **These passwords are for local demos only. Change them before
anyone else uses the system.**

## Vessel positions: VSAT and AIS

The map shows the newest of three sources; a position older than 36 hours is marked out of date.

1. **Daily report:** the noon latitude and longitude typed in by the vessel (or filled from the device's GPS).
2. **VSAT:** an onboard GPS/VSAT gateway posts positions to `POST /api/positions/feed` with an `X-Feed-Key` header.
   Off until `MARIS_FEED_KEY` is set in `backend/.env`.
3. **AIS:** with a free [aisstream.io](https://aisstream.io) key in `backend/.env` (`AISSTREAM_API_KEY`), run
   `python -m scripts.ais_listener` from `backend/`. Shore-based AIS reaches roughly 30 nautical miles, so vessels
   far offshore may only appear through reports or VSAT.

Copy [`backend/.env.example`](backend/.env.example) to `backend/.env` for these settings. `.env` is never committed.

## Offline daily reports

Vessels on an intermittent VSAT link can file reports with no connection: they are kept on the device and sent
automatically when the link returns. Each carries a reference made on the device, so a resend after a dropped link
is accepted once, not refused as a duplicate. A service worker keeps the app itself available offline (HTTPS or
localhost).

## Project structure

```
backend/
  app/
    main.py            app entry; serves the API and the built frontend
    models.py          database tables
    schemas.py         input validation
    auth.py            sign-in, sessions, roles, audit
    core/              business rules: billing, fleet operations, tracking, assistant
    api/               HTTP routes, one file per area
  scripts/seed.py      demo data
  scripts/ais_listener.py   live AIS positions from aisstream.io
  tests/               pytest suite
frontend/
  src/pages/           one file per screen
  src/components/      layout, map, assistant, shared pieces
  src/api.ts           types, data loading, formatting
  src/offline.ts       offline outbox
  public/sw.js         service worker
setup/logins.json      demo accounts
```

## Tests

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q
```

The suite covers the billing rules, certificate surveys, permissions, contract rules, positions, maintenance and
defects, crew rules, hire readiness, the planner, client isolation and sign-off, the assistant and offline resends.

## Known limits

- Tables are created but never altered: after a model change, reload the demo data or add a migration tool (Alembic).
- Money is stored as floating-point rupees; switch to exact decimals before real billing.
- No lockout after repeated wrong passwords.
- ISM, ISSC and MLC intermediate verifications are not tracked yet.
- A daily report's noon position is taken as 12:00 IST.
