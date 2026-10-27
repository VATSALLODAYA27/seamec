"""Vendors, the spares catalogue, stock on each vessel and at the shore warehouse, purchase orders, and spares for
maintenance jobs. The rules live in core/supply.py.

Purchase order flow: DRAFT (anyone raises it) -> APPROVED (manager up to the limit, admin above) -> ORDERED ->
PART_RECEIVED / RECEIVED as deliveries arrive. A draft or approved order can be cancelled.
"""
import math
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import audit, manager, staff
from ..core.supply import MANAGER_PO_LIMIT, book_cost, is_vessel, move, release_waiting, stock_line
from ..db import get_session
from ..models import (SHORE, Equipment, MaintenanceJob, Part, POLine, PurchaseOrder, SpareRequest, StockItem, StockMove, User, Vendor, Vessel,
                      as_dict)
from ..schemas import PartIn, POIn, ReceiveIn, ReorderIn, SpareRequestIn, StockAdjustIn, StockLevelIn, TransferIn, VendorIn
from .fleet import get_or_404, today

router = APIRouter(prefix="/api", tags=["supply"], dependencies=[Depends(staff)])


def check_location(session: Session, location: str) -> str:
    if location != SHORE and session.get(Vessel, location) is None:
        raise HTTPException(422, "The location must be a vessel or the shore warehouse.")
    return location


# ---------------- Vendors ----------------


@router.get("/vendors")
def list_vendors(session: Session = Depends(get_session)):
    spend = dict(session.execute(select(PurchaseOrder.vendor_id, func.sum(PurchaseOrder.total))
                                 .where(PurchaseOrder.status.in_(("ORDERED", "PART_RECEIVED", "RECEIVED"))).group_by(PurchaseOrder.vendor_id)).all())
    return [{**as_dict(v), "spend": round(spend.get(v.id, 0), 2)} for v in session.scalars(select(Vendor).order_by(Vendor.category, Vendor.name))]


def _save_vendor(session: Session, v: Vendor, body: VendorIn) -> None:
    clash = session.scalars(select(Vendor).where(func.lower(Vendor.name) == body.name.strip().lower(), Vendor.id != (v.id or 0))).first()
    if clash:
        raise HTTPException(409, f"{clash.name} is already in the vendor list.")
    for k, val in body.model_dump().items():
        setattr(v, k, val.strip() if isinstance(val, str) else val)


@router.post("/vendors", status_code=201)
def create_vendor(body: VendorIn, user: User = Depends(manager), session: Session = Depends(get_session)):
    v = Vendor(name=body.name, category=body.category)
    _save_vendor(session, v, body)
    session.add(v)
    audit(session, user, "vendor.created", f"vendor {body.name}", body.category)
    session.commit()
    return as_dict(v)


@router.put("/vendors/{vendor_id}")
def update_vendor(vendor_id: int, body: VendorIn, user: User = Depends(manager), session: Session = Depends(get_session)):
    v = get_or_404(session, Vendor, vendor_id, "Vendor")
    _save_vendor(session, v, body)
    audit(session, user, "vendor.updated", f"vendor {v.name}", "approved" if v.approved else "not approved")
    session.commit()
    return as_dict(v)


# ---------------- Parts and stock ----------------


@router.get("/parts")
def list_parts(session: Session = Depends(get_session)):
    vendors = {v.id: v.name for v in session.scalars(select(Vendor))}
    totals = dict(session.execute(select(StockItem.part_id, func.sum(StockItem.qty)).group_by(StockItem.part_id)).all())
    return [{**as_dict(p), "vendor_name": vendors.get(p.vendor_id), "total_qty": totals.get(p.id, 0)} for p in session.scalars(select(Part).order_by(Part.name))]


@router.post("/parts", status_code=201)
def create_part(body: PartIn, user: User = Depends(manager), session: Session = Depends(get_session)):
    if session.scalars(select(Part).where(Part.part_no == body.part_no.strip())).first():
        raise HTTPException(409, f"Part number {body.part_no} already exists.")
    if body.vendor_id:
        get_or_404(session, Vendor, body.vendor_id, "Vendor")
    p = Part(**{**body.model_dump(), "part_no": body.part_no.strip(), "name": body.name.strip()})
    session.add(p)
    audit(session, user, "part.created", f"part {p.part_no}", p.name)
    session.commit()
    return as_dict(p)


