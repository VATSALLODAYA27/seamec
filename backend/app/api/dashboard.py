"""The fleet control tower: what every vessel is doing and earning this month, and what needs attention."""
from collections import defaultdict
from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import manager, staff
from ..core.billing import add_days, month_hire
from ..db import get_session
from ..models import AuditEntry, Certificate, Contract, DailyReport, HireInvoice, Vessel
from .fleet import ATTENTION, INVALID, cert_out, days_left, today

router = APIRouter(prefix="/api", tags=["dashboard"], dependencies=[Depends(staff)])


@router.get("/dashboard")
def dashboard(session: Session = Depends(get_session)):
    now = today()
    period = now[:7]
    elapsed = max(date.today().day - 1, 1)  # whole days so far this month; today's reports are not in yet
    vessels = session.scalars(select(Vessel).order_by(Vessel.vessel_type, Vessel.name)).all()
    contracts = session.scalars(select(Contract).where(Contract.status == "ACTIVE")).all()
    reports = session.scalars(select(DailyReport)).all()
    by_vessel = defaultdict(list)  # grouped once, instead of scanning every report for every vessel
    for r in reports:
        by_vessel[r.vessel_id].append(r)

    rows = []
    for v in vessels:
        mine = by_vessel[v.vessel_id]
        contract = next((c for c in contracts if c.vessel_id == v.vessel_id and c.start_date <= now <= c.end_date), None)
        revenue = 0.0
        paid_hrs = 0.0
        if contract:
            calc = month_hire(contract, [r for r in mine if r.contract_no == contract.contract_no], period)
            revenue = calc["amount"]
            h = calc["hours"]
            paid_hrs = h["operating"] + h["standby"] + h["breakdown_paid"]
        last = max((r.on_date for r in mine), default=None)
        week = {add_days(now, -i) for i in range(1, 8)}
        missing = len(week - {r.on_date for r in mine}) if contract else 0
        opex = v.daily_opex * elapsed
        rows.append({
            "vessel_id": v.vessel_id, "name": v.name, "vessel_type": v.vessel_type, "status": v.status,
            "client": contract.client if contract else None, "contract_no": contract.contract_no if contract else None,
            "revenue_mtd": round(revenue, 2), "opex_mtd": round(opex, 2), "pnl_mtd": round(revenue - opex, 2),
            "utilisation": round(100 * paid_hrs / (elapsed * 24), 1), "last_report": last, "missing_reports_7d": missing,
        })

    certs = [cert_out(c) for c in session.scalars(select(Certificate).order_by(Certificate.expires_on))]
    names = {v.vessel_id: v.name for v in vessels}
    severity = {"EXPIRED": 0, "SURVEY_OVERDUE": 1, "EXPIRING": 2, "SURVEY_DUE": 3}
    cert_alerts = sorted(({**c, "vessel_name": names[c["vessel_id"]]} for c in certs if c["state"] != "VALID"),
                         key=lambda c: (severity[c["state"]], c["expires_on"]))
    pending = sorted((r for r in reports if r.status == "SUBMITTED"), key=lambda r: r.on_date)
    open_invoices = session.scalars(select(HireInvoice).where(HireInvoice.status == "APPROVED")).all()
    ending = sorted((c for c in contracts if days_left(c.end_date) <= 90), key=lambda c: c.end_date)
    bg_expiring = [c for c in contracts if c.bg_expiry and days_left(c.bg_expiry) <= 60]

    return {
        "period": period,
        "days_elapsed": elapsed,
        "kpis": {
            "vessels": len(vessels),
            "on_hire": sum(v.status == "ON_HIRE" for v in vessels),
            "dry_dock": sum(v.status == "DRY_DOCK" for v in vessels),
            "utilisation": round(sum(r["utilisation"] for r in rows) / max(len(rows), 1), 1),
            "revenue_mtd": round(sum(r["revenue_mtd"] for r in rows), 2),
            "pnl_mtd": round(sum(r["pnl_mtd"] for r in rows), 2),
            "receivables": round(sum(i.total for i in open_invoices), 2),
            "overdue": round(sum(i.total for i in open_invoices if days_left(i.due_date) < 0), 2),
            "reports_pending": len(pending),
            "certs_expired": sum(c["state"] in INVALID for c in certs),  # expired, or annual survey missed
            "certs_expiring": sum(c["state"] in ATTENTION for c in certs),  # expiring soon, or survey window open
        },
        "fleet": rows,
        "cert_alerts": cert_alerts[:10],
        "pending_reports": [{"id": r.id, "vessel_id": r.vessel_id, "vessel_name": names[r.vessel_id], "on_date": r.on_date} for r in pending[:10]],
        "contracts_ending": [{"contract_no": c.contract_no, "vessel_name": names[c.vessel_id], "client": c.client, "end_date": c.end_date,
                              "days_left": days_left(c.end_date)} for c in ending],
        "bg_expiring": [{"contract_no": c.contract_no, "bg_amount": c.bg_amount, "bg_expiry": c.bg_expiry, "days_left": days_left(c.bg_expiry)} for c in bg_expiring],
    }


@router.get("/audit", dependencies=[Depends(manager)])
def audit_log(session: Session = Depends(get_session)):
    rows = session.scalars(select(AuditEntry).order_by(AuditEntry.id.desc()).limit(500)).all()
    return [{"id": e.id, "at": e.at, "username": e.username, "role": e.role, "action": e.action, "target": e.target, "detail": e.detail} for e in rows]
