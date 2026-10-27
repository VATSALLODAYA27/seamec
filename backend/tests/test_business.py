"""Tenders, off hire and claims, supply, port calls, dry docks, insurance, documents and finance."""
import base64
from types import SimpleNamespace as NS

import pytest

from app.core.billing import month_hire
from app.core.commercial import hours_by_day, straight_off_hire, tender_model
from tests.test_api import client_as, day
from tests.test_billing import CONTRACT, report


def problems(readiness: dict) -> str:
    return " | ".join(p for c in readiness["checks"] for p in c["problems"])


def warnings(readiness: dict) -> str:
    return " | ".join(w for c in readiness["checks"] for w in c["warnings"])


# ---------------- Rules on their own ----------------


def test_off_hire_periods_split_by_day_and_only_other_causes_skip_the_allowance():
    assert hours_by_day("2026-10-01T20:00", "2026-10-03T06:00") == {"2026-10-01": 4.0, "2026-10-02": 24.0, "2026-10-03": 6.0}
    events = [NS(reason="CREW", start_at="2026-10-01T00:00", end_at="2026-10-01T10:00"),
              NS(reason="BREAKDOWN", start_at="2026-10-02T00:00", end_at="2026-10-02T05:00")]
    assert straight_off_hire(events, "2026-10-31T00:00") == {"2026-10-01": 10.0}
    # 10 h breakdown on the 1st, all of it a crew shortage: off hire even with allowance left.
    calc = month_hire(CONTRACT, [report(1, op=14, bd=10)], "2026-10", {"2026-10-01": 10.0})
    assert calc["hours"]["off_hire"] == 10 and calc["hours"]["breakdown_paid"] == 0


def test_tender_margin_and_break_even_rate():
    t = NS(start_date="2026-11-01", end_date="2026-11-30", operating_rate=20.0, standby_rate=10.0, operating_share=0.5, mob_fee=100.0, demob_fee=0.0,
           mob_cost=40.0, extra_daily_cost=1.0, probability=0.5)
    m = tender_model(t, daily_opex=9.0)
    assert (m["days"], m["day_rate"], m["revenue"], m["cost"], m["margin"]) == (30, 15.0, 550.0, 340.0, 210.0)
    # At the break-even operating rate the margin is zero.
    assert tender_model(NS(**{**vars(t), "operating_rate": m["breakeven_rate"]}), 9.0)["margin"] == pytest.approx(0, abs=0.01)


# ---------------- Tenders ----------------


def test_tender_pipeline_win_loss_and_contract_from_a_won_bid():
    manager = client_as("manager")
    out = manager.get("/api/tenders").json()
    stats = out["stats"]
    assert stats["decided"] == 5 and stats["won"] == 2 and stats["win_rate"] == 40.0 and stats["price_gap_pct"] > 0
    clash = next(t for t in out["tenders"] if t["ref"] == "WOC-T-2026-090")
    assert clash["vessel_clash"].startswith("On contract WOC/DSV/2026/014")
    assert client_as("ops").post("/api/tenders", json={}).status_code == 403

    bid = {"ref": "TEST-T-1", "client": "Test Energy", "vessel_type": "OSV", "vessel_id": "SM-AGASTYA", "scope": "Survey support",
           "start_date": day(102), "end_date": day(115), "due_on": day(5), "operating_rate": 900000, "standby_rate": 500000}
    assert "is a DSV" in manager.post("/api/tenders", json=bid).json()["detail"]
    tid = manager.post("/api/tenders", json={**bid, "vessel_id": "SM-DIAMOND"}).json()["id"]
    assert manager.post(f"/api/tenders/{tid}/outcome", json={"status": "WON"}).status_code == 409  # submit first
    manager.post(f"/api/tenders/{tid}/outcome", json={"status": "SUBMITTED"})
    assert manager.post(f"/api/tenders/{tid}/outcome", json={"status": "LOST"}).status_code == 422  # needs a reason
    assert manager.post(f"/api/tenders/{tid}/outcome", json={"status": "WON"}).json()["status"] == "WON"
    # SEAMEC Diamond's radio certificate survey was missed, so the contract checks still refuse it.
    refused = manager.post(f"/api/tenders/{tid}/contract", json={"contract_no": "TE/OSV/001"})
    assert refused.status_code == 409 and "annual survey overdue" in refused.json()["detail"]
    made = manager.post(f"/api/tenders/{tid}/contract", json={"contract_no": "TE/OSV/001", "vessel_id": "SM-VALARCHI"})
    assert made.status_code == 201 and made.json()["operating_rate"] == 900000
    assert manager.post(f"/api/tenders/{tid}/contract", json={"contract_no": "TE/OSV/002"}).status_code == 409


