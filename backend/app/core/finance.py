"""Profit and loss per vessel and per contract, budget against actual, and a 12-month forecast.

A vessel's cost on a day:
- running cost (Vessel.daily_opex): crew, victualling, lubes, management
- insurance: each policy's premium spread evenly over its days; a fleet-wide policy is shared equally by the vessels
- booked costs (CostEntry): spares, port calls, dry docks, insurance recoveries and anything entered by hand
A day's running cost and insurance belong to the contract the vessel was on that day; other days are idle cost.
Revenue is charter hire: the invoice where one has been drafted, otherwise worked out from the approved daily
reports. An amount accepted on a charterer's performance claim comes off the revenue of the month it concerns.

Everything is built from one set of facts, (vessel, contract, month, category) -> amount, so the P&L, the budget
comparison and the dashboard always agree.
"""
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (Budget, Contract, CostEntry, DailyReport, DryDockItem, DryDockProject, HireInvoice, InsurancePolicy, OffHireEvent,
                      PerformanceClaim, Tender, Vessel)
from .billing import hire_lines, hire_months, month_days, months_between
from .commercial import straight_off_hire, tender_model

COSTS = ("RUNNING", "INSURANCE", "SPARES", "PORT", "DRYDOCK", "OTHER")
BOOKED = ("SPARES", "PORT", "DRYDOCK", "INSURANCE", "OTHER")  # categories a CostEntry can have
BUDGET_LINES = ("REVENUE",) + COSTS
DEFAULT_OPERATING_SHARE = 0.9  # for a contract with no approved reports yet


def _days(first: date, last: date) -> list[date]:
    return [first + timedelta(days=i) for i in range((last - first).days + 1)]


def now_minute() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M")


class Premiums:
    """Insurance premium per vessel per day."""

    def __init__(self, policies: list[InsurancePolicy], fleet_size: int):
        self.rows = [(p.vessel_id, p.start_date, p.end_date,
                      p.premium / ((date.fromisoformat(p.end_date) - date.fromisoformat(p.start_date)).days + 1) / (1 if p.vessel_id else max(fleet_size, 1)))
                     for p in policies]

    def on(self, vessel_id: str, day: str) -> float:
        return sum(rate for vid, start, end, rate in self.rows if start <= day <= end and vid in (None, vessel_id))


def contract_on(contracts: list[Contract], day: str) -> Contract | None:
    return next((c for c in contracts if c.start_date <= day <= c.end_date), None)


def hire_by_contract(session: Session, contracts: list[Contract], last: str) -> dict[str, dict[str, dict]]:
    """For each contract, every month up to `last`: hours and the hire amount (the invoice's where one exists)."""
    nos = [c.contract_no for c in contracts]
    reports, events = defaultdict(list), defaultdict(list)
    for r in session.scalars(select(DailyReport).where(DailyReport.contract_no.in_(nos))):
        reports[r.contract_no].append(r)
    for e in session.scalars(select(OffHireEvent).where(OffHireEvent.contract_no.in_(nos))):
        events[e.contract_no].append(e)
    invoiced = {(i.contract_no, i.period): i.amount for i in session.scalars(select(HireInvoice).where(HireInvoice.contract_no.in_(nos)))}
    now = now_minute()
    out = {}
    for c in contracts:
        months = hire_months(c, reports[c.contract_no], last, straight_off_hire(events[c.contract_no], now))
        out[c.contract_no] = {
            m: {"hours": v["hours"],
                "amount": invoiced.get((c.contract_no, m), round(sum(line["amount"] for line in hire_lines(c, m, v["hours"])), 2))}
            for m, v in months.items()
        }
    return out


