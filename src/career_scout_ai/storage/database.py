from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from career_scout_ai.storage.models import Base

DEFAULT_DB_PATH = Path(__file__).resolve().parents[3] / "data" / "career_scout.db"


def get_engine(db_path: Path = DEFAULT_DB_PATH) -> Engine:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(f"sqlite:///{db_path}", echo=False)


def init_db(db_path: Path = DEFAULT_DB_PATH) -> Engine:
    """Create all tables. Idempotent — safe to call multiple times."""
    engine = get_engine(db_path)
    Base.metadata.create_all(engine)
    return engine


def get_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine)
