"""The MARIS assistant: answers questions from MARIS's own data and pages, and nothing else.

It works by recognising what a question is about (a vessel, certificates, revenue, a page, "how do I ...")
and reading the live data the pages themselves use. It never makes up an answer: anything it does not
recognise as being about MARIS is politely refused, with suggestions.

shortcut: matching is keyword based. A language model could phrase answers more freely later, but it would
still have to be fed only these facts.
"""
import re

from sqlalchemy.orm import Session

from sqlalchemy import select

from ..api.billing import list_invoices
from ..api.dashboard import dashboard
from ..api.fleet import list_vessels
from ..core.fleetops import crew_alerts, maintenance, manning_gaps, on_board, planner, readiness
from ..models import User, Vessel

SUGGESTIONS = [
    "Which vessels are hire-ready?",
    "Any open defects?",
    "Crew reliefs due",
    "When is dry dock due?",
    "Where is SEAMEC Princess?",
    "Which certificates are expired?",
]

REFUSAL = (
    "I can only help with MARIS: the fleet, positions, hire readiness, maintenance and defects, crew, certificates, "
    "daily reports, contracts, invoices, the planner, and how to use these pages. Try one of the questions below."
)

# Pages: words that point at them, where they are, and who can open them.
PAGES = [
    (("control tower", "dashboard", "home", "overview"), "/", "Control tower", None),
    (("readiness", "hire ready", "hire-ready"), "/readiness", "Hire readiness", None),
    (("maintenance", "defects", "pms", "jobs"), "/maintenance", "Maintenance", None),
    (("crew", "rotation", "reliefs", "manning"), "/crew", "Crew", None),
    (("planner", "timeline", "schedule"), "/planner", "Planner", None),
    (("vessel", "vessels", "fleet", "ship", "ships", "map"), "/vessels", "Vessels and fleet map", None),
    (("certificate", "certificates", "certs"), "/certificates", "Certificates", None),
    (("daily report", "daily reports", "report", "reports", "dpr"), "/reports", "Daily reports", None),
    (("contract", "contracts", "charter"), "/contracts", "Contracts", None),
    (("invoice", "invoices", "billing", "bill", "hire invoice"), "/invoices", "Hire invoices", None),
    (("audit", "audit log", "history", "log"), "/audit", "Audit log", ("manager",)),
    (("user", "users", "account", "accounts"), "/users", "Users", ()),
]

# "How do I ..." answers: topic words, the steps, the page, and who may do it (None = everyone).
HOWTO = [
    (("file", "submit", "enter", "add", "create", "fill"), ("report", "dpr"),
     "To file a daily report:\n1. Click \"File daily report\" (on the Control tower or Daily reports page).\n"
     "2. Pick the vessel and date, enter the location and the noon latitude and longitude.\n"
     "3. Split the 24 hours into operating, standby, weather, breakdown and transit; they must add up to 24.\n"
     "4. Add work done, dive and ROV hours, fuel on board and any incidents, then click \"File report\".\n"
     "It then waits for an ops manager to approve it.", "/reports?new=1", "File a daily report", None),
    (("approve", "reject", "check"), ("report", "reports", "dpr"),
     "To approve or reject daily reports:\n1. Open Daily reports and filter Status to \"Awaiting approval\".\n"
     "2. Use the tick to approve, or the cross to reject with a reason so the vessel can correct and refile.\n"
     "Only approved reports are billed.", "/reports?status=SUBMITTED", "Reports awaiting approval", ("manager",)),
    (("draft", "create", "make", "raise", "generate"), ("invoice", "invoices", "bill"),
     "To draft a hire invoice:\n1. Open Hire invoices and click \"Draft invoice\".\n2. Choose the contract and a finished month; "
     "the preview shows how the approved reports became money.\n3. Click \"Draft invoice\", then open it and \"Approve\". "
     "When the client pays, use \"Record payment\".\nAll reports for that month must be approved or rejected first.",
     "/invoices", "Hire invoices", ("manager",)),
    (("renew", "update", "extend"), ("certificate", "certificates", "cert"),
     "To renew a certificate:\n1. Open Certificates (sorted by expiry).\n2. Click \"Renew\" on the row and enter the new issue and expiry dates.",
     "/certificates", "Certificates", ("manager",)),
    (("create", "add", "new", "make"), ("contract", "contracts", "charter"),
     "To create a contract:\n1. Open Contracts and click \"New contract\".\n2. Enter client, vessel, period, operating and standby rates, "
     "paid breakdown hours per month, fees and bank guarantee.\nA vessel already on contract, or with an expired critical certificate, is refused.",
     "/contracts", "Contracts", ()),
    (("close", "fix", "clear"), ("defect", "defects", "breakdown"),
     "To close a defect:\n1. Open Maintenance and find the open defect (open defects are listed first).\n"
     "2. Click \"Close\" and write what was found and done.\nAn open defect on critical equipment keeps the vessel not hire-ready.",
     "/maintenance", "Maintenance", None),
    (("record", "enter", "update"), ("hours", "running", "counter"),
     "To record running hours:\n1. Open Maintenance and switch to the Equipment tab.\n2. Click \"Hours\" on the item and enter the counter reading.\n"
     "Jobs that repeat by running hours fall due from these readings.", "/maintenance", "Maintenance", None),
    (("assign", "send", "relieve", "relief", "plan"), ("crew", "diver", "relief", "seafarer"),
     "To assign a relief:\n1. Open Crew and click \"Assign\".\n2. Pick a person who is ashore, the vessel, sign-on and relief dates.\n"
     "MARIS refuses a trip past the 11-month MLC limit, or one in which any of the person's certificates would lapse.",
     "/crew", "Crew", ("manager",)),
    (("create", "add", "new", "make"), ("user", "users", "account", "login"),
     "To add a user:\n1. Open Users (admin only) and click \"Add user\".\n2. Enter username, name, role and a first password.\n"
     "Switch the account off there to sign that person out everywhere.", "/users", "Users", ()),
]


