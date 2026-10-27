"""Load demo data: the fleet, certificates, contracts, 60 days of daily reports, past invoices, a few automatic positions,
and (scripts/seed_business.py) the tenders, supply, port call, dry dock, insurance and finance records.

What is real and what is not:
- Vessel names, and the IMO numbers, MMSIs and flags below, are from public AIS ship directories (checked
  Oct 2026). Blank means not found; nothing is made up. Check them against the registry before relying on them.
- Clients, contract numbers, rates, positions, certificate dates and report figures are invented demo values.
Dates are relative to today, so the demo always looks current.

Run from backend/:  python -m scripts.seed --reset      (--reset wipes the database first)
"""
import json
import random
import sys
from datetime import date, datetime, timedelta, timezone

from app import config
from app.api.fleet import add_months, survey
from app.auth import make_hash
from app.core.billing import month_hire
from app.core.tracking import iso
from app.db import Base, SessionLocal, engine, migrate
from scripts.seed_business import seed_business
from app.models import (Assignment, Certificate, Contract, CrewCertificate, CrewMember, DailyReport, Equipment, HireInvoice, MaintenanceJob,
                        ManningRequirement, PositionFix, Timesheet, User, Vessel)

TODAY = date.today()


def d(offset: int) -> str:
    return (TODAY + timedelta(days=offset)).isoformat()


L = 100_000  # one lakh rupees

VESSELS = [
    # id, name, type, IMO, MMSI, flag, built, owner, running cost per day (demo), status
    ("SM-II", "SEAMEC II", "DSV", "8109292", "419227000", "India", None, "SEAMEC Ltd", 13 * L, "ON_HIRE"),
    ("SM-III", "SEAMEC III", "DSV", "8128339", "419228000", "India", None, "SEAMEC Ltd", 13 * L, "DRY_DOCK"),
    ("SM-PRINCESS", "SEAMEC Princess", "DSV", "8302959", "419603000", "India", 1984, "SEAMEC Ltd", 16 * L, "ON_HIRE"),
    ("SM-PALADIN", "SEAMEC Paladin", "DSV", "9388091", "352978118", "Panama", None, "SEAMEC Ltd", 15 * L, "ON_HIRE"),
    ("SM-SWORDFISH", "SEAMEC Swordfish", "DSV", "9385300", "538005198", "Marshall Islands", None, "SEAMEC Ltd", 11 * L, "ON_HIRE"),
    ("SM-AGASTYA", "SEAMEC Agastya", "DSV", "9483061", "538011888", "Marshall Islands", None, "SEAMEC Ltd", 14 * L, "AVAILABLE"),
    ("SM-DIAMOND", "SEAMEC Diamond", "OSV", "", None, "", None, "SEAMEC Ltd", 6 * L, "AVAILABLE"),
    ("SM-GLORIOUS", "SEAMEC Glorious", "BARGE", "1037555", "419902276", "India", None, "SEAMEC Ltd", 5 * L, "ON_HIRE"),
    ("SM-GALLANT", "SEAMEC Gallant", "BULK", "", None, "", None, "SEAMEC International FZE", 8 * L, "ON_HIRE"),
    ("SM-VALARCHI", "Chennai Valarchi", "BULK", "", None, "", None, "Seamate Shipping FZC", 7 * L, "AVAILABLE"),
]

# Base port for each vessel (where it sits with no reported position). Coordinates are approximate.
BASES = {
    "SM-II": ("Mumbai Port", 18.94, 72.85), "SM-III": ("Cochin shipyard (dry dock)", 9.96, 76.27),
    "SM-PRINCESS": ("Mumbai Port", 18.94, 72.85), "SM-PALADIN": ("Mumbai Port", 18.94, 72.85),
    "SM-SWORDFISH": ("Kakinada anchorage", 16.98, 82.30), "SM-AGASTYA": ("Mumbai outer anchorage", 18.88, 72.78),
    "SM-DIAMOND": ("Mumbai outer anchorage", 18.86, 72.80), "SM-GLORIOUS": ("Mumbai Port", 18.94, 72.85),
    "SM-GALLANT": ("Jebel Ali", 25.01, 55.06), "SM-VALARCHI": ("Chennai Port", 13.10, 80.30),
}
# Where each on-hire vessel works (demo offshore points). The bulk carrier sails a route instead.
FIELDS = {"SM-PRINCESS": (19.42, 71.33), "SM-PALADIN": (19.10, 71.85), "SM-II": (18.98, 72.12), "SM-SWORDFISH": (16.55, 82.45), "SM-GLORIOUS": (19.36, 71.42)}
VOYAGE = [(25.01, 55.06), (22.4, 60.2), (18.6, 64.8), (14.9, 69.5), (12.8, 74.2), (9.2, 76.0)]  # Jebel Ali to off Kochi

