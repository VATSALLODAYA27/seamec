"""Verified data only: the fleet as it stands, each vessel's last area from public AIS, and SEAMEC's contract awards
from its stock-exchange disclosures. Nothing is invented. Checked on 28 October 2026.

A fact is used only when the exchange filing itself (its title and summary) or two independent reports agree.
What is not public is left empty rather than guessed: running costs, day rates for most charters, certificates,
crew, equipment, insurance, daily reports and invoices. Enter those from SEAMEC's own records.

Money: MARIS keeps rupees. US dollar values are converted at the RBI reference rate below, and the original
dollar figure is kept in each record's note.

Loaded by:  python -m scripts.seed --reset          (the invented demo set: --reset --demo)
"""
from datetime import date, timedelta

from app.models import Tender, Vessel

CHECKED_ON = "2026-10-28"
# RBI reference rate (FBIL), 27 Oct 2026 at 1 pm: https://www.rbi.org.in/home.aspx
# Older contracts are converted at the same rate, so their rupee values are today's value of the dollar amount.
USD_INR = 95.1623


def inr(usd: float) -> float:
    return round(usd * USD_INR, 2)


def plus_days(start: str, days: int) -> str:
    return (date.fromisoformat(start) + timedelta(days=days - 1)).isoformat()


# id, name, type, IMO, MMSI, flag, built, owner, status, last area seen on AIS (VesselFinder, 28 Oct 2026; area only, no coordinates published)
# Status ON_HIRE only where a SEAMEC filing says the vessel is on charter and no later filing says otherwise.
# Running cost per day is not public: 0 means "not on file".
VESSELS = [
    ("SM-II", "SEAMEC II", "DSV", "8109292", "419227000", "India", None, "SEAMEC Ltd", "ON_HIRE",  # G R Infraprojects subcontract, filed 30 Sep 2026
     "Indian Coast, 1.7 kn, bound for ID 13A (VesselFinder AIS, 28 Oct 2026)"),
    ("SM-III", "SEAMEC III", "DSV", "8128339", "419228000", "India", None, "SEAMEC Ltd", "AVAILABLE",
     "Indian Coast, at anchor; last port Mumbai anchorage (VesselFinder AIS, 28 Oct 2026)"),
    ("SM-PRINCESS", "SEAMEC Princess", "DSV", "8302959", "419603000", "India", 1984, "SEAMEC Ltd", "AVAILABLE",
     "Arrived Mumbai anchorage 22 Oct 2026, 13:08 UTC (VesselFinder AIS)"),
    ("SM-PALADIN", "SEAMEC Paladin", "DSV", "9388091", "352978118", "Panama", None, "SEAMEC Ltd", "ON_HIRE",  # ONGC charter, on hire 15 Jul 2026 06:10
     "Indian Coast; last port Nhava Sheva, left 10 Sep 2026 (VesselFinder AIS, 28 Oct 2026)"),
    ("SM-SWORDFISH", "SEAMEC Swordfish", "DSV", "9385300", "538005198", "Marshall Islands", None, "SEAMEC Ltd", "ON_HIRE",  # Safeen Al Behar, on hire 29 May 2026
     "Persian Gulf, restricted in ability to manoeuvre, bound for Zuluf oilfield (VesselFinder AIS, 28 Oct 2026); pin at the field"),
    ("SM-AGASTYA", "SEAMEC Agastya", "DSV", "9483061", "538011888", "Marshall Islands", None, "SEAMEC Ltd", "ON_HIRE",  # HAL Offshore for ONGC, from 4 Dec 2025
     "Indian Coast, bound for Cluster 7; last port Mumbai anchorage (VesselFinder AIS, 28 Oct 2026)"),
    ("SM-DIAMOND", "SEAMEC Diamond", "OSV", "", None, "", None, "SEAMEC Ltd", "ON_HIRE",  # back on ONGC hire 10 Apr 2026 after dry dock
     "Not found on public AIS"),
    ("SM-GLORIOUS", "SEAMEC Glorious", "BARGE", "1037555", "419902276", "India", None, "SEAMEC Ltd", "AVAILABLE",
     "Indian Coast, bound for Y5; arrived Mumbai anchorage 2 Oct 2026 (VesselFinder AIS, last seen 25 days ago)"),
    ("SM-VALARCHI", "Chennai Valarchi", "BULK", "", None, "", None, "Seamate Shipping FZC", "AVAILABLE", "Not found on public AIS"),
    # Bought from HAL Offshore (MoA filed 21 Jul 2026); taken over at Kakinada, Oct 2026.
    ("SM-ANANT", "SEAMEC Anant", "OSV", "9412206", "419001911", "India", 2023, "SEAMEC Ltd", "AVAILABLE",
     "Indian Coast, under way to Mumbai; last port Kakinada anchorage (VesselFinder AIS, 28 Oct 2026)"),
]
# Map pins only where AIS names a place with a published position; all approximate (no exact fix is public).
# Mumbai Port: Wikipedia, 18°56'41.687"N 72°50'38.909"E. Zuluf oilfield: Global Energy Monitor wiki and MarineLink, 28.611N 49.059E.
# Not pinned: "Indian Coast" only (Paladin, Anant), Cluster 7 and ID 13A (no published coordinates), and no AIS (Diamond, Valarchi).
MUMBAI_PORT, ZULUF_FIELD = (18.9449, 72.8441), (28.611, 49.059)
AT_PORT = {"SM-PRINCESS": MUMBAI_PORT, "SM-III": MUMBAI_PORT, "SM-GLORIOUS": MUMBAI_PORT, "SM-SWORDFISH": ZULUF_FIELD}