def money(v: float) -> str:
    a, sign = abs(v), "-" if v < 0 else ""
    if a >= 1e7:
        return f"{sign}₹{a / 1e7:.2f} Cr"
    if a >= 1e5:
        return f"{sign}₹{a / 1e5:.2f} L"
    return f"{sign}₹{a:,.0f}"


def words(q: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", q))


def has(q: str, *terms: str) -> bool:
    """True when any term appears in the question as whole words."""
    return any(re.search(rf"\b{re.escape(t)}\b", q) for t in terms)


def allowed(user: User, roles) -> bool:
    return roles is None or user.role == "admin" or user.role in roles


def reply(answer: str, links=(), suggestions=None) -> dict:
    return {"answer": answer, "links": [{"label": label, "to": to} for label, to in links], "suggestions": suggestions or []}


def find_vessel(q: str, vessels: list[dict]) -> dict | None:
    """The vessel a question names. Longest name first, so "seamec iii" is not read as "seamec ii"."""
    for v in sorted(vessels, key=lambda v: -len(v["name"])):
        name = v["name"].lower()
        short = name.split()[-1]  # "princess", "valarchi"; not "ii"/"iii", which need "seamec"
        if has(q, name) or (short not in ("ii", "iii") and has(q, short)):
            return v
    return None


def readiness_line(r: dict) -> str:
    if r["ready"]:
        return "Hire-ready: yes" + (f" ({r['warnings']} things to watch)." if r["warnings"] else ".")
    problems = [p for c in r["checks"] for p in c["problems"]]
    return f"Hire-ready: no. {'; '.join(problems[:4])}" + (f" (+{len(problems) - 4} more)" if len(problems) > 4 else "") + "."


def vessel_answer(v: dict, fleet_row: dict | None, ready: dict | None = None) -> dict:
    lines = [f"{v['name']} ({v['vessel_type']}) is {v['status'].replace('_', ' ').lower()}."]
    if v["client"]:
        lines.append(f"Contract {v['contract_no']} with {v['client']}, until {v['contract_end']}.")
    p = v["position"]
    if p:
        if p["source"] == "BASE":
            when = "base port, no reported position"
        else:
            when = f"{p['source']}, {p['age_hours']:g} h ago" + (", out of date" if p["stale"] else "")
        lines.append(f"Position: {p['label']} at {p['lat']:.3f}, {p['lon']:.3f} ({when}).")
    if fleet_row and fleet_row["contract_no"]:
        lines.append(f"This month: revenue {money(fleet_row['revenue_mtd'])}, cost {money(fleet_row['cost_mtd'])}, "
                     f"profit {money(fleet_row['pnl_mtd'])}, utilisation {fleet_row['utilisation']}%.")
        if fleet_row["missing_reports_7d"]:
            lines.append(f"Missing daily reports in the last 7 days: {fleet_row['missing_reports_7d']}.")
    if v["certs_expired"]:
        lines.append(f"Certificates: {v['certs_expired']} not valid (expired or annual survey missed), so it cannot go on a new contract.")
    elif v["certs_expiring"]:
        lines.append(f"Certificates: {v['certs_expiring']} need action soon (expiring, or survey window open).")
    else:
        lines.append("Certificates: all valid.")
    if ready:
        lines.append(readiness_line(ready))
    return reply("\n".join(lines), [(f"Open {v['name']}", f"/vessels/{v['vessel_id']}"), ("Hire readiness", "/readiness")],
                 ["Which vessels are hire-ready?", "Any open defects?"])


def answer(question: str, user: User, session: Session) -> dict:
    q = " ".join(question.lower().split())
    if not q or has(q, "hi", "hello", "hey", "help") and len(words(q)) <= 3 or has(q, "what can you do", "who are you"):
        return reply("Hello! I answer questions about MARIS's data and help you find your way around. For example:", suggestions=SUGGESTIONS)

    # "How do I ..."
    if has(q, "how", "steps", "way to", "procedure", "process"):
        for verbs, topics, text, to, label, roles in HOWTO:
            if has(q, *topics) and has(q, *verbs):
                if not allowed(user, roles):
                    return reply(f"{text.splitlines()[0]} This needs an ops manager or admin; your role cannot do it.")
                return reply(text, [(label, to)])

    nav = has(q, "go to", "take me", "open the", "open page", "navigate", "show me the", "where is the", "where can i find", "page")  # not bare "open": "open defects"
    page = next(((to, label, roles) for keys, to, label, roles in PAGES if has(q, *keys)), None)
    if nav and page and not find_vessel(q, list_vessels(session)):
        to, label, roles = page
        if not allowed(user, roles):
            return reply(f"The {label} page is for ops managers and admins only.")
        return reply(f"Here is {label}.", [(f"Open {label}", to)])

    vessels = list_vessels(session)
    d = dashboard(session)
    k = d["kpis"]
    fleet = {r["vessel_id"]: r for r in d["fleet"]}

    v = find_vessel(q, vessels)
    vessel_row = session.get(Vessel, v["vessel_id"]) if v else None

    # Hire readiness
    if has(q, "ready", "readiness", "hire ready", "go on hire", "fit for hire", "mobilise", "mobilize"):
        if vessel_row:
            r = readiness(session, vessel_row)
            lines = [readiness_line(r)] + [f"• {c['check']}: " + ("OK" if c["ok"] else "; ".join(c["problems"])) for c in r["checks"]]
            warns = [w for c in r["checks"] for w in c["warnings"]]
            if warns:
                lines.append("To watch: " + "; ".join(warns[:4]))
            return reply("\n".join(lines), [(f"Open {vessel_row.name}", f"/vessels/{vessel_row.vessel_id}"), ("Hire readiness", "/readiness")])
        rows = [readiness(session, x) for x in session.scalars(select(Vessel).order_by(Vessel.name))]
        ready = [r["name"] for r in rows if r["ready"]]
        lines = [f"Hire-ready now: {', '.join(ready) or 'none'}."]
        lines += [f"• {r['name']}: " + "; ".join(p for c in r["checks"] for p in c["problems"])[:160] for r in rows if not r["ready"]]
        return reply("\n".join(lines), [("Open Hire readiness", "/readiness")], ["Is SEAMEC Agastya ready for hire?"])

    # Maintenance and defects
    if has(q, "defect", "defects", "breakdown", "breakdowns", "maintenance", "pms", "overdue job", "overdue jobs", "repair", "repairs", "failure", "failures", "compressor", "dp"):
        jobs = maintenance(session, vessel_row.vessel_id if vessel_row else None)
        names = {x["vessel_id"]: x["name"] for x in vessels}
        open_defects = [j for j in jobs if j["state"] == "OPEN"]
        overdue = [j for j in jobs if j["state"] == "OVERDUE"]
        repeat = {(j["vessel_id"], j["equipment"]) for j in jobs if j["repeat_failure"]}
        where = f" on {vessel_row.name}" if vessel_row else ""
        lines = [f"Open defects{where}: {len(open_defects)}. Overdue planned jobs: {len(overdue)}."]
        lines += [f"• {names[j['vessel_id']]}: {j['equipment']}{' (critical)' if j['critical'] else ''}, defect raised {j['raised_on']}, {j['downtime_hrs']:g} h down"
                  for j in open_defects[:6]]
        lines += [f"• {names[j['vessel_id']]}: {j['equipment']}{' (critical)' if j['critical'] else ''}, {j['title']} overdue" for j in overdue[:6]]
        if repeat:
            lines.append("Repeat failures (3+ defects in 60 days): " + ", ".join(f"{names[vid]} {eq}" for vid, eq in sorted(repeat)) + ".")
        return reply("\n".join(lines), [("Open Maintenance", "/maintenance")], ["How do I close a defect?", "Which vessels are hire-ready?"])

    # Crew
    if has(q, "crew", "relief", "reliefs", "rotation", "mlc", "medical", "medicals", "diver", "divers", "seafarer", "seafarers", "manning", "sign off", "on board", "onboard"):
        rows = crew_alerts(session, on_board(session, vessel_row.vessel_id if vessel_row else None))
        names = {x["vessel_id"]: x["name"] for x in vessels}
        flagged = [(r, a) for r in rows for a in r["alerts"] if a["level"] in ("BLOCK", "WARN")]
        soon = [(r, a) for r in rows for a in r["alerts"] if a["level"] == "INFO"]
        lines = [f"{len(rows)} people on board{' ' + vessel_row.name if vessel_row else ''}. Needing action: {len(flagged)}. Reliefs in the next 14 days: {len(soon)}."]
        lines += [f"• {names[r['vessel_id']]}: {r['name']} ({r['rank']}): {a['text']}" for r, a in flagged[:8]]
        vids = [vessel_row.vessel_id] if vessel_row else list(names)
        for vid in vids:
            gaps = manning_gaps(session, vid, [r for r in rows if r["vessel_id"] == vid])
            if gaps and (vessel_row or session.get(Vessel, vid).status == "ON_HIRE"):
                lines.append(f"• {names[vid]} is short of: " + ", ".join(f"{g['rank']} {g['on_board']}/{g['required']}" for g in gaps))
        return reply("\n".join(lines), [("Open Crew", "/crew")], ["How do I assign a relief?"])

    # Planner: dry dock timing and idle time
    if has(q, "planner", "idle", "next contract", "bottom survey", "docking") or (has(q, "dry dock", "drydock") and has(q, "due", "when", "plan", "next", "window")):
        plan = planner(session)
        rows = [p for p in plan if not vessel_row or p["vessel_id"] == vessel_row.vessel_id]
        lines = [f"• {p['name']}: bottom survey due {p['bottom_survey_due'] or 'not recorded'}; idle {p['idle_days_180']} of the next 180 days"
                 + (f" ({money(p['idle_cost_180'])} running cost)" if p["idle_days_180"] else "") + (f". {p['suggestion']}" if p["suggestion"] else "")
                 for p in rows]
        return reply("Dry dock (bottom survey at most every 36 months) and idle time:\n" + "\n".join(lines), [("Open Planner", "/planner")])

    if v:
        return vessel_answer(v, fleet.get(v["vessel_id"]), readiness(session, vessel_row))

    if has(q, "certificate", "certificates", "cert", "certs", "expired", "expiring", "expire", "expires"):
        alerts = d["cert_alerts"]
        if not alerts:
            return reply("Every certificate is valid; none expires within 60 days.", [("Open Certificates", "/certificates")])
        lines = [f"{k['certs_expired']} no longer valid and {k['certs_expiring']} needing action soon:"]
        for c in alerts:
            state = {
                "EXPIRED": f"expired {-c['days_left']} days ago ({c['expires_on']})",
                "SURVEY_OVERDUE": f"annual survey missed (window closed {c['survey_to']}), so not valid",
                "EXPIRING": f"expires in {c['days_left']} days ({c['expires_on']})",
                "SURVEY_DUE": f"annual survey window open until {c['survey_to']}",
            }[c["state"]]
            lines.append(f"• {c['vessel_name']}: {c['name']}, {state}")
        return reply("\n".join(lines), [("Open Certificates", "/certificates")], ["How do I renew a certificate?"])

    if has(q, "where", "position", "positions", "location", "located", "map", "coordinates"):
        lines = ["Last known positions:"]
        for x in vessels:
            p = x["position"]
            if p:
                lines.append(f"• {x['name']}: {p['label']} ({p['lat']:.2f}, {p['lon']:.2f})" + ("" if p["source"] == "REPORT" else ", base port"))
        return reply("\n".join(lines), [("Open fleet map", "/vessels")], ["Where is SEAMEC Gallant?"])

    if has(q, "revenue", "earn", "earned", "earning", "earnings", "income", "profit", "loss", "pnl", "money", "making"):
        rows = [r for r in d["fleet"] if r["contract_no"]]
        best = max(rows, key=lambda r: r["pnl_mtd"], default=None)
        worst = min(rows, key=lambda r: r["pnl_mtd"], default=None)
        lines = [f"{d['period']} so far ({d['days_elapsed']} days): hire revenue {money(k['revenue_mtd'])}, fleet profit {money(k['pnl_mtd'])} "
                 "(after the running cost of every vessel, idle ones included)."]
        if best:
            lines.append(f"Most profitable: {best['name']} ({money(best['pnl_mtd'])}). Least: {worst['name']} ({money(worst['pnl_mtd'])}).")
        idle = [r["name"] for r in d["fleet"] if not r["contract_no"]]
        if idle:
            lines.append(f"Not earning (no contract): {', '.join(idle)}.")
        return reply("\n".join(lines), [("Open Control tower", "/"), ("Open Hire invoices", "/invoices")], ["What is the fleet utilisation?"])

    if has(q, "utilisation", "utilization", "utilised", "utilized", "busy"):
        lines = [f"Fleet utilisation this month: {k['utilisation']}% (paid hours over all hours, idle vessels included)."]
        lines += [f"• {r['name']}: {r['utilisation']}%" for r in sorted(d["fleet"], key=lambda r: -r["utilisation"])]
        return reply("\n".join(lines), [("Open Control tower", "/")])

    if has(q, "missing"):
        rows = [r for r in d["fleet"] if r["missing_reports_7d"]]
        text = "No daily reports are missing in the last 7 days." if not rows else "Missing daily reports in the last 7 days:\n" + "\n".join(
            f"• {r['name']}: {r['missing_reports_7d']}" for r in rows)
        return reply(text, [("Open Daily reports", "/reports")])

    if has(q, "pending", "approve", "approval", "waiting", "awaiting") and has(q, "report", "reports", "dpr", "approve", "approval"):
        pend = d["pending_reports"]
        if not pend:
            return reply("No daily reports are waiting for approval.", [("Open Daily reports", "/reports")])
        lines = [f"{k['reports_pending']} daily reports are waiting for approval:"] + [f"• {p['vessel_name']}, {p['on_date']}" for p in pend]
        return reply("\n".join(lines), [("Review them", "/reports?status=SUBMITTED")], ["How do I approve a report?"])

    if has(q, "overdue", "unpaid", "receivable", "receivables", "outstanding", "owe", "owed", "due", "payment", "payments", "paid"):
        open_inv = [i for i in list_invoices(session) if i["status"] == "APPROVED"]
        lines = [f"Unpaid approved invoices: {money(k['receivables'])}, of which {money(k['overdue'])} is overdue."]
        lines += [f"• {i['inv_no']} {i['vessel_name']} ({i['period']}): {money(i['total'])}, due {i['due_date']}" + (" OVERDUE" if i["overdue"] else "") for i in open_inv]
        return reply("\n".join(lines), [("Open Hire invoices", "/invoices")])

    if has(q, "ending", "ends", "expiring contract", "renewal", "bank guarantee", "guarantee", "bg"):
        lines = ["Contracts ending within 90 days:"] + [f"• {c['vessel_name']} ({c['client']}): ends {c['end_date']}, {c['days_left']} days" for c in d["contracts_ending"]]
        if len(lines) == 1:
            lines = ["No contract ends within 90 days."]
        lines += [f"Bank guarantee for {b['contract_no']} ({money(b['bg_amount'])}) expires {b['bg_expiry']}." for b in d["bg_expiring"]]
        return reply("\n".join(lines), [("Open Contracts", "/contracts")])

    statuses = {"on hire": "ON_HIRE", "working": "ON_HIRE", "available": "AVAILABLE", "idle": "AVAILABLE", "free": "AVAILABLE", "dry dock": "DRY_DOCK", "drydock": "DRY_DOCK"}
    wanted = next((s for word, s in statuses.items() if has(q, word)), None)
    if wanted or has(q, "fleet", "vessels", "ships", "how many"):
        groups = {s: [x["name"] for x in vessels if x["status"] == s] for s in ("ON_HIRE", "AVAILABLE", "DRY_DOCK")}
        label = {"ON_HIRE": "On hire", "AVAILABLE": "Available", "DRY_DOCK": "In dry dock"}
        shown = [wanted] if wanted else list(groups)
        lines = [f"The fleet has {len(vessels)} vessels."] + [f"• {label[s]} ({len(groups[s])}): {', '.join(groups[s]) or 'none'}" for s in shown]
        return reply("\n".join(lines), [("Open Vessels", "/vessels")])

    if page:  # just a page name, e.g. "invoices"
        to, label, roles = page
        if allowed(user, roles):
            return reply(f"Here is {label}.", [(f"Open {label}", to)])

    return reply(REFUSAL, suggestions=SUGGESTIONS)
