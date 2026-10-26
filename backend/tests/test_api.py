from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.db import SessionLocal, migrate
from app.main import app
from scripts.seed import seed, seed_users

PASSWORDS = {"admin": "Seamec@Admin26", "ops": "dsv-ops-2026", "manager": "fleet-mgr-2026", "woc.rep": "client-rep-2026"}


@pytest.fixture(scope="module", autouse=True)
def data():
    migrate()
    with SessionLocal() as session:
        seed_users(session)
        seed(session)


def client_as(username: str) -> TestClient:
    c = TestClient(app)
    assert c.post("/api/auth/login", json={"username": username, "password": PASSWORDS[username]}).status_code == 200
    return c


def day(offset: int) -> str:
    return (date.today() + timedelta(days=offset)).isoformat()


REPORT = {"vessel_id": "SM-DIAMOND", "location": "Mumbai anchorage", "operating_hrs": 0, "standby_hrs": 24, "weather_hrs": 0,
          "breakdown_hrs": 0, "transit_hrs": 0, "work_done": "Idle, awaiting charter"}


def test_signed_out_is_refused():
    assert TestClient(app).get("/api/dashboard").status_code == 401


def test_dashboard_sees_the_seeded_fleet():
    body = client_as("ops").get("/api/dashboard").json()
    k = body["kpis"]
    assert k["vessels"] == 10 and k["on_hire"] == 6 and k["dry_dock"] == 1
    assert k["certs_expired"] == 2 and k["reports_pending"] > 0 and k["revenue_mtd"] > 0
    paladin = next(v for v in body["fleet"] if v["vessel_id"] == "SM-PALADIN")
    assert paladin["missing_reports_7d"] == 1


def test_report_must_cover_24_hours_and_only_once():
    ops = client_as("ops")
    assert ops.post("/api/reports", json={**REPORT, "on_date": day(-1), "standby_hrs": 20}).status_code == 422
    assert ops.post("/api/reports", json={**REPORT, "on_date": day(1)}).status_code == 422
    first = ops.post("/api/reports", json={**REPORT, "on_date": day(-1)})
    assert first.status_code == 201 and first.json()["contract_no"] is None
    assert ops.post("/api/reports", json={**REPORT, "on_date": day(-1)}).status_code == 409


def test_only_a_manager_approves_and_a_rejected_report_can_be_filed_again():
    ops, manager = client_as("ops"), client_as("manager")
    rid = ops.post("/api/reports", json={**REPORT, "on_date": day(-2)}).json()["id"]
    assert ops.post(f"/api/reports/{rid}/approve").status_code == 403
    assert manager.post(f"/api/reports/{rid}/reject", json={"reason": ""}).status_code == 422
    assert manager.post(f"/api/reports/{rid}/reject", json={"reason": "Fuel figure missing"}).status_code == 200
    again = ops.post("/api/reports", json={**REPORT, "on_date": day(-2), "fuel_rob": 310})
    assert again.status_code == 201
    assert manager.post(f"/api/reports/{again.json()['id']}/approve").json()["status"] == "APPROVED"


def test_contract_rules_expired_certificate_and_double_booking():
    admin = client_as("admin")
    new = {"contract_no": "TEST/001", "client": "Test client", "vessel_id": "SM-AGASTYA", "scope": "Diving support", "start_date": day(5),
           "end_date": day(100), "operating_rate": 2_000_000, "standby_rate": 1_000_000, "breakdown_allowance_hrs": 24}
    refused = admin.post("/api/contracts", json=new)
    assert refused.status_code == 409 and "Diving System" in refused.json()["detail"]
    unsurveyed = admin.post("/api/contracts", json={**new, "vessel_id": "SM-DIAMOND"})
    assert unsurveyed.status_code == 409 and "annual survey overdue" in unsurveyed.json()["detail"]
    assert admin.post("/api/contracts", json={**new, "vessel_id": "SM-PRINCESS"}).status_code == 409  # already on hire
    assert client_as("manager").post("/api/contracts", json={**new, "vessel_id": "SM-VALARCHI"}).status_code == 403
    assert admin.post("/api/contracts", json={**new, "vessel_id": "SM-VALARCHI"}).status_code == 201


