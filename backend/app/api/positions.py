"""The automatic position feed: an onboard VSAT/GPS gateway (or the AIS listener) posts positions here.

It is not used by people, so it does not use the sign-in cookie. It needs the shared key in the X-Feed-Key header,
and it is switched off until MARIS_FEED_KEY is set.
"""
import hmac
from datetime import timedelta

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config
from ..core.tracking import iso, parse_iso, utc_now
from ..db import get_session
from ..models import PositionFix, Vessel
from ..schemas import FeedIn

router = APIRouter(prefix="/api/positions", tags=["positions"])

MAX_AGE = timedelta(days=30)
CLOCK_SLACK = timedelta(minutes=10)


def store_fixes(session: Session, fixes) -> dict:
    """Save fixes for known vessels; skip (with a reason) unknown vessels and impossible times."""
    vessels = session.scalars(select(Vessel)).all()
    by_id = {v.vessel_id: v for v in vessels}
    by_mmsi = {v.mmsi: v for v in vessels if v.mmsi}
    now = utc_now()
    stored, skipped = 0, []
    for i, f in enumerate(fixes):
        vessel = by_id.get(f.vessel_id) if f.vessel_id else by_mmsi.get(f.mmsi)
        if vessel is None:
            skipped.append({"index": i, "reason": f"unknown vessel {f.vessel_id or f.mmsi}"})
            continue
        at = parse_iso(f.at) if f.at else now
        if at > now + CLOCK_SLACK or at < now - MAX_AGE:
            skipped.append({"index": i, "reason": "time is in the future or older than 30 days"})
            continue
        session.add(PositionFix(vessel_id=vessel.vessel_id, at=iso(at), lat=f.lat, lon=f.lon, sog=f.sog, cog=f.cog, source=f.source))
        stored += 1
    return {"stored": stored, "skipped": skipped}


@router.post("/feed")
def feed(body: FeedIn, x_feed_key: str = Header(default=""), session: Session = Depends(get_session)):
    if not config.FEED_KEY:
        raise HTTPException(503, "The position feed is switched off. Set MARIS_FEED_KEY on the server to switch it on.")
    if not hmac.compare_digest(x_feed_key.encode(), config.FEED_KEY.encode()):
        raise HTTPException(401, "Wrong or missing X-Feed-Key.")
    result = store_fixes(session, body.fixes)
    session.commit()  # not written to the audit log: a gateway posts every few minutes and would drown it
    return result
