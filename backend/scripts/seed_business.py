"""Demo data for the business modules: vendors, spares and stock, purchase orders, port calls, dry docks, insurance,
tenders, off hire, performance claims, documents, cost history and budgets. Called by scripts/seed.py.

Every company name here is invented and marked "(demo)". Amounts and dates are demo values, relative to today.
Each warning the modules can raise is set up at least once, so it can be seen working.
"""
import random
from collections import defaultdict
from datetime import date, timedelta

from app.api.documents import store
from app.core.billing import month_days, months_between
from app.core.finance import contract_on
from app.models import (SHORE, Budget, Contract, CostEntry, DailyReport, DisbursementLine, Document, DryDockItem, DryDockProject, Equipment,
                        InsuranceClaim, InsurancePolicy, MaintenanceJob, OffHireEvent, Part, PerformanceClaim, POLine, PortCall, PurchaseOrder,
                        SecurityCamera, SecurityDrill, SecurityIncident, SpareRequest, StockItem, StockMove, Tender, Vendor, Vessel,
                        VesselSecurity, YardQuote)

TODAY = date.today()
L, CR = 100_000, 10_000_000


def d(offset: int) -> str:
    return (TODAY + timedelta(days=offset)).isoformat()


VENDORS = {
    # key: name, category, country, rating, approved
    "compressors": ("Konkan Marine Spares (demo)", "SPARES", "India", 4, True),
    "engines": ("Gulf Engine Parts LLC (demo)", "SPARES", "UAE", 3, True),
    "diving": ("Bharat Diving Systems (demo)", "SPARES", "India", 5, True),
    "electronics": ("Coastline Marine Electronics (demo)", "SPARES", "India", 4, True),
    "safety": ("SafeSea Equipment (demo)", "SPARES", "India", 4, True),
    "stores": ("Harbour Ship Chandlers (demo)", "STORES", "India", 3, True),
    "hydraulics": ("Western Hydraulics Service (demo)", "SERVICE", "India", None, False),  # awaiting evaluation
    "agent_mumbai": ("Mumbai Port Agency (demo)", "AGENT", "India", 4, True),
    "agent_kakinada": ("Godavari Shipping Agency (demo)", "AGENT", "India", 3, True),
    "agent_kochi": ("Malabar Marine Agency (demo)", "AGENT", "India", 4, True),
    "yard_kerala": ("Kerala Ship Repair Yard (demo)", "YARD", "India", 4, True),
    "yard_gulf": ("Arabian Gulf Drydocks (demo)", "YARD", "UAE", 5, True),
    "yard_lanka": ("Lanka Dockyard (demo)", "YARD", "Sri Lanka", 3, True),
}

# part no, name, unit, unit cost, vendor, lead days, held for (equipment name starts with), minimum on board
PARTS = [
    ("DAC-VK-01", "Dive compressor valve kit", "set", 85_000, "compressors", 21, "Dive air compressors", 2),
    ("DAC-FLT-02", "Dive compressor air filter set", "set", 18_000, "compressors", 10, "Dive air compressors", 4),
    ("DIV-SCR-01", "CO2 scrubber cartridge", "pc", 12_000, "diving", 14, "Diving system", 10),
    ("DIV-UMB-03", "Bell umbilical connector", "pc", 2_40_000, "diving", 45, "Diving system", 1),
    ("HRU-O2-01", "Rescue unit oxygen regulator", "pc", 65_000, "diving", 30, "Hyperbaric rescue unit", 1),
    ("DP-MRU-01", "DP motion reference unit", "pc", 3_80_000, "electronics", 60, "DP control system", 1),
    ("GEN-INJ-01", "Generator fuel injector", "pc", 42_000, "engines", 21, "Main generators", 6),
    ("GEN-INJ-02", "Barge generator fuel injector", "pc", 31_000, "engines", 21, "Generators", 4),
    ("FIR-DET-01", "Smoke detector head", "pc", 6_500, "safety", 7, "Fire detection", 10),
    ("LB-HOOK-01", "On-load release hook pin set", "set", 55_000, "safety", 30, "Lifeboats", 1),
    ("LR-HRU-01", "Liferaft hydrostatic release", "pc", 9_000, "safety", 10, "Liferafts", 4),
    ("ROV-HOSE-01", "A-frame hydraulic hose", "pc", 28_000, "engines", 14, "ROV launch system", 2),
    ("ME-FP-01", "Main engine fuel pump element", "pc", 1_10_000, "engines", 30, "Main engine", 2),
    ("SG-SEAL-01", "Steering gear ram seal kit", "set", 48_000, "engines", 21, "Steering gear", 1),
    ("STO-LUBE-01", "Lube oil, 208 L drum", "drum", 38_000, "stores", 5, None, 0),
    ("STO-PPE-01", "PPE kit (coverall, boots, gloves)", "set", 4_500, "stores", 5, None, 0),
]