def test_invoice_draft_approve_pay():
    manager = client_as("manager")
    invoices = manager.get("/api/invoices").json()
    last_month = (date.today().replace(day=1) - timedelta(days=1)).isoformat()[:7]
    existing = next(i for i in invoices if i["period"] == last_month and i["status"] == "APPROVED")
    # The seed already billed last month, so drafting it again is refused.
    assert manager.post("/api/invoices", json={"contract_no": existing["contract_no"], "period": last_month}).status_code == 409
    assert manager.post("/api/invoices", json={"contract_no": existing["contract_no"], "period": date.today().isoformat()[:7]}).status_code == 409
    paid = manager.post(f"/api/invoices/{existing['inv_no']}/pay", json={"paid_on": day(0)})
    assert paid.json()["status"] == "PAID"
    preview = manager.get("/api/invoices/preview", params={"contract_no": existing["contract_no"], "period": last_month}).json()
    assert preview["total"] == pytest.approx(preview["amount"] * (1 + preview["tax_rate"]), abs=0.02)


def test_admin_manages_users_and_a_switched_off_user_is_signed_out():
    admin = client_as("admin")
    assert client_as("manager").get("/api/users").status_code == 403
    assert admin.post("/api/users", json={"username": "diver1", "name": "Diver One", "role": "ops", "password": "short"}).status_code == 422
    assert admin.post("/api/users", json={"username": "diver1", "name": "Diver One", "role": "ops", "password": "long-enough-pass"}).status_code == 201
    PASSWORDS["diver1"] = "long-enough-pass"
    diver = client_as("diver1")
    assert diver.get("/api/auth/me").json()["role"] == "ops"
    assert admin.post("/api/users/diver1/active", json={"active": False}).json()["active"] is False
    assert diver.get("/api/auth/me").status_code == 401
    assert admin.post("/api/users/admin/active", json={"active": False}).status_code == 409


def test_wrong_password_is_refused():
    assert TestClient(app).post("/api/auth/login", json={"username": "ops", "password": "nope"}).status_code == 401


def test_vessel_positions_come_from_reports_else_base_port():
    ops = client_as("ops")
    vessels = {v["vessel_id"]: v for v in ops.get("/api/vessels").json()}
    assert vessels["SM-PRINCESS"]["position"]["source"] == "VSAT" and vessels["SM-SWORDFISH"]["position"]["source"] == "REPORT"
    base = vessels["SM-III"]["position"]
    assert (base["lat"], base["lon"], base["source"], base["at"]) == (9.96, 76.27, "BASE", None)
    assert len(ops.get("/api/vessels/SM-PRINCESS").json()["track"]) > 10
    bad = {**REPORT, "on_date": day(-4), "lat": 95, "lon": 72}
    assert ops.post("/api/reports", json=bad).status_code == 422
    assert ops.post("/api/reports", json={**bad, "lat": 19.0, "lon": None}).status_code == 422
    assert ops.post("/api/reports", json={**bad, "lat": 18.9, "lon": 72.9}).status_code == 201
    moved = {v["vessel_id"]: v for v in ops.get("/api/vessels").json()}["SM-DIAMOND"]["position"]
    assert (moved["lat"], moved["source"]) == (18.9, "REPORT")


def ask(who: str, question: str) -> dict:
    res = client_as(who).post("/api/assistant", json={"question": question})
    assert res.status_code == 200
    return res.json()


def test_assistant_answers_from_maris_data():
    certs = ask("ops", "Which certificates are expired?")
    assert "SEAMEC Agastya" in certs["answer"] and certs["links"][0]["to"] == "/certificates"
    princess = ask("ops", "where is princess right now")
    assert "VSAT" in princess["answer"] and princess["links"][0]["to"] == "/vessels/SM-PRINCESS"
    assert "SEAMEC III" in ask("ops", "is seamec iii in dry dock?")["answer"].split(" (")[0]
    assert "hire revenue" in ask("ops", "How much revenue this month?")["answer"]
    assert "waiting for approval" in ask("manager", "Which reports need approval?")["answer"]


