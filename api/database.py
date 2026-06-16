"""
Base de datos SQLite con SQLModel
"""

from sqlmodel import SQLModel, create_engine, Session
from contextlib import contextmanager

DATABASE_URL = "sqlite:///./data/legal_mvp.db"
engine = create_engine(DATABASE_URL, echo=False, connect_args={"check_same_thread": False})


async def init_db():
    SQLModel.metadata.create_all(engine)
    print("[DB] Base de datos inicializada")


def get_session():
    with Session(engine) as session:
        yield session


@contextmanager
def get_sync_session():
    with Session(engine) as session:
        yield session
