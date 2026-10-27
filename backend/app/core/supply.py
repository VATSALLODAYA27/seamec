"""Stock, its movements, critical spares, and maintenance jobs waiting for a spare.

- Every change to a quantity goes through `move`, which keeps the stock line and the movement trail in step.
- Cost: spares on board are a vessel cost. A receipt straight to a vessel is booked to it at the purchase price;
  a receipt at the shore warehouse is stock (not yet a cost) until it is sent on board.
- ISM Code 10.3 asks for spares for critical equipment to be kept on board. A stock line that names a piece of
  critical equipment is a critical spare: none on board blocks hire readiness, below its minimum is a warning.
- A job waiting for a spare is released (the spare issued to it) as soon as enough arrives on that vessel.
"""
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import SHORE, Contract, CostEntry, Equipment, MaintenanceJob, Part, SpareRequest, StockItem, StockMove, User, Vessel
from .finance import contract_on

MANAGER_PO_LIMIT = 10_00_000  # a manager approves purchase orders up to ₹10 lakh; above that, an admin


def stock_line(session: Session, part_id: int, location: str) -> StockItem:
    line = session.scalars(select(StockItem).where(StockItem.part_id == part_id, StockItem.location == location)).first()
    if line is None:
        line = StockItem(part_id=part_id, location=location, qty=0, min_qty=0)
        session.add(line)
        session.flush()
    return line


def book_cost(session: Session, vessel_id: str, on: str, category: str, amount: float, description: str, source: str, ref: str, user: User) -> None:
    c = contract_on(session.scalars(select(Contract).where(Contract.vessel_id == vessel_id)).all(), on)
    session.add(CostEntry(vessel_id=vessel_id, contract_no=c.contract_no if c else None, on_date=on, category=category, amount=round(amount, 2),
                          description=description, source=source, ref=ref, created_by=user.username))


def move(session: Session, part: Part, location: str, qty: float, kind: str, ref: str, user: User) -> StockItem:
    line = stock_line(session, part.id, location)
    if line.qty + qty < -1e-9:
        raise HTTPException(409, f"Only {line.qty:g} {part.unit} of {part.name} at {location}.")
    line.qty = round(line.qty + qty, 3)
    session.add(StockMove(part_id=part.id, location=location, qty=qty, kind=kind, ref=ref, by=user.username))
    return line


def release_waiting(session: Session, part: Part, vessel_id: str, today: str, user: User) -> int:
    """Issue newly arrived spares to jobs on this vessel that are waiting for them, oldest first."""
    waiting = session.scalars(select(SpareRequest).join(MaintenanceJob, MaintenanceJob.id == SpareRequest.job_id).join(Equipment, Equipment.id == MaintenanceJob.equipment_id)
                              .where(SpareRequest.part_id == part.id, SpareRequest.status == "WAITING", Equipment.vessel_id == vessel_id)
                              .order_by(SpareRequest.id)).all()
    released = 0
    for req in waiting:
        if stock_line(session, part.id, vessel_id).qty < req.qty:
            break
        move(session, part, vessel_id, -req.qty, "ISSUE", f"job {req.job_id}", user)
        req.status, req.issued_on = "ISSUED", today
        released += 1
    return released


def is_vessel(session: Session, location: str) -> bool:
    return location != SHORE and session.get(Vessel, location) is not None


def critical_spares(session: Session, vessel_id: str) -> list[dict]:
    """Critical spares on this vessel below their minimum."""
    rows = session.execute(select(StockItem, Part, Equipment).join(Part, Part.id == StockItem.part_id).join(Equipment, Equipment.id == StockItem.equipment_id)
                           .where(StockItem.location == vessel_id, Equipment.critical, StockItem.qty < StockItem.min_qty)).all()
    return [{"part": p.name, "part_no": p.part_no, "equipment": e.name, "qty": s.qty, "min_qty": s.min_qty, "unit": p.unit} for s, p, e in rows]


def waiting_by_job(session: Session, job_ids: list[int]) -> dict[int, list[dict]]:
    out: dict[int, list[dict]] = {}
    for req, part in session.execute(select(SpareRequest, Part).join(Part, Part.id == SpareRequest.part_id)
                                     .where(SpareRequest.job_id.in_(job_ids), SpareRequest.status == "WAITING")):
        out.setdefault(req.job_id, []).append({"request_id": req.id, "part_id": part.id, "part": part.name, "qty": req.qty, "unit": part.unit, "po_no": req.po_no})
    return out