def test_assistant_navigates_and_explains_respecting_roles():
    assert ask("ops", "take me to hire invoices")["links"] == [{"label": "Open Hire invoices", "to": "/invoices"}]
    assert ask("ops", "how do I file a daily report")["links"][0]["to"] == "/reports?new=1"
    assert "your role cannot" in ask("ops", "how do I draft an invoice")["answer"]
    assert ask("manager", "how do I draft an invoice")["links"][0]["to"] == "/invoices"
    assert ask("ops", "open the users page")["links"] == []


def test_assistant_refuses_questions_outside_maris():
    for q in ("What is the capital of France?", "write me a poem", "how do I bake a cake", "what is the weather in Delhi"):
        out = ask("ops", q)
        assert out["answer"].startswith("I can only help with MARIS") and out["links"] == [] and out["suggestions"]


def test_ais_messages_are_read_as_documented_and_bad_values_dropped():
    from app.core.tracking import parse_aisstream

    msg = {"MessageType": "PositionReport", "MetaData": {"MMSI": 352978118},
           "Message": {"PositionReport": {"UserID": 352978118, "Latitude": 19.1, "Longitude": 71.85, "Sog": 1.2, "Cog": 360, "TrueHeading": 87}}}
    assert parse_aisstream(msg) == {"mmsi": "352978118", "lat": 19.1, "lon": 71.85, "sog": 1.2, "cog": None}
    no_position = {**msg, "Message": {"PositionReport": {"UserID": 352978118, "Latitude": 91, "Longitude": 181}}}
    assert parse_aisstream(no_position) is None
    assert parse_aisstream({"MessageType": "ShipStaticData", "Message": {}}) is None


def test_position_feed_needs_the_key_and_stores_by_mmsi(monkeypatch):
    from app import config

    fix = {"fixes": [{"mmsi": "419227000", "lat": 18.99, "lon": 72.11, "source": "VSAT"}, {"mmsi": "999999999", "lat": 1, "lon": 1}]}
    monkeypatch.setattr(config, "FEED_KEY", "")
    assert TestClient(app).post("/api/positions/feed", json=fix).status_code == 503
    monkeypatch.setattr(config, "FEED_KEY", "test-feed-key")
    assert TestClient(app).post("/api/positions/feed", json=fix, headers={"X-Feed-Key": "wrong"}).status_code == 401
    out = TestClient(app).post("/api/positions/feed", json=fix, headers={"X-Feed-Key": "test-feed-key"}).json()
    assert out["stored"] == 1 and "unknown vessel" in out["skipped"][0]["reason"]
    seamec_ii = {v["vessel_id"]: v for v in client_as("ops").get("/api/vessels").json()}["SM-II"]["position"]
    assert (seamec_ii["source"], seamec_ii["lat"], seamec_ii["stale"]) == ("VSAT", 18.99, False)


def test_certificate_survey_endorsement_clears_the_warning():
    manager = client_as("manager")
    radio = next(c for c in manager.get("/api/certificates").json() if c["vessel_id"] == "SM-II" and "Radio" in c["name"])
    assert radio["state"] == "SURVEY_DUE"
    assert manager.post(f"/api/certificates/{radio['id']}/endorse", json={"on": day(1)}).status_code == 422
    assert manager.post(f"/api/certificates/{radio['id']}/endorse", json={"on": day(0)}).json()["state"] == "VALID"


# ---------------- Maintenance, crew, readiness, planner, client portal ----------------


