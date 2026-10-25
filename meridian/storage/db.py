"""Persistence for fills, events and PnL points (SQLite locally, Postgres on Render).

Writes are tiny and infrequent, so they run in a worker thread via `asyncio.to_thread`
and never block the trading loop.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Engine
from sqlalchemy.pool import StaticPool
from sqlmodel import Field, Session, SQLModel, create_engine, select


def utcnow() -> datetime:
    return datetime.now(UTC)


class FillRow(SQLModel, table=True):
    __tablename__ = "fills"
    id: int | None = Field(default=None, primary_key=True)
    fill_id: str = Field(index=True, unique=True)
    order_id: str | None = None
    client_order_id: str | None = None
    side: str
    size: int
    price: str
    fee: str
    role: str
    realized_delta: str
    position_after: int
    ts: datetime = Field(default_factory=utcnow, index=True)


class EventRow(SQLModel, table=True):
    __tablename__ = "events"
    id: int | None = Field(default=None, primary_key=True)
    kind: str = Field(index=True)
    message: str
    ts: datetime = Field(default_factory=utcnow, index=True)


class DecisionRow(SQLModel, table=True):
    __tablename__ = "decisions"
    id: int | None = Field(default=None, primary_key=True)
    kind: str = Field(index=True)
    summary: str
    payload: str  # the full decision record as JSON, including every input value
    ts: datetime = Field(default_factory=utcnow, index=True)


class PnlRow(SQLModel, table=True):
    __tablename__ = "pnl_points"
    id: int | None = Field(default=None, primary_key=True)
    realized: str
    unrealized: str
    total: str
    position: int
    mark: str | None = None
    ts: datetime = Field(default_factory=utcnow, index=True)


def normalize_url(url: str) -> str:
    # Render hands out postgres:// URLs; SQLAlchemy + psycopg 3 needs postgresql+psycopg://
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    return url


def make_engine(url: str) -> Engine:
    url = normalize_url(url)
    if url.startswith("sqlite"):
        kwargs: dict = {"connect_args": {"check_same_thread": False}}
        if ":memory:" in url:
            kwargs["poolclass"] = StaticPool
        engine = create_engine(url, **kwargs)
    else:
        engine = create_engine(url, pool_pre_ping=True)
    SQLModel.metadata.create_all(engine)
    return engine


class Store:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def add(self, row: SQLModel) -> None:
        with Session(self.engine) as s:
            s.add(row)
            try:
                s.commit()
            except Exception:
                s.rollback()  # duplicate fill ids are expected after a reconnect

    def recent_fills(self, limit: int = 100) -> list[FillRow]:
        with Session(self.engine) as s:
            return list(s.exec(select(FillRow).order_by(FillRow.id.desc()).limit(limit)))

    def recent_events(self, limit: int = 200) -> list[EventRow]:
        with Session(self.engine) as s:
            return list(s.exec(select(EventRow).order_by(EventRow.id.desc()).limit(limit)))

    def pnl_history(self, limit: int = 720) -> list[PnlRow]:
        with Session(self.engine) as s:
            rows = list(s.exec(select(PnlRow).order_by(PnlRow.id.desc()).limit(limit)))
        return list(reversed(rows))
