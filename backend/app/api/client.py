"""The client portal: a client's representative sees the daily reports for their own contracts and signs (or
disputes) the monthly timesheet before the hire invoice is approved.

A client account only ever sees contracts whose client name matches its own (users.client_name).
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import audit, role_in
from ..core.billing import month_days, month_hire
from ..core.tracking import iso, utc_now
from ..db import get_session
from ..models import Contract, DailyReport, Timesheet, User, Vessel
from ..schemas import TimesheetDecisionIn
from .fleet import today

client_only = role_in("client")
router = APIRouter(prefix="/api/client", tags=["client portal"])


def own_contract(session: Session, user: User, contract_no: str) -> Contract:
    c = session.get(Contract, contract_no)
    # The same answer for "not yours" and "does not exist", so a client cannot probe other clients' contracts.
    if c is None or user.role != "admin" and c.client != user.client_name:
        raise HTTPException(404, "Contract not found.")
    return c


@router.get("/contracts")
def my_contracts(user: User = Depends(client_only), session: Session = Depends(get_session)):
    q = select(Contract).order_by(Contract.start_date.desc())
    if user.role != "admin":
        q = q.where(Contract.client == user.client_name)
    names = {v.vessel_id: v.name for v in session.scalars(select(Vessel))}
    return [{"contract_no": c.contract_no, "vessel_name": names[c.vessel_id], "scope": c.scope, "start_date": c.start_date,
             "end_date": c.end_date, "status": c.status} for c in session.scalars(q)]


@router.get("/timesheet")
def timesheet(contract_no: str, period: str, user: User = Depends(client_only), session: Session = Depends(get_session)):
    c = own_contract(session, user, contract_no)
    days = [d for d in month_days(period) if c.start_date <= d <= c.end_date]
    reports = session.scalars(select(DailyReport).where(DailyReport.contract_no == c.contract_no)).all()
    rows = [{"on_date": r.on_date, "location": r.location, "operating_hrs": r.operating_hrs, "standby_hrs": r.standby_hrs,
             "weather_hrs": r.weather_hrs, "breakdown_hrs": r.breakdown_hrs, "transit_hrs": r.transit_hrs, "work_done": r.work_done,
             "dive_hrs": r.dive_hrs} for r in sorted(reports, key=lambda r: r.on_date) if r.on_date in days and r.status == "APPROVED"]
    calc = month_hire(c, reports, period)
    sheet = session.scalars(select(Timesheet).where(Timesheet.contract_no == c.contract_no, Timesheet.period == period)).first()
    return {"contract_no": c.contract_no, "period": period, "rows": rows, "hours": calc["hours"], "missing_dates": calc["missing_dates"],
            "pending_dates": calc["pending_dates"], "lines": calc["lines"], "amount": calc["amount"],
            "signoff": {"status": sheet.status, "by": sheet.by, "at": sheet.at, "note": sheet.note} if sheet else None}


@router.post("/timesheet")
def decide(body: TimesheetDecisionIn, user: User = Depends(client_only), session: Session = Depends(get_session)):
    c = own_contract(session, user, body.contract_no)
    if body.period >= today()[:7]:
        raise HTTPException(409, "A month can be signed once it has ended.")
    calc = month_hire(c, session.scalars(select(DailyReport).where(DailyReport.contract_no == c.contract_no)).all(), body.period)
    if not calc["contract_days"]:
        raise HTTPException(409, "The contract did not run in that month.")
    if calc["pending_dates"]:
        raise HTTPException(409, "Some daily reports for that month are still being checked by SEAMEC; try again once they are approved.")
    if body.decision == "DISPUTED" and not body.note.strip():
        raise HTTPException(422, "Say what is disputed, so SEAMEC can correct it.")
    sheet = session.scalars(select(Timesheet).where(Timesheet.contract_no == c.contract_no, Timesheet.period == body.period)).first()
    if sheet and sheet.status == "SIGNED":
        raise HTTPException(409, "This timesheet is already signed.")
    if sheet is None:
        sheet = Timesheet(contract_no=c.contract_no, period=body.period, status=body.decision, by=user.name, at=iso(utc_now()))
        session.add(sheet)
    sheet.status, sheet.by, sheet.at, sheet.note = body.decision, user.name, iso(utc_now()), body.note.strip()
    audit(session, user, f"timesheet.{body.decision.lower()}", f"contract {c.contract_no}", f"{body.period}: {body.note.strip()}")
    session.commit()
    return {"status": sheet.status, "by": sheet.by, "at": sheet.at, "note": sheet.note}