# ---------------- Off hire and claims ----------------


def test_off_hire_is_logged_once_and_ended():
    ops, manager = client_as("ops"), client_as("manager")
    events = ops.get("/api/off-hire").json()
    gallant = next(e for e in events if e["vessel_id"] == "SM-GALLANT")
    assert gallant["status"] == "OPEN" and gallant["uses_allowance"]
    overlap = {"vessel_id": "SM-GALLANT", "start_at": f"{day(0)}T06:00", "reason": "CREW", "description": "Overlapping"}
    assert ops.post("/api/off-hire", json=overlap).status_code == 409
    assert ops.post(f"/api/off-hire/{gallant['id']}/end", json={"end_at": f"{day(-1)}T00:00"}).status_code == 422
    assert ops.post(f"/api/off-hire/{gallant['id']}/end", json={"end_at": f"{day(0)}T05:00"}).json()["status"] == "ENDED"
    assert ops.post(f"/api/off-hire/{gallant['id']}/agree").status_code == 403
    assert manager.post(f"/api/off-hire/{gallant['id']}/agree").json()["status"] == "AGREED"


def test_client_raises_a_claim_only_on_its_own_contracts_and_the_office_decides():
    client, manager = client_as("woc.rep"), client_as("manager")
    claim = {"contract_no": "WOC/DSV/2026/014", "kind": "DIVING", "period": day(0)[:7], "description": "Bell run delayed 4 h by winch fault",
             "amount_claimed": 500000}
    assert client.post("/api/client/claims", json={**claim, "contract_no": "BEL/MSV/2026/003"}).status_code == 404
    cid = client.post("/api/client/claims", json=claim).json()["id"]
    assert any(c["id"] == cid for c in client.get("/api/client/claims").json())
    over = {"status": "ACCEPTED", "amount_agreed": 600000, "note": "Agreed"}
    assert manager.post(f"/api/claims/{cid}/decide", json=over).status_code == 422
    assert manager.post(f"/api/claims/{cid}/decide", json={**over, "amount_agreed": 300000}).json()["status"] == "ACCEPTED"
    # The accepted credit comes off this month's revenue in the P&L.
    pnl = manager.get("/api/finance/pnl").json()
    princess = next(c for c in pnl["contracts"] if c["contract_no"] == "WOC/DSV/2026/014")
    assert princess["claims"] >= 300000 and princess["revenue"] == pytest.approx(princess["hire"] - princess["claims"], abs=0.01)


# ---------------- Supply ----------------