# Statutory and class certificates. Under the IMO harmonized system (HSSC) these run up to 5 years; the SOLAS,
# load line, MARPOL and class certificates need an annual survey within 3 months of each anniversary. ISM (SMC),
# ISPS (ISSC) and MLC have one intermediate verification instead, which MARIS does not track yet, so annual=False.
# name, issuing authority, annual survey
SHIP_CERTS = [
    ("Class certificate", "Classification society", True),
    ("Cargo Ship Safety Construction", "Flag state", True),
    ("Cargo Ship Safety Equipment", "Flag state", True),
    ("Cargo Ship Safety Radio", "Flag state", True),
    ("International Load Line", "Flag state", True),
    ("IOPP (MARPOL Annex I)", "Flag state", True),
    ("IAPP (MARPOL Annex VI)", "Flag state", True),
    ("Safety Management Certificate (ISM)", "Flag state", False),
    ("International Ship Security (ISSC)", "Flag state", False),
    ("Maritime Labour Certificate (MLC)", "Flag state", False),
]
# Diving systems: IMO Diving Code (MSC.548(107), in force 1 Jan 2024). Its survey cycle is not modelled, so no annual flag.
DIVING_CERT = ("Diving System Safety Certificate (IMO Diving Code)", "Classification society", False)
# SEAMEC Glorious is a non-propelled pontoon. SOLAS does not apply to ships not propelled by mechanical means,
# so it carries only class, load line and pollution certificates here.
BARGE_CERTS = [SHIP_CERTS[0], SHIP_CERTS[4], SHIP_CERTS[5]]

CONTRACTS = [
    # no, client, vessel, scope, start, end, operating, standby, allowance h/month, weather billed at, tax label, tax rate, mob, demob, BG expiry
    ("WOC/DSV/2026/014", "Western Offshore Oil Corp (demo)", "SM-PRINCESS", "SBM inspection and maintenance, saturation diving", d(-200), d(530), 28 * L, 14 * L, 24, "STANDBY", "GST", 0.18, 0, 0, d(560)),
    ("WOC/DSV/2026/022", "Western Offshore Oil Corp (demo)", "SM-PALADIN", "Pipeline inspection, ROV survey and repair", d(-130), d(235), 26 * L, 13 * L, 24, "STANDBY", "GST", 0.18, 0, 0, d(40)),
    ("BEL/MSV/2026/003", "Bay Energy Ltd (demo)", "SM-II", "Riser and clamp repair, diving support", d(-23), d(340), 22 * L, 11 * L, 24, "STANDBY", "GST", 0.18, 60 * L, 40 * L, d(370)),
    ("GSC/DSV/2025/031", "Gulf Subsea Contractors (demo)", "SM-SWORDFISH", "Air diving support, platform inspection", d(-357), d(22), 15 * L, 8 * L, 24, "OPERATING", "GST", 0.18, 0, 25 * L, d(52)),
    ("WOC/ACB/2026/005", "Western Offshore Oil Corp (demo)", "SM-GLORIOUS", "Accommodation barge, 300 persons", d(-90), d(275), 9 * L, 9 * L, 24, "OPERATING", "GST", 0.18, 0, 0, d(305)),
    # A time charter has one hire rate, so standby = operating and weather is on full hire.
    # The owner is the UAE company, so no Indian GST is charged; its own tax treatment is for its tax adviser.
    ("TC/GALLANT/2026/02", "Coastal Bulk Charterers (demo)", "SM-GALLANT", "Time charter, Supramax trades", d(-75), d(105), 12 * L, 12 * L, 24, "OPERATING", "No Indian GST (UAE owner)", 0.0, 0, 0, None),
]

# Months since the last bottom (dry dock) survey; HSSC allows at most 36. Demo values, chosen to show the planner's rules.
LAST_BOTTOM_SURVEY_MONTHS = {"SM-II": 10, "SM-III": 37, "SM-PRINCESS": 20, "SM-PALADIN": 33, "SM-SWORDFISH": 30, "SM-AGASTYA": 14,
                             "SM-DIAMOND": 25, "SM-GLORIOUS": 12, "SM-GALLANT": 26, "SM-VALARCHI": 35}

