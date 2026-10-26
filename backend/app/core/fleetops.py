"""Fleet operations rules: maintenance status, crew alerts, hire readiness and the planner.

The rules, and where they come from:
- ISM Code 10.3: the company identifies equipment whose sudden failure may be hazardous ("critical") and takes
  specific measures for its reliability. Here: an overdue planned job, or an open defect, on critical equipment
  makes the vessel not hire-ready.
- MLC 2006 (Standard A2.5 with the annual leave rules, as read by the ILO): at most 11 months' continuous service
  on board without leave.
- Crew certificate validity is whatever the certificate says; typical limits (STCW medical up to 2 years,
  IMCA D 014 diver medical up to 12 months) only shape the demo data.
- HSSC: the outside of the bottom is inspected at least twice in 5 years, never more than 36 months apart.
"""
from collections import Counter, defaultdict
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..api.fleet import INVALID, add_months, cert_out
from ..models import Assignment, Certificate, Contract, CrewCertificate, CrewMember, Equipment, MaintenanceJob, ManningRequirement, Vessel

DUE_SOON_DAYS = 14
MLC_MAX_MONTHS = 11
MLC_WARN_MONTHS = 10
BOTTOM_SURVEY_MAX_MONTHS = 36
REPEAT_FAILURES = 3  # this many defects on one item ...
REPEAT_WINDOW_DAYS = 60  # ... within this many days is flagged as a repeat failure


def _d(iso_day: str | None) -> date | None:
    return date.fromisoformat(iso_day) if iso_day else None


# ---------------- Maintenance ----------------


def job_status(job: MaintenanceJob, eq: Equipment, today: date | None = None) -> dict:
    """When a planned job falls due, by calendar and/or running hours, whichever comes first."""
    today = today or date.today()
    if job.kind == "DEFECT":
        return {"state": "OPEN" if job.status == "OPEN" else "CLOSED", "due_on": None, "hours_left": None, "days_left": None}
    due_on = _d(job.last_done_on) + timedelta(days=job.interval_days) if job.interval_days and job.last_done_on else None
    days_left = (due_on - today).days if due_on else None
    hours_left = None
    if job.interval_hours and job.last_done_hours is not None:
        hours_left = round(job.last_done_hours + job.interval_hours - eq.running_hours, 1)
    if (days_left is not None and days_left < 0) or (hours_left is not None and hours_left < 0):
        state = "OVERDUE"
    elif (days_left is not None and days_left <= DUE_SOON_DAYS) or (hours_left is not None and job.interval_hours and hours_left <= 0.1 * job.interval_hours):
        state = "DUE_SOON"
    else:
        state = "OK"
    return {"state": state, "due_on": due_on.isoformat() if due_on else None, "days_left": days_left, "hours_left": hours_left}


def maintenance(session: Session, vessel_id: str | None = None) -> list[dict]:
    """Every job with its equipment and status; open defects and overdue critical work first."""
    eq_query = select(Equipment)
    if vessel_id:
        eq_query = eq_query.where(Equipment.vessel_id == vessel_id)
    equipment = {e.id: e for e in session.scalars(eq_query)}
    if not equipment:
        return []
    jobs = session.scalars(select(MaintenanceJob).where(MaintenanceJob.equipment_id.in_(equipment))).all()
    since = (date.today() - timedelta(days=REPEAT_WINDOW_DAYS)).isoformat()
    recent_defects = Counter(j.equipment_id for j in jobs if j.kind == "DEFECT" and (j.raised_on or "") >= since)
    out = []
    for j in jobs:
        e = equipment[j.equipment_id]
        out.append({
            "id": j.id, "kind": j.kind, "title": j.title, "equipment_id": e.id, "equipment": e.name, "system": e.system,
            "critical": e.critical, "vessel_id": e.vessel_id, "running_hours": e.running_hours,
            "interval_days": j.interval_days, "interval_hours": j.interval_hours, "last_done_on": j.last_done_on, "last_done_hours": j.last_done_hours,
            "raised_on": j.raised_on, "report_id": j.report_id, "downtime_hrs": j.downtime_hrs, "closed_on": j.closed_on, "note": j.note,
            "repeat_failure": recent_defects[e.id] >= REPEAT_FAILURES,
            **job_status(j, e),
        })
    rank = {"OPEN": 0, "OVERDUE": 1, "DUE_SOON": 2, "OK": 3, "CLOSED": 4}
    return sorted(out, key=lambda j: (rank[j["state"]], not j["critical"], j["due_on"] or "9999"))


# ---------------- Crew ----------------


def on_board(session: Session, vessel_id: str | None = None, today: date | None = None) -> list[Assignment]:
    today_s = (today or date.today()).isoformat()
    q = select(Assignment).where(Assignment.signed_off.is_(None), Assignment.sign_on <= today_s)
    if vessel_id:
        q = q.where(Assignment.vessel_id == vessel_id)
    return session.scalars(q).all()


