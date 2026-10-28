"""The automatic position feed: a vessel's onboard VSAT/GPS gateway posts its positions here.

It is not used by people, so it does not use the sign-in cookie. Each vessel has its own key (X-Feed-Key header),
issued with scripts/feed_key.py, and a key can post positions for its own vessel only. The feed is switched off
until the first key is issued.

Satellite links drop, so gateways resend. A position within FEED_EVERY of one already kept for the vessel is
skipped: that drops exact resends, and keeps a gateway that posts every few seconds from filling the database.
"""
from bisect import bisect_left, insort
from datetime import timedelta

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import digest
from ..core.tracking import iso, parse_iso, utc_now
from ..db import get_session
from ..models import FeedKey, PositionFix, Vessel
from ..schemas import FeedIn

router = APIRouter(prefix="/api/positions", tags=["positions"])

MAX_AGE = timedelta(days=30)
CLOCK_SLACK = timedelta(minutes=10)
FEED_EVERY = timedelta(minutes=5)  # at most one stored position per vessel in any 5 minutes


def store_fixes(session: Session, fixes, vessel: Vessel) -> dict:
    """Save the fixes for the key's vessel, oldest first. Each skipped one gets its index and the reason."""
    now = utc_now()
    skipped, wanted = [], []
    for i, f in enumerate(fixes):
        if (f.vessel_id and f.vessel_id != vessel.vessel_id) or (f.mmsi and f.mmsi != vessel.mmsi):
            skipped.append({"index": i, "reason": f"this key is for {vessel.name} only"})
            continue
        at = parse_iso(f.at) if f.at else now
        if at > now + CLOCK_SLACK or at < now - MAX_AGE:
            skipped.append({"index": i, "reason": "time is in the future or older than 30 days"})
            continue
        wanted.append((at, i, f))
    if not wanted:
        return {"stored": 0, "skipped": skipped}

    # The positions already kept around this batch's times, so resends and too-close fixes can be spotted.
    first, last = min(w[0] for w in wanted) - FEED_EVERY, max(w[0] for w in wanted) + FEED_EVERY
    kept = sorted(parse_iso(at) for at in session.scalars(select(PositionFix.at).where(
        PositionFix.vessel_id == vessel.vessel_id, PositionFix.at >= iso(first), PositionFix.at <= iso(last))))
    stored = 0
    for at, i, f in sorted(wanted, key=lambda w: w[0]):
        j = bisect_left(kept, at)
        if (j < len(kept) and kept[j] - at < FEED_EVERY) or (j > 0 and at - kept[j - 1] < FEED_EVERY):
            skipped.append({"index": i, "reason": "a position within 5 minutes of this one is already stored"})
            continue
        insort(kept, at)
        session.add(PositionFix(vessel_id=vessel.vessel_id, at=iso(at), lat=f.lat, lon=f.lon, sog=f.sog, cog=f.cog, source="VSAT"))
        stored += 1
    return {"stored": stored, "skipped": sorted(skipped, key=lambda s: s["index"])}


@router.post("/feed")
def feed(body: FeedIn, x_feed_key: str = Header(default=""), session: Session = Depends(get_session)):
    if not session.scalar(select(func.count()).select_from(FeedKey)):
        raise HTTPException(503, "The position feed is switched off. Issue a vessel's key with: python -m scripts.feed_key <vessel_id>")
    key = session.scalar(select(FeedKey).where(FeedKey.digest == digest(x_feed_key))) if x_feed_key else None
    if key is None:
        raise HTTPException(401, "Wrong or missing X-Feed-Key.")
    result = store_fixes(session, body.fixes, session.get(Vessel, key.vessel_id))
    session.commit()  # not written to the audit log: a gateway posts every few minutes and would drown it
    return result