# Equipment by vessel type: name, system, critical (ISM 10.3), planned job, every N days, every N running hours.
# The systems are what such vessels carry; the intervals are demo values: real ones come from the maker's manual
# and, for diving plant, IMCA D 018.
EQUIPMENT = {
    "DSV": [
        ("Diving system (chambers, bell, life support)", "Diving", True, "Periodic examination and function test", 180, None),
        ("Hyperbaric rescue unit", "Diving", True, "Launch system and life support check", 180, None),
        ("Dive air compressors", "Diving", True, "Service and air quality test", 90, 1000),
        ("DP control system", "DP", True, "DP annual trials and FMEA check", 365, None),
        ("Main generators", "Power", True, "Generator service", None, 2000),
        ("Fire detection and fixed fire-fighting", "Safety", True, "Inspection and test", 90, None),
        ("Lifeboats and davits", "Safety", True, "Davit and on-load release check", 180, None),
        ("ROV launch system (A-frame)", "Lifting", False, "Wire and A-frame inspection", 180, None),
    ],
    "OSV": [
        ("DP control system", "DP", True, "DP annual trials and FMEA check", 365, None),
        ("Main generators", "Power", True, "Generator service", None, 2000),
        ("Fire detection and fixed fire-fighting", "Safety", True, "Inspection and test", 90, None),
        ("Lifeboats and davits", "Safety", True, "Davit and on-load release check", 180, None),
    ],
    "BARGE": [
        ("Generators", "Power", True, "Generator service", None, 2000),
        ("Fire detection and fixed fire-fighting", "Safety", True, "Inspection and test", 90, None),
        ("Liferafts", "Safety", True, "Annual liferaft service", 365, None),
        ("Mooring winches", "Lifting", False, "Brake test and inspection", 180, None),
    ],
    "BULK": [
        ("Main engine", "Propulsion", True, "Main engine unit overhaul", None, 8000),
        ("Steering gear", "Propulsion", True, "Steering gear test", 90, None),
        ("Generators", "Power", True, "Generator service", None, 2000),
        ("Hatch covers", "Cargo", False, "Hatch cover weathertightness check", 180, None),
    ],
}

# Minimum crew by rank (demo; the real numbers come from each vessel's Minimum Safe Manning Document and, for the
# dive team, the client's / IMCA requirement).
MANNING = {
    "DSV": [("Master", 1), ("Chief Officer", 1), ("DPO", 2), ("Chief Engineer", 1), ("Second Engineer", 1), ("Diving Supervisor", 2), ("Diver", 4)],
    "OSV": [("Master", 1), ("Chief Officer", 1), ("DPO", 2), ("Chief Engineer", 1), ("Second Engineer", 1)],
    "BARGE": [("Barge Master", 1), ("Chief Engineer", 1)],
    "BULK": [("Master", 1), ("Chief Officer", 1), ("Chief Engineer", 1), ("Second Engineer", 1)],
}
# Certificates by rank, with how long they run when issued. Diver medical: up to 12 months (IMCA D 014);
# STCW medical: up to 2 years; certificate of competency: revalidated every 5 years (STCW I/11).
DIVE_TEAM = ("Diving Supervisor", "Diver")
CERTS_FOR_RANK = {
    "marine": [("STCW Certificate of Competency", 60), ("Seafarer medical (STCW)", 24)],
    "DPO": [("STCW Certificate of Competency", 60), ("Seafarer medical (STCW)", 24), ("DP Operator certificate", 60)],
    "dive": [("Diver medical (IMCA D 014)", 12), ("Diving qualification", 60)],
}
FIRST = ["Arjun", "Rahul", "Vikram", "Suresh", "Anil", "Ravi", "Kiran", "Manoj", "Deepak", "Sanjay", "Ajay", "Naveen", "Prakash", "Rohit", "Imran", "Joseph",
         "Thomas", "Abdul", "Harish", "Gopal", "Karthik", "Nitin", "Pradeep", "Sameer", "Vinod", "Ashok", "Rajesh", "Sunil", "Mohan", "Faisal"]
LAST = ["Nair", "Menon", "Pillai", "Sharma", "Singh", "Iyer", "Rao", "Patil", "Desai", "Khan", "Fernandes", "D'Souza", "Kumar", "Joshi", "Shetty", "Varghese"]

