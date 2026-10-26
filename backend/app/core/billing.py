"""Charter hire for one contract and one month, worked out from the approved daily progress reports.

How each hour of a report is paid:
- operating and transit hours: operating rate
- standby hours: standby rate
- weather hours: as the contract says (weather_billing): operating rate or standby rate. Charter forms differ here
  (BIMCO SUPPLYTIME has one hire rate and no standby rate), so it is a contract term, not a fixed rule.
- breakdown hours: paid at the operating rate out of the maintenance allowance, then off hire (not paid)

The maintenance allowance follows BIMCO SUPPLYTIME 2017 clause 13: so many hours per month, pro rata for part
months. When the contract says it accrues (allowance_accrues), unused hours carry forward to later months.

Mobilization and demobilization fees are added in the month the contract starts or ends.
Days with no approved report are not billed; they are listed so someone chases the report.
"""
import calendar
from datetime import date, timedelta


def month_days(period: str) -> list[str]:
    year, month = map(int, period.split("-"))
    return [date(year, month, d).isoformat() for d in range(1, calendar.monthrange(year, month)[1] + 1)]


def months_between(first: str, last: str) -> list[str]:
    """Every month from the one containing `first` to `last` ("YYYY-MM"), in order."""
    y, m = int(first[:4]), int(first[5:7])
    out = []
    while f"{y:04d}-{m:02d}" <= last:
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def accrual(contract, period: str) -> float:
    """Allowance earned in one month: the monthly hours, pro rata to the contract days in that month."""
    days = month_days(period)
    inside = sum(contract.start_date <= d <= contract.end_date for d in days)
    return contract.breakdown_allowance_hrs * inside / len(days)


def classify(report, allowance_left: float, weather_billing: str) -> dict:
    """One report's hours sorted into paid-at-operating, paid-at-standby, paid breakdown and off hire."""
    paid_bd = min(report.breakdown_hrs, max(allowance_left, 0))
    weather_at_operating = weather_billing == "OPERATING"
    return {
        "operating": report.operating_hrs + report.transit_hrs + (report.weather_hrs if weather_at_operating else 0),
        "standby": report.standby_hrs + (0 if weather_at_operating else report.weather_hrs),
        "breakdown_paid": paid_bd,
        "off_hire": report.breakdown_hrs - paid_bd,
    }


def month_hire(contract, reports, period: str) -> dict:
    """The invoice breakdown. `reports` are every report for the contract (any status, any date)."""
    days = [d for d in month_days(period) if contract.start_date <= d <= contract.end_date]
    by_date = {r.on_date: r for r in reports if r.on_date in days}
    weather_billing = getattr(contract, "weather_billing", "STANDBY")
    accrues = getattr(contract, "allowance_accrues", True)

    # Walk every month of the contract up to this one, so earlier months' use of the allowance is counted.
    approved = sorted((r for r in reports if r.status == "APPROVED" and contract.start_date <= r.on_date <= contract.end_date), key=lambda r: r.on_date)
    hrs = {"operating": 0.0, "standby": 0.0, "breakdown_paid": 0.0, "off_hire": 0.0}
    allowance_left = 0.0
    allowance_this_month = 0.0
    for month in months_between(contract.start_date, period):
        earned = accrual(contract, month)
        allowance_left = (allowance_left if accrues else 0.0) + earned
        if month == period:
            allowance_this_month = allowance_left
        for r in (r for r in approved if r.on_date[:7] == month):
            part = classify(r, allowance_left, weather_billing)
            allowance_left -= part["breakdown_paid"]
            if month == period:
                for k, v in part.items():
                    hrs[k] += v

    lines = [
        {"label": "Operating (incl. transit)" + (" and weather" if weather_billing == "OPERATING" else ""), "days": hrs["operating"] / 24, "rate": contract.operating_rate},
        {"label": "Breakdown within maintenance allowance", "days": hrs["breakdown_paid"] / 24, "rate": contract.operating_rate},
        {"label": "Standby" + (" (incl. weather)" if weather_billing != "OPERATING" else ""), "days": hrs["standby"] / 24, "rate": contract.standby_rate},
        {"label": "Off hire (breakdown over allowance)", "days": hrs["off_hire"] / 24, "rate": 0.0},
    ]
    if contract.mob_fee and contract.start_date in days:
        lines.append({"label": "Mobilization fee", "days": None, "rate": contract.mob_fee})
    if contract.demob_fee and contract.end_date in days:
        lines.append({"label": "Demobilization fee", "days": None, "rate": contract.demob_fee})
    for line in lines:
        # Amount from the exact days; the days are rounded only for display.
        line["amount"] = round(line["rate"] if line["days"] is None else line["days"] * line["rate"], 2)
        line["days"] = None if line["days"] is None else round(line["days"], 3)

    return {
        "period": period,
        "contract_days": len(days),
        "reported_days": sum(1 for r in by_date.values() if r.status == "APPROVED"),
        "pending_dates": sorted(d for d, r in by_date.items() if r.status == "SUBMITTED"),
        "missing_dates": [d for d in days if d not in by_date or by_date[d].status == "REJECTED"],
        "hours": {k: round(v, 2) for k, v in hrs.items()},
        "allowance_hrs": round(allowance_this_month, 2),
        "allowance_left_hrs": round(allowance_left, 2) if days else None,
        "allowance_accrues": accrues,
        "weather_billing": weather_billing,
        "lines": lines,
        "amount": round(sum(line["amount"] for line in lines), 2),
    }


def add_days(iso: str, n: int) -> str:
    return (date.fromisoformat(iso) + timedelta(days=n)).isoformat()