@router.get("/stock")
def list_stock(location: str | None = None, session: Session = Depends(get_session)):
    """Every stock line with its part, the equipment it is held for, and whether it is short."""
    q = select(StockItem, Part).join(Part, Part.id == StockItem.part_id).order_by(StockItem.location, Part.name)
    if location:
        q = q.where(StockItem.location == location)
    equipment = {e.id: e for e in session.scalars(select(Equipment))}
    names = {v.vessel_id: v.name for v in session.scalars(select(Vessel))}
    waiting = defaultdict(float)
    for req, vid in session.execute(select(SpareRequest, Equipment.vessel_id).join(MaintenanceJob, MaintenanceJob.id == SpareRequest.job_id)
                                    .join(Equipment, Equipment.id == MaintenanceJob.equipment_id).where(SpareRequest.status == "WAITING")):
        waiting[(req.part_id, vid)] += req.qty
    out = []
    for s, p in session.execute(q):
        e = equipment.get(s.equipment_id)
        out.append({**as_dict(s), "part_no": p.part_no, "part": p.name, "unit": p.unit, "unit_cost": p.unit_cost, "value": round(s.qty * p.unit_cost, 2),
                    "location_name": "Shore warehouse" if s.location == SHORE else names.get(s.location, s.location),
                    "equipment": e.name if e else None, "critical": bool(e and e.critical), "short": s.qty < s.min_qty,
                    "waiting_qty": waiting.get((s.part_id, s.location), 0)})
    return out


@router.put("/stock/level")
def set_level(body: StockLevelIn, user: User = Depends(manager), session: Session = Depends(get_session)):
    """Set the minimum to keep at a place, and (on a vessel) the equipment the spare is held for."""
    get_or_404(session, Part, body.part_id, "Part")
    check_location(session, body.location)
    if body.equipment_id is not None:
        e = get_or_404(session, Equipment, body.equipment_id, "Equipment")
        if e.vessel_id != body.location:
            raise HTTPException(422, "That equipment is not on this vessel.")
    line = stock_line(session, body.part_id, body.location)
    line.min_qty, line.equipment_id, line.bin = body.min_qty, body.equipment_id, body.bin.strip()
    audit(session, user, "stock.level", f"part {body.part_id}", f"{body.location}: minimum {body.min_qty:g}")
    session.commit()
    return as_dict(line)


@router.post("/stock/adjust")
def adjust(body: StockAdjustIn, user: User = Depends(manager), session: Session = Depends(get_session)):
    """Correct a quantity after a stock count. The difference is recorded with the reason."""
    part = get_or_404(session, Part, body.part_id, "Part")
    line = stock_line(session, part.id, check_location(session, body.location))
    diff = round(body.qty - line.qty, 3)
    if diff:
        move(session, part, body.location, diff, "ADJUST", body.reason.strip(), user)
        if diff > 0 and is_vessel(session, body.location):
            release_waiting(session, part, body.location, today(), user)
    audit(session, user, "stock.adjusted", f"part {part.part_no}", f"{body.location}: {diff:+g} ({body.reason.strip()})")
    session.commit()
    return as_dict(line)


@router.post("/stock/transfer")
def transfer(body: TransferIn, user: User = Depends(staff), session: Session = Depends(get_session)):
    """Send spares from one place to another, usually from the shore warehouse to a vessel. A transfer onto a
    vessel books the spares' cost to it, and issues them to any job there waiting for them."""
    part = get_or_404(session, Part, body.part_id, "Part")
    check_location(session, body.from_location)
    check_location(session, body.to_location)
    if body.from_location == body.to_location:
        raise HTTPException(422, "Choose two different places.")
    ref = f"{body.from_location} -> {body.to_location}"
    move(session, part, body.from_location, -body.qty, "TRANSFER", ref, user)
    move(session, part, body.to_location, body.qty, "TRANSFER", ref, user)
    released = 0
    if is_vessel(session, body.to_location):
        if body.from_location == SHORE:
            book_cost(session, body.to_location, today(), "SPARES", body.qty * part.unit_cost, f"{part.name} x {body.qty:g} from shore stock", "TRANSFER", part.part_no, user)
        released = release_waiting(session, part, body.to_location, today(), user)
    audit(session, user, "stock.transfer", f"part {part.part_no}", f"{body.qty:g} {part.unit} {ref}")
    session.commit()
    return {"moved": body.qty, "jobs_released": released}


