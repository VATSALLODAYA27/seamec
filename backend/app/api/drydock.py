"""Dry dock as a project: the work list with budget against actual, yard quotes compared on their full cost,
and the docking itself.

Yard comparison: a quote's evaluated cost = the yard's price + the cost of getting there and back (deviation) +
the vessel's running cost for every day in dock. The cheapest price is not always the cheapest docking.

PLANNING -> CONTRACTED (a yard chosen) -> IN_DOCK (the vessel shows as in dry dock) -> COMPLETED (back in service,
bottom survey recorded, actual cost booked to the vessel).
"""
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import audit, manager, staff
from ..core.supply import book_cost
from ..db import get_session
from ..models import DryDockItem, DryDockProject, User, Vendor, Vessel, YardQuote, as_dict
from ..schemas import DryDockIn, DryDockItemIn, PortStatusIn, YardQuoteIn
from .fleet import active_contract, get_or_404, today

router = APIRouter(prefix="/api/drydock", tags=["dry dock"], dependencies=[Depends(staff)])


def project_out(p: DryDockProject, v: Vessel, items: list[DryDockItem], quotes: list[YardQuote], vendors: dict) -> dict:
    ranked = sorted(({**as_dict(q), "yard": vendors[q.vendor_id].name, "time_cost": q.days * v.daily_opex,
                      "evaluated": round(q.price + q.deviation_cost + q.days * v.daily_opex, 2), "chosen": q.id == p.yard_quote_id} for q in quotes),
                    key=lambda q: q["evaluated"])
    for i, q in enumerate(ranked):
        q["rank"] = i + 1
    live = [i for i in items if i.status != "DEFERRED"]
    chosen = next((q for q in ranked if q["chosen"]), None)
    return {**as_dict(p), "vessel_name": v.name, "budget": round(sum(i.budget for i in live), 2), "actual": round(sum(i.actual for i in live), 2),
            "items_open": sum(i.status == "OPEN" for i in items), "items_done": sum(i.status == "DONE" for i in items),
            "yard": chosen["yard"] if chosen else None, "items": [as_dict(i) for i in items], "quotes": ranked}


@router.get("")
def list_projects(session: Session = Depends(get_session)):
    vessels = {v.vessel_id: v for v in session.scalars(select(Vessel))}
    vendors = {v.id: v for v in session.scalars(select(Vendor))}
    items, quotes = defaultdict(list), defaultdict(list)
    for i in session.scalars(select(DryDockItem).order_by(DryDockItem.category, DryDockItem.id)):
        items[i.project_id].append(i)
    for q in session.scalars(select(YardQuote)):
        quotes[q.project_id].append(q)
    projects = session.scalars(select(DryDockProject).order_by(DryDockProject.planned_start.desc())).all()
    return [project_out(p, vessels[p.vessel_id], items[p.id], quotes[p.id], vendors) for p in projects]


def _open(session: Session, project_id: int) -> DryDockProject:
    p = get_or_404(session, DryDockProject, project_id, "Dry dock project")
    if p.status == "COMPLETED":
        raise HTTPException(409, "This dry dock is completed.")
    return p


@router.post("", status_code=201)
def create_project(body: DryDockIn, user: User = Depends(manager), session: Session = Depends(get_session)):
    v = get_or_404(session, Vessel, body.vessel_id, "Vessel")
    if session.scalars(select(DryDockProject).where(DryDockProject.vessel_id == v.vessel_id, DryDockProject.status != "COMPLETED")).first():
        raise HTTPException(409, f"{v.name} already has a dry dock in hand.")
    p = DryDockProject(**body.model_dump(), created_by=user.username)
    session.add(p)
    audit(session, user, "drydock.created", f"vessel {v.vessel_id}", f"{body.title} {body.planned_start}")
    session.commit()
    return as_dict(p)


@router.put("/{project_id}")
def update_project(project_id: int, body: DryDockIn, user: User = Depends(manager), session: Session = Depends(get_session)):
    p = _open(session, project_id)
    if body.vessel_id != p.vessel_id:
        raise HTTPException(422, "A project stays with its vessel.")
    p.title, p.planned_start, p.planned_end, p.bottom_survey = body.title, body.planned_start, body.planned_end, body.bottom_survey
    audit(session, user, "drydock.updated", f"vessel {p.vessel_id}", f"{body.planned_start} to {body.planned_end}")
    session.commit()
    return as_dict(p)


