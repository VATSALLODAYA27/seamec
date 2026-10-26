"""Maintenance, crew rotation, hire readiness and the planner. The rules live in core/fleetops.py."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import audit, manager, staff
from ..core.fleetops import (MLC_MAX_MONTHS, crew_alerts, maintenance, manning_gaps, on_board, planner, readiness)
from ..db import get_session
from ..models import Assignment, CrewCertificate, CrewMember, Equipment, MaintenanceJob, User, Vessel, as_dict
from ..schemas import AssignIn, CloseDefectIn, HoursIn, JobDoneIn, SignOffIn
from .fleet import add_months, get_or_404, today

router = APIRouter(prefix="/api", tags=["fleet operations"], dependencies=[Depends(staff)])


# ---------------- Maintenance ----------------


@router.get("/maintenance")
def list_jobs(vessel: str | None = None, session: Session = Depends(get_session)):
    return maintenance(session, vessel)


@router.get("/equipment")
def list_equipment(vessel: str | None = None, session: Session = Depends(get_session)):
    q = select(Equipment).order_by(Equipment.vessel_id, Equipment.system, Equipment.name)
    if vessel:
        q = q.where(Equipment.vessel_id == vessel)
    return [as_dict(e) for e in session.scalars(q)]


@router.post("/equipment/{equipment_id}/hours")
def record_hours(equipment_id: int, body: HoursIn, user: User = Depends(staff), session: Session = Depends(get_session)):
    e = get_or_404(session, Equipment, equipment_id, "Equipment")
    if body.hours < e.running_hours:
        raise HTTPException(422, f"A running-hours counter only goes up; the last reading was {e.running_hours:g}.")
    e.running_hours, e.hours_updated_on = body.hours, today()
    audit(session, user, "equipment.hours", f"equipment {e.id}", f"{e.name}: {body.hours:g} h")
    session.commit()
    return as_dict(e)


@router.post("/maintenance/jobs/{job_id}/done")
def job_done(job_id: int, body: JobDoneIn, user: User = Depends(staff), session: Session = Depends(get_session)):
    job = get_or_404(session, MaintenanceJob, job_id, "Job")
    if job.kind != "PLANNED":
        raise HTTPException(409, "A defect is closed, not marked done.")
    if body.on > today():
        raise HTTPException(422, "The date cannot be in the future.")
    e = session.get(Equipment, job.equipment_id)
    job.last_done_on, job.last_done_hours = body.on, body.hours if body.hours is not None else e.running_hours
    audit(session, user, "maintenance.done", f"job {job.id}", f"{e.name}: {job.title}")
    session.commit()
    return as_dict(job)


@router.post("/maintenance/jobs/{job_id}/close")
def close_defect(job_id: int, body: CloseDefectIn, user: User = Depends(staff), session: Session = Depends(get_session)):
    job = get_or_404(session, MaintenanceJob, job_id, "Job")
    if job.kind != "DEFECT" or job.status != "OPEN":
        raise HTTPException(409, "Only an open defect can be closed.")
    job.status, job.closed_on, job.note = "CLOSED", today(), body.note.strip()
    audit(session, user, "defect.closed", f"job {job.id}", body.note.strip())
    session.commit()
    return as_dict(job)


# ---------------- Crew ----------------


@router.get("/crew/onboard")
def crew_on_board(vessel: str | None = None, session: Session = Depends(get_session)):
    rows = crew_alerts(session, on_board(session, vessel))
    vessels = [vessel] if vessel else [v.vessel_id for v in session.scalars(select(Vessel))]
    gaps = {vid: manning_gaps(session, vid, [r for r in rows if r["vessel_id"] == vid]) for vid in vessels}
    return {"crew": rows, "gaps": {k: v for k, v in gaps.items() if v}}


@router.get("/crew")
def list_crew(session: Session = Depends(get_session)):
    """Everyone, with where they are now and their certificates: who is free to send as a relief."""
    aboard = {a.crew_id: a for a in on_board(session)}
    certs: dict[int, list] = {}
    for c in session.scalars(select(CrewCertificate)):
        certs.setdefault(c.crew_id, []).append({"name": c.name, "expires_on": c.expires_on})
    out = []
    for p in session.scalars(select(CrewMember).where(CrewMember.active).order_by(CrewMember.rank, CrewMember.name)):
        a = aboard.get(p.id)
        out.append({"id": p.id, "name": p.name, "rank": p.rank, "on_board": a.vessel_id if a else None,
                    "certificates": sorted(certs.get(p.id, []), key=lambda c: c["expires_on"])})
    return out


@router.post("/crew/assignments", status_code=201)
def assign(body: AssignIn, user: User = Depends(manager), session: Session = Depends(get_session)):
    person = get_or_404(session, CrewMember, body.crew_id, "Crew member")
    get_or_404(session, Vessel, body.vessel_id, "Vessel")
    if body.relief_due <= body.sign_on:
        raise HTTPException(422, "The relief date must be after the sign-on date.")
    limit = add_months(date.fromisoformat(body.sign_on), MLC_MAX_MONTHS).isoformat()
    if body.relief_due > limit:
        raise HTTPException(422, f"Planned relief is after the 11-month MLC limit ({limit}).")
    busy = session.scalars(select(Assignment).where(Assignment.crew_id == person.id, Assignment.signed_off.is_(None),
                                                    Assignment.relief_due >= body.sign_on)).first()
    if busy:
        raise HTTPException(409, f"{person.name} is already assigned to {busy.vessel_id} until {busy.relief_due}.")
    lapsing = [c for c in session.scalars(select(CrewCertificate).where(CrewCertificate.crew_id == person.id)) if c.expires_on < body.relief_due]
    if lapsing:
        raise HTTPException(409, f"{person.name}'s {', '.join(f'{c.name} (expires {c.expires_on})' for c in lapsing)} would lapse on board. Renew first.")
    a = Assignment(crew_id=person.id, vessel_id=body.vessel_id, sign_on=body.sign_on, relief_due=body.relief_due)
    session.add(a)
    audit(session, user, "crew.assigned", f"vessel {body.vessel_id}", f"{person.name} ({person.rank}) {body.sign_on} to {body.relief_due}")
    session.commit()
    return as_dict(a)


@router.post("/crew/assignments/{assignment_id}/sign-off")
def sign_off(assignment_id: int, body: SignOffIn, user: User = Depends(manager), session: Session = Depends(get_session)):
    a = get_or_404(session, Assignment, assignment_id, "Assignment")
    if a.signed_off:
        raise HTTPException(409, "Already signed off.")
    if body.on < a.sign_on or body.on > today():
        raise HTTPException(422, "The sign-off date must be between sign-on and today.")
    a.signed_off = body.on
    person = session.get(CrewMember, a.crew_id)
    audit(session, user, "crew.signed_off", f"vessel {a.vessel_id}", f"{person.name} on {body.on}")
    session.commit()
    return as_dict(a)


# ---------------- Readiness and planner ----------------


@router.get("/readiness")
def all_readiness(session: Session = Depends(get_session)):
    return [readiness(session, v) for v in session.scalars(select(Vessel).order_by(Vessel.vessel_type, Vessel.name))]


@router.get("/readiness/{vessel_id}")
def one_readiness(vessel_id: str, session: Session = Depends(get_session)):
    return readiness(session, get_or_404(session, Vessel, vessel_id, "Vessel"))


@router.get("/planner")
def get_planner(session: Session = Depends(get_session)):
    return planner(session)