TYPICAL_DAY_RATE = {"DSV": 22 * L, "OSV": 9 * L, "BARGE": 9 * L, "BULK": 10 * L}
MONTHLY = {  # budgeted spares, port and other costs per month, by vessel type
    "DSV": {"SPARES": 18 * L, "PORT": 4 * L, "OTHER": 3 * L},
    "OSV": {"SPARES": 6 * L, "PORT": 2 * L, "OTHER": 1 * L},
    "BARGE": {"SPARES": 4 * L, "PORT": 1 * L, "OTHER": 1 * L},
    "BULK": {"SPARES": 8 * L, "PORT": 10 * L, "OTHER": 2 * L},
}
HULL_VALUE = {"DSV": 180 * CR, "OSV": 60 * CR, "BARGE": 40 * CR, "BULK": 90 * CR}


def seed_business(session, rng: random.Random) -> None:
    vessels = {v.vessel_id: v for v in session.query(Vessel)}
    contracts = session.query(Contract).all()
    by_vessel = defaultdict(list)
    for c in contracts:
        by_vessel[c.vessel_id].append(c)

    def cost(vid, on, category, amount, description, source="MANUAL", ref=""):
        c = contract_on(by_vessel[vid], on)
        session.add(CostEntry(vessel_id=vid, contract_no=c.contract_no if c else None, on_date=on, category=category, amount=round(amount, 2),
                              description=description, source=source, ref=ref, created_by="manager"))

    # ---- Vendors, parts, stock ----
    vendor = {}
    for key, (name, category, country, rating, approved) in VENDORS.items():
        vendor[key] = Vendor(name=name, category=category, country=country, rating=rating, approved=approved,
                             contact="Sales desk", email=f"{key.replace('_', '.')}@example.com", payment_terms_days=30 if category != "AGENT" else 0)
        session.add(vendor[key])
    session.flush()
    part = {}
    for no, name, unit, unit_cost, vkey, lead, _, _ in PARTS:
        part[no] = Part(part_no=no, name=name, maker="", unit=unit, unit_cost=unit_cost, vendor_id=vendor[vkey].id, lead_days=lead)
        session.add(part[no])
    session.flush()

    def stock(no, location, qty, minimum=0, equipment=None):
        session.add(StockItem(part_id=part[no].id, location=location, qty=qty, min_qty=minimum, equipment_id=equipment.id if equipment else None))
        session.add(StockMove(part_id=part[no].id, location=location, qty=qty, kind="ADJUST", ref="Opening stock count", by="manager"))

    equipment = defaultdict(list)
    for e in session.query(Equipment):
        equipment[e.vessel_id].append(e)
    # Set cases: Paladin has no compressor valve kits (blocks hire, and its open defect waits for them);
    # SEAMEC II holds 1 of 2 DP reference units; Swordfish 6 of 10 scrubber cartridges (warnings).
    special = {("SM-PALADIN", "DAC-VK-01"): (0, 2), ("SM-II", "DP-MRU-01"): (1, 2), ("SM-SWORDFISH", "DIV-SCR-01"): (6, 10)}
    for vid in vessels:
        for no, _, _, _, _, _, held_for, minimum in PARTS:
            e = next((e for e in equipment[vid] if held_for and e.name.startswith(held_for)), None)
            if e:
                qty, minimum = special.get((vid, no), (minimum + rng.randint(0, 2), minimum))
                stock(no, vid, qty, minimum, e)
    for no, *_ in PARTS:
        stock(no, SHORE, rng.randint(3, 12), 2)
    session.flush()
    session.query(StockItem).filter(StockItem.part_id == part["GEN-INJ-01"].id, StockItem.location == SHORE).one().qty = 1  # shore below its minimum

    # ---- Purchase orders ----
    counter = defaultdict(int)

    def po(vkey, deliver_to, raised, status, lines, note="", received=None):
        ym = raised[2:4] + raised[5:7]
        counter[ym] += 1
        order = PurchaseOrder(po_no=f"PO-{ym}-{counter[ym]:03d}", vendor_id=vendor[vkey].id, deliver_to=deliver_to, status=status, note=note,
                              raised_by="ops", raised_on=raised, approved_by="manager" if status not in ("DRAFT",) else None,
                              ordered_on=raised if status in ("ORDERED", "RECEIVED") else None,
                              total=round(sum(part[no].unit_cost * qty for no, qty in lines), 2))
        session.add(order)
        session.flush()
        for no, qty in lines:
            session.add(POLine(po_no=order.po_no, part_id=part[no].id, description=part[no].name, qty=qty, unit_price=part[no].unit_cost,
                               received_qty=qty if status == "RECEIVED" else 0))
            if status == "RECEIVED":
                session.query(StockItem).filter(StockItem.part_id == part[no].id, StockItem.location == deliver_to).one().qty += qty
                session.add(StockMove(part_id=part[no].id, location=deliver_to, qty=qty, kind="RECEIPT", ref=order.po_no, by="ops"))
        if status == "RECEIVED" and deliver_to != SHORE:
            cost(deliver_to, received, "SPARES", order.total, f"{order.po_no} received", "PO", order.po_no)
        return order

    po("compressors", "SM-PRINCESS", d(-24), "RECEIVED", [("DAC-FLT-02", 4)], received=d(-20))
    po("engines", SHORE, d(-38), "RECEIVED", [("GEN-INJ-02", 8)], "Shore pool top-up", received=d(-31))
    paladin_order = po("compressors", "SM-PALADIN", d(-2), "ORDERED", [("DAC-VK-01", 2)], "Urgent: compressor defect, none on board")
    po("electronics", "SM-II", d(-1), "DRAFT", [("DP-MRU-01", 1)], "Second reference unit to bring stock to minimum")
    po("diving", SHORE, d(-1), "DRAFT", [("DIV-UMB-03", 5)], "Fleet spare pool for bell umbilicals")  # above ₹10 L: needs an admin
    po("stores", "SM-GLORIOUS", d(-3), "APPROVED", [("STO-LUBE-01", 6), ("STO-PPE-01", 40)])

    # Paladin's open compressor defect is blocked, waiting for the valve kits on order.
    defect = (session.query(MaintenanceJob).join(Equipment, Equipment.id == MaintenanceJob.equipment_id)
              .filter(Equipment.vessel_id == "SM-PALADIN", Equipment.name.startswith("Dive air"), MaintenanceJob.kind == "DEFECT",
                      MaintenanceJob.status == "OPEN").first())
    session.add(SpareRequest(job_id=defect.id, part_id=part["DAC-VK-01"].id, qty=2, status="WAITING", po_no=paladin_order.po_no, requested_on=d(-2)))

    # ---- Port calls ----
    def call(vid, port, purpose, eta, agent, status, lines, advance=0.0):
        pc = PortCall(vessel_id=vid, port=port, purpose=purpose, eta=eta, etd=eta, agent_id=vendor[agent].id, appointed_on=d(-50) if eta < d(-40) else d(-8),
                      status=status, ata=eta if status != "PLANNED" else None, atd=eta if status in ("SAILED", "CLOSED") else None,
                      advance_paid=advance, created_by="ops")
        session.add(pc)
        session.flush()
        for item, pda, fda in lines:
            session.add(DisbursementLine(port_call_id=pc.id, item=item, pda=pda, fda=fda))
        if status == "CLOSED":
            cost(vid, eta, "PORT", sum(f for _, _, f in lines), f"{port}: {purpose}", "PORT_CALL", f"port call {pc.id}")

    call("SM-SWORDFISH", "Kakinada", "Crew change and stores", d(-40), "agent_kakinada", "CLOSED",
         [("Port dues", 1.2 * L, 1.25 * L), ("Pilotage", 45_000, 45_000), ("Agency fee", 35_000, 35_000), ("Launch hire", 60_000, 78_000),
          ("Crew transport", 40_000, 38_000)], advance=2.5 * L)
    call("SM-GALLANT", "Kochi", "Bunkers and stores", d(-5), "agent_kochi", "SAILED",
         [("Port dues", 3.8 * L, 4.1 * L), ("Pilotage and towage", 2.2 * L, 2.9 * L), ("Agency fee", 50_000, 50_000), ("Garbage disposal", 25_000, None)],
         advance=6 * L)
    call("SM-PRINCESS", "Mumbai", "Crew change by launch", d(6), "agent_mumbai", "PLANNED",
         [("Launch hire", 70_000, None), ("Agency fee", 30_000, None), ("Immigration and customs", 15_000, None)])

    # ---- Dry docks ----
    def project(vid, title, start, days, status, quotes, items, chosen=None, actual_start=None):
        p = DryDockProject(vessel_id=vid, title=title, planned_start=start, planned_end=(date.fromisoformat(start) + timedelta(days=days)).isoformat(),
                           status=status, actual_start=actual_start, created_by="manager")
        session.add(p)
        session.flush()
        ids = {}
        for key, price, ydays, deviation in quotes:
            q = YardQuote(project_id=p.id, vendor_id=vendor[key].id, price=price, days=ydays, deviation_cost=deviation)
            session.add(q)
            session.flush()
            ids[key] = q.id
        p.yard_quote_id = ids.get(chosen)
        for category, description, budget, actual, state in items:
            session.add(DryDockItem(project_id=p.id, category=category, description=description, budget=budget, actual=actual, status=state))

    project("SM-III", "Intermediate docking and bottom survey", d(-12), 28, "IN_DOCK",
            [("yard_kerala", 3.6 * CR, 26, 8 * L), ("yard_lanka", 3.1 * CR, 30, 22 * L)],
            [("HULL", "Hull blasting and painting, underwater areas", 1.2 * CR, 1.1 * CR, "DONE"),
             ("CLASS", "Bottom survey and tailshaft survey with class", 35 * L, 32 * L, "DONE"),
             ("MACHINERY", "Sea chest valves overhaul", 22 * L, 25 * L, "DONE"),
             ("MACHINERY", "Tunnel thrusters overhaul", 60 * L, 0, "OPEN"),
             ("DIVING", "Saturation system pressure test and recertification", 45 * L, 0, "OPEN"),
             ("SAFETY", "Lifeboat davit load test", 8 * L, 7.5 * L, "DONE"),
             ("ELECTRICAL", "Main switchboard insulation survey", 12 * L, 0, "OPEN"),
             ("OTHER", "Anchor chain ranging and calibration", 9 * L, 0, "DEFERRED")],
            chosen="yard_kerala", actual_start=d(-12))
    project("SM-VALARCHI", "Special survey docking", d(12), 20, "CONTRACTED",
            [("yard_lanka", 1.4 * CR, 18, 9 * L), ("yard_gulf", 1.7 * CR, 15, 26 * L)],
            [("HULL", "Hull blasting and painting", 55 * L, 0, "OPEN"), ("CLASS", "Special survey items", 30 * L, 0, "OPEN"),
             ("MACHINERY", "Main engine crankshaft deflections", 6 * L, 0, "OPEN")], chosen="yard_lanka")
    project("SM-PALADIN", "Bottom survey docking (36-month limit)", d(80), 18, "PLANNING",
            [("yard_kerala", 2.9 * CR, 18, 10 * L), ("yard_gulf", 3.3 * CR, 14, 45 * L), ("yard_lanka", 2.6 * CR, 22, 28 * L)],
            [("HULL", "Hull blasting and painting", 1.0 * CR, 0, "OPEN"), ("CLASS", "Bottom and tailshaft survey", 30 * L, 0, "OPEN"),
             ("DIVING", "Dive compressor replacement (repeat failures)", 85 * L, 0, "OPEN")])

    # ---- Insurance ----
    start = date(TODAY.year if (TODAY.month, TODAY.day) >= (2, 20) else TODAY.year - 1, 2, 20)  # P&I renews on 20 February
    pi = InsurancePolicy(kind="PI", insurer="North Sea P&I Club (demo)", policy_no="PI-SEAMEC-FLEET", vessel_id=None, sum_insured=0, deductible=15 * L,
                         premium=2.4 * CR, start_date=start.isoformat(), end_date=(start.replace(year=start.year + 1) - timedelta(days=1)).isoformat())
    session.add(pi)
    session.add(InsurancePolicy(kind="CREW", insurer="Bharat General Insurance (demo)", policy_no="GPA-2026-0412", vessel_id=None, sum_insured=25 * CR,
                                deductible=0, premium=45 * L, start_date=d(-200), end_date=d(165)))
    hm = {}
    for vid, v in vessels.items():
        began = TODAY - timedelta(days=rng.randint(40, 300))
        if vid == "SM-GLORIOUS":
            began = TODAY - timedelta(days=334)  # expires in 30 days, renewal not on file yet
        if vid == "SM-DIAMOND":
            began = TODAY - timedelta(days=370)  # lapsed 5 days ago: not hire-ready
        si = HULL_VALUE[v.vessel_type]
        hm[vid] = InsurancePolicy(kind="HM", insurer="Oceanic Hull Underwriters (demo)", policy_no=f"HM-{vid[3:]}-{began.year}", vessel_id=vid, sum_insured=si,
                                  deductible=round(si * 0.005, -5), premium=round(si * 0.011, -5), start_date=began.isoformat(),
                                  end_date=(began + timedelta(days=364)).isoformat())
        session.add(hm[vid])
    session.add(InsurancePolicy(kind="LOH", insurer="Oceanic Hull Underwriters (demo)", policy_no="LOH-PRINCESS-26", vessel_id="SM-PRINCESS",
                                sum_insured=20 * CR, deductible=14 * 28 * L, premium=1.1 * CR, start_date=hm["SM-PRINCESS"].start_date,
                                end_date=hm["SM-PRINCESS"].end_date))
    session.flush()
    session.add(InsuranceClaim(policy_id=hm["SM-SWORDFISH"].id, vessel_id="SM-SWORDFISH", incident_on=max(d(-120), hm["SM-SWORDFISH"].start_date),
                               description="Contact with platform boat landing in swell; bulwark and fender damage", amount=1.8 * CR, status="SETTLED",
                               recovered=80 * L, settled_on=d(-30), created_by="manager"))
    cost("SM-SWORDFISH", d(-30), "INSURANCE", -80 * L, "Insurance recovery: contact damage", "INSURANCE", "claim 1")
    session.add(InsuranceClaim(policy_id=hm["SM-GLORIOUS"].id, vessel_id="SM-GLORIOUS", incident_on=max(d(-50), hm["SM-GLORIOUS"].start_date),
                               description="Heavy weather damage to mooring winches and wires", amount=1.4 * CR, status="SUBMITTED", created_by="manager"))
    session.add(InsuranceClaim(policy_id=pi.id, vessel_id="SM-II", incident_on=max(d(-25), pi.start_date),
                               description="Crew injury during anchor handling; medical and repatriation costs", amount=18 * L, status="NOTIFIED", created_by="manager"))

    # ---- Tenders ----
    contract = {c.contract_no: c for c in contracts}

    def tender(ref, client, vtype, vid, scope, start, end, due, op, sb, status, prob, winning=None, note="", contract_no=None, share=0.85, mob=0, mob_cost=0):
        session.add(Tender(ref=ref, client=client, vessel_type=vtype, vessel_id=vid, scope=scope, start_date=start, end_date=end, due_on=due,
                           operating_rate=op, standby_rate=sb, operating_share=share, mob_fee=mob, mob_cost=mob_cost, probability=prob, status=status,
                           winning_rate=winning, outcome_note=note, contract_no=contract_no, created_by="manager"))

    for no, ref, due in (("BEL/MSV/2026/003", "BEL-T-2025-118", -70), ("WOC/DSV/2026/022", "WOC-T-2026-041", -160)):
        c = contract[no]
        tender(ref, c.client, "DSV", c.vessel_id, c.scope, c.start_date, c.end_date, d(due), c.operating_rate, c.standby_rate, "WON", 1.0,
               note="Best technical score and price", contract_no=no, mob=c.mob_fee, mob_cost=c.mob_fee * 0.6)
    tender("ESP-T-2026-007", "Eastern Shelf Petroleum (demo)", "DSV", "SM-AGASTYA", "Saturation diving campaign, 6 months", d(-150), d(30), d(-180),
           30 * L, 15 * L, "LOST", 0, winning=26.5 * L, note="Price: lost to a lower bid")
    tender("GSC-T-2026-019", "Gulf Subsea Contractors (demo)", "DSV", "SM-SWORDFISH", "Air diving, riser inspection", d(-60), d(120), d(-95),
           17 * L, 8.5 * L, "LOST", 0, winning=16 * L, note="Price: about 6% above the winner")
    tender("BEL-T-2026-033", "Bay Energy Ltd (demo)", "OSV", "SM-DIAMOND", "Field support with ROV, DP2", d(-40), d(320), d(-75),
           9.5 * L, 5 * L, "LOST", 0, note="Technical: client wanted a DP2 vessel with an ROV hangar")
    tender("GSC-T-2026-022", "Gulf Subsea Contractors (demo)", "DSV", None, "Pipeline repair standby", d(20), d(80), d(-20),
           18 * L, 9 * L, "WITHDRAWN", 0, note="No vessel free in the window")
    tender("WOC-T-2026-077", "Western Offshore Oil Corp (demo)", "DSV", "SM-SWORDFISH", "Air diving support, 12 months, follow-on", d(30), d(395), d(-5),
           16.5 * L, 8 * L, "SUBMITTED", 0.5)
    tender("ESP-T-2026-015", "Eastern Shelf Petroleum (demo)", "DSV", "SM-AGASTYA", "Saturation diving, platform tie-ins", d(45), d(225), d(-3),
           25 * L, 12 * L, "SUBMITTED", 0.35, mob=40 * L, mob_cost=22 * L)
    tender("WOC-T-2026-090", "Western Offshore Oil Corp (demo)", "DSV", "SM-PRINCESS", "SBM campaign, east field", d(100), d(280), d(12),
           29 * L, 14 * L, "DRAFT", 0.3)  # Princess is still on contract then: shown as a clash
    tender("CBC-T-2026-004", "Coastal Bulk Charterers (demo)", "BULK", "SM-VALARCHI", "Time charter, 6 months", d(40), d(220), d(9),
           7.5 * L, 7.5 * L, "DRAFT", 0.4, share=1.0)
    tender("MRL-T-2026-002", "Mangalore Refinery Logistics (demo)", "BARGE", None, "Accommodation barge for shutdown, 250 persons", d(60), d(150), d(20),
           8.5 * L, 8.5 * L, "DRAFT", 0.25, share=1.0)

    # ---- Off hire ----
    # A breakdown in this month's reports, logged and agreed with the charterer.
    month_start = TODAY.replace(day=1).isoformat()
    breakdown = (session.query(DailyReport).filter(DailyReport.on_date >= month_start, DailyReport.breakdown_hrs > 0, DailyReport.contract_no.is_not(None))
                 .order_by(DailyReport.on_date).first())
    if breakdown:
        session.add(OffHireEvent(vessel_id=breakdown.vessel_id, contract_no=breakdown.contract_no, start_at=f"{breakdown.on_date}T06:00",
                                 end_at=f"{breakdown.on_date}T{6 + int(breakdown.breakdown_hrs):02d}:00", reason="BREAKDOWN",
                                 description=f"Breakdown: {breakdown.work_done[:60]}", status="AGREED", logged_by="ops", agreed_by="manager"))
    # Swordfish off hire for 6 hours for want of a DPO: straight off hire, outside the maintenance allowance.
    if TODAY.day > 2:
        day = d(-min(8, TODAY.day - 1))
        r = session.query(DailyReport).filter(DailyReport.vessel_id == "SM-SWORDFISH", DailyReport.on_date == day).first()
        if r and not (breakdown and (breakdown.vessel_id, breakdown.on_date) == (r.vessel_id, r.on_date)):
            moved = min(6.0, r.operating_hrs)
            r.operating_hrs -= moved
            r.breakdown_hrs += moved
            r.breakdown_equipment_id = r.breakdown_equipment_id or next(e.id for e in equipment["SM-SWORDFISH"] if e.name.startswith("DP"))
            session.add(OffHireEvent(vessel_id="SM-SWORDFISH", contract_no=r.contract_no, start_at=f"{day}T12:00", end_at=f"{day}T{12 + int(moved):02d}:00",
                                     reason="CREW", description="Short of a DPO after a medical sign-off; DP operations stopped until relief",
                                     status="ENDED", logged_by="ops"))
    # SEAMEC Gallant off hire now, changing a fuel pump element at anchorage.
    session.add(OffHireEvent(vessel_id="SM-GALLANT", contract_no="TC/GALLANT/2026/02", start_at=f"{d(0)}T04:00", reason="MAINTENANCE",
                             description="Main engine fuel pump element change at anchorage", status="OPEN", logged_by="ops"))

    # ---- Performance claims ----
    last_month = (TODAY.replace(day=1) - timedelta(days=1)).isoformat()[:7]
    bel = contract["BEL/MSV/2026/003"]
    session.add(PerformanceClaim(contract_no="WOC/DSV/2026/022", kind="DP", period=TODAY.isoformat()[:7], amount_claimed=9 * L,
                                 description="DP2 capability lost for 5 hours; saturation dive suspended and bell recovered", status="OPEN",
                                 raised_by="P. Raghavan (client representative)", raised_on=d(-4), response_due=d(10)))
    session.add(PerformanceClaim(contract_no=bel.contract_no, kind="FUEL", period=max(last_month, bel.start_date[:7]), amount_claimed=6.5 * L,
                                 description="Fuel consumption above the warranted 12 m3 a day on standby", status="ACCEPTED", amount_agreed=4 * L,
                                 raised_by="Bay Energy Ltd (demo)", raised_on=d(-12), response_due=d(2), decided_by="manager",
                                 decision_note="Agreed for 9 days after the generator governor fault; the rest was weather"))
    session.add(PerformanceClaim(contract_no="GSC/DSV/2025/031", kind="SPEED", period=last_month, amount_claimed=3 * L,
                                 description="Transit to location slower than the warranted 10 knots", status="REJECTED",
                                 raised_by="Gulf Subsea Contractors (demo)", raised_on=d(-20), response_due=d(-6), decided_by="manager",
                                 decision_note="Head seas of 3.5 m on passage, as logged; not a performance failure"))

    # ---- Documents ----
    def document(entity, key, kind, title, text):
        data = text.encode()
        session.add(Document(entity=entity, entity_key=key, kind=kind, title=title, version=1, filename=f"{title.replace(' ', '_')}.txt",
                             content_type="text/plain", size=len(data), sha256=store(data), uploaded_by="manager"))

    for c in contracts:
        if c.vessel_id != "SM-GALLANT":  # the time charter's charter party is not on file yet
            document("contract", c.contract_no, "CHARTER_PARTY", "Charter party",
                     f"DEMO DOCUMENT\nCharter party {c.contract_no}\nOwners: SEAMEC Ltd\nCharterers: {c.client}\nVessel: {vessels[c.vessel_id].name}\n"
                     f"Period: {c.start_date} to {c.end_date}\nForm: BIMCO SUPPLYTIME 2017 with riders\n")
    document("contract", "WOC/DSV/2026/014", "ADDENDUM", "Addendum 1 - rate review", "DEMO DOCUMENT\nAddendum 1: standby rate reviewed.\n")
    document("drydock", "1", "QUOTE", "Kerala yard quotation", "DEMO DOCUMENT\nYard quotation for intermediate docking.\n")

    # ---- Cost history and budgets for this year ----
    year_months = months_between(f"{TODAY.year}-01", TODAY.isoformat()[:7])
    for vid, v in vessels.items():
        plan = MONTHLY[v.vessel_type]
        for m in year_months:
            days = [x for x in month_days(m) if x < TODAY.isoformat()]
            if not days:
                continue
            share = len(days) / len(month_days(m))
            for category, budget in plan.items():
                on = days[min(14, len(days) - 1)]
                factor = rng.uniform(0.6, 1.5) if category != "OTHER" else rng.uniform(0.5, 1.3)
                cost(vid, on, category, budget * share * factor, {"SPARES": "Spares and stores", "PORT": "Port and agency", "OTHER": "Sundry costs"}[category]
                     + " (history)", "MANUAL", "history")
    # SEAMEC II's last docking, 10 months ago, if it fell this year.
    docked = (TODAY - timedelta(days=300)).isoformat()
    if docked[:4] == str(TODAY.year):
        cost("SM-II", docked, "DRYDOCK", 3.2 * CR, "Intermediate docking (history)", "DRYDOCK", "history")

    # ---- Ship security: cameras, drills, an incident or two, security levels ----
    for vid, v in vessels.items():
        places = ["Gangway", "Bridge", "Engine room"] + (["Dive control", "Moon pool"] if v.vessel_type == "DSV" else [])
        for place in places:
            broken = (vid, place) == ("SM-PALADIN", "Gangway")  # set case: a gangway camera with a fault
            session.add(SecurityCamera(vessel_id=vid, name=place, kind="PTZ" if place == "Gangway" else "FIXED", status="FAULT" if broken else "WORKING",
                                       checked_on=d(-rng.randint(1, 20)), note="No picture since power surge" if broken else ""))
        # Set case: SEAMEC Agastya's last drill was 4 months ago, so it is overdue.
        session.add(SecurityDrill(vessel_id=vid, kind="DRILL", on_date=d(-120 if vid == "SM-AGASTYA" else -rng.randint(10, 80)),
                                  scenario=rng.choice(["Unauthorised boarding", "Stowaway search", "Access control at gangway"]), by="ops"))
        session.add(SecurityDrill(vessel_id=vid, kind="EXERCISE", on_date=d(-rng.randint(60, 300)), scenario="Piracy approach, with company security officer", by="ops"))
        session.add(VesselSecurity(vessel_id=vid, level=1, sso=f"Chief Officer, {v.name}", set_on=d(-200), set_by="manager"))
    session.get(VesselSecurity, "SM-SWORDFISH").level = 2  # demo: heightened level while working in the Gulf
    session.add(SecurityIncident(vessel_id="SM-PRINCESS", happened_at=f"{d(-5)}T02:40", kind="SUSPICIOUS_APPROACH", severity="MEDIUM",
                                 description="Unlit fishing craft approached to 0.5 nm at night; turned away after searchlight and VHF call",
                                 action_taken="Security level watch doubled; reported to MRCC Mumbai", reported_to_authorities=True, logged_by="ops"))
    session.add(SecurityIncident(vessel_id="SM-GLORIOUS", happened_at=f"{d(-40)}T15:10", kind="THEFT", severity="LOW",
                                 description="Mooring rope missing from aft store", action_taken="Store locked; access log checked", status="CLOSED",
                                 logged_by="ops", closed_by="manager", closed_note="Rope found mislaid in forward store"))

    fleet_premium_per_vessel =(pi.premium + 45 * L) / len(vessels) / 12
    dock_months = {"SM-III": {TODAY.isoformat()[:7]: 2.3 * CR}, "SM-VALARCHI": {d(15)[:7]: 0.9 * CR}, "SM-PALADIN": {d(85)[:7]: 2.2 * CR}}
    for vid, v in vessels.items():
        for m in months_between(f"{TODAY.year}-01", f"{TODAY.year}-12"):
            n = len(month_days(m))
            lines = {"REVENUE": TYPICAL_DAY_RATE[v.vessel_type] * n * 0.75, "RUNNING": v.daily_opex * n,
                     "INSURANCE": hm[vid].premium / 12 + fleet_premium_per_vessel, **MONTHLY[v.vessel_type],
                     "DRYDOCK": dock_months.get(vid, {}).get(m, 0)}
            for category, amount in lines.items():
                if amount:
                    session.add(Budget(vessel_id=vid, period=m, category=category, amount=round(amount, -3)))
    session.flush()

