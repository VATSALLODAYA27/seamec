"""Ship security: the camera register, security incidents, drills and exercises, and each vessel's security level.

Vessel and office staff record camera checks, incidents and drills; a manager sets the security level and closes
incidents. The rules for when drills fall due are in core/security.py.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import audit, manager, staff
from ..core.security import vessel_security
from ..db import get_session
from ..models import SecurityCamera, SecurityDrill, SecurityIncident, User, Vessel, VesselSecurity, as_dict
from ..schemas import CameraCheckIn, CameraIn, DrillIn, IncidentCloseIn, IncidentIn, SecurityLevelIn
from .fleet import get_or_404, today

router = APIRouter(prefix="/api/security", tags=["security"], dependencies=[Depends(staff)])


@router.get("")
def overview(session: Session = Depends(get_session)):
    vessels = session.scalars(select(Vessel).order_by(Vessel.vessel_type, Vessel.name)).all()
    names = {v.vessel_id: v.name for v in vessels}
    cameras = session.scalars(select(SecurityCamera).order_by(SecurityCamera.vessel_id, SecurityCamera.name)).all()
    camera_names = {c.id: c.name for c in cameras}
    incidents = session.scalars(select(SecurityIncident).order_by(SecurityIncident.status.desc(), SecurityIncident.happened_at.desc())).all()
    drills = session.scalars(select(SecurityDrill).order_by(SecurityDrill.on_date.desc()).limit(300)).all()
    return {
        "vessels": [vessel_security(session, v) for v in vessels],
        "cameras": [{**as_dict(c), "vessel_name": names[c.vessel_id]} for c in cameras],
        "incidents": [{**as_dict(i), "vessel_name": names[i.vessel_id], "camera_name": camera_names.get(i.camera_id)} for i in incidents],
        "drills": [{**as_dict(d), "vessel_name": names[d.vessel_id]} for d in drills],
    }


# ---------------- Cameras ----------------


@router.post("/cameras", status_code=201)
def add_camera(body: CameraIn, user: User = Depends(staff), session: Session = Depends(get_session)):
    get_or_404(session, Vessel, body.vessel_id, "Vessel")
    cam = SecurityCamera(**body.model_dump(), checked_on=today())
    session.add(cam)
    audit(session, user, "camera.added", f"vessel {body.vessel_id}", body.name)
    session.commit()
    return as_dict(cam)


@router.put("/cameras/{camera_id}")
def edit_camera(camera_id: int, body: CameraIn, user: User = Depends(staff), session: Session = Depends(get_session)):
    cam = get_or_404(session, SecurityCamera, camera_id, "Camera")
    if body.vessel_id != cam.vessel_id:
        raise HTTPException(422, "A camera stays with its vessel; remove it and add it to the other vessel.")
    cam.name, cam.kind, cam.view_url, cam.note = body.name, body.kind, body.view_url, body.note
    audit(session, user, "camera.edited", f"vessel {cam.vessel_id}", cam.name)
    session.commit()
    return as_dict(cam)


@router.post("/cameras/{camera_id}/check")
def check_camera(camera_id: int, body: CameraCheckIn, user: User = Depends(staff), session: Session = Depends(get_session)):
    cam = get_or_404(session, SecurityCamera, camera_id, "Camera")
    if body.on > today():
        raise HTTPException(422, "The check date cannot be in the future.")
    cam.status, cam.checked_on, cam.note = body.status, body.on, body.note.strip() or cam.note
    audit(session, user, "camera.checked", f"vessel {cam.vessel_id}", f"{cam.name}: {body.status.lower()}")
    session.commit()
    return as_dict(cam)


@router.delete("/cameras/{camera_id}", status_code=204)
def remove_camera(camera_id: int, user: User = Depends(manager), session: Session = Depends(get_session)):
    cam = get_or_404(session, SecurityCamera, camera_id, "Camera")
    if session.scalars(select(SecurityIncident.id).where(SecurityIncident.camera_id == camera_id)).first():
        raise HTTPException(409, "An incident refers to this camera's footage; mark the camera offline instead.")
    session.delete(cam)
    audit(session, user, "camera.removed", f"vessel {cam.vessel_id}", cam.name)
    session.commit()


# ---------------- Incidents ----------------


@router.post("/incidents", status_code=201)
def log_incident(body: IncidentIn, user: User = Depends(staff), session: Session = Depends(get_session)):
    get_or_404(session, Vessel, body.vessel_id, "Vessel")
    if body.happened_at[:10] > today():
        raise HTTPException(422, "An incident cannot be in the future.")
    if body.camera_id is not None:
        cam = get_or_404(session, SecurityCamera, body.camera_id, "Camera")
        if cam.vessel_id != body.vessel_id:
            raise HTTPException(422, "That camera is on another vessel.")
    inc = SecurityIncident(**body.model_dump(), logged_by=user.username)
    session.add(inc)
    audit(session, user, "security.incident", f"vessel {body.vessel_id}", f"{body.severity} {body.kind}: {body.description[:80]}")
    session.commit()
    return as_dict(inc)


@router.post("/incidents/{incident_id}/close")
def close_incident(incident_id: int, body: IncidentCloseIn, user: User = Depends(manager), session: Session = Depends(get_session)):
    inc = get_or_404(session, SecurityIncident, incident_id, "Incident")
    if inc.status != "OPEN":
        raise HTTPException(409, "This incident is already closed.")
    inc.status, inc.closed_by, inc.closed_note = "CLOSED", user.username, body.note.strip()
    audit(session, user, "security.closed", f"vessel {inc.vessel_id}", body.note.strip())
    session.commit()
    return as_dict(inc)


# ---------------- Drills and security level ----------------


@router.post("/drills", status_code=201)
def record_drill(body: DrillIn, user: User = Depends(staff), session: Session = Depends(get_session)):
    get_or_404(session, Vessel, body.vessel_id, "Vessel")
    if body.on_date > today():
        raise HTTPException(422, "A drill is recorded once it has been held.")
    drill = SecurityDrill(**body.model_dump(), by=user.username)
    session.add(drill)
    audit(session, user, f"security.{body.kind.lower()}", f"vessel {body.vessel_id}", f"{body.on_date}: {body.scenario}")
    session.commit()
    return as_dict(drill)


@router.put("/vessels/{vessel_id}")
def set_level(vessel_id: str, body: SecurityLevelIn, user: User = Depends(manager), session: Session = Depends(get_session)):
    get_or_404(session, Vessel, vessel_id, "Vessel")
    sec = session.get(VesselSecurity, vessel_id) or VesselSecurity(vessel_id=vessel_id)
    sec.level, sec.sso, sec.set_on, sec.set_by = body.level, body.sso.strip(), today(), user.username
    session.merge(sec)
    audit(session, user, "security.level", f"vessel {vessel_id}", f"level {body.level}, SSO {body.sso.strip() or '-'}")
    session.commit()
    return as_dict(sec)