LOCATIONS = {"SM-PRINCESS": "West Field SBM-2", "SM-PALADIN": "Pipeline WF-17", "SM-II": "Platform BH-4", "SM-SWORDFISH": "South Field P-9",
             "SM-GLORIOUS": "West Field complex", "SM-GALLANT": "At sea / Arabian Sea trade"}
WORK = ["SBM hawser and hose change-out", "Pipeline span survey by ROV", "Riser clamp installation", "Platform jacket inspection",
        "Saturation diving, valve replacement", "Anode survey and CP readings", "Standby at location for client permit"]


def reports_for(contract: Contract, vessel_type: str, rng: random.Random) -> list[DailyReport]:
    out = []
    start = max(date.fromisoformat(contract.start_date), TODAY - timedelta(days=60))
    fuel = 420.0
    day = start
    diving = vessel_type == "DSV"
    while day < TODAY:
        on = day.isoformat()
        day += timedelta(days=1)
        if contract.vessel_id == "SM-PALADIN" and on == d(-3):
            continue  # a missing report, for the dashboard to catch
        roll = rng.random()
        weather = rng.choice([0, 0, 0, 6, 12]) if roll < 0.25 else 0
        breakdown = rng.choice([4, 8, 14]) if roll > 0.93 else 0
        standby = rng.choice([0, 0, 4, 8]) if 0.25 <= roll < 0.45 else 0
        transit = 3 if rng.random() < 0.05 else 0
        operating = 24 - weather - breakdown - standby - transit
        received = 220.0 if fuel < 160 else 0.0
        fuel = round(fuel + received - rng.uniform(11, 19), 1)
        if contract.vessel_id in FIELDS:  # a few hundred metres of drift around the work site
            lat, lon = (round(c + rng.uniform(-0.02, 0.02), 4) for c in FIELDS[contract.vessel_id])
        else:  # the bulk carrier moves along its voyage, back and forth
            leg = (day - start).days % (2 * len(VOYAGE) - 2)
            lat, lon = VOYAGE[leg if leg < len(VOYAGE) else 2 * len(VOYAGE) - 2 - leg]
        out.append(DailyReport(
            vessel_id=contract.vessel_id, contract_no=contract.contract_no, on_date=on, location=LOCATIONS[contract.vessel_id], lat=lat, lon=lon,
            operating_hrs=operating, standby_hrs=standby, weather_hrs=weather, breakdown_hrs=breakdown, transit_hrs=transit,
            work_done=rng.choice(WORK) if diving else "Operations as per charter",
            dive_hrs=round(rng.uniform(10, 40), 1) if diving and operating > 12 else 0, rov_hrs=round(rng.uniform(0, 8), 1) if diving else 0,
            fuel_rob=fuel, fuel_received=received, pob=rng.randint(60, 110) if contract.vessel_id != "SM-GLORIOUS" else rng.randint(220, 290),
            incidents="Near miss: dropped object, no injury. Toolbox talk held." if rng.random() < 0.03 else "",
            # The last two days are still waiting for the office.
            status="SUBMITTED" if on >= d(-2) else "APPROVED", submitted_by="ops", approved_by=None if on >= d(-2) else "manager",
        ))
    return out


def certificate(vessel_id: str, name: str, authority: str, annual: bool, expires: date) -> Certificate:
    """A 5-year certificate expiring on `expires`, endorsed for every annual survey whose window has opened."""
    issued = add_months(expires, -60)
    c = Certificate(vessel_id=vessel_id, name=name, authority=authority, annual_survey=annual, issued_on=issued.isoformat(), expires_on=expires.isoformat())
    if annual:
        opened = [a for k in range(1, 5) if issued < (a := add_months(expires, -12 * k)) and add_months(a, -3) <= TODAY]
        if opened:
            a = max(opened)
            c.endorsed_on = min(TODAY, a - timedelta(days=30)).isoformat()
    return c