def facts(session: Session, first: str, last: str) -> tuple[Counter, Counter]:
    """Amounts by (vessel_id, contract_no or None, month, category) from month `first` to month `last`, up to
    yesterday, and paid hire hours by (vessel_id, month). Categories: REVENUE, CLAIMS and the cost lines."""
    today = date.today()
    start = date.fromisoformat(f"{first}-01")
    end = min(date.fromisoformat(month_days(last)[-1]), today - timedelta(days=1))
    amounts, paid_hours = Counter(), Counter()
    vessels = session.scalars(select(Vessel)).all()
    contracts = session.scalars(select(Contract).where(Contract.start_date <= end.isoformat(), Contract.end_date >= start.isoformat())).all()
    by_vessel = defaultdict(list)
    for c in contracts:
        by_vessel[c.vessel_id].append(c)

    # Revenue: hire per contract month, less accepted performance claims.
    for no, months in hire_by_contract(session, contracts, min(last, today.isoformat()[:7])).items():
        vid = next(c.vessel_id for c in contracts if c.contract_no == no)
        for m, v in months.items():
            if first <= m <= last:
                amounts[(vid, no, m, "REVENUE")] += v["amount"]
                paid_hours[(vid, m)] += v["hours"]["operating"] + v["hours"]["standby"] + v["hours"]["breakdown_paid"]
    vessel_of = {c.contract_no: c.vessel_id for c in contracts}
    for claim in session.scalars(select(PerformanceClaim).where(PerformanceClaim.status == "ACCEPTED", PerformanceClaim.period >= first,
                                                                PerformanceClaim.period <= last)):
        vid = vessel_of.get(claim.contract_no) or session.get(Contract, claim.contract_no).vessel_id
        amounts[(vid, claim.contract_no, claim.period, "CLAIMS")] += claim.amount_agreed or 0

    # Running cost and insurance, day by day, to the contract of the day.
    premiums = Premiums(session.scalars(select(InsurancePolicy)).all(), len(vessels))
    for v in vessels:
        for d in _days(start, end):
            day = d.isoformat()
            c = contract_on(by_vessel[v.vessel_id], day)
            key = (v.vessel_id, c.contract_no if c else None, day[:7])
            amounts[key + ("RUNNING",)] += v.daily_opex
            amounts[key + ("INSURANCE",)] += premiums.on(v.vessel_id, day)

    for e in session.scalars(select(CostEntry).where(CostEntry.on_date >= start.isoformat(), CostEntry.on_date <= end.isoformat())):
        amounts[(e.vessel_id, e.contract_no, e.on_date[:7], e.category)] += e.amount
    return amounts, paid_hours


def _row(parts: Counter) -> dict:
    revenue = parts["REVENUE"] - parts["CLAIMS"]
    cost = sum(parts[c] for c in COSTS)
    return {"hire": round(parts["REVENUE"], 2), "claims": round(parts["CLAIMS"], 2), "revenue": round(revenue, 2),
            **{c.lower(): round(parts[c], 2) for c in COSTS}, "cost": round(cost, 2), "profit": round(revenue - cost, 2),
            "margin_pct": round(100 * (revenue - cost) / revenue, 1) if revenue > 0 else None}


def pnl(session: Session, first: str, last: str) -> dict:
    amounts, paid_hours = facts(session, first, last)
    vessels = session.scalars(select(Vessel).order_by(Vessel.vessel_type, Vessel.name)).all()
    names = {v.vessel_id: v.name for v in vessels}
    by_vessel, idle, by_contract, total = defaultdict(Counter), defaultdict(Counter), defaultdict(Counter), Counter()
    for (vid, no, _, cat), amount in amounts.items():
        by_vessel[vid][cat] += amount
        total[cat] += amount
        if no:
            by_contract[no][cat] += amount
        elif cat in ("RUNNING", "INSURANCE"):
            idle[vid][cat] += amount
    contracts = {c.contract_no: c for c in session.scalars(select(Contract).where(Contract.contract_no.in_(list(by_contract))))}
    hours = Counter()
    for (vid, _), h in paid_hours.items():
        hours[vid] += h
    return {
        "first": first, "last": last,
        "vessels": [{"vessel_id": v.vessel_id, "name": v.name, "vessel_type": v.vessel_type, "status": v.status, **_row(by_vessel[v.vessel_id]),
                     "idle_cost": round(sum(idle[v.vessel_id].values()), 2), "paid_hours": round(hours[v.vessel_id], 2)} for v in vessels],
        "contracts": sorted(({"contract_no": no, "client": contracts[no].client, "vessel_id": contracts[no].vessel_id,
                              "vessel_name": names[contracts[no].vessel_id], "status": contracts[no].status, **_row(parts)}
                             for no, parts in by_contract.items()), key=lambda r: -r["revenue"]),
        "totals": _row(total),
    }


def budget_vs_actual(session: Session, year: int, vessel_id: str | None = None) -> dict:
    first, last = f"{year}-01", f"{year}-12"
    amounts, _ = facts(session, first, last)
    actual = defaultdict(Counter)  # month -> category -> amount
    for (vid, _, month, cat), amount in amounts.items():
        if vessel_id in (None, vid):
            actual[month]["REVENUE" if cat in ("REVENUE", "CLAIMS") else cat] += -amount if cat == "CLAIMS" else amount
    q = select(Budget).where(Budget.period >= first, Budget.period <= last)
    if vessel_id:
        q = q.where(Budget.vessel_id == vessel_id)
    budget = defaultdict(Counter)
    for b in session.scalars(q):
        budget[b.period][b.category] += b.amount
    months = months_between(first, last)
    done = date.today().isoformat()[:7]
    lines = []
    for cat in BUDGET_LINES:
        by_month = [{"period": m, "budget": round(budget[m][cat], 2), "actual": round(actual[m][cat], 2) if m <= done else None} for m in months]
        to_date_budget = sum(r["budget"] for r in by_month if r["period"] <= done)
        to_date_actual = sum(r["actual"] or 0 for r in by_month if r["period"] <= done)
        # For revenue more is better; for a cost less is better. Variance is signed so positive is always favourable.
        variance = to_date_actual - to_date_budget if cat == "REVENUE" else to_date_budget - to_date_actual
        lines.append({"category": cat, "budget_year": round(sum(r["budget"] for r in by_month), 2), "budget_to_date": round(to_date_budget, 2),
                      "actual_to_date": round(to_date_actual, 2), "variance": round(variance, 2), "months": by_month})
    return {"year": year, "vessel_id": vessel_id, "through": done, "lines": lines}


