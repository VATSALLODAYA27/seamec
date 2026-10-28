"""Tenders (bids, margin model, win-loss), off-hire events, and charterers' performance claims."""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import audit, manager, staff
from ..core.commercial import OFF_HIRE_REASONS, hours_by_day, straight_off_hire, tender_model, win_loss
from ..core.finance import now_minute
from ..db import get_session
from ..models import Contract, DailyReport, OffHireEvent, PerformanceClaim, Tender, User, Vessel, as_dict
from ..schemas import ClaimDecisionIn, ClaimIn, ContractIn, OffHireEndIn, OffHireIn, TenderIn, TenderOutcomeIn, TenderToContractIn
from .fleet import active_contract, get_or_404, new_contract, today

router = APIRouter(prefix="/api", tags=["commercial"], dependencies=[Depends(staff)])

CLAIM_RESPONSE_DAYS = 14  # answer a charterer's claim within two weeks


def straight_off(session: Session, contract_no: str) -> dict[str, float]:
    """Off-hire hours per day the maintenance allowance does not cover, for billing this contract."""
    return straight_off_hire(session.scalars(select(OffHireEvent).where(OffHireEvent.contract_no == contract_no)).all(), now_minute())


# ---------------- Tenders ----------------


def _vessel_clash(session: Session, t: Tender) -> str | None:
    if not t.vessel_id:
        return None
    c = session.scalars(select(Contract).where(Contract.vessel_id == t.vessel_id, Contract.status == "ACTIVE",
                                               Contract.start_date <= t.end_date, Contract.end_date >= t.start_date)).first()
    return f"On contract {c.contract_no} until {c.end_date}" if c else None


@router.get("/tenders")
def list_tenders(session: Session = Depends(get_session)):
    vessels = {v.vessel_id: v for v in session.scalars(select(Vessel))}
    tenders = session.scalars(select(Tender).order_by(Tender.due_on.desc())).all()
    # A bid with no vessel named is costed at the cheapest vessel of its type that could do it.
    # A running cost of 0 means it is not on file, so the bid is not costed.
    cheapest = {}
    for v in vessels.values():
        if v.daily_opex > 0:
            cheapest[v.vessel_type] = min(cheapest.get(v.vessel_type, v.daily_opex), v.daily_opex)
    models = {t.id: tender_model(t, (vessels[t.vessel_id].daily_opex or None) if t.vessel_id else cheapest.get(t.vessel_type)) for t in tenders}
    rows = [{**as_dict(t), "vessel_name": vessels[t.vessel_id].name if t.vessel_id else None, "model": models[t.id],
             "vessel_clash": _vessel_clash(session, t) if t.status in ("DRAFT", "SUBMITTED") else None} for t in tenders]
    return {"tenders": rows, "stats": win_loss(tenders, models)}


def _check_vessel(session: Session, body: TenderIn) -> None:
    if body.vessel_id:
        v = get_or_404(session, Vessel, body.vessel_id, "Vessel")
        if v.vessel_type != body.vessel_type:
            raise HTTPException(422, f"{v.name} is a {v.vessel_type}, not a {body.vessel_type}.")


@router.post("/tenders", status_code=201)
def create_tender(body: TenderIn, user: User = Depends(manager), session: Session = Depends(get_session)):
    _check_vessel(session, body)
    if session.scalars(select(Tender).where(Tender.ref == body.ref)).first():
        raise HTTPException(409, f"Tender {body.ref} already exists.")
    t = Tender(**body.model_dump(), created_by=user.username)
    session.add(t)
    audit(session, user, "tender.created", f"tender {body.ref}", body.client)
    session.commit()
    return as_dict(t)


@router.put("/tenders/{tender_id}")
def update_tender(tender_id: int, body: TenderIn, user: User = Depends(manager), session: Session = Depends(get_session)):
    t = get_or_404(session, Tender, tender_id, "Tender")
    if t.status not in ("DRAFT", "SUBMITTED"):
        raise HTTPException(409, "A decided bid cannot be changed.")
    _check_vessel(session, body)
    for k, v in body.model_dump().items():
        setattr(t, k, v)
    audit(session, user, "tender.updated", f"tender {t.ref}")
    session.commit()
    return as_dict(t)


