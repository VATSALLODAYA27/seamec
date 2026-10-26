from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from . import config

config.VAR_DIR.mkdir(parents=True, exist_ok=True)

IS_SQLITE = config.DATABASE_URL.startswith("sqlite")
engine = create_engine(config.DATABASE_URL, connect_args={"check_same_thread": False} if IS_SQLITE else {})
SessionLocal = sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_session():
    with SessionLocal() as session:
        yield session


def migrate(target=engine) -> None:
    """Create any missing tables. Existing tables and rows are left alone."""
    # shortcut: create_all never changes an existing table; add Alembic before real data is kept.
    from . import models  # noqa: F401  (registers every table)

    Base.metadata.create_all(target)
