"""Tender margin modelling, win-loss figures, and splitting off-hire periods into hours per day.

Margin model for a bid:
  revenue = days x (operating share x operating rate + (1 - share) x standby rate) + mobilization + demobilization fees
  cost    = days x (vessel running cost per day + project cost per day) + our mobilization cost
The break-even operating rate is the operating rate at which that margin is zero, with the standby rate unchanged.
"""
from collections import defaultdict
from datetime import date, datetime, timedelta

# Off-hire reasons, and whether they use the contract's maintenance allowance (SUPPLYTIME 2017 cl. 13) first.
OFF_HIRE_REASONS = {"BREAKDOWN": True, "MAINTENANCE": True, "CREW": False, "DOCUMENTS": False, "OTHER": False}


def tender_model(t, daily_opex: float | None) -> dict:
    """`daily_opex` None means the vessel's running cost is not on file: revenue only, no margin."""
    days = (date.fromisoformat(t.end_date) - date.fromisoformat(t.start_date)).days + 1
    share = t.operating_share
    day_rate = share * t.operating_rate + (1 - share) * t.standby_rate
    fees = t.mob_fee + t.demob_fee
    revenue = days * day_rate + fees
    if daily_opex is None:
        return {"days": days, "day_rate": round(day_rate, 2), "revenue": round(revenue, 2), "cost": None, "margin": None, "margin_pct": None,
                "breakeven_rate": None, "expected_margin": None}
    cost = days * (daily_opex + t.extra_daily_cost) + t.mob_cost
    margin = revenue - cost
    breakeven = (cost - fees - days * (1 - share) * t.standby_rate) / (days * share) if share > 0 else None
    return {
        "days": days, "day_rate": round(day_rate, 2), "revenue": round(revenue, 2), "cost": round(cost, 2), "margin": round(margin, 2),
        "margin_pct": round(100 * margin / revenue, 1) if revenue else None,
        "breakeven_rate": round(breakeven, 2) if breakeven is not None else None,
        "expected_margin": round(margin * t.probability, 2),
    }


def win_loss(tenders: list, models: dict[int, dict]) -> dict:
    """Win rate by number and by value over decided bids, by client, and how far off the winning price lost bids were."""
    decided = [t for t in tenders if t.status in ("WON", "LOST")]
    won = [t for t in decided if t.status == "WON"]

    def rate(group):
        return round(100 * sum(t.status == "WON" for t in group) / len(group), 1) if group else None

    by_client = defaultdict(list)
    for t in decided:
        by_client[t.client].append(t)
    gaps = [100 * (t.operating_rate - t.winning_rate) / t.winning_rate for t in decided if t.status == "LOST" and t.winning_rate]
    value = lambda group: round(sum(models[t.id]["revenue"] for t in group), 2)
    open_bids = [t for t in tenders if t.status in ("DRAFT", "SUBMITTED")]
    return {
        "decided": len(decided), "won": len(won), "win_rate": rate(decided),
        "won_value": value(won), "lost_value": value([t for t in decided if t.status == "LOST"]),
        "value_win_rate": round(100 * value(won) / value(decided), 1) if decided and value(decided) else None,
        "pipeline_value": value(open_bids),
        "weighted_pipeline": round(sum(models[t.id]["revenue"] * t.probability for t in open_bids), 2),
        "price_gap_pct": round(sum(gaps) / len(gaps), 1) if gaps else None,  # our rate above the winner's, on average
        "by_client": sorted(({"client": c, "bids": len(g), "won": sum(t.status == "WON" for t in g), "win_rate": rate(g)} for c, g in by_client.items()),
                            key=lambda r: -r["bids"]),
    }


def hours_by_day(start_at: str, end_at: str) -> dict[str, float]:
    """Split a period ("YYYY-MM-DDTHH:MM") into hours on each calendar day."""
    start, end = datetime.fromisoformat(start_at), datetime.fromisoformat(end_at)
    out: dict[str, float] = {}
    while start < end:
        midnight = datetime.combine(start.date() + timedelta(days=1), datetime.min.time())
        upto = min(end, midnight)
        out[start.date().isoformat()] = out.get(start.date().isoformat(), 0.0) + (upto - start).total_seconds() / 3600
        start = upto
    return out


def straight_off_hire(events: list, now: str) -> dict[str, float]:
    """Hours per day that are off hire for a reason the maintenance allowance does not cover."""
    out: dict[str, float] = defaultdict(float)
    for e in events:
        if not OFF_HIRE_REASONS.get(e.reason, False):
            for day, hrs in hours_by_day(e.start_at, e.end_at or now).items():
                out[day] += hrs
    return {d: min(h, 24.0) for d, h in out.items()}

