"""Vessels, their certificates, and charter contracts."""
import calendar
from collections import defaultdict
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select, tuple_
from sqlalchemy.orm import Session

from .. import config
from ..auth import admin, audit, manager, staff
from ..core.tracking import age_hours, iso, report_time, utc_now
from ..db import get_session
from ..models import Certificate, Contract, DailyReport, HireInvoice, PositionFix, User, Vessel, as_dict
from ..schemas import CertificateRenewIn, ContractIn, EndorseIn

router = APIRouter(prefix="/api", tags=["fleet"], dependencies=[Depends(staff)])

EXPIRY_WARN_DAYS = 60
SURVEY_WINDOW_MONTHS = 3  # HSSC: annual survey within 3 months before or after each anniversary date


def today() -> str:
    return date.today().isoformat()


def days_left(iso_day: str) -> int:
    return (date.fromisoformat(iso_day) - date.today()).days


def add_months(day: date, n: int) -> date:
    y, m = divmod(day.month - 1 + n, 12)
    y, m = day.year + y, m + 1
    return date(y, m, min(day.day, calendar.monthrange(y, m)[1]))


def survey(c: Certificate) -> dict:
    """Where the certificate stands on its annual surveys.

    Under the IMO harmonized system (HSSC) the anniversary date is the day and month of the expiry date, and each
    annual survey must be done within 3 months either side of it. A certificate whose survey was missed is no
    longer valid. `endorsed_on` is the latest annual endorsement; anniversaries before it count as done.
    """
    none = {"survey": None, "survey_from": None, "survey_to": None}
    if not c.annual_survey:
        return none
    expiry, issued, now = date.fromisoformat(c.expires_on), date.fromisoformat(c.issued_on), date.today()
    endorsed = date.fromisoformat(c.endorsed_on) if c.endorsed_on else None
    anniversaries = sorted(a for k in range(1, 5) if (a := add_months(expiry, -12 * k)) > issued)
    for a in anniversaries:
        start, end = add_months(a, -SURVEY_WINDOW_MONTHS), add_months(a, SURVEY_WINDOW_MONTHS)
        if endorsed and endorsed >= start:
            continue  # this anniversary's survey is done
        state = "UPCOMING" if now < start else "DUE" if now <= end else "OVERDUE"
        return {"survey": state, "survey_from": start.isoformat(), "survey_to": end.isoformat()}
    return none  # no annual survey left before expiry; the renewal survey is next


def cert_out(c: Certificate) -> dict:
    left = days_left(c.expires_on)
    s = survey(c)
    # Most serious first: a lapsed certificate, then one about to lapse, then a survey window that is open.
    if left < 0:
        state = "EXPIRED"
    elif s["survey"] == "OVERDUE":
        state = "SURVEY_OVERDUE"
    elif left <= EXPIRY_WARN_DAYS:
        state = "EXPIRING"
    elif s["survey"] == "DUE":
        state = "SURVEY_DUE"
    else:
        state = "VALID"
    return {**as_dict(c), **s, "days_left": left, "state": state}


INVALID = ("EXPIRED", "SURVEY_OVERDUE")  # the certificate no longer counts
ATTENTION = ("EXPIRING", "SURVEY_DUE")


def active_contract(session: Session, vessel_id: str, on: str | None = None) -> Contract | None:
    on = on or today()
    return session.scalars(
        select(Contract).where(Contract.vessel_id == vessel_id, Contract.status == "ACTIVE", Contract.start_date <= on, Contract.end_date >= on)
    ).first()


def _position(lat, lon, at, source, label) -> dict:
    age = age_hours(at)
    return {"lat": lat, "lon": lon, "at": at, "on_date": at[:10], "source": source, "label": label,
            "age_hours": age, "stale": age > config.POSITION_STALE_HOURS}