def forecast(session: Session, horizon: int = 12) -> dict:
    """The next `horizon` months from today: contracted hire at each contract's recent earning rate, the tender
    pipeline weighted by its chance of winning, running cost, insurance, planned dry docks, and other costs at
    their last 90 days' rate."""
    today = date.today()
    months = months_between(today.isoformat()[:7], (today.replace(day=1) + timedelta(days=31 * (horizon - 1))).isoformat()[:7])[:horizon]
    vessels = session.scalars(select(Vessel)).all()
    opex = {v.vessel_id: v.daily_opex for v in vessels}
    contracts = session.scalars(select(Contract).where(Contract.status == "ACTIVE", Contract.end_date >= today.isoformat())).all()
    hire = hire_by_contract(session, contracts, today.isoformat()[:7])
    premiums = Premiums(session.scalars(select(InsurancePolicy)).all(), len(vessels))
    since = (today - timedelta(days=90)).isoformat()
    other_per_day = sum(e.amount for e in session.scalars(select(CostEntry).where(
        CostEntry.on_date >= since, CostEntry.category.in_(("SPARES", "PORT", "OTHER"))))) / 90

    def earning_per_day(c: Contract) -> float:
        recent = [v["hours"] for m, v in sorted(hire[c.contract_no].items())[-3:]]
        hrs = {k: sum(h[k] for h in recent) for k in ("operating", "standby", "breakdown_paid", "off_hire")}
        total = sum(hrs.values())
        if not total:
            return DEFAULT_OPERATING_SHARE * c.operating_rate + (1 - DEFAULT_OPERATING_SHARE) * c.standby_rate
        return ((hrs["operating"] + hrs["breakdown_paid"]) * c.operating_rate + hrs["standby"] * c.standby_rate) / total

    rates = {c.contract_no: earning_per_day(c) for c in contracts}
    tenders = [(t, tender_model(t, opex.get(t.vessel_id, 0))) for t in session.scalars(select(Tender).where(Tender.status.in_(("DRAFT", "SUBMITTED"))))]
    docks = []
    for p in session.scalars(select(DryDockProject).where(DryDockProject.status != "COMPLETED")):
        budget = sum(i.budget for i in session.scalars(select(DryDockItem).where(DryDockItem.project_id == p.id)))
        days = _days(date.fromisoformat(p.planned_start), date.fromisoformat(p.planned_end))
        docks.append(({d.isoformat() for d in days}, budget / len(days)))
    budgets = Counter()
    for b in session.scalars(select(Budget).where(Budget.period >= months[0], Budget.period <= months[-1])):
        budgets[(b.period, "REVENUE" if b.category == "REVENUE" else "COST")] += b.amount

    rows = []
    for m in months:
        days = [d for d in month_days(m) if d >= today.isoformat()]
        row = Counter()
        for c in contracts:
            on = [d for d in days if c.start_date <= d <= c.end_date]
            row["contracted"] += len(on) * rates[c.contract_no] + (c.demob_fee if c.end_date in on else 0)
        for t, model in tenders:
            on = [d for d in days if t.start_date <= d <= t.end_date]
            row["pipeline"] += t.probability * (len(on) * model["day_rate"] + (t.mob_fee if t.start_date in on else 0) + (t.demob_fee if t.end_date in on else 0))
        for v in vessels:
            row["running"] += len(days) * v.daily_opex
            row["insurance"] += sum(premiums.on(v.vessel_id, d) for d in days)
        row["drydock"] = sum(per_day * len(dates.intersection(days)) for dates, per_day in docks)
        row["other"] = other_per_day * len(days)
        revenue = row["contracted"] + row["pipeline"]
        cost = row["running"] + row["insurance"] + row["drydock"] + row["other"]
        rows.append({"period": m, "days": len(days), **{k: round(row[k], 2) for k in ("contracted", "pipeline", "running", "insurance", "drydock", "other")},
                     "revenue": round(revenue, 2), "cost": round(cost, 2), "profit": round(revenue - cost, 2),
                     "budget_revenue": round(budgets[(m, "REVENUE")], 2), "budget_cost": round(budgets[(m, "COST")], 2)})
    totals = {k: round(sum(r[k] for r in rows), 2) for k in ("contracted", "pipeline", "revenue", "cost", "profit")}
    return {"months": rows, "totals": totals}