def test_job_waits_for_a_spare_and_receiving_the_order_releases_it():
    ops, manager = client_as("ops"), client_as("manager")
    paladin = ops.get("/api/readiness/SM-PALADIN").json()
    assert "Dive compressor valve kit for Dive air compressors: none on board" in problems(paladin)
    assert "awaiting Dive compressor valve kit" in problems(paladin)
    job = next(j for j in ops.get("/api/maintenance", params={"vessel": "SM-PALADIN"}).json() if j["awaiting_spares"])
    po_no = job["awaiting_spares"][0]["po_no"]
    po = next(p for p in ops.get("/api/purchase-orders").json() if p["po_no"] == po_no)
    assert po["status"] == "ORDERED"
    line = po["lines"][0]
    assert ops.post(f"/api/purchase-orders/{po_no}/receive", json={"lines": {str(line["id"]): 3}}).status_code == 422  # more than ordered
    ops.post(f"/api/purchase-orders/{po_no}/receive", json={"lines": {str(line["id"]): 2}})
    after = next(j for j in ops.get("/api/maintenance", params={"vessel": "SM-PALADIN"}).json() if j["id"] == job["id"])
    assert after["awaiting_spares"] == []
    # The 2 kits went straight to the waiting job, so the vessel is still at 0 of 2: still short, but no longer waiting.
    paladin = ops.get("/api/readiness/SM-PALADIN").json()
    assert "awaiting" not in problems(paladin) and "valve kit for Dive air compressors: none on board" in problems(paladin)
    costs = manager.get("/api/finance/costs", params={"vessel": "SM-PALADIN"}).json()
    assert any(c["ref"] == po_no and c["category"] == "SPARES" and c["amount"] == po["total"] for c in costs)


def test_requesting_a_spare_issues_it_from_stock_or_blocks_the_job():
    ops = client_as("ops")
    parts = {p["part_no"]: p for p in ops.get("/api/parts").json()}
    job = next(j for j in ops.get("/api/maintenance", params={"vessel": "SM-PRINCESS"}).json() if j["equipment"].startswith("Dive air"))
    stock = {s["part_no"]: s for s in ops.get("/api/stock", params={"location": "SM-PRINCESS"}).json()}
    issued = ops.post(f"/api/maintenance/jobs/{job['id']}/spares", json={"part_id": parts["DAC-FLT-02"]["id"], "qty": 1}).json()
    assert issued["status"] == "ISSUED"
    left = {s["part_no"]: s for s in ops.get("/api/stock", params={"location": "SM-PRINCESS"}).json()}["DAC-FLT-02"]["qty"]
    assert left == stock["DAC-FLT-02"]["qty"] - 1
    waiting = ops.post(f"/api/maintenance/jobs/{job['id']}/spares", json={"part_id": parts["DAC-VK-01"]["id"], "qty": 50}).json()
    assert waiting["status"] == "WAITING"
    assert next(j for j in ops.get("/api/maintenance", params={"vessel": "SM-PRINCESS"}).json() if j["id"] == job["id"])["awaiting_spares"]
    order = ops.post(f"/api/maintenance/spares/{waiting['id']}/order").json()
    assert order["status"] == "DRAFT" and order["deliver_to"] == "SM-PRINCESS"
    assert ops.post(f"/api/maintenance/spares/{waiting['id']}/order").status_code == 409


def test_transfer_from_shore_books_the_cost_and_cannot_overdraw():
    ops, manager = client_as("ops"), client_as("manager")
    shore = {s["part_no"]: s for s in ops.get("/api/stock", params={"location": "SHORE"}).json()}["FIR-DET-01"]
    body = {"part_id": shore["part_id"], "from_location": "SHORE", "to_location": "SM-DIAMOND", "qty": shore["qty"] + 1}
    assert ops.post("/api/stock/transfer", json=body).status_code == 409
    assert ops.post("/api/stock/transfer", json={**body, "qty": 2}).status_code == 200
    costs = manager.get("/api/finance/costs", params={"vessel": "SM-DIAMOND"}).json()
    assert any(c["source"] == "TRANSFER" and c["amount"] == 2 * shore["unit_cost"] for c in costs)


def test_purchase_order_approval_limit_and_reorder():
    manager, admin = client_as("manager"), client_as("admin")
    big = next(p for p in manager.get("/api/purchase-orders").json() if p["needs_admin"] and p["status"] == "DRAFT")
    assert manager.post(f"/api/purchase-orders/{big['po_no']}/approve").status_code == 403
    assert admin.post(f"/api/purchase-orders/{big['po_no']}/approve").json()["status"] == "APPROVED"
    vendors = manager.get("/api/vendors").json()
    unapproved = next(v for v in vendors if not v["approved"])
    po = {"vendor_id": unapproved["id"], "deliver_to": "SHORE", "lines": [{"description": "Hydraulic service", "qty": 1, "unit_price": 1000}]}
    assert manager.post("/api/purchase-orders", json=po).status_code == 409
    reorder = manager.get("/api/stock/reorder").json()
    assert any(r["location"] == "SHORE" and r["part_no"] == "GEN-INJ-01" and r["to_order"] > 0 for r in reorder)
    made = manager.post("/api/stock/reorder", json={"location": "SHORE"}).json()
    assert made["orders"]
    assert not any(r["location"] == "SHORE" and r["part_no"] == "GEN-INJ-01" and r["to_order"] > 0 for r in manager.get("/api/stock/reorder").json())


