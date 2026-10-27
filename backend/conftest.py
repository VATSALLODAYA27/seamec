import os
import tempfile

# Must be set before app.config is imported, so tests never touch the real database.
os.environ["SEAMEC_VAR_DIR"] = tempfile.mkdtemp(prefix="seamec-test-")


import pytest  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def data():
    """One demo database for the whole run, loaded once."""
    from app.db import SessionLocal, migrate
    from scripts.seed import seed, seed_users

    migrate()
    with SessionLocal() as session:
        seed_users(session)
        seed(session)
