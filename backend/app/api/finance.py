"""Profit and loss, budgets, the forecast, and the cost ledger. Managers only. The rules are in core/finance.py."""
import re
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import audit, manager
from ..core.finance import budget_vs_actual, forecast, pnl
from ..core.supply import book_cost
from ..db import get_session
from ..models import Budget, CostEntry, User, Vessel, as_dict
from ..schemas import MONTH, BudgetBatchIn, CostIn
from .fleet import get_or_404, today

router = APIRouter(prefix="/api/finance", tags=["finance"], dependencies=[Depends(manager)])


def _month(value: str | None, default: str) -> str:
    value = value or default
    if not re.fullmatch(MONTH[1:-1], value):
        raise HTTPException(422, "Months are written like 2026-10.")
    return value


@router.get("/pnl")
def get_pnl(first: str | None = None, last: str | None = None, session: Session = Depends(get_session)):
    first = _month(first, today()[:7])
    last = _month(last, first)
    if last < first:
        raise HTTPException(422, "The last month must not be before the first.")
    return pnl(session, first, last)


@router.get("/budget")
def get_budget(year: int | None = None, vessel: str | None = None, session: Session = Depends(get_session)):
    return budget_vs_actual(session, year or date.today().year, vessel)


@router.put("/budget")
def set_budget(body: BudgetBatchIn, user: User = Depends(manager), session: Session = Depends(get_session)):
    vessels = {v.vessel_id for v in session.scalars(select(Vessel))}
    existing = {(b.vessel_id, b.period, b.category): b for b in session.scalars(select(Budget).where(
        Budget.period.in_({r.period for r in body.rows})))}
    for r in body.rows:
        if r.vessel_id not in vessels:
            raise HTTPException(422, f"Unknown vessel {r.vessel_id}.")
        row = existing.get((r.vessel_id, r.period, r.category))
        if row is None:
            session.add(Budget(**r.model_dump()))
        else:
            row.amount = r.amount
    audit(session, user, "budget.set", "budget", f"{len(body.rows)} lines")
    session.commit()
    return {"saved": len(body.rows)}


@router.get("/forecast")
def get_forecast(session: Session = Depends(get_session)):
    return forecast(session)


@router.get("/costs")
def list_costs(first: str | None = None, last: str | None = None, vessel: str | None = None, session: Session = Depends(get_session)):
    first = _month(first, today()[:7])
    last = _month(last, first)
    q = select(CostEntry).where(CostEntry.on_date >= f"{first}-01", CostEntry.on_date <= f"{last}-31").order_by(CostEntry.on_date.desc(), CostEntry.id.desc())
    if vessel:
        q = q.where(CostEntry.vessel_id == vessel)
    names = {v.vessel_id: v.name for v in session.scalars(select(Vessel))}
    return [{**as_dict(e), "vessel_name": names[e.vessel_id]} for e in session.scalars(q)]


@router.post("/costs", status_code=201)
def add_cost(body: CostIn, user: User = Depends(manager), session: Session = Depends(get_session)):
    get_or_404(session, Vessel, body.vessel_id, "Vessel")
    if body.on_date > today():
        raise HTTPException(422, "A cost is booked once it is incurred.")
    book_cost(session, body.vessel_id, body.on_date, body.category, body.amount, body.description.strip(), "MANUAL", "", user)
    audit(session, user, "cost.booked", f"vessel {body.vessel_id}", f"{body.category} {body.amount:,.2f}: {body.description.strip()}")
    session.commit()
    return {"ok": True}