@router.post("/tenders/{tender_id}/outcome")
def tender_outcome(tender_id: int, body: TenderOutcomeIn, user: User = Depends(manager), session: Session = Depends(get_session)):
    t = get_or_404(session, Tender, tender_id, "Tender")
    allowed = {"DRAFT": ("SUBMITTED", "WITHDRAWN"), "SUBMITTED": ("WON", "LOST", "WITHDRAWN")}
    if body.status not in allowed.get(t.status, ()):
        raise HTTPException(409, f"A {t.status.lower()} bid cannot be marked {body.status.lower()}.")
    if body.status == "LOST" and not body.note.strip():
        raise HTTPException(422, "Say why it was lost (price, technical, availability ...), so the win-loss record is useful.")
    t.status, t.outcome_note = body.status, body.note.strip()
    t.winning_rate = body.winning_rate if body.status == "LOST" else None
    t.probability = {"WON": 1.0, "LOST": 0.0, "WITHDRAWN": 0.0}.get(body.status, t.probability)
    audit(session, user, f"tender.{body.status.lower()}", f"tender {t.ref}", body.note.strip())
    session.commit()
    return as_dict(t)


@router.post("/tenders/{tender_id}/contract", status_code=201)
def tender_to_contract(tender_id: int, body: TenderToContractIn, user: User = Depends(manager), session: Session = Depends(get_session)):
    """Turn a won bid into a charter contract on the bid's terms. The usual contract checks apply."""
    t = get_or_404(session, Tender, tender_id, "Tender")
    if t.status != "WON" or t.contract_no:
        raise HTTPException(409, "Only a won bid without a contract can become one.")
    vessel_id = body.vessel_id or t.vessel_id
    if not vessel_id:
        raise HTTPException(422, "Choose the vessel for the contract.")
    contract = new_contract(session, ContractIn(
        contract_no=body.contract_no, client=t.client, vessel_id=vessel_id, scope=t.scope, start_date=t.start_date, end_date=t.end_date,
        operating_rate=t.operating_rate, standby_rate=t.standby_rate, breakdown_allowance_hrs=24, mob_fee=t.mob_fee, demob_fee=t.demob_fee), user)
    t.contract_no, t.vessel_id = contract.contract_no, vessel_id
    session.commit()
    return as_dict(contract)


# ---------------- Off hire ----------------


def _reported_breakdown(session: Session, e: OffHireEvent) -> tuple[float, float]:
    """Breakdown hours in the daily reports over the event's days, and the event's hours on those same days.
    Days with no report yet (today, while it is ongoing) are left out of both."""
    days = hours_by_day(e.start_at, e.end_at or now_minute())
    reports = session.scalars(select(DailyReport).where(
        DailyReport.vessel_id == e.vessel_id, DailyReport.on_date.in_(list(days)), DailyReport.status != "REJECTED")).all()
    return sum(r.breakdown_hrs for r in reports), sum(days[r.on_date] for r in reports)


@router.get("/off-hire")
def list_off_hire(session: Session = Depends(get_session)):
    names = {v.vessel_id: v.name for v in session.scalars(select(Vessel))}
    clients = {c.contract_no: c.client for c in session.scalars(select(Contract))}
    out = []
    for e in session.scalars(select(OffHireEvent).order_by(OffHireEvent.start_at.desc())):
        hours = round(sum(hours_by_day(e.start_at, e.end_at or now_minute()).values()), 1)
        reported, expected = _reported_breakdown(session, e)
        out.append({**as_dict(e), "vessel_name": names[e.vessel_id], "client": clients.get(e.contract_no), "hours": hours,
                    "uses_allowance": OFF_HIRE_REASONS[e.reason], "reported_breakdown_hrs": reported,
                    # Daily reports should show at least this much breakdown time over the same days.
                    "mismatch": e.contract_no is not None and reported + 0.5 < expected})
    return out


@router.post("/off-hire", status_code=201)
def log_off_hire(body: OffHireIn, user: User = Depends(staff), session: Session = Depends(get_session)):
    vessel = get_or_404(session, Vessel, body.vessel_id, "Vessel")
    if body.start_at[:10] > today():
        raise HTTPException(422, "Off hire cannot start in the future.")
    contract = active_contract(session, body.vessel_id, body.start_at[:10])
    overlap = session.scalars(select(OffHireEvent).where(OffHireEvent.vessel_id == body.vessel_id, OffHireEvent.start_at < (body.end_at or "9999"),
                                                         (OffHireEvent.end_at.is_(None)) | (OffHireEvent.end_at > body.start_at))).first()
    if overlap:
        raise HTTPException(409, f"{vessel.name} is already off hire from {overlap.start_at.replace('T', ' ')}.")
    e = OffHireEvent(**body.model_dump(), contract_no=contract.contract_no if contract else None, status="ENDED" if body.end_at else "OPEN",
                     logged_by=user.username)
    session.add(e)
    audit(session, user, "offhire.logged", f"vessel {body.vessel_id}", f"{body.reason}: {body.description}")
    session.commit()
    return as_dict(e)


