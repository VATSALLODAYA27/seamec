"""Port calls: the agent appointed, the proforma disbursement account (PDA) agreed before arrival, and the final
account (FDA) after sailing. Closing a call books the FDA total to the vessel as a port cost."""
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import audit, manager, staff
from ..core.supply import book_cost
from ..db import get_session
from ..models import DisbursementLine, PortCall, User, Vendor, Vessel, as_dict
from ..schemas import AccountIn, PortCallIn, PortStatusIn
from .fleet import get_or_404, today

router = APIRouter(prefix="/api/port-calls", tags=["port calls"], dependencies=[Depends(staff)])

VARIANCE_FLAG = 0.10  # an FDA line more than 10% over its PDA estimate is flagged for a query to the agent


def call_out(pc: PortCall, lines: list[DisbursementLine], vessel: str, agent: str | None) -> dict:
    pda = sum(line.pda for line in lines)
    final = all(line.fda is not None for line in lines) and bool(lines)
    fda = sum(line.fda or 0 for line in lines) if final else None
    return {**as_dict(pc), "vessel_name": vessel, "agent_name": agent, "pda_total": round(pda, 2), "fda_total": round(fda, 2) if fda is not None else None,
            "balance": round(fda - pc.advance_paid, 2) if fda is not None else None,  # + owed to the agent, - refund due
            "variance_pct": round(100 * (fda - pda) / pda, 1) if fda is not None and pda else None,
            "lines": [{**as_dict(line), "over": line.fda is not None and line.pda > 0 and line.fda > line.pda * (1 + VARIANCE_FLAG)} for line in lines]}


@router.get("")
def list_calls(session: Session = Depends(get_session)):
    names = {v.vessel_id: v.name for v in session.scalars(select(Vessel))}
    agents = {v.id: v.name for v in session.scalars(select(Vendor))}
    lines = defaultdict(list)
    for line in session.scalars(select(DisbursementLine).order_by(DisbursementLine.id)):
        lines[line.port_call_id].append(line)
    calls = session.scalars(select(PortCall).order_by(PortCall.eta.desc())).all()
    return [call_out(pc, lines[pc.id], names[pc.vessel_id], agents.get(pc.agent_id)) for pc in calls]


def _agent(session: Session, agent_id: int | None) -> Vendor | None:
    if agent_id is None:
        return None
    v = get_or_404(session, Vendor, agent_id, "Agent")
    if v.category != "AGENT" or not v.approved:
        raise HTTPException(422, f"{v.name} is not an approved port agent.")
    return v


@router.post("", status_code=201)
def create_call(body: PortCallIn, user: User = Depends(staff), session: Session = Depends(get_session)):
    get_or_404(session, Vessel, body.vessel_id, "Vessel")
    agent = _agent(session, body.agent_id)
    pc = PortCall(vessel_id=body.vessel_id, port=body.port.strip(), purpose=body.purpose.strip(), eta=body.eta, etd=body.etd,
                  agent_id=agent.id if agent else None, appointed_on=today() if agent else None, created_by=user.username)
    session.add(pc)
    session.flush()
    session.add_all(DisbursementLine(port_call_id=pc.id, item=line.item.strip(), pda=line.pda) for line in body.lines)
    audit(session, user, "portcall.created", f"vessel {body.vessel_id}", f"{body.port} {body.eta}")
    session.commit()
    return as_dict(pc)


@router.post("/{call_id}/appoint")
def appoint_agent(call_id: int, agent_id: int, user: User = Depends(staff), session: Session = Depends(get_session)):
    pc = get_or_404(session, PortCall, call_id, "Port call")
    if pc.status == "CLOSED":
        raise HTTPException(409, "This port call is closed.")
    agent = _agent(session, agent_id)
    pc.agent_id, pc.appointed_on = agent.id, today()
    audit(session, user, "portcall.agent", f"port call {pc.id}", agent.name)
    session.commit()
    return as_dict(pc)


@router.post("/{call_id}/arrived")
def arrived(call_id: int, body: PortStatusIn, user: User = Depends(staff), session: Session = Depends(get_session)):
    pc = get_or_404(session, PortCall, call_id, "Port call")
    if pc.status != "PLANNED":
        raise HTTPException(409, "Only a planned call can arrive.")
    if body.on > today():
        raise HTTPException(422, "The date cannot be in the future.")
    pc.status, pc.ata = "ARRIVED", body.on
    audit(session, user, "portcall.arrived", f"port call {pc.id}", body.on)
    session.commit()
    return as_dict(pc)


@router.post("/{call_id}/sailed")
def sailed(call_id: int, body: PortStatusIn, user: User = Depends(staff), session: Session = Depends(get_session)):
    pc = get_or_404(session, PortCall, call_id, "Port call")
    if pc.status != "ARRIVED":
        raise HTTPException(409, "Only a vessel in port can sail.")
    if body.on < pc.ata or body.on > today():
        raise HTTPException(422, "Sailing must be between arrival and today.")
    pc.status, pc.atd = "SAILED", body.on
    audit(session, user, "portcall.sailed", f"port call {pc.id}", body.on)
    session.commit()
    return as_dict(pc)


@router.put("/{call_id}/account")
def save_account(call_id: int, body: AccountIn, user: User = Depends(staff), session: Session = Depends(get_session)):
    """Save the PDA and, once the agent sends it, the FDA figures line by line, and the advance paid."""
    pc = get_or_404(session, PortCall, call_id, "Port call")
    if pc.status == "CLOSED":
        raise HTTPException(409, "This port call is closed.")
    existing = {line.id: line for line in session.scalars(select(DisbursementLine).where(DisbursementLine.port_call_id == pc.id))}
    keep = set()
    for line in body.lines:
        row = existing.get(line.id) if line.id else None
        if row is None:
            row = DisbursementLine(port_call_id=pc.id, item="")
            session.add(row)
        row.item, row.pda, row.fda = line.item.strip(), line.pda, line.fda
        keep.add(row.id)
    for line_id, row in existing.items():
        if line_id not in keep:
            session.delete(row)
    pc.advance_paid = body.advance_paid
    audit(session, user, "portcall.account", f"port call {pc.id}", f"{len(body.lines)} lines")
    session.commit()
    return as_dict(pc)


@router.post("/{call_id}/close")
def close_call(call_id: int, user: User = Depends(manager), session: Session = Depends(get_session)):
    """Approve the FDA: the call's cost is booked to the vessel on its arrival date."""
    pc = get_or_404(session, PortCall, call_id, "Port call")
    if pc.status != "SAILED":
        raise HTTPException(409, "Close the call once the vessel has sailed.")
    lines = session.scalars(select(DisbursementLine).where(DisbursementLine.port_call_id == pc.id)).all()
    if not lines or any(line.fda is None for line in lines):
        raise HTTPException(409, "Enter the final (FDA) amount on every line first.")
    total = sum(line.fda for line in lines)
    book_cost(session, pc.vessel_id, pc.ata, "PORT", total, f"{pc.port}: {pc.purpose}", "PORT_CALL", f"port call {pc.id}", user)
    pc.status = "CLOSED"
    audit(session, user, "portcall.closed", f"port call {pc.id}", f"FDA {total:,.2f}")
    session.commit()
    return as_dict(pc)