@router.get("/stock/moves")
def stock_moves(part_id: int, location: str | None = None, session: Session = Depends(get_session)):
    q = select(StockMove).where(StockMove.part_id == part_id).order_by(StockMove.id.desc()).limit(200)
    if location:
        q = q.where(StockMove.location == location)
    return [as_dict(m) for m in session.scalars(q)]


@router.get("/stock/reorder")
def reorder_list(session: Session = Depends(get_session)):
    """Stock lines below their minimum, with what to order to bring them back up and whether an order is already open."""
    open_qty = defaultdict(float)
    for line, po in session.execute(select(POLine, PurchaseOrder).join(PurchaseOrder, PurchaseOrder.po_no == POLine.po_no)
                                    .where(PurchaseOrder.status.in_(("DRAFT", "APPROVED", "ORDERED", "PART_RECEIVED")), POLine.part_id.is_not(None))):
        open_qty[(line.part_id, po.deliver_to)] += line.qty - line.received_qty
    rows = [r for r in list_stock(None, session) if r["short"]]
    for r in rows:
        r["on_order"] = open_qty.get((r["part_id"], r["location"]), 0)
        r["to_order"] = max(math.ceil(r["min_qty"] - r["qty"] - r["on_order"]), 0)
    return sorted(rows, key=lambda r: (not r["critical"], r["location"]))


@router.post("/stock/reorder", status_code=201)
def raise_reorders(body: ReorderIn, user: User = Depends(staff), session: Session = Depends(get_session)):
    """Draft purchase orders for everything short at one place, one per preferred vendor."""
    check_location(session, body.location)
    parts = {p.id: p for p in session.scalars(select(Part))}
    by_vendor = defaultdict(list)
    skipped = []
    for r in reorder_list(session):
        if r["location"] != body.location or not r["to_order"]:
            continue
        p = parts[r["part_id"]]
        (by_vendor[p.vendor_id].append((p, r["to_order"])) if p.vendor_id else skipped.append(p.name))
    made = [_new_po(session, user, vendor_id, body.location, [{"part_id": p.id, "description": p.name, "qty": q, "unit_price": p.unit_cost} for p, q in lines],
                    "Reorder to minimum stock").po_no for vendor_id, lines in by_vendor.items()]
    if not made:
        raise HTTPException(409, "Nothing to order here" + (f"; no preferred vendor for {', '.join(skipped)}" if skipped else "") + ".")
    session.commit()
    return {"orders": made, "skipped": skipped}


# ---------------- Purchase orders ----------------


def _po_no(session: Session) -> str:
    prefix = f"PO-{today()[2:4]}{today()[5:7]}-"
    used = [int(n[-3:]) for n in session.scalars(select(PurchaseOrder.po_no).where(PurchaseOrder.po_no.like(prefix + "%")))]
    return f"{prefix}{max(used, default=0) + 1:03d}"


def _new_po(session: Session, user: User, vendor_id: int, deliver_to: str, lines: list[dict], note: str = "", needed_by: str | None = None) -> PurchaseOrder:
    vendor = get_or_404(session, Vendor, vendor_id, "Vendor")
    if not vendor.approved:
        raise HTTPException(409, f"{vendor.name} is not an approved vendor.")
    po = PurchaseOrder(po_no=_po_no(session), vendor_id=vendor.id, deliver_to=check_location(session, deliver_to), note=note, needed_by=needed_by,
                       raised_by=user.username, raised_on=today())
    session.add(po)
    session.flush()
    for line in lines:
        if line.get("part_id") is not None:
            part = get_or_404(session, Part, line["part_id"], "Part")
            line = {**line, "description": line.get("description") or part.name}
        session.add(POLine(po_no=po.po_no, **line))
    po.total = round(sum(line["qty"] * line["unit_price"] for line in lines), 2)
    audit(session, user, "po.raised", f"po {po.po_no}", f"{vendor.name}: {po.total:,.2f}")
    return po