# ---------------- Port calls, dry dock, insurance ----------------


def test_port_call_closes_only_with_a_full_final_account_and_books_the_cost():
    ops, manager = client_as("ops"), client_as("manager")
    gallant = next(c for c in ops.get("/api/port-calls").json() if c["vessel_id"] == "SM-GALLANT")
    assert gallant["status"] == "SAILED" and gallant["fda_total"] is None
    assert "every line" in manager.post(f"/api/port-calls/{gallant['id']}/close").json()["detail"]
    lines = [{**line, "fda": line["fda"] if line["fda"] is not None else 20000} for line in gallant["lines"]]
    ops.put(f"/api/port-calls/{gallant['id']}/account", json={"lines": lines, "advance_paid": gallant["advance_paid"]})
    updated = next(c for c in ops.get("/api/port-calls").json() if c["id"] == gallant["id"])
    assert updated["fda_total"] == pytest.approx(sum(line["fda"] for line in lines)) and any(line["over"] for line in updated["lines"])
    assert ops.post(f"/api/port-calls/{gallant['id']}/close").status_code == 403
    assert manager.post(f"/api/port-calls/{gallant['id']}/close").json()["status"] == "CLOSED"
    costs = manager.get("/api/finance/costs", params={"vessel": "SM-GALLANT", "first": day(-40)[:7], "last": day(0)[:7]}).json()
    assert any(c["source"] == "PORT_CALL" and c["amount"] == pytest.approx(updated["fda_total"]) for c in costs)


def test_dry_dock_ranks_yards_on_full_cost_and_completion_records_the_bottom_survey():
    manager = client_as("manager")
    projects = {p["vessel_id"]: p for p in manager.get("/api/drydock").json()}
    paladin = projects["SM-PALADIN"]
    cheapest_price = min(paladin["quotes"], key=lambda q: q["price"])
    assert paladin["quotes"][0]["rank"] == 1 and paladin["quotes"][0]["evaluated"] <= cheapest_price["evaluated"]
    sm3 = projects["SM-III"]
    assert sm3["status"] == "IN_DOCK" and sm3["yard"].startswith("Kerala")
    assert "work item" in manager.post(f"/api/drydock/{sm3['id']}/complete", json={"on": day(0)}).json()["detail"]
    for item in sm3["items"]:
        if item["status"] == "OPEN":
            manager.put(f"/api/drydock/items/{item['id']}", json={**{k: item[k] for k in ("category", "description", "budget")}, "actual": item["budget"], "status": "DONE"})
    assert manager.post(f"/api/drydock/{sm3['id']}/complete", json={"on": day(0)}).json()["status"] == "COMPLETED"
    vessel = manager.get("/api/vessels/SM-III").json()
    assert vessel["status"] == "AVAILABLE" and vessel["last_bottom_survey_on"] == day(0)
    assert "The vessel is in dry dock." not in problems(manager.get("/api/readiness/SM-III").json())
    assert any(c["source"] == "DRYDOCK" for c in manager.get("/api/finance/costs", params={"vessel": "SM-III"}).json())