def seed_operations(session, rng: random.Random, types: dict) -> None:
    """Equipment, maintenance and defects, crew on board, manning, bottom surveys and client sign-offs."""
    for vid, months in LAST_BOTTOM_SURVEY_MONTHS.items():
        session.get(Vessel, vid).last_bottom_survey_on = add_months(TODAY, -months).isoformat()

    # Equipment and planned jobs, mostly up to date.
    equipment: dict[str, list[Equipment]] = {}
    for vid, vtype in types.items():
        equipment[vid] = []
        for name, system, critical, job, days, hours in EQUIPMENT[vtype]:
            e = Equipment(vessel_id=vid, name=name, system=system, critical=critical, running_hours=float(rng.randint(8000, 60000)), hours_updated_on=d(-3))
            session.add(e)
            session.flush()
            equipment[vid].append(e)
            session.add(MaintenanceJob(equipment_id=e.id, kind="PLANNED", title=job, interval_days=days, interval_hours=hours,
                                       last_done_on=d(-rng.randint(5, int(days * 0.7))) if days else d(-30),
                                       last_done_hours=e.running_hours - rng.randint(50, int(hours * 0.6)) if hours else None))
    session.flush()

    # Every breakdown in the daily reports raised a defect on a critical working system; old ones are closed.
    for r in session.query(DailyReport).filter(DailyReport.breakdown_hrs > 0):
        critical = [e for e in equipment[r.vessel_id] if e.critical and e.system in ("Diving", "DP", "Power", "Propulsion")]
        e = rng.choice(critical)
        r.breakdown_equipment_id = e.id
        recent = r.on_date >= d(-5)
        session.add(MaintenanceJob(equipment_id=e.id, kind="DEFECT", title=f"Breakdown {r.on_date}: {r.work_done[:60]}", raised_on=r.on_date, report_id=r.id,
                                   downtime_hrs=r.breakdown_hrs, status="OPEN" if recent else "CLOSED",
                                   closed_on=None if recent else (date.fromisoformat(r.on_date) + timedelta(days=1)).isoformat(),
                                   note="" if recent else "Repaired and tested; back in service."))

    # Set cases: Paladin's dive compressors keep failing (repeat failure, one still open), and SEAMEC II's
    # DP trials are overdue. Both are critical, so neither vessel is hire-ready.
    compressors = next(e for e in equipment["SM-PALADIN"] if e.name.startswith("Dive air"))
    for ago, status in ((40, "CLOSED"), (22, "CLOSED"), (2, "OPEN")):
        session.add(MaintenanceJob(equipment_id=compressors.id, kind="DEFECT", title="Compressor tripped on high temperature", raised_on=d(-ago),
                                   downtime_hrs=6, status=status, closed_on=d(-ago + 1) if status == "CLOSED" else None,
                                   note="Cooler cleaned, restarted." if status == "CLOSED" else ""))
    dp = next(e for e in equipment["SM-II"] if e.name.startswith("DP"))
    session.query(MaintenanceJob).filter(MaintenanceJob.equipment_id == dp.id, MaintenanceJob.kind == "PLANNED").one().last_done_on = d(-370)

    # Manning and crew. Vessels on hire are fully crewed; idle and docked vessels carry a skeleton crew.
    used = set()

    def person(rank: str) -> CrewMember:
        while True:
            name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
            if name not in used:
                used.add(name)
                break
        p = CrewMember(name=name, rank=rank)
        session.add(p)
        session.flush()
        kind = "dive" if rank in DIVE_TEAM else "DPO" if rank == "DPO" else "marine"
        for cert, months in CERTS_FOR_RANK[kind]:
            issued = TODAY - timedelta(days=rng.randint(10, months * 30 - 120))
            session.add(CrewCertificate(crew_id=p.id, name=cert, expires_on=add_months(issued, months).isoformat()))
        return p

    for vid, vtype in types.items():
        status = session.get(Vessel, vid).status
        for rank, count in MANNING[vtype]:
            session.add(ManningRequirement(vessel_id=vid, rank=rank, count=count))
            aboard = count if status == "ON_HIRE" else (1 if rank in ("Master", "Barge Master", "Chief Engineer") else 0)
            for _ in range(aboard):
                p = person(rank)
                rotation = rng.randint(28, 35) if rank in DIVE_TEAM else rng.randint(90, 120)
                sign_on = TODAY - timedelta(days=rng.randint(3, rotation - 5))
                session.add(Assignment(crew_id=p.id, vessel_id=vid, sign_on=sign_on.isoformat(), relief_due=(sign_on + timedelta(days=rotation)).isoformat()))
        session.flush()
    # A pool ashore, free to send as reliefs.
    for rank in ["Master", "Chief Officer", "DPO", "DPO", "Chief Engineer", "Second Engineer", "Diving Supervisor", "Diver", "Diver", "Diver", "Diver"]:
        person(rank)
    session.flush()

    def aboard_as(vid, rank):
        return session.query(Assignment).join(CrewMember, CrewMember.id == Assignment.crew_id).filter(
            Assignment.vessel_id == vid, CrewMember.rank == rank, Assignment.signed_off.is_(None)).first()

    # Set cases: a Princess diver whose medical runs out before relief; Swordfish's chief engineer close to the
    # 11-month MLC limit; Glorious's barge master past it.
    diver = aboard_as("SM-PRINCESS", "Diver")
    medical = session.query(CrewCertificate).filter(CrewCertificate.crew_id == diver.crew_id, CrewCertificate.name.startswith("Diver medical")).one()
    medical.expires_on = (date.fromisoformat(diver.relief_due) - timedelta(days=4)).isoformat()
    chief = aboard_as("SM-SWORDFISH", "Chief Engineer")
    chief.sign_on, chief.relief_due = add_months(TODAY, -10).isoformat(), d(20)
    master = aboard_as("SM-GLORIOUS", "Barge Master")
    master.sign_on, master.relief_due = (add_months(TODAY, -11) - timedelta(days=9)).isoformat(), d(5)

    # Client sign-off: Western Offshore Oil Corp contracts need the monthly timesheet signed before invoicing.
    # Past months are signed; last month's SEAMEC Paladin timesheet is still with the client, so its invoice is a draft.
    last_month = (TODAY.replace(day=1) - timedelta(days=1)).isoformat()[:7]
    for c in session.query(Contract).filter(Contract.client.startswith("Western Offshore")):
        c.client_signoff_required = True
        for inv in session.query(HireInvoice).filter(HireInvoice.contract_no == c.contract_no):
            if c.vessel_id == "SM-PALADIN" and inv.period == last_month:
                inv.status, inv.approved_by = "DRAFT", None
                continue
            session.add(Timesheet(contract_no=c.contract_no, period=inv.period, status="SIGNED", by="P. Raghavan (client representative)",
                                  at=f"{inv.invoice_date}T05:30:00Z", note=""))