def test_breakdown_in_a_report_needs_equipment_and_raises_a_defect():
    ops = client_as("ops")
    equipment = ops.get("/api/equipment", params={"vessel": "SM-AGASTYA"}).json()
    dp = next(e for e in equipment if e["name"].startswith("DP"))
    broken = {**REPORT, "vessel_id": "SM-AGASTYA", "on_date": day(-1), "standby_hrs": 18, "breakdown_hrs": 6}
    assert "which equipment" in ops.post("/api/reports", json=broken).json()["detail"]
    other_vessel = ops.get("/api/equipment", params={"vessel": "SM-DIAMOND"}).json()[0]["id"]
    assert ops.post("/api/reports", json={**broken, "breakdown_equipment_id": other_vessel}).status_code == 422
    assert ops.post("/api/reports", json={**broken, "breakdown_equipment_id": dp["id"]}).status_code == 201
    defect = next(j for j in ops.get("/api/maintenance", params={"vessel": "SM-AGASTYA"}).json() if j["kind"] == "DEFECT" and j["state"] == "OPEN")
    assert defect["equipment"] == dp["name"] and defect["downtime_hrs"] == 6
    readiness = ops.get("/api/readiness/SM-AGASTYA").json()
    assert any("DP control system: open defect" in p for c in readiness["checks"] for p in c["problems"])
    assert ops.post(f"/api/maintenance/jobs/{defect['id']}/close", json={"note": "Replaced card, DP trial passed"}).json()["status"] == "CLOSED"


def test_running_hours_only_go_up_and_done_jobs_reset_the_clock():
    ops = client_as("ops")
    gen = next(e for e in ops.get("/api/equipment", params={"vessel": "SM-PRINCESS"}).json() if e["name"] == "Main generators")
    assert ops.post(f"/api/equipment/{gen['id']}/hours", json={"hours": gen["running_hours"] - 1}).status_code == 422
    job = next(j for j in ops.get("/api/maintenance", params={"vessel": "SM-PRINCESS"}).json() if j["equipment_id"] == gen["id"])
    ops.post(f"/api/equipment/{gen['id']}/hours", json={"hours": job["last_done_hours"] + job["interval_hours"] + 5})
    job = next(j for j in ops.get("/api/maintenance", params={"vessel": "SM-PRINCESS"}).json() if j["equipment_id"] == gen["id"])
    assert job["state"] == "OVERDUE" and job["hours_left"] == -5
    ops.post(f"/api/maintenance/jobs/{job['id']}/done", json={"on": day(0)})
    assert next(j for j in ops.get("/api/maintenance", params={"vessel": "SM-PRINCESS"}).json() if j["id"] == job["id"])["state"] == "OK"


def test_readiness_reflects_the_set_cases():
    ready = {r["vessel_id"]: r for r in client_as("ops").get("/api/readiness").json()}
    problems = lambda vid: " | ".join(p for c in ready[vid]["checks"] for p in c["problems"])
    assert "Diving System Safety Certificate" in problems("SM-AGASTYA") and "Diver: 0 of 4" in problems("SM-AGASTYA")
    assert "annual survey missed" in problems("SM-DIAMOND")
    assert "11 months (MLC)" in problems("SM-GLORIOUS")
    assert "DP control system: overdue" in problems("SM-II")
    assert "The vessel is in dry dock." in problems("SM-III")
    princess = ready["SM-PRINCESS"]
    assert any("Diver medical" in w for c in princess["checks"] for w in c["warnings"])


def test_crew_assignment_enforces_mlc_and_certificate_validity():
    manager = client_as("manager")
    crew = manager.get("/api/crew").json()
    free_diver = next(p for p in crew if p["rank"] == "Diver" and not p["on_board"])
    base = {"crew_id": free_diver["id"], "vessel_id": "SM-AGASTYA", "sign_on": day(1)}
    assert "11-month MLC" in manager.post("/api/crew/assignments", json={**base, "relief_due": day(400)}).json()["detail"]
    medical = next(c for c in free_diver["certificates"] if c["name"].startswith("Diver medical"))
    lapses = manager.post("/api/crew/assignments", json={**base, "relief_due": (date.fromisoformat(medical["expires_on"]) + timedelta(days=1)).isoformat()})
    assert lapses.status_code == 409 and "Diver medical" in lapses.json()["detail"]
    assert client_as("ops").post("/api/crew/assignments", json={**base, "relief_due": day(20)}).status_code == 403
    assert manager.post("/api/crew/assignments", json={**base, "relief_due": day(20)}).status_code == 201
    assert manager.post("/api/crew/assignments", json={**base, "vessel_id": "SM-DIAMOND", "relief_due": day(25)}).status_code == 409