# Not loaded: SEAMEC Gallant, sold 17 Sep 2026 (board approval filed 14 Jul 2026; completion reported 17 Sep 2026).

# Contract awards, as won tenders. One line each: ref, client, type, vessel, scope, start, days, rupees per day, note (facts and sources).
# The rupee day rate is the disclosed contract value spread over its days; the per-day split is not published unless stated.
AWARDS = [
    ("ONGC-NOA-2026-03-13-SAMUDRA-SEVAK", "ONGC", "DSV", None,
     "Operation and maintenance of ONGC's multipurpose support vessel Samudra Sevak, in consortium with Supreme Hydro",
     "2026-03-13", 738, round(410.74e7 / 738, 2),
     "Notification of award 13 Mar 2026; ₹410.74 crore for 738 days; work to start within 60 days of award, so dates are from the award date. "
     "Sources: multibagg.ai, splash247.com, businessupturn.com."),
    ("HAL-AGASTYA-2025-12-04", "HAL Offshore Ltd (for ONGC)", "DSV", "SM-AGASTYA",
     "Charter hire of SEAMEC Agastya (ex NPP Nusantara), deployed under HAL's ONGC contract",
     "2025-12-04", 1461, inr(25_000),
     "Effective 4 Dec 2025; US$25,000 a day for the balance period of 4 years; about US$43.07 million including GST. Related party: HAL holds 70.77%. "
     "Sources: NSE filing 'Contract with HAL for NPP NUSANTARA' (4 Dec 2025), filingreader.com, stockopedia.com."),
    ("HAL-ANANT-2026-10-21", "HAL Offshore Ltd (for ONGC)", "OSV", "SM-ANANT",
     "Charter hire of SEAMEC Anant for ONGC inspection, maintenance and repair",
     "2026-10-21", 1225, inr(55e6 / 1225),
     "Agreement dated 21 Oct 2026; about 1,225 days; about US$55 million excluding GST. Start of hire not disclosed, so dates are from the agreement. "
     "Related party. Sources: BSE filing summary (arthneeti.com), sahi.com."),
    ("LAMPRELL-GLORIOUS-2026-07-15", "Lamprell Energy (for ONGC)", "BARGE", "SM-GLORIOUS",
     "Charter hire of barge SEAMEC Glorious, Mumbai High and West Coast including Daman",
     "2026-10-15", 180, inr(5.21e6 / 180),
     "BIMCO charter filed 15 Jul 2026; firm 180 days with option to extend; to start 15-31 Oct 2026; US$5.21 million including GST. "
     "Sources: hdfcsky.com, tradebrains.in, jmfinancialservices.in."),
    ("GRIL-PRP8A-DSF2-2026-09-30", "G R Infraprojects Ltd (for ONGC)", "DSV", "SM-II",
     "Subsea installation for ONGC's Pipeline Replacement Project PRP-8A and DSF-2, SEAMEC II",
     "2026-09-30", 180, inr(19.02e6 / 180),
     "Subcontract filed 30 Sep 2026; 180 days with option to extend; about US$19.02 million excluding GST. Start not disclosed, so dates are from the filing. "
     "Source: BSE filing SEAMEC/BSE&NSE/SMO/GRILPRP8A&DSF2/3009/2026."),
    ("ONGC-NOA-2026-03-26-SAMUDRA-PRABHA", "ONGC", "DSV", None,
     "Operation and maintenance of ONGC's multipurpose support vessel Samudra Prabha, in consortium with Supreme Hydro",
     "2026-03-26", 698, round(329.92e7 / 698, 2),
     "Notification of award 26 Mar 2026; about ₹329.92 crore including GST; 698 days; contract signed by 1 Jun 2026, terms unchanged. "
     "Sources: angelone.in, constructionworld.in, whalesbook.com, filingreader.com."),
    ("GRIL-PRP8A-DSF2-2025-12-11", "G R Infraprojects Ltd (for ONGC)", "DSV", "SM-III",
     "Second-season subsea installation and diving, ONGC PRP-VIII A and DSF II projects, lump sum",
     "2025-12-25", 150, inr(16.72e6 / 150),
     "Subcontract filed 11 Dec 2025; about US$16.72 million excluding GST; 150 days; operations from 25 Dec 2025. Not a related party. "
     "Sources: NSE filing 'Subcontract GRIL' (11 Dec 2025), constructionworld.in, business-standard.com, projectstoday.com."),
    ("LAMPRELL-PRINCESS-2026-05-12", "Lamprell Energy (for ONGC)", "DSV", "SM-PRINCESS",
     "Charter hire of SEAMEC Princess, West Coast oilfield including Daman",
     "2026-05-12", 15, inr(2.12e6 / 15),
     "Charter filed 12 May 2026; firm 15 days with option to extend; about US$2.12 million excluding GST. "
     "Sources: Reuters brief (stockopedia.com), sahi.com, whalesbook.com."),
    ("SUPREME-PRINCESS-2026-02-14", "Supreme Offshore Construction (for ONGC)", "DSV", "SM-PRINCESS",
     "Charter hire of SEAMEC Princess for saturation and air diving, ONGC West Coast",
     "2026-02-14", 4, inr(460_000 / 4),
     "On hire 14 Feb 2026 21:30; firm about 4 days with option to extend; about US$460,000 excluding GST; off hire 18 Feb 2026 21:30. "
     "Sources: NSE filing 'Arrangement with Supreme' (16 Feb 2026), scanx.trade, dsij.in."),
    ("LT-GLORIOUS-2025-10-15", "Larsen & Toubro Ltd (for ONGC)", "BARGE", "SM-GLORIOUS",
     "Barge SEAMEC Glorious for offshore accommodation and hook-up, Mumbai High and West Coast",
     "2025-10-15", 150, round(28_85_62_500 / 150, 2),
     "BIMCO charter dated 15 Oct 2025; firm 150 days; ₹28,85,62,500 excluding GST; to start 1-30 Oct 2025. "
     "Extended by addendum (Apr 2026) to 15 May 2026 for ₹6,54,07,500 excluding GST. "
     "Sources: NSE filing 'Charter Larsen Toubro' (15 Oct 2025), scanx.trade, jmfinancialservices.in, whalesbook.com."),
    ("SAFEEN-SWORDFISH-2025-02-05", "Safeen Al Behar", "DSV", "SM-SWORDFISH",
     "Charter hire of SEAMEC Swordfish, Saudi Arabia and UAE",
     "2025-05-21", 730, inr(57.40e6 / 730),
     "BIMCO charter 5 Feb 2025; firm 730 days with option to extend; US$57.40 million for the firm period; start moved to 21 May 2025 by Addendum 1. "
     "Sources: NSE filing 'Addendum with Safeen Swordfish' (22 May 2025), pm-global.co.uk, Reuters brief (stockopedia.com)."),
    ("MERMAID-SWORDFISH-2024-12-21", "Mermaid Subsea Services", "DSV", "SM-SWORDFISH",
     "Charter hire of SEAMEC Swordfish, Saudi Arabia and UAE",
     "2024-12-21", 50, inr(3.46e6 / 50),
     "Firm 50 days from 21 Dec 2024 with option to extend; US$3.46 million. "
     "Sources: NSE filing 'Charter on hire Swordfish with Mermaid' (23 Dec 2024), Reuters brief (stockopedia.com)."),
    ("MUBARAK-SEAMECIII-2025-06-05", "Mubarak Bridge Maritime FZCO", "DSV", "SM-III",
     "Charter hire of SEAMEC III, India West Coast",
     "2025-06-05", 20, inr(2.16e6 / 20),
     "BIMCO charter 5 Jun 2025; firm 20 days at US$70,000 a day; about US$2.16 million with mobilisation and demobilisation, excluding GST; "
     "completed and off hire 25 Jun 2025. Sources: NSE filing 'Bimco Charter Mubarak Bridge' (6 Jun 2025), Reuters briefs (stockopedia.com), itiger.com."),
    ("HAL-PALADIN-2023-04-13", "HAL Offshore Ltd (for ONGC)", "DSV", "SM-PALADIN",
     "Charter hire of SEAMEC Paladin for five years, deployed on ONGC work",
     "2023-04-13", 1827, inr(35_000),
     "Charter party Feb 2023; US$35,000 a day; about US$64 million for 5 years excluding GST; on hire 13 Apr 2023. Related party. "
     "A later report's US$102.77 million is not used: the filing says US$64 million. Sources: BSE filing (Feb 2023), moneyworks4me.com, Reuters brief (stockopedia.com)."),
]
# Found but not loaded, because a fact the record needs is not disclosed or not confirmed:
# - HAL Offshore diving subcontracts on Samudra Prabha (US$9.42M) and Samudra Sevak (US$9.96M), 23 Jul 2026: no period disclosed.
# - Posh India Offshore subcontract (PRP-VIII Gr B, Daman), US$5.61M max, Mar 2025, with SEAMEC Princess at US$37,000/day from
#   1 Apr 2026: end date only from one "likely by May 2026" report.
# - MV Goodman charter with HAL Offshore (₹6.30 crore, 45 days, Oct 2025): which side charters the vessel is unclear.


def seed_verified(session) -> None:
    for vid, name, vtype, imo, mmsi, flag, built, entity, status, area in VESSELS:
        lat, lon = AT_PORT.get(vid, (None, None))
        session.add(Vessel(vessel_id=vid, name=name, vessel_type=vtype, imo=imo, mmsi=mmsi, flag=flag, built_year=built, entity=entity,
                           daily_opex=0, status=status, base_port=area, base_lat=lat, base_lon=lon))
    for ref, client, vtype, vid, scope, start, days, rate, note in AWARDS:
        session.add(Tender(ref=ref, client=client, vessel_type=vtype, vessel_id=vid, scope=scope, start_date=start, end_date=plus_days(start, days),
                           due_on=start, operating_rate=rate, standby_rate=rate, operating_share=1.0, probability=1.0, status="WON",
                           outcome_note=note, created_by="verified"))
    session.commit()