def crew_alerts(session: Session, assignments: list[Assignment], today: date | None = None) -> list[dict]:
    """One row per person on board, with what needs doing about them."""
    today = today or date.today()
    people = {c.id: c for c in session.scalars(select(CrewMember).where(CrewMember.id.in_([a.crew_id for a in assignments])))}
    certs = defaultdict(list)
    for c in session.scalars(select(CrewCertificate).where(CrewCertificate.crew_id.in_(people))):
        certs[c.crew_id].append(c)
    out = []
    for a in assignments:
        person = people[a.crew_id]
        sign_on, relief = _d(a.sign_on), _d(a.relief_due)
        limit = add_months(sign_on, MLC_MAX_MONTHS)
        alerts = []
        if today > limit:
            alerts.append(("BLOCK", f"On board longer than 11 months (MLC) since {limit.isoformat()}"))
        elif today >= add_months(sign_on, MLC_WARN_MONTHS):
            alerts.append(("WARN", f"Reaches the 11-month MLC limit on {limit.isoformat()}"))
        if relief > limit:
            alerts.append(("WARN", f"Planned relief {a.relief_due} is after the 11-month MLC limit"))
        if relief < today:
            alerts.append(("WARN", f"Relief overdue since {a.relief_due}"))
        elif (relief - today).days <= DUE_SOON_DAYS:
            alerts.append(("INFO", f"Relief due {a.relief_due}"))
        for c in certs[person.id]:
            expires = _d(c.expires_on)
            if expires < today:
                alerts.append(("BLOCK", f"{c.name} expired {c.expires_on}"))
            elif expires <= relief:
                alerts.append(("WARN", f"{c.name} expires {c.expires_on}, before the planned relief"))
        out.append({
            "assignment_id": a.id, "crew_id": person.id, "name": person.name, "rank": person.rank, "vessel_id": a.vessel_id,
            "sign_on": a.sign_on, "relief_due": a.relief_due, "days_on_board": (today - sign_on).days, "mlc_limit": limit.isoformat(),
            "certificates": [{"name": c.name, "expires_on": c.expires_on} for c in sorted(certs[person.id], key=lambda c: c.expires_on)],
            "alerts": [{"level": level, "text": text} for level, text in alerts],
        })
    level_rank = {"BLOCK": 0, "WARN": 1, "INFO": 2}
    return sorted(out, key=lambda r: (min((level_rank[a["level"]] for a in r["alerts"]), default=3), r["vessel_id"], r["rank"]))


def manning_gaps(session: Session, vessel_id: str, aboard: list[dict]) -> list[dict]:
    have = Counter(r["rank"] for r in aboard)
    need = session.scalars(select(ManningRequirement).where(ManningRequirement.vessel_id == vessel_id)).all()
    return [{"rank": m.rank, "required": m.count, "on_board": have[m.rank]} for m in need if have[m.rank] < m.count]


# ---------------- Hire readiness ----------------


def bottom_survey(v: Vessel, today: date | None = None) -> dict:
    today = today or date.today()
    if not v.last_bottom_survey_on:
        return {"due_by": None, "days_left": None}
    due = add_months(_d(v.last_bottom_survey_on), BOTTOM_SURVEY_MAX_MONTHS)
    return {"due_by": due.isoformat(), "days_left": (due - today).days}


def readiness(session: Session, vessel: Vessel) -> dict:
    """Can this vessel go on hire now? Every check, with what fails (blocks) and what to watch (warnings)."""
    checks = []

    def check(name: str, problems: list[str], warnings: list[str] = ()):
        checks.append({"check": name, "ok": not problems, "problems": problems, "warnings": list(warnings)})

    check("Not in dry dock", ["The vessel is in dry dock."] if vessel.status == "DRY_DOCK" else [])

    certs = [cert_out(c) for c in session.scalars(select(Certificate).where(Certificate.vessel_id == vessel.vessel_id))]
    check("Statutory and class certificates",
          [f"{c['name']}: {'expired' if c['state'] == 'EXPIRED' else 'annual survey missed'}" for c in certs if c["critical"] and c["state"] in INVALID],
          [f"{c['name']}: {'expires ' + c['expires_on'] if c['state'] == 'EXPIRING' else 'survey window open until ' + str(c['survey_to'])}"
           for c in certs if c["state"] in ("EXPIRING", "SURVEY_DUE")])

    hull = bottom_survey(vessel)
    if hull["days_left"] is None:
        check("Bottom survey (36-month limit)", [], ["No bottom survey date recorded."])
    else:
        check("Bottom survey (36-month limit)",
              [f"Overdue since {hull['due_by']}"] if hull["days_left"] < 0 else [],
              [f"Due by {hull['due_by']} ({hull['days_left']} days)"] if 0 <= hull["days_left"] <= 180 else [])

    aboard = crew_alerts(session, on_board(session, vessel.vessel_id))
    gaps = manning_gaps(session, vessel.vessel_id, aboard)
    check("Minimum crew on board", [f"{g['rank']}: {g['on_board']} of {g['required']}" for g in gaps])
    check("Crew certificates and MLC limits",
          [f"{r['name']} ({r['rank']}): {a['text']}" for r in aboard for a in r["alerts"] if a["level"] == "BLOCK"],
          [f"{r['name']} ({r['rank']}): {a['text']}" for r in aboard for a in r["alerts"] if a["level"] == "WARN"])

    jobs = maintenance(session, vessel.vessel_id)
    check("Critical equipment (ISM 10.3)",
          [f"{j['equipment']}: {'open defect' if j['kind'] == 'DEFECT' else 'overdue: ' + j['title']}" for j in jobs
           if j["critical"] and j["state"] in ("OPEN", "OVERDUE")],
          [f"{j['equipment']}: {j['title']} due {j['due_on'] or ''}".strip() for j in jobs if j["critical"] and j["state"] == "DUE_SOON"]
          + [f"{j['equipment']}: repeat failures" for j in jobs if j["repeat_failure"] and j["state"] == "OPEN"])

    blocking = [c for c in checks if not c["ok"]]
    return {"vessel_id": vessel.vessel_id, "name": vessel.name, "ready": not blocking, "blocking": len(blocking),
            "warnings": sum(len(c["warnings"]) for c in checks), "checks": checks}


