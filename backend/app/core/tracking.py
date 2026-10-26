"""Vessel positions from three sources, newest wins:

- REPORT: the noon position in the daily progress report (typed in by the vessel)
- VSAT:   the vessel's own GPS, posted automatically over its VSAT link by an onboard gateway (see api/positions.py)
- AIS:    the vessel's AIS transponder, picked up through aisstream.io (see scripts/ais_listener.py)

All times are UTC ISO text, "YYYY-MM-DDTHH:MM:SSZ", which sorts correctly as text.
"""
from datetime import datetime, timedelta, timezone

# A daily report's position is the noon position. SEAMEC works off India, so noon is taken as 12:00 IST.
# shortcut: a vessel working in another time zone would need its own noon offset.
NOON_UTC = "T06:30:00Z"

# AIS sends 91 for "latitude not available" and 181 for "longitude not available".
AIS_NO_LAT, AIS_NO_LON = 91, 181


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def report_time(on_date: str) -> str:
    return on_date + NOON_UTC


def age_hours(at: str) -> float:
    return round((utc_now() - parse_iso(at)).total_seconds() / 3600, 1)


def parse_aisstream(message: dict) -> dict | None:
    """A PositionReport from aisstream.io as {mmsi, lat, lon, sog, cog}; None for any other or unusable message.

    Message shape (aisstream.io documentation): {"MessageType": "PositionReport", "MetaData": {"MMSI": ...},
    "Message": {"PositionReport": {"UserID", "Latitude", "Longitude", "Sog", "Cog", "TrueHeading", ...}}}
    """
    if message.get("MessageType") != "PositionReport":
        return None
    report = (message.get("Message") or {}).get("PositionReport") or {}
    mmsi = report.get("UserID") or (message.get("MetaData") or {}).get("MMSI")
    lat, lon = report.get("Latitude"), report.get("Longitude")
    if mmsi is None or lat is None or lon is None:
        return None
    if abs(lat) >= AIS_NO_LAT or abs(lon) >= AIS_NO_LON or abs(lat) > 90 or abs(lon) > 180:
        return None
    sog = report.get("Sog")
    cog = report.get("Cog")
    return {
        "mmsi": str(mmsi).zfill(9),
        "lat": float(lat),
        "lon": float(lon),
        "sog": float(sog) if sog is not None and 0 <= sog < 102.3 else None,  # 102.3 = not available
        "cog": float(cog) if cog is not None and 0 <= cog < 360 else None,  # 360 = not available
    }


def too_soon(last_at: str | None, now: datetime, minutes: int) -> bool:
    """True when the last stored fix is newer than `minutes`; used to keep one AIS fix per vessel per interval."""
    return last_at is not None and now - parse_iso(last_at) < timedelta(minutes=minutes)