def test_planner_flags_the_dry_dock_clash():
    plan = {p["vessel_id"]: p for p in client_as("ops").get("/api/planner").json()}
    assert "during contract WOC/DSV/2026/022" in plan["SM-PALADIN"]["suggestion"]
    assert plan["SM-III"]["suggestion"].startswith("In dry dock now") and plan["SM-PALADIN"]["suggestion_level"] == "clash"
    assert plan["SM-AGASTYA"]["idle_days_180"] == 180


def test_client_sees_only_its_own_contracts_and_nothing_internal():
    client = client_as("woc.rep")
    contracts = client.get("/api/client/contracts").json()
    assert contracts and all(c["contract_no"].startswith("WOC/") for c in contracts)
    for internal in ("/api/dashboard", "/api/vessels", "/api/reports", "/api/invoices", "/api/maintenance", "/api/crew"):
        assert client.get(internal).status_code == 403, internal
    assert client.post("/api/assistant", json={"question": "revenue"}).status_code == 403
    last_month = (date.today().replace(day=1) - timedelta(days=1)).isoformat()[:7]
    assert client.get("/api/client/timesheet", params={"contract_no": "TC/GALLANT/2026/02", "period": last_month}).status_code == 404
    assert client_as("ops").get("/api/client/contracts").status_code == 403


def test_invoice_waits_for_the_clients_timesheet_signature():
    manager, client = client_as("manager"), client_as("woc.rep")
    last_month = (date.today().replace(day=1) - timedelta(days=1)).isoformat()[:7]
    draft = next(i for i in manager.get("/api/invoices").json() if i["contract_no"] == "WOC/DSV/2026/022" and i["period"] == last_month)
    assert draft["status"] == "DRAFT" and draft["signoff"] is None
    assert "has not signed" in manager.post(f"/api/invoices/{draft['inv_no']}/approve").json()["detail"]
    sheet = client.get("/api/client/timesheet", params={"contract_no": "WOC/DSV/2026/022", "period": last_month}).json()
    assert sheet["rows"] and sheet["signoff"] is None
    assert client.post("/api/client/timesheet", json={"contract_no": "WOC/DSV/2026/022", "period": last_month, "decision": "DISPUTED"}).status_code == 422
    client.post("/api/client/timesheet", json={"contract_no": "WOC/DSV/2026/022", "period": last_month, "decision": "DISPUTED", "note": "3rd: weather was 8 h, not 6"})
    assert "disputed it" in manager.post(f"/api/invoices/{draft['inv_no']}/approve").json()["detail"]
    client.post("/api/client/timesheet", json={"contract_no": "WOC/DSV/2026/022", "period": last_month, "decision": "SIGNED"})
    assert manager.post(f"/api/invoices/{draft['inv_no']}/approve").json()["status"] == "APPROVED"


def test_assistant_covers_the_fleet_modules():
    assert "Hire-ready now: " in ask("ops", "Which vessels are hire-ready?")["answer"]
    agastya = ask("ops", "is agastya ready for hire?")["answer"]
    assert agastya.startswith("Hire-ready: no") and "Diving System Safety Certificate" in agastya
    defects = ask("ops", "any open defects?")
    assert "Repeat failures" in defects["answer"] and "Dive air compressors" in defects["answer"] and defects["links"][0]["to"] == "/maintenance"
    crew = ask("ops", "crew reliefs due")["answer"]
    assert "11 months (MLC)" in crew
    assert "during contract WOC/DSV/2026/022" in ask("ops", "when is dry dock due for paladin")["answer"]
    assert "In dry dock" in ask("ops", "which vessels are in dry dock")["answer"]
    assert "MLC" in ask("manager", "how do I assign a relief")["answer"]


def test_a_report_sent_twice_after_a_dropped_link_is_accepted_once():
    ops = client_as("ops")
    body = {**REPORT, "vessel_id": "SM-VALARCHI", "on_date": day(-6), "client_ref": "device-abc-1"}
    first = ops.post("/api/reports", json=body)
    again = ops.post("/api/reports", json=body)
    assert first.status_code == 201 and again.status_code == 201 and again.json()["id"] == first.json()["id"]
    assert ops.post("/api/reports", json={**body, "client_ref": "another-device"}).status_code == 409
