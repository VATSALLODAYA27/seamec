"""Issue, replace or withdraw the position-feed key for one vessel's onboard VSAT gateway.

The key is printed once: give it to the gateway as its X-Feed-Key header. MARIS keeps only its SHA-256, so a lost
key is replaced, not recovered. Issuing a new key for a vessel replaces its old one straight away.

Run from backend/:
    python -m scripts.feed_key SM-PRINCESS            issue (or replace) the key
    python -m scripts.feed_key SM-PRINCESS --revoke   withdraw it
"""
import secrets
import sys

from app.auth import digest
from app.db import SessionLocal, migrate
from app.models import FeedKey, Vessel


def issue(session, vessel_id: str) -> str:
    if session.get(Vessel, vessel_id) is None:
        raise SystemExit(f"No vessel {vessel_id}.")
    key = secrets.token_urlsafe(32)
    session.merge(FeedKey(vessel_id=vessel_id, digest=digest(key)))
    session.commit()
    return key


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    migrate()
    with SessionLocal() as session:
        vessel_id = sys.argv[1]
        if "--revoke" in sys.argv:
            row = session.get(FeedKey, vessel_id)
            if row:
                session.delete(row)
                session.commit()
            print(f"{vessel_id}: no feed key now.")
        else:
            print(f"{vessel_id} feed key (shown once; give it to the gateway as X-Feed-Key):")
            print(issue(session, vessel_id))