@router.post("/{project_id}/items", status_code=201)
def add_item(project_id: int, body: DryDockItemIn, user: User = Depends(manager), session: Session = Depends(get_session)):
    p = _open(session, project_id)
    item = DryDockItem(project_id=p.id, **body.model_dump())
    session.add(item)
    session.commit()
    return as_dict(item)


@router.put("/items/{item_id}")
def update_item(item_id: int, body: DryDockItemIn, user: User = Depends(manager), session: Session = Depends(get_session)):
    item = get_or_404(session, DryDockItem, item_id, "Work item")
    _open(session, item.project_id)
    for k, v in body.model_dump().items():
        setattr(item, k, v)
    session.commit()
    return as_dict(item)


@router.post("/{project_id}/quotes", status_code=201)
def add_quote(project_id: int, body: YardQuoteIn, user: User = Depends(manager), session: Session = Depends(get_session)):
    p = _open(session, project_id)
    yard = get_or_404(session, Vendor, body.vendor_id, "Yard")
    if yard.category != "YARD":
        raise HTTPException(422, f"{yard.name} is not a shipyard in the vendor list.")
    q = YardQuote(project_id=p.id, **body.model_dump())
    session.add(q)
    audit(session, user, "drydock.quote", f"vessel {p.vessel_id}", f"{yard.name}: {body.price:,.0f}, {body.days} days")
    session.commit()
    return as_dict(q)


@router.post("/{project_id}/select/{quote_id}")
def select_yard(project_id: int, quote_id: int, user: User = Depends(manager), session: Session = Depends(get_session)):
    p = _open(session, project_id)
    q = get_or_404(session, YardQuote, quote_id, "Quote")
    if q.project_id != p.id:
        raise HTTPException(422, "That quote is for another project.")
    if p.status == "IN_DOCK":
        raise HTTPException(409, "The vessel is already in dock.")
    yard = session.get(Vendor, q.vendor_id)
    if not yard.approved:
        raise HTTPException(409, f"{yard.name} is not an approved vendor.")
    p.yard_quote_id, p.status = q.id, "CONTRACTED"
    audit(session, user, "drydock.yard", f"vessel {p.vessel_id}", yard.name)
    session.commit()
    return as_dict(p)


@router.post("/{project_id}/start")
def start_docking(project_id: int, body: PortStatusIn, user: User = Depends(manager), session: Session = Depends(get_session)):
    p = _open(session, project_id)
    if p.status != "CONTRACTED":
        raise HTTPException(409, "Choose the yard before the vessel goes into dock.")
    if body.on > today():
        raise HTTPException(422, "The date cannot be in the future.")
    v = session.get(Vessel, p.vessel_id)
    p.status, p.actual_start, v.status = "IN_DOCK", body.on, "DRY_DOCK"
    audit(session, user, "drydock.started", f"vessel {v.vessel_id}", body.on)
    session.commit()
    return as_dict(p)


@router.post("/{project_id}/complete")
def complete_docking(project_id: int, body: PortStatusIn, user: User = Depends(manager), session: Session = Depends(get_session)):
    p = _open(session, project_id)
    if p.status != "IN_DOCK":
        raise HTTPException(409, "Only a vessel in dock can come out.")
    if body.on < p.actual_start or body.on > today():
        raise HTTPException(422, "The date must be between going into dock and today.")
    items = session.scalars(select(DryDockItem).where(DryDockItem.project_id == p.id)).all()
    if any(i.status == "OPEN" for i in items):
        raise HTTPException(409, "Mark every work item done or deferred first.")
    v = session.get(Vessel, p.vessel_id)
    p.status, p.actual_end = "COMPLETED", body.on
    v.status = "ON_HIRE" if active_contract(session, v.vessel_id) else "AVAILABLE"
    if p.bottom_survey:
        v.last_bottom_survey_on = body.on
    actual = sum(i.actual for i in items if i.status == "DONE")
    if actual:
        book_cost(session, v.vessel_id, body.on, "DRYDOCK", actual, p.title, "DRYDOCK", f"dry dock {p.id}", user)
    audit(session, user, "drydock.completed", f"vessel {v.vessel_id}", f"{body.on}, actual {actual:,.2f}")
    session.commit()
    return as_dict(p)
