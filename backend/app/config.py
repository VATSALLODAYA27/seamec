import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")  # optional local settings

SETUP_DIR = BACKEND_DIR.parent / "setup"
SEED_USERS_FILE = SETUP_DIR / "logins.json"

# Everything the tool writes lives in var/.
VAR_DIR = Path(os.environ.get("SEAMEC_VAR_DIR", BACKEND_DIR / "var"))
# One SQLite file by default. Set SEAMEC_DATABASE_URL to use a database server instead.
DATABASE_URL = os.environ.get("SEAMEC_DATABASE_URL", f"sqlite:///{VAR_DIR / 'app.db'}")

FRONTEND_DIST = BACKEND_DIR.parent / "frontend" / "dist"
# Set SEAMEC_COOKIE_SECURE=1 once the tool is served over HTTPS.
COOKIE_SECURE = os.environ.get("SEAMEC_COOKIE_SECURE") == "1"

# Automatic positions. AISSTREAM_API_KEY is used by scripts/ais_listener.py; not set by default. The VSAT feed uses
# one key per vessel, issued with scripts/feed_key.py and kept (hashed) in the database.
AISSTREAM_API_KEY = os.environ.get("AISSTREAM_API_KEY", "")
POSITION_STALE_HOURS = 36  # a vessel not heard from for longer is shown as stale
