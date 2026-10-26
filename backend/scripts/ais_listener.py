"""Bring in live AIS positions for the fleet from aisstream.io and store them as AIS fixes.

aisstream.io rules this follows (from its documentation): connect from a server, never a browser; keep the key
server-side; send the subscription within 3 seconds; at most 200 MMSIs per subscription; no replay, so a gap while
disconnected is simply missed.

Coverage: AIS from shore stations reaches roughly 30 nautical miles. A vessel working further offshore (Mumbai High
is about 85 nm out) may not be heard; its position then still comes from daily reports or VSAT.

Setup: put the key in backend/.env as AISSTREAM_API_KEY=... (see .env.example). Then, from backend/:
    python -m scripts.ais_listener              keep running (restart it with the server)
    python -m scripts.ais_listener --minutes 5  run for 5 minutes and print a summary (a quick check)

Only vessels with an MMSI in MARIS are followed. One fix per vessel is stored every STORE_EVERY_MINUTES.
"""
import argparse
import asyncio
import json
import sys
import time

from sqlalchemy import func, select

from app import config
from app.core.tracking import iso, parse_aisstream, too_soon, utc_now
from app.db import SessionLocal, migrate
from app.models import PositionFix, Vessel

URL = "wss://stream.aisstream.io/v0/stream"
STORE_EVERY_MINUTES = 15
STATUS_EVERY_SECONDS = 60
# aisstream.io does not send an error for a wrong key: it just closes the connection straight away. This many
# immediate drops in a row, with nothing received, is taken as a refused key rather than a network problem.
QUICK_DROP_SECONDS = 15
QUICK_DROPS_MEAN_REFUSED = 3
WHOLE_WORLD = [[[-90, -180], [90, 180]]]  # a bounding box is required; the MMSI filter does the narrowing


class Refused(Exception):
    """aisstream.io answered with an error (wrong key, malformed subscription): retrying will not help."""


def fleet_mmsis(session) -> dict[str, tuple[str, str]]:
    return {v.mmsi: (v.vessel_id, v.name) for v in session.scalars(select(Vessel).where(Vessel.mmsi.is_not(None)))}


def last_fixes(session) -> dict[str, str]:
    rows = session.execute(select(PositionFix.vessel_id, func.max(PositionFix.at)).where(PositionFix.source == "AIS").group_by(PositionFix.vessel_id))
    return dict(rows.all())


async def listen(stop_at: float | None) -> dict:
    import websockets  # only this script needs it

    migrate()
    with SessionLocal() as session:
        fleet = fleet_mmsis(session)
        last = last_fixes(session)
    if not fleet:
        sys.exit("No vessel has an MMSI in MARIS, so there is nothing to follow.")
    subscription = {"APIKey": config.AISSTREAM_API_KEY, "BoundingBoxes": WHOLE_WORLD,
                    "FiltersShipMMSI": list(fleet)[:200], "FilterMessageTypes": ["PositionReport"]}
    heard: dict[str, int] = {}
    stored = 0
    delay = 5
    quick_drops = 0
    next_status = time.monotonic() + STATUS_EVERY_SECONDS
    while stop_at is None or time.monotonic() < stop_at:
        try:
            opened, received = time.monotonic(), False
            async with websockets.connect(URL) as ws:
                await ws.send(json.dumps(subscription))  # within aisstream's 3-second limit
                print(f"Subscribed for {len(fleet)} vessels: {', '.join(name for _, name in fleet.values())}. Waiting for data.", flush=True)
                while stop_at is None or time.monotonic() < stop_at:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=5)
                    except asyncio.TimeoutError:
                        raw = None
                    if time.monotonic() >= next_status:
                        print(f"{iso(utc_now())}  listening; position reports heard so far: {sum(heard.values())}, stored: {stored}", flush=True)
                        next_status = time.monotonic() + STATUS_EVERY_SECONDS
                    if raw is None:
                        continue
                    if not received:
                        received, quick_drops, delay = True, 0, 5
                        print("Data is flowing: the key was accepted.", flush=True)
                    message = json.loads(raw)
                    if message.get("error"):
                        raise Refused(message["error"])
                    fix = parse_aisstream(message)
                    if not fix or fix["mmsi"] not in fleet:
                        continue
                    vessel_id, name = fleet[fix["mmsi"]]
                    heard[name] = heard.get(name, 0) + 1
                    now = utc_now()
                    if too_soon(last.get(vessel_id), now, STORE_EVERY_MINUTES):
                        continue
                    with SessionLocal() as session:
                        session.add(PositionFix(vessel_id=vessel_id, at=iso(now), lat=fix["lat"], lon=fix["lon"], sog=fix["sog"], cog=fix["cog"], source="AIS"))
                        session.commit()
                    last[vessel_id] = iso(now)
                    stored += 1
                    print(f"{iso(now)}  {name}: {fix['lat']:.4f}, {fix['lon']:.4f}" + (f", {fix['sog']:.1f} kn" if fix["sog"] is not None else ""), flush=True)
        except Refused:
            raise
        except (OSError, websockets.WebSocketException) as error:
            if not received and time.monotonic() - opened < QUICK_DROP_SECONDS:
                quick_drops += 1
                if quick_drops >= QUICK_DROPS_MEAN_REFUSED:
                    raise Refused("it closed the connection straight after the subscription, three times, without sending anything")
            print(f"Connection lost ({error}); retrying in {delay} s.", flush=True)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 300)  # back off, up to 5 minutes
    return {"heard": heard, "stored": stored, "fleet": [name for _, name in fleet.values()]}


def main() -> None:
    parser = argparse.ArgumentParser(description="Live AIS positions for the MARIS fleet from aisstream.io")
    parser.add_argument("--minutes", type=float, help="stop after this many minutes and print a summary")
    args = parser.parse_args()
    if not config.AISSTREAM_API_KEY:
        sys.exit("No key: add AISSTREAM_API_KEY=... to backend/.env (copy .env.example), then run this again.")
    stop_at = time.monotonic() + args.minutes * 60 if args.minutes else None
    try:
        result = asyncio.run(listen(stop_at))
    except Refused as error:
        sys.exit(f"aisstream.io refused the connection: {error}. Check the key in backend/.env.")
    except KeyboardInterrupt:
        return
    print("\nSummary")
    for name in result["fleet"]:
        print(f"  {name}: {result['heard'].get(name, 0)} position reports heard")
    print(f"  Stored as AIS fixes: {result['stored']}")
    if not result["heard"]:
        print("  None heard. Normal if the vessels are beyond shore-station range (about 30 nm) or have AIS off;"
              " their positions keep coming from daily reports and VSAT.")


if __name__ == "__main__":
    main()