def po_out(po: PurchaseOrder, vendor: Vendor, lines: list[POLine], parts: dict, names: dict) -> dict:
    return {**as_dict(po), "vendor_name": vendor.name, "deliver_to_name": "Shore warehouse" if po.deliver_to == SHORE else names.get(po.deliver_to, po.deliver_to),
            "needs_admin": po.total > MANAGER_PO_LIMIT,
            "lines": [{**as_dict(line), "part_no": parts[line.part_id].part_no if line.part_id else None,
                       "unit": parts[line.part_id].unit if line.part_id else ""} for line in lines]}


@router.get("/purchase-orders")
def list_pos(session: Session = Depends(get_session)):
    vendors = {v.id: v for v in session.scalars(select(Vendor))}
    parts = {p.id: p for p in session.scalars(select(Part))}
    names = {v.vessel_id: v.name for v in session.scalars(select(Vessel))}
    lines = defaultdict(list)
    for line in session.scalars(select(POLine).order_by(POLine.id)):
        lines[line.po_no].append(line)
    return [po_out(po, vendors[po.vendor_id], lines[po.po_no], parts, names)
            for po in session.scalars(select(PurchaseOrder).order_by(PurchaseOrder.raised_on.desc(), PurchaseOrder.po_no.desc()))]


@router.post("/purchase-orders", status_code=201)
def create_po(body: POIn, user: User = Depends(staff), session: Session = Depends(get_session)):
    po = _new_po(session, user, body.vendor_id, body.deliver_to, [line.model_dump() for line in body.lines], body.note.strip(), body.needed_by)
    session.commit()
    return as_dict(po)


@router.post("/purchase-orders/{po_no}/approve")
def approve_po(po_no: str, user: User = Depends(manager), session: Session = Depends(get_session)):
    po = get_or_404(session, PurchaseOrder, po_no, "Purchase order")
    if po.status != "DRAFT":
        raise HTTPException(409, "Only a draft can be approved.")
    if po.total > MANAGER_PO_LIMIT and user.role != "admin":
        raise HTTPException(403, f"Orders above ₹{MANAGER_PO_LIMIT:,.0f} need an admin's approval.")
    po.status, po.approved_by = "APPROVED", user.username
    audit(session, user, "po.approved", f"po {po_no}", f"{po.total:,.2f}")
    session.commit()
    return as_dict(po)


@router.post("/purchase-orders/{po_no}/order")
def mark_ordered(po_no: str, user: User = Depends(manager), session: Session = Depends(get_session)):
    po = get_or_404(session, PurchaseOrder, po_no, "Purchase order")
    if po.status != "APPROVED":
        raise HTTPException(409, "Only an approved order can be sent to the vendor.")
    po.status, po.ordered_on = "ORDERED", today()
    audit(session, user, "po.ordered", f"po {po_no}")
    session.commit()
    return as_dict(po)


@router.post("/purchase-orders/{po_no}/cancel")
def cancel_po(po_no: str, user: User = Depends(manager), session: Session = Depends(get_session)):
    po = get_or_404(session, PurchaseOrder, po_no, "Purchase order")
    if po.status not in ("DRAFT", "APPROVED"):
        raise HTTPException(409, "An order already with the vendor cannot be cancelled here.")
    po.status = "CANCELLED"
    for req in session.scalars(select(SpareRequest).where(SpareRequest.po_no == po_no, SpareRequest.status == "WAITING")):
        req.po_no = None  # the job still waits for the spare, now with no order behind it
    audit(session, user, "po.cancelled", f"po {po_no}")
    session.commit()
    return as_dict(po)


