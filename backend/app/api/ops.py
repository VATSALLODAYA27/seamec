"""Daily progress reports: filed by the vessel, approved by the office. Approved reports drive billing."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import audit, manager, staff
from ..db import get_session
from ..models import DailyReport, Equipment, MaintenanceJob, User, Vessel, as_dict
from ..schemas import DailyReportIn, ReasonIn
from .fleet import active_contract, get_or_404, today

router = APIRouter(prefix="/api/reports", tags=["operations"], dependencies=[Depends(staff)])

FUEL_ALERT_M3 = 25  # a day burning more than this is flagged for a look


def with_fuel(rows: list[DailyReport]) -> list[dict]:
    """Each report with the fuel it used: yesterday's fuel on board + received - today's fuel on board."""
    prev: dict[str, DailyReport] = {}
    out = {}
    for r in sorted(rows, key=lambda r: r.on_date):
        before = prev.get(r.vessel_id)
        used = round(before.fuel_rob + r.fuel_received - r.fuel_rob, 1) if before else None
        out[r.id] = {**as_dict(r), "fuel_used": used, "fuel_alert": used is not None and (used > FUEL_ALERT_M3 or used < 0)}
        prev[r.vessel_id] = r
    return [out[r.id] for r in rows]


@router.get("")
def list_reports(vessel: str | None = None, status: str | None = None, session: Session = Depends(get_session)):
    query = select(DailyReport).order_by(DailyReport.on_date.desc(), DailyReport.vessel_id)
    if vessel:
        query = query.where(DailyReport.vessel_id == vessel)
    rows = session.scalars(query).all()
    names = {v.vessel_id: v.name for v in session.scalars(select(Vessel))}
    out = [{**r, "vessel_name": names[r["vessel_id"]]} for r in with_fuel(rows)]
    return [r for r in out if not status or r["status"] == status]


@router.post("", status_code=201)
def file_report(body: DailyReportIn, user: User = Depends(staff), session: Session = Depends(get_session)):
    vessel = get_or_404(session, Vessel, body.vessel_id, "Vessel")
    if body.on_date > today():
        raise HTTPException(422, "A report cannot be filed for a future date.")
    existing = session.scalars(select(DailyReport).where(DailyReport.vessel_id == body.vessel_id, DailyReport.on_date == body.on_date)).first()
    if existing and body.client_ref and existing.client_ref == body.client_ref:
        return as_dict(existing)  # the same report sent again: already received
    if existing and existing.status != "REJECTED":
        raise HTTPException(409, f"{vessel.name} already has a report for {body.on_date}.")
    if existing:  # a rejected report is replaced by the corrected one, and so is any defect it raised
        for job in session.scalars(select(MaintenanceJob).where(MaintenanceJob.report_id == existing.id, MaintenanceJob.status == "OPEN")):
            session.delete(job)
        session.delete(existing)
        session.flush()
    equipment = None
    if body.breakdown_hrs > 0:
        has_register = session.scalars(select(Equipment.id).where(Equipment.vessel_id == body.vessel_id)).first() is not None
        if has_register and body.breakdown_equipment_id is None:
            raise HTTPException(422, "Say which equipment broke down, so a defect can be raised on it.")
        if body.breakdown_equipment_id is not None:
            equipment = session.get(Equipment, body.breakdown_equipment_id)
            if equipment is None or equipment.vessel_id != body.vessel_id:
                raise HTTPException(422, "That equipment is not on this vessel.")
    contract = active_contract(session, body.vessel_id, body.on_date)
    report = DailyReport(**body.model_dump(), contract_no=contract.contract_no if contract else None, submitted_by=user.username)
    if body.breakdown_hrs == 0:
        report.breakdown_equipment_id = None
    session.add(report)
    session.flush()
    if equipment:
        session.add(MaintenanceJob(equipment_id=equipment.id, kind="DEFECT", title=f"Breakdown {body.on_date}: {body.work_done[:80]}",
                                   raised_on=body.on_date, report_id=report.id, downtime_hrs=body.breakdown_hrs))
    audit(session, user, "report.filed", f"report {report.id}", f"{vessel.name} {body.on_date}")
    session.commit()
    return as_dict(report)


def decide(report_id: int, new_status: str, reason: str, user: User, session: Session) -> dict:
    r = get_or_404(session, DailyReport, report_id, "Report")
    if r.status != "SUBMITTED":
        raise HTTPException(409, f"This report is already {r.status.lower()}.")
    r.status, r.approved_by = new_status, user.username
    audit(session, user, f"report.{new_status.lower()}", f"report {r.id}", reason or f"{r.vessel_id} {r.on_date}")
    session.commit()
    return as_dict(r)


@router.post("/{report_id}/approve")
def approve(report_id: int, user: User = Depends(manager), session: Session = Depends(get_session)):
    return decide(report_id, "APPROVED", "", user, session)


@router.post("/{report_id}/reject")
def reject(report_id: int, body: ReasonIn, user: User = Depends(manager), session: Session = Depends(get_session)):
    if not body.reason.strip():
        raise HTTPException(422, "Give a reason, so the vessel knows what to correct.")
    return decide(report_id, "REJECTED", body.reason.strip(), user, session)
