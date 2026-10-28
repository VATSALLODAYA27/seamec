"""Ship security under the ISPS Code: when drills and exercises fall due, and what to warn about.

- Drills: at least once every 3 months (ISPS Code Part B, 13.6).
- Exercises: at least once each calendar year, with no more than 18 months between them (Part B, 13.7).
  So the next exercise is due by the earlier of 31 December of the following year and 18 months after the last.
- Security level 1 is normal; 2 (heightened) and 3 (exceptional) are set by the flag state or port and are flagged.
"""
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..api.fleet import add_months
from ..models import SecurityCamera, SecurityDrill, SecurityIncident, Vessel, VesselSecurity

DRILL_MONTHS = 3
EXERCISE_MAX_MONTHS = 18
DUE_SOON_DAYS = 30


def _state(due: date | None, today: date) -> str:
    if due is None or due < today:
        return "OVERDUE"  # never done counts as overdue
    return "DUE_SOON" if (due - today).days <= DUE_SOON_DAYS else "OK"


def drill_due(drills: list[SecurityDrill], today: date | None = None) -> dict:
    """Last drill and exercise, when the next of each is due, and how that stands today."""
    today = today or date.today()
    last_drill = max((d.on_date for d in drills if d.kind == "DRILL"), default=None)
    last_ex = max((d.on_date for d in drills if d.kind == "EXERCISE"), default=None)
    drill_by = add_months(date.fromisoformat(last_drill), DRILL_MONTHS) if last_drill else None
    ex_by = None
    if last_ex:
        last = date.fromisoformat(last_ex)
        ex_by = min(date(last.year + 1, 12, 31), add_months(last, EXERCISE_MAX_MONTHS))
    return {
        "drill": {"last": last_drill, "due": drill_by.isoformat() if drill_by else None, "state": _state(drill_by, today)},
        "exercise": {"last": last_ex, "due": ex_by.isoformat() if ex_by else None, "state": _state(ex_by, today)},
    }


def vessel_security(session: Session, vessel: Vessel) -> dict:
    sec = session.get(VesselSecurity, vessel.vessel_id)
    drills = session.scalars(select(SecurityDrill).where(SecurityDrill.vessel_id == vessel.vessel_id)).all()
    cameras = session.scalars(select(SecurityCamera).where(SecurityCamera.vessel_id == vessel.vessel_id)).all()
    open_incidents = session.scalars(select(SecurityIncident).where(SecurityIncident.vessel_id == vessel.vessel_id,
                                                                    SecurityIncident.status == "OPEN")).all()
    return {
        "vessel_id": vessel.vessel_id, "name": vessel.name, "level": sec.level if sec else 1, "sso": sec.sso if sec else "",
        "set_on": sec.set_on if sec else "", **drill_due(drills),
        "cameras": len(cameras), "cameras_down": [c.name for c in cameras if c.status != "WORKING"],
        "open_incidents": len(open_incidents), "open_high": sum(i.severity == "HIGH" for i in open_incidents),
    }


def security_warnings(session: Session, vessel: Vessel) -> list[str]:
    """For hire readiness: nothing here stops hire, but each is worth a look before the vessel goes."""
    s = vessel_security(session, vessel)
    out = []
    if s["level"] > 1:
        out.append(f"Security level {s['level']} in force")
    for kind, label in (("drill", "Security drill (every 3 months)"), ("exercise", "Security exercise (yearly)")):
        d = s[kind]
        if d["state"] == "OVERDUE":
            out.append(f"{label}: {'overdue since ' + d['due'] if d['due'] else 'none recorded'}")
    if s["cameras_down"]:
        out.append(f"Cameras not working: {', '.join(s['cameras_down'])}")
    if s["open_high"]:
        out.append(f"{s['open_high']} open high-severity security incident{'s' if s['open_high'] > 1 else ''}")
    return out
