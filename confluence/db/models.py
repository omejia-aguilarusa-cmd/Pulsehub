from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Float, Integer, DateTime, JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    signal_id: Mapped[str] = mapped_column(String, index=True)
    symbol: Mapped[str] = mapped_column(String, index=True)
    asset_class: Mapped[str] = mapped_column(String)
    side: Mapped[str] = mapped_column(String)
    mode: Mapped[str] = mapped_column(String)
    entry: Mapped[float] = mapped_column(Float)
    stop: Mapped[float] = mapped_column(Float)
    target: Mapped[float] = mapped_column(Float)
    qty: Mapped[float] = mapped_column(Float)
    fees: Mapped[float] = mapped_column(Float, default=0.0)
    opened_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String, default="open")
    meta: Mapped[dict] = mapped_column(JSON, default={})


class Journal(Base):
    __tablename__ = "journal"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trade_id: Mapped[int] = mapped_column(Integer, index=True)
    pnl: Mapped[float] = mapped_column(Float)
    mae: Mapped[float] = mapped_column(Float)
    mfe: Mapped[float] = mapped_column(Float)
    r_realized: Mapped[float] = mapped_column(Float)
    hit: Mapped[int] = mapped_column(Integer)  # 1/0
    ev: Mapped[float] = mapped_column(Float)
    drawdown: Mapped[float] = mapped_column(Float)
    filled_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SignalLog(Base):
    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    signal_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    symbol: Mapped[str] = mapped_column(String, index=True)
    asset_class: Mapped[str] = mapped_column(String)
    side: Mapped[str] = mapped_column(String)
    mode: Mapped[str] = mapped_column(String)
    entry: Mapped[float] = mapped_column(Float)
    stop: Mapped[float] = mapped_column(Float)
    probability: Mapped[float] = mapped_column(Float)
    score: Mapped[float] = mapped_column(Float)
    rr: Mapped[float] = mapped_column(Float)
    confidence: Mapped[str] = mapped_column(String)
    sources: Mapped[dict] = mapped_column(JSON, default={})
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


__all__ = ["Base", "Trade", "Journal", "SignalLog"]