def seed_users(session) -> None:
    """The demo accounts from setup/logins.json. Those passwords are for a local demo only."""
    for u in json.loads(config.SEED_USERS_FILE.read_text(encoding="utf-8")):
        session.merge(User(username=u["username"], name=u["name"], role=u["role"], password_hash=make_hash(u["password"]), active=True,
                           client_name=u.get("client_name")))
    session.commit()


def seed(session) -> None:
    rng = random.Random(7)
    types = {}
    for vid, name, vtype, imo, mmsi, flag, built, entity, opex, status in VESSELS:
        types[vid] = vtype
        session.add(Vessel(vessel_id=vid, name=name, vessel_type=vtype, imo=imo, mmsi=mmsi, flag=flag, built_year=built, entity=entity,
                           daily_opex=opex, status=status, base_port=BASES[vid][0], base_lat=BASES[vid][1], base_lon=BASES[vid][2]))
        certs = BARGE_CERTS if vtype == "BARGE" else SHIP_CERTS + ([DIVING_CERT] if vtype == "DSV" else [])
        for name_, authority, annual in certs:
            session.add(certificate(vid, name_, authority, annual, TODAY + timedelta(days=rng.randint(120, 1700))))
    session.flush()

    # A few certificates set to show each warning, so the alerts can be seen working.
    def cert(vid, prefix):
        return session.query(Certificate).filter(Certificate.vessel_id == vid, Certificate.name.startswith(prefix)).one()

    agastya = cert("SM-AGASTYA", "Diving System")  # expired: Agastya cannot go on a new contract until it is renewed
    agastya.expires_on, agastya.issued_on = d(-12), add_months(TODAY - timedelta(days=12), -60).isoformat()
    paladin = cert("SM-PALADIN", "Cargo Ship Safety Equipment")  # expires in 30 days
    new = certificate("SM-PALADIN", paladin.name, paladin.authority, True, TODAY + timedelta(days=30))
    paladin.issued_on, paladin.expires_on, paladin.endorsed_on = new.issued_on, new.expires_on, new.endorsed_on
    radio = cert("SM-II", "Cargo Ship Safety Radio")  # anniversary in 30 days: survey window open, not yet surveyed
    radio.expires_on = add_months(TODAY + timedelta(days=30), 24).isoformat()
    radio.issued_on = add_months(date.fromisoformat(radio.expires_on), -60).isoformat()
    radio.endorsed_on = (TODAY + timedelta(days=30) - timedelta(days=365 + 20)).isoformat()
    missed = cert("SM-DIAMOND", "Cargo Ship Safety Radio")  # anniversary 4 months ago, window closed, never surveyed
    missed.expires_on = add_months(TODAY - timedelta(days=120), 36).isoformat()
    missed.issued_on = add_months(date.fromisoformat(missed.expires_on), -60).isoformat()
    missed.endorsed_on = (TODAY - timedelta(days=120 + 365 + 15)).isoformat()
    for c, expect in ((radio, "DUE"), (missed, "OVERDUE")):
        assert survey(c)["survey"] == expect, (c.name, survey(c))

    for no, client, vid, scope, start, end, op, sb, allowance, weather, tax_label, tax_rate, mob, demob, bg in CONTRACTS:
        contract = Contract(contract_no=no, client=client, vessel_id=vid, scope=scope, start_date=start, end_date=end, operating_rate=op, standby_rate=sb,
                            breakdown_allowance_hrs=allowance, allowance_accrues=True, weather_billing=weather, tax_label=tax_label, tax_rate=tax_rate,
                            mob_fee=mob, demob_fee=demob, payment_terms_days=30, bg_amount=round(op * 30 * 0.1, -5) if bg else 0, bg_expiry=bg,
                            created_by="admin")
        session.add(contract)
        reports = reports_for(contract, types[vid], rng)
        session.add_all(reports)

        # Invoices for the two months before this one: the older one paid, the last one approved and awaiting payment.
        last_month = (TODAY.replace(day=1) - timedelta(days=1)).replace(day=1)
        for month_start, status in (((last_month - timedelta(days=1)).replace(day=1), "PAID"), (last_month, "APPROVED")):
            period = month_start.isoformat()[:7]
            calc = month_hire(contract, reports, period)
            if not calc["reported_days"]:
                continue
            tax = round(calc["amount"] * tax_rate, 2)
            issued = (month_start.replace(day=28) + timedelta(days=8)).isoformat()
            n = len([o for o in session.new if isinstance(o, HireInvoice) and o.period == period]) + 1
            session.add(HireInvoice(inv_no=f"INV-{period[2:4]}{period[5:7]}-{n:03d}", contract_no=no, period=period, invoice_date=issued,
                                    due_date=(date.fromisoformat(issued) + timedelta(days=30)).isoformat(), calc=calc, amount=calc["amount"],
                                    tax_label=tax_label, tax_rate=tax_rate, tax=tax, total=round(calc["amount"] + tax, 2), status=status,
                                    created_by="manager", approved_by="manager",
                                    paid_on=(date.fromisoformat(issued) + timedelta(days=27)).isoformat() if status == "PAID" else None))

    seed_operations(session, rng, types)

    # Automatic positions for today: SEAMEC Princess's own GPS over VSAT every 30 minutes, and SEAMEC Paladin by AIS
    # every hour. These are what an onboard gateway and the AIS listener would store.
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    for i in range(12):
        lat, lon = FIELDS["SM-PRINCESS"]
        session.add(PositionFix(vessel_id="SM-PRINCESS", at=iso(now - timedelta(minutes=30 * i)), lat=round(lat + rng.uniform(-0.01, 0.01), 4),
                                lon=round(lon + rng.uniform(-0.01, 0.01), 4), sog=round(rng.uniform(0, 0.4), 1), source="VSAT"))
    for i in range(6):
        lat, lon = FIELDS["SM-PALADIN"]
        session.add(PositionFix(vessel_id="SM-PALADIN", at=iso(now - timedelta(hours=i, minutes=7)), lat=round(lat + 0.01 * i, 4),
                                lon=round(lon - 0.01 * i, 4), sog=1.2, cog=135.0, source="AIS"))
    seed_business(session, rng)
    session.commit()


if __name__ == "__main__":
    if "--reset" in sys.argv:
        Base.metadata.drop_all(engine)
    migrate()
    with SessionLocal() as session:
        if session.query(Vessel).count():
            sys.exit("The database already has data. Run with --reset to wipe it and load the demo data again.")
        seed_users(session)
        seed(session)
        print(f"Loaded {len(VESSELS)} vessels, {len(CONTRACTS)} contracts and their reports into {config.DATABASE_URL}")
