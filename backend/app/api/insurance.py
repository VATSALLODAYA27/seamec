"""Insurance policies (hull and machinery, P&I, crew, loss of hire) and claims on them.

A vessel needs hull and machinery and P&I cover in force to go on hire (charter parties require the owner to keep
both; see core/fleetops.readiness). A settled claim books the recovery against the vessel as a negative cost; the
repair itself is costed where it was paid (a purchase order, a dry dock).
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import audit, manager, staff
from ..core.supply import book_cost
from ..db import get_session
from ..models import InsuranceClaim, InsurancePolicy, User, Vessel, as_dict
from ..schemas import InsuranceClaimIn, InsuranceClaimUpdateIn, PolicyIn
from .fleet import days_left, get_or_404, today

router = APIRouter(prefix="/api/insurance", tags=["insurance"], dependencies=[Depends(staff)])

EXPIRY_WARN_DAYS = 45
REQUIRED = ("HM", "PI")  # cover a vessel must have in force to go on hire


def policy_state(p: InsurancePolicy) -> str:
    now = today()
    if p.start_date > now:
        return "FUTURE"
    if p.end_date < now:
        return "EXPIRED"
    return "EXPIRING" if days_left(p.end_date) <= EXPIRY_WARN_DAYS else "IN_FORCE"


def cover_gaps(policies: list[InsurancePolicy], vessel_id: str) -> tuple[list[str], list[str]]:
    """What is missing (blocks hire) and what is about to lapse (warning) for one vessel."""
    now = today()
    mine = [p for p in policies if p.vessel_id in (None, vessel_id) and p.start_date <= now <= p.end_date]
    label = {"HM": "Hull and machinery", "PI": "P&I"}
    missing = [f"No {label[k]} cover in force" for k in REQUIRED if not any(p.kind == k for p in mine)]
    lapsing = [f"{label.get(p.kind, p.kind)} ({p.insurer}) expires {p.end_date}" for p in mine
               if p.kind in REQUIRED and days_left(p.end_date) <= EXPIRY_WARN_DAYS
               and not any(q.kind == p.kind and q.vessel_id in (None, vessel_id) and q.start_date <= p.end_date < q.end_date and q.id != p.id for q in policies)]
    return missing, lapsing


@router.get("/policies")
def list_policies(session: Session = Depends(get_session)):
    names = {v.vessel_id: v.name for v in session.scalars(select(Vessel))}
    claims = session.scalars(select(InsuranceClaim)).all()
    out = []
    for p in session.scalars(select(InsurancePolicy).order_by(InsurancePolicy.end_date)):
        mine = [c for c in claims if c.policy_id == p.id]
        out.append({**as_dict(p), "vessel_name": names.get(p.vessel_id) if p.vessel_id else "Whole fleet", "state": policy_state(p),
                    "days_left": days_left(p.end_date), "open_claims": sum(c.status in ("NOTIFIED", "SUBMITTED") for c in mine)})
    return out


@router.post("/policies", status_code=201)
def create_policy(body: PolicyIn, user: User = Depends(manager), session: Session = Depends(get_session)):
    if body.vessel_id:
        get_or_404(session, Vessel, body.vessel_id, "Vessel")
    p = InsurancePolicy(**body.model_dump())
    session.add(p)
    audit(session, user, "policy.created", f"policy {body.policy_no}", f"{body.kind} {body.insurer} to {body.end_date}")
    session.commit()
    return as_dict(p)


@router.put("/policies/{policy_id}")
def update_policy(policy_id: int, body: PolicyIn, user: User = Depends(manager), session: Session = Depends(get_session)):
    p = get_or_404(session, InsurancePolicy, policy_id, "Policy")
    for k, v in body.model_dump().items():
        setattr(p, k, v)
    audit(session, user, "policy.updated", f"policy {p.policy_no}")
    session.commit()
    return as_dict(p)


@router.get("/claims")
def list_claims(session: Session = Depends(get_session)):
    names = {v.vessel_id: v.name for v in session.scalars(select(Vessel))}
    policies = {p.id: p for p in session.scalars(select(InsurancePolicy))}
    out = []
    for c in session.scalars(select(InsuranceClaim).order_by(InsuranceClaim.incident_on.desc())):
        p = policies[c.policy_id]
        out.append({**as_dict(c), "vessel_name": names[c.vessel_id], "policy_no": p.policy_no, "kind": p.kind, "insurer": p.insurer,
                    "deductible": p.deductible, "expected_recovery": round(max(c.amount - p.deductible, 0), 2)})
    return out


@router.post("/claims", status_code=201)
def create_claim(body: InsuranceClaimIn, user: User = Depends(manager), session: Session = Depends(get_session)):
    p = get_or_404(session, InsurancePolicy, body.policy_id, "Policy")
    get_or_404(session, Vessel, body.vessel_id, "Vessel")
    if p.vessel_id not in (None, body.vessel_id):
        raise HTTPException(422, "That policy does not cover this vessel.")
    if not p.start_date <= body.incident_on <= p.end_date:
        raise HTTPException(422, f"The policy did not cover {body.incident_on} ({p.start_date} to {p.end_date}).")
    if body.incident_on > today():
        raise HTTPException(422, "The incident date cannot be in the future.")
    c = InsuranceClaim(**body.model_dump(), created_by=user.username)
    session.add(c)
    audit(session, user, "insclaim.notified", f"vessel {body.vessel_id}", f"{p.kind} {p.policy_no}: {body.amount:,.0f}")
    session.commit()
    return as_dict(c)


@router.post("/claims/{claim_id}/status")
def update_claim(claim_id: int, body: InsuranceClaimUpdateIn, user: User = Depends(manager), session: Session = Depends(get_session)):
    c = get_or_404(session, InsuranceClaim, claim_id, "Claim")
    allowed = {"NOTIFIED": ("SUBMITTED", "REJECTED"), "SUBMITTED": ("SETTLED", "REJECTED")}
    if body.status not in allowed.get(c.status, ()):
        raise HTTPException(409, f"A {c.status.lower()} claim cannot become {body.status.lower()}.")
    if body.on > today() or body.on < c.incident_on:
        raise HTTPException(422, "The date must be between the incident and today.")
    if body.status == "SETTLED":
        if body.recovered is None or body.recovered > c.amount:
            raise HTTPException(422, "Give the amount recovered (no more than the amount claimed).")
        c.recovered, c.settled_on = body.recovered, body.on
        if body.recovered:
            book_cost(session, c.vessel_id, body.on, "INSURANCE", -body.recovered, f"Insurance recovery: {c.description[:80]}", "INSURANCE", f"claim {c.id}", user)
    c.status = body.status
    audit(session, user, f"insclaim.{body.status.lower()}", f"vessel {c.vessel_id}", f"claim {c.id}")
    session.commit()
    return as_dict(c)


def expiring(session: Session) -> list[dict]:
    """Policies lapsing soon with no renewal on file, for the dashboard."""
    policies = session.scalars(select(InsurancePolicy)).all()
    now = date.today().isoformat()
    out = []
    for p in policies:
        if p.start_date <= now <= p.end_date and days_left(p.end_date) <= EXPIRY_WARN_DAYS and not any(
                q.kind == p.kind and q.vessel_id == p.vessel_id and q.start_date <= p.end_date < q.end_date and q.id != p.id for q in policies):
            out.append({"id": p.id, "kind": p.kind, "insurer": p.insurer, "end_date": p.end_date, "days_left": days_left(p.end_date)})
    return out