def positions(session: Session) -> dict[str, dict]:
    """Each vessel's last known position: the newest of its latest report position and latest VSAT/AIS fix,
    else its base port."""
    out = {}
    for v in session.scalars(select(Vessel)):
        if v.base_lat is not None:
            out[v.vessel_id] = {"lat": v.base_lat, "lon": v.base_lon, "at": None, "on_date": None, "source": "BASE",
                                "label": v.base_port, "age_hours": None, "stale": False}

    has_pos = (DailyReport.lat.is_not(None), DailyReport.status != "REJECTED")
    newest_report = select(DailyReport.vessel_id, func.max(DailyReport.on_date)).where(*has_pos).group_by(DailyReport.vessel_id)
    candidates = defaultdict(list)
    for r in session.scalars(select(DailyReport).where(*has_pos, tuple_(DailyReport.vessel_id, DailyReport.on_date).in_(newest_report))):
        candidates[r.vessel_id].append(_position(r.lat, r.lon, report_time(r.on_date), "REPORT", r.location))
    newest_fix = select(PositionFix.vessel_id, func.max(PositionFix.at)).group_by(PositionFix.vessel_id)
    for f in session.scalars(select(PositionFix).where(tuple_(PositionFix.vessel_id, PositionFix.at).in_(newest_fix))):
        speed = f", {f.sog:.1f} kn" if f.sog is not None else ""
        candidates[f.vessel_id].append(_position(f.lat, f.lon, f.at, f.source, f"{f.source} position{speed}"))
    for vessel_id, found in candidates.items():
        out[vessel_id] = max(found, key=lambda p: p["at"])
    return out