@router.post("/purchase-orders/{po_no}/receive")
def receive(po_no: str, body: ReceiveIn, user: User = Depends(staff), session: Session = Depends(get_session)):
    """Record what arrived. Stock goes up where the order was delivered; on a vessel the cost is booked to it and
    waiting jobs get their spares."""
    po = get_or_404(session, PurchaseOrder, po_no, "Purchase order")
    if po.status not in ("ORDERED", "PART_RECEIVED"):
        raise HTTPException(409, "Only an order with the vendor can be received.")
    lines = {line.id: line for line in session.scalars(select(POLine).where(POLine.po_no == po_no))}
    if not body.lines or any(i not in lines for i in body.lines):
        raise HTTPException(422, "Name lines of this order.")
    on_vessel = is_vessel(session, po.deliver_to)
    cost = 0.0
    for line_id, qty in body.lines.items():
        line = lines[line_id]
        if qty <= 0 or line.received_qty + qty > line.qty + 1e-9:
            raise HTTPException(422, f"{line.description}: {line.qty - line.received_qty:g} still to come.")
        line.received_qty += qty
        cost += qty * line.unit_price
        if line.part_id:
            part = session.get(Part, line.part_id)
            part.unit_cost = line.unit_price  # last purchase price
            move(session, part, po.deliver_to, qty, "RECEIPT", po_no, user)
            if on_vessel:
                release_waiting(session, part, po.deliver_to, today(), user)
    if on_vessel:
        book_cost(session, po.deliver_to, today(), "SPARES", cost, f"{po_no} received", "PO", po_no, user)
    po.status = "RECEIVED" if all(line.received_qty >= line.qty - 1e-9 for line in lines.values()) else "PART_RECEIVED"
    audit(session, user, "po.received", f"po {po_no}", f"{cost:,.2f}")
    session.commit()
    return as_dict(po)


# ---------------- Spares for maintenance jobs ----------------


@router.post("/maintenance/jobs/{job_id}/spares", status_code=201)
def request_spare(job_id: int, body: SpareRequestIn, user: User = Depends(staff), session: Session = Depends(get_session)):
    """Take a spare for a job. If the vessel has it, it is issued now; otherwise the job waits for it."""
    job = get_or_404(session, MaintenanceJob, job_id, "Job")
    if job.kind == "DEFECT" and job.status != "OPEN":
        raise HTTPException(409, "This defect is closed.")
    part = get_or_404(session, Part, body.part_id, "Part")
    vessel_id = session.get(Equipment, job.equipment_id).vessel_id
    req = SpareRequest(job_id=job.id, part_id=part.id, qty=body.qty, requested_on=today())
    session.add(req)
    if stock_line(session, part.id, vessel_id).qty >= body.qty:
        move(session, part, vessel_id, -body.qty, "ISSUE", f"job {job.id}", user)
        req.status, req.issued_on = "ISSUED", today()
    shore = stock_line(session, part.id, SHORE).qty
    audit(session, user, "spare.requested", f"job {job.id}", f"{part.name} x {body.qty:g}: {req.status.lower()}")
    session.commit()
    return {**as_dict(req), "shore_qty": shore}


@router.post("/maintenance/spares/{request_id}/order", status_code=201)
def order_for_request(request_id: int, user: User = Depends(staff), session: Session = Depends(get_session)):
    """Raise a draft purchase order, delivered to the vessel, for a spare a job is waiting for."""
    req = get_or_404(session, SpareRequest, request_id, "Spare request")
    if req.status != "WAITING" or req.po_no:
        raise HTTPException(409, "This spare is not waiting, or is already on order.")
    part = session.get(Part, req.part_id)
    if not part.vendor_id:
        raise HTTPException(409, f"{part.name} has no preferred vendor; raise the order from Supply.")
    vessel_id = session.get(Equipment, session.get(MaintenanceJob, req.job_id).equipment_id).vessel_id
    po = _new_po(session, user, part.vendor_id, vessel_id, [{"part_id": part.id, "description": part.name, "qty": req.qty, "unit_price": part.unit_cost}],
                 f"For maintenance job {req.job_id}")
    req.po_no = po.po_no
    session.commit()
    return as_dict(po)


@router.post("/maintenance/spares/{request_id}/cancel")
def cancel_request(request_id: int, user: User = Depends(staff), session: Session = Depends(get_session)):
    req = get_or_404(session, SpareRequest, request_id, "Spare request")
    if req.status != "WAITING":
        raise HTTPException(409, "Only a waiting request can be cancelled.")
    req.status = "CANCELLED"
    audit(session, user, "spare.cancelled", f"job {req.job_id}")
    session.commit()
    return as_dict(req)
