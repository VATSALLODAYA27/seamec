from types import SimpleNamespace as NS

from app.core.billing import month_hire

CONTRACT = NS(start_date="2026-10-01", end_date="2027-09-30", operating_rate=24_000_00.0, standby_rate=12_000_00.0,
              breakdown_allowance_hrs=24.0, mob_fee=50_00_000.0, demob_fee=0.0)


def report(day, op=24.0, sb=0.0, wx=0.0, bd=0.0, tr=0.0, status="APPROVED"):
    return NS(on_date=f"2026-10-{day:02d}", operating_hrs=op, standby_hrs=sb, weather_hrs=wx, breakdown_hrs=bd, transit_hrs=tr, status=status)


def test_full_month_of_operating_days_plus_mobilization():
    calc = month_hire(CONTRACT, [report(d) for d in range(1, 32)], "2026-10")
    assert calc["hours"]["operating"] == 31 * 24
    assert calc["amount"] == 31 * CONTRACT.operating_rate + CONTRACT.mob_fee
    assert calc["missing_dates"] == [] and calc["reported_days"] == 31


def test_breakdown_is_paid_until_the_allowance_then_off_hire():
    # 20 h breakdown on two days: the first 24 h are paid at operating rate, the other 16 h are off hire.
    reports = [report(1, op=4, bd=20), report(2, op=4, bd=20)]
    calc = month_hire(CONTRACT, reports, "2026-10")
    assert calc["hours"] == {"operating": 8, "standby": 0, "breakdown_paid": 24, "off_hire": 16}
    assert calc["amount"] == round(32 / 24 * CONTRACT.operating_rate + CONTRACT.mob_fee, 2)


def test_weather_is_paid_at_standby_and_unapproved_days_are_not_billed():
    reports = [report(1, op=12, wx=12), report(2, status="SUBMITTED"), report(3, status="REJECTED")]
    calc = month_hire(CONTRACT, reports, "2026-10")
    assert calc["hours"]["standby"] == 12
    assert calc["pending_dates"] == ["2026-10-02"]
    assert "2026-10-03" in calc["missing_dates"] and "2026-10-02" not in calc["missing_dates"]
    assert calc["reported_days"] == 1


def test_only_days_inside_the_contract_count():
    short = NS(**{**vars(CONTRACT), "start_date": "2026-10-20", "mob_fee": 0.0})
    calc = month_hire(short, [report(d) for d in range(1, 32)], "2026-10")
    assert calc["contract_days"] == 12 and calc["reported_days"] == 12


def test_unused_allowance_carries_forward_to_the_next_month():
    # October: no breakdown, so 24 h carry into November, which earns 24 more: 48 h are paid there.
    reports = [report(1)] + [NS(**{**vars(report(1)), "on_date": "2026-11-02", "operating_hrs": 0.0, "breakdown_hrs": 24.0}),
                             NS(**{**vars(report(1)), "on_date": "2026-11-03", "operating_hrs": 0.0, "breakdown_hrs": 24.0})]
    calc = month_hire(CONTRACT, reports, "2026-11")
    assert calc["allowance_hrs"] == 48 and calc["hours"]["breakdown_paid"] == 48 and calc["hours"]["off_hire"] == 0


def test_allowance_without_carry_forward_resets_each_month():
    no_carry = NS(**{**vars(CONTRACT), "allowance_accrues": False})
    reports = [NS(**{**vars(report(1)), "on_date": "2026-11-02", "operating_hrs": 0.0, "breakdown_hrs": 24.0}),
               NS(**{**vars(report(1)), "on_date": "2026-11-03", "operating_hrs": 0.0, "breakdown_hrs": 24.0})]
    calc = month_hire(no_carry, reports, "2026-11")
    assert calc["hours"]["breakdown_paid"] == 24 and calc["hours"]["off_hire"] == 24


def test_allowance_is_pro_rata_in_a_part_month():
    # Starts on 16 October: 16 of 31 days, so 24 * 16 / 31 hours of allowance.
    late = NS(**{**vars(CONTRACT), "start_date": "2026-10-16", "mob_fee": 0.0})
    calc = month_hire(late, [report(16, op=0, bd=24)], "2026-10")
    assert calc["hours"]["breakdown_paid"] == round(24 * 16 / 31, 2)


def test_weather_can_be_billed_at_the_operating_rate():
    on_hire = NS(**{**vars(CONTRACT), "weather_billing": "OPERATING", "mob_fee": 0.0})
    calc = month_hire(on_hire, [report(1, op=12, wx=12)], "2026-10")
    assert calc["hours"]["operating"] == 24 and calc["hours"]["standby"] == 0