def test_insurance_cover_counts_for_readiness_and_a_settled_claim_books_the_recovery():
    manager = client_as("manager")
    assert "No Hull and machinery cover in force" in problems(manager.get("/api/readiness/SM-DIAMOND").json())
    assert "Hull and machinery (Oceanic Hull Underwriters (demo)) expires" in warnings(manager.get("/api/readiness/SM-GLORIOUS").json())
    claim = next(c for c in manager.get("/api/insurance/claims").json() if c["status"] == "SUBMITTED")
    assert manager.post(f"/api/insurance/claims/{claim['id']}/status", json={"status": "SETTLED", "on": day(0), "recovered": claim["amount"] + 1}).status_code == 422
    manager.post(f"/api/insurance/claims/{claim['id']}/status", json={"status": "SETTLED", "on": day(0), "recovered": 5000000})
    costs = manager.get("/api/finance/costs", params={"vessel": claim["vessel_id"]}).json()
    assert any(c["source"] == "INSURANCE" and c["amount"] == -5000000 for c in costs)


# ---------------- Documents ----------------


def test_documents_are_versioned_typed_and_downloaded_as_attachments():
    manager, ops = client_as("manager"), client_as("ops")
    body = {"entity": "contract", "entity_key": "TC/GALLANT/2026/02", "kind": "CHARTER_PARTY", "title": "Charter party", "filename": "cp.pdf",
            "content_base64": base64.b64encode(b"%PDF-1.4 demo").decode()}
    assert manager.post("/api/documents", json={**body, "filename": "cp.html"}).status_code == 422
    assert ops.post("/api/documents", json=body).status_code == 403
    first = manager.post("/api/documents", json=body).json()
    second = manager.post("/api/documents", json=body).json()
    assert (first["version"], second["version"]) == (1, 2)
    file = ops.get(f"/api/documents/{second['id']}/file")
    assert file.content == b"%PDF-1.4 demo" and file.headers["content-disposition"].startswith("attachment")
    gallant = next(c for c in ops.get("/api/contracts").json() if c["contract_no"] == "TC/GALLANT/2026/02")
    assert gallant["cp_on_file"]


# ---------------- Finance ----------------


def test_pnl_adds_up_and_matches_the_dashboard():
    manager = client_as("manager")
    pnl = manager.get("/api/finance/pnl").json()
    assert pnl["totals"]["profit"] == pytest.approx(sum(v["profit"] for v in pnl["vessels"]), abs=1)
    assert pnl["totals"]["cost"] == pytest.approx(sum(v["cost"] for v in pnl["vessels"]), abs=1)
    dash = manager.get("/api/dashboard").json()
    assert dash["kpis"]["pnl_mtd"] == pytest.approx(pnl["totals"]["profit"], abs=1)
    assert {a["label"] for a in dash["attention"]} >= {"Critical spares below minimum", "Vessels without H&M or P&I cover"}
    assert client_as("ops").get("/api/finance/pnl").status_code == 403
    assert manager.get("/api/finance/pnl", params={"first": "2026-13"}).status_code == 422


def test_budget_forecast_and_manual_costs():
    manager = client_as("manager")
    budget = manager.get("/api/finance/budget").json()
    running = next(line for line in budget["lines"] if line["category"] == "RUNNING")
    assert running["budget_year"] > 0 and running["actual_to_date"] > 0 and len(running["months"]) == 12
    forecast = manager.get("/api/finance/forecast").json()
    assert len(forecast["months"]) == 12 and forecast["totals"]["pipeline"] > 0 and forecast["months"][0]["running"] > 0
    assert manager.post("/api/finance/costs", json={"vessel_id": "SM-II", "on_date": day(1), "category": "OTHER", "amount": 1, "description": "Future"}).status_code == 422
    assert manager.post("/api/finance/costs", json={"vessel_id": "SM-II", "on_date": day(0), "category": "OTHER", "amount": 125000, "description": "Survey fee"}).status_code == 201
    saved = manager.put("/api/finance/budget", json={"rows": [{"vessel_id": "SM-II", "period": day(0)[:7], "category": "OTHER", "amount": 999000}]})
    assert saved.json()["saved"] == 1
    other = next(line for line in manager.get("/api/finance/budget", params={"vessel": "SM-II"}).json()["lines"] if line["category"] == "OTHER")
    assert next(m for m in other["months"] if m["period"] == day(0)[:7])["budget"] == 999000