# ---------------- Planner ----------------


def planner(session: Session, horizon_days: int = 365) -> list[dict]:
    """For each vessel over the next year: contracts, the bottom-survey deadline, certificate expiries,
    crew reliefs, idle days with their running cost, and a suggestion where the timing clashes."""
    today = date.today()
    end = today + timedelta(days=horizon_days)
    contracts = session.scalars(select(Contract).where(Contract.status == "ACTIVE", Contract.end_date >= today.isoformat())).all()
    out = []
    for v in session.scalars(select(Vessel).order_by(Vessel.vessel_type, Vessel.name)):
        mine = sorted((c for c in contracts if c.vessel_id == v.vessel_id), key=lambda c: c.start_date)
        events = [{"type": "CONTRACT", "label": f"{c.client} ({c.contract_no})", "from": max(c.start_date, today.isoformat()), "to": c.end_date} for c in mine]
        booked = set()
        for c in mine:
            day = max(_d(c.start_date), today)
            while day <= min(_d(c.end_date), end):
                booked.add(day)
                day += timedelta(days=1)
        idle_days = [today + timedelta(days=i) for i in range(180) if today + timedelta(days=i) not in booked]
        hull = bottom_survey(v)
        if hull["due_by"] and hull["due_by"] <= end.isoformat():
            events.append({"type": "DRYDOCK_DUE", "label": "Bottom survey due (36 months)", "from": hull["due_by"], "to": hull["due_by"]})
        for c in session.scalars(select(Certificate).where(Certificate.vessel_id == v.vessel_id)):
            if c.expires_on <= end.isoformat():
                events.append({"type": "CERT_EXPIRY", "label": f"{c.name} expires", "from": c.expires_on, "to": c.expires_on})
        reliefs = session.scalars(select(Assignment).where(Assignment.vessel_id == v.vessel_id, Assignment.signed_off.is_(None),
                                                           Assignment.relief_due <= (today + timedelta(days=30)).isoformat())).all()
        # Suggestion: the clash that matters most first.
        suggestion = None
        first_free = min(idle_days) if idle_days else None
        if v.status == "DRY_DOCK":
            suggestion = "In dry dock now: record the bottom survey date when it is done, then line up the next charter."
        elif hull["days_left"] is not None and hull["days_left"] < 0:
            suggestion = f"Bottom survey overdue since {hull['due_by']}: dock now or agree an in-water survey with class."
        elif hull["due_by"] and any(c.start_date <= hull["due_by"] <= c.end_date for c in mine):
            c = next(c for c in mine if c.start_date <= hull["due_by"] <= c.end_date)
            suggestion = (f"Bottom survey falls due on {hull['due_by']}, during contract {c.contract_no}. "
                          "Plan a docking break with the client, or an in-water survey if class accepts it.")
        elif hull["due_by"] and first_free and first_free.isoformat() <= hull["due_by"] and hull["days_left"] <= 365:
            suggestion = f"Free from {first_free.isoformat()}, before the bottom survey is due ({hull['due_by']}): a good window to dry dock."
        elif idle_days and len(idle_days) >= 30 and v.status != "DRY_DOCK":
            suggestion = f"No contract for {len(idle_days)} of the next 180 days from {first_free.isoformat()}: line up the next charter."
        out.append({
            "vessel_id": v.vessel_id, "name": v.name, "vessel_type": v.vessel_type, "status": v.status,
            "contract_end": mine[-1].end_date if mine else None,
            "idle_days_180": len(idle_days), "idle_cost_180": round(len(idle_days) * v.daily_opex, 2),
            "bottom_survey_due": hull["due_by"], "reliefs_30d": len(reliefs),
            "events": sorted(events, key=lambda e: e["from"]), "suggestion": suggestion,
        })
    return out