@router.post("/off-hire/{event_id}/end")
def end_off_hire(event_id: int, body: OffHireEndIn, user: User = Depends(staff), session: Session = Depends(get_session)):
    e = get_or_404(session, OffHireEvent, event_id, "Off-hire event")
    if e.status != "OPEN":
        raise HTTPException(409, "This off hire has already ended.")
    if body.end_at <= e.start_at:
        raise HTTPException(422, "The end must be after the start.")
    e.end_at, e.status = body.end_at, "ENDED"
    audit(session, user, "offhire.ended", f"vessel {e.vessel_id}", body.end_at)
    session.commit()
    return as_dict(e)


@router.post("/off-hire/{event_id}/agree")
def agree_off_hire(event_id: int, user: User = Depends(manager), session: Session = Depends(get_session)):
    """The charterer has accepted the off-hire statement."""
    e = get_or_404(session, OffHireEvent, event_id, "Off-hire event")
    if e.status != "ENDED":
        raise HTTPException(409, "Only an ended off hire can be agreed.")
    e.status, e.agreed_by = "AGREED", user.username
    audit(session, user, "offhire.agreed", f"vessel {e.vessel_id}", f"event {e.id}")
    session.commit()
    return as_dict(e)


# ---------------- Performance claims ----------------


def claim_out(c: PerformanceClaim, contract: Contract, vessel_name: str) -> dict:
    overdue = c.status == "OPEN" and c.response_due < today()
    return {**as_dict(c), "client": contract.client, "vessel_id": contract.vessel_id, "vessel_name": vessel_name, "overdue": overdue}


def raise_claim(session: Session, body: ClaimIn, user: User, contract: Contract) -> PerformanceClaim:
    if body.period > today()[:7] or body.period < contract.start_date[:7]:
        raise HTTPException(422, "The month must be one the contract has run in.")
    c = PerformanceClaim(**body.model_dump(), raised_by=user.name, raised_on=today(),
                         response_due=(date.today() + timedelta(days=CLAIM_RESPONSE_DAYS)).isoformat())
    session.add(c)
    audit(session, user, "claim.raised", f"contract {contract.contract_no}", f"{body.kind}: {body.amount_claimed:,.0f}")
    return c


@router.get("/claims")
def list_claims(session: Session = Depends(get_session)):
    contracts = {c.contract_no: c for c in session.scalars(select(Contract))}
    names = {v.vessel_id: v.name for v in session.scalars(select(Vessel))}
    rows = session.scalars(select(PerformanceClaim).order_by(PerformanceClaim.status.desc(), PerformanceClaim.raised_on.desc())).all()
    return [claim_out(c, contracts[c.contract_no], names[contracts[c.contract_no].vessel_id]) for c in rows]


@router.post("/claims", status_code=201)
def create_claim(body: ClaimIn, user: User = Depends(manager), session: Session = Depends(get_session)):
    """Record a claim the charterer sent in by email or letter."""
    c = raise_claim(session, body, user, get_or_404(session, Contract, body.contract_no, "Contract"))
    session.commit()
    return as_dict(c)


@router.post("/claims/{claim_id}/decide")
def decide_claim(claim_id: int, body: ClaimDecisionIn, user: User = Depends(manager), session: Session = Depends(get_session)):
    c = get_or_404(session, PerformanceClaim, claim_id, "Claim")
    if c.status != "OPEN":
        raise HTTPException(409, "This claim is already decided.")
    if body.status == "ACCEPTED":
        if body.amount_agreed is None or body.amount_agreed <= 0:
            raise HTTPException(422, "Give the amount agreed.")
        if body.amount_agreed > c.amount_claimed:
            raise HTTPException(422, "The amount agreed cannot be more than the amount claimed.")
    c.status, c.decided_by, c.decision_note = body.status, user.username, body.note.strip()
    c.amount_agreed = body.amount_agreed if body.status == "ACCEPTED" else None
    audit(session, user, f"claim.{body.status.lower()}", f"contract {c.contract_no}", body.note.strip())
    session.commit()
    return as_dict(c)