def track(session: Session, vessel_id: str, days: int = 30) -> list[dict]:
    """Where the vessel has been: report positions and automatic fixes, oldest first, at most one point per 3 hours."""
    since = iso(utc_now() - timedelta(days=days))
    points = [{"lat": r.lat, "lon": r.lon, "at": report_time(r.on_date)} for r in session.scalars(
        select(DailyReport).where(DailyReport.vessel_id == vessel_id, DailyReport.lat.is_not(None), DailyReport.status != "REJECTED",
                                  DailyReport.on_date >= since[:10]))]
    points += [{"lat": f.lat, "lon": f.lon, "at": f.at} for f in session.scalars(
        select(PositionFix).where(PositionFix.vessel_id == vessel_id, PositionFix.at >= since))]
    thinned, last_slot = [], None
    for p in sorted(points, key=lambda p: p["at"]):
        slot = (p["at"][:10], int(p["at"][11:13]) // 3)
        if slot != last_slot:
            thinned.append(p)
            last_slot = slot
    return thinned


def get_or_404(session: Session, model, key, what: str):
    row = session.get(model, key)
    if row is None:
        raise HTTPException(404, f"{what} not found.")
    return row


@router.get("/vessels")
def list_vessels(session: Session = Depends(get_session)):
    now = today()
    certs = defaultdict(list)
    for c in session.scalars(select(Certificate)):
        certs[c.vessel_id].append(cert_out(c))
    contracts = {c.vessel_id: c for c in session.scalars(
        select(Contract).where(Contract.status == "ACTIVE", Contract.start_date <= now, Contract.end_date >= now))}
    where = positions(session)
    out = []
    for v in session.scalars(select(Vessel).order_by(Vessel.vessel_type, Vessel.name)):
        mine, contract = certs[v.vessel_id], contracts.get(v.vessel_id)
        out.append({
            **as_dict(v),
            "contract_no": contract.contract_no if contract else None,
            "client": contract.client if contract else None,
            "contract_end": contract.end_date if contract else None,
            "certs_expired": sum(c["state"] in INVALID for c in mine),
            "certs_expiring": sum(c["state"] in ATTENTION for c in mine),
            "position": where.get(v.vessel_id),
        })
    return out


@router.get("/vessels/{vessel_id}")
def vessel_detail(vessel_id: str, session: Session = Depends(get_session)):
    v = get_or_404(session, Vessel, vessel_id, "Vessel")
    certs = session.scalars(select(Certificate).where(Certificate.vessel_id == vessel_id).order_by(Certificate.expires_on)).all()
    contracts = session.scalars(select(Contract).where(Contract.vessel_id == vessel_id).order_by(Contract.start_date.desc())).all()
    reports = session.scalars(select(DailyReport).where(DailyReport.vessel_id == vessel_id).order_by(DailyReport.on_date.desc()).limit(31)).all()
    return {
        **as_dict(v),
        "certificates": [cert_out(c) for c in certs],
        "contracts": [as_dict(c) for c in contracts],
        "reports": [as_dict(r) for r in reports],
        "position": positions(session).get(vessel_id),
        "track": track(session, vessel_id),
    }


@router.get("/certificates")
def list_certificates(session: Session = Depends(get_session)):
    names = {v.vessel_id: v.name for v in session.scalars(select(Vessel))}
    rows = session.scalars(select(Certificate).order_by(Certificate.expires_on)).all()
    return [{**cert_out(c), "vessel_name": names[c.vessel_id]} for c in rows]


@router.post("/certificates/{cert_id}/renew")
def renew_certificate(cert_id: int, body: CertificateRenewIn, user: User = Depends(manager), session: Session = Depends(get_session)):
    c = get_or_404(session, Certificate, cert_id, "Certificate")
    old = c.expires_on
    c.issued_on, c.expires_on, c.endorsed_on = body.issued_on, body.expires_on, None  # a renewed certificate starts a new survey cycle
    audit(session, user, "certificate.renewed", f"vessel {c.vessel_id}", f"{c.name}: {old} -> {c.expires_on}")
    session.commit()
    return cert_out(c)


@router.post("/certificates/{cert_id}/endorse")
def endorse_certificate(cert_id: int, body: EndorseIn, user: User = Depends(manager), session: Session = Depends(get_session)):
    """Record an annual survey endorsement."""
    c = get_or_404(session, Certificate, cert_id, "Certificate")
    if body.on > today():
        raise HTTPException(422, "The survey date cannot be in the future.")
    if body.on < c.issued_on:
        raise HTTPException(422, "The survey date is before the certificate was issued.")
    c.endorsed_on = body.on
    audit(session, user, "certificate.endorsed", f"vessel {c.vessel_id}", f"{c.name}: annual survey {body.on}")
    session.commit()
    return cert_out(c)


def contract_out(c: Contract, vessel_names: dict, billed: float) -> dict:
    return {**as_dict(c), "vessel_name": vessel_names.get(c.vessel_id), "days_left": days_left(c.end_date), "billed": billed,
            "bg_days_left": days_left(c.bg_expiry) if c.bg_expiry else None}


@router.get("/contracts")
def list_contracts(session: Session = Depends(get_session)):
    names = {v.vessel_id: v.name for v in session.scalars(select(Vessel))}
    billed: dict[str, float] = {}
    for inv in session.scalars(select(HireInvoice).where(HireInvoice.status != "DRAFT")):
        billed[inv.contract_no] = billed.get(inv.contract_no, 0) + inv.amount
    rows = session.scalars(select(Contract).order_by(Contract.status, Contract.start_date.desc())).all()
    return [contract_out(c, names, round(billed.get(c.contract_no, 0), 2)) for c in rows]


@router.post("/contracts", status_code=201)
def create_contract(body: ContractIn, user: User = Depends(admin), session: Session = Depends(get_session)):
    vessel = get_or_404(session, Vessel, body.vessel_id, "Vessel")
    if session.get(Contract, body.contract_no):
        raise HTTPException(409, f"Contract {body.contract_no} already exists.")
    clash = session.scalars(
        select(Contract).where(Contract.vessel_id == body.vessel_id, Contract.status == "ACTIVE",
                               Contract.start_date <= body.end_date, Contract.end_date >= body.start_date)
    ).first()
    if clash:
        raise HTTPException(409, f"{vessel.name} is already on contract {clash.contract_no} ({clash.start_date} to {clash.end_date}).")
    critical = session.scalars(select(Certificate).where(Certificate.vessel_id == body.vessel_id, Certificate.critical)).all()
    expired = [c.name for c in critical if c.expires_on < body.start_date]
    unsurveyed = [c.name for c in critical if c.name not in expired and cert_out(c)["state"] == "SURVEY_OVERDUE"]
    if expired or unsurveyed:
        reasons = ([f"expired on the start date: {', '.join(expired)}"] if expired else []) + (
            [f"annual survey overdue: {', '.join(unsurveyed)}"] if unsurveyed else [])
        raise HTTPException(409, f"{vessel.name} cannot go on hire: {'; '.join(reasons)}.")
    contract = Contract(**body.model_dump(), created_by=user.username)
    session.add(contract)
    if body.start_date <= today() <= body.end_date:
        vessel.status = "ON_HIRE"
    audit(session, user, "contract.created", f"contract {contract.contract_no}", f"{vessel.name} for {body.client}")
    session.commit()
    return contract_out(contract, {vessel.vessel_id: vessel.name}, 0)


@router.post("/contracts/{contract_no}/complete")
def complete_contract(contract_no: str, user: User = Depends(manager), session: Session = Depends(get_session)):
    c = get_or_404(session, Contract, contract_no, "Contract")
    if c.status != "ACTIVE":
        raise HTTPException(409, "Only an active contract can be completed.")
    c.status = "COMPLETED"
    vessel = session.get(Vessel, c.vessel_id)
    if vessel.status == "ON_HIRE":
        vessel.status = "AVAILABLE"
    audit(session, user, "contract.completed", f"contract {contract_no}")
    session.commit()
    return as_dict(c)
