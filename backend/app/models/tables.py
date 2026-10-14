"""설계서 4장 데이터 모델 (테이블 9개)."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from ..util import utcnow
from ..db import Base, JSONType


class Series(Base):
    __tablename__ = "series"
    series_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    source: Mapped[str] = mapped_column(String(200))  # 예: "FRED", "한국은행 ECOS", "SYNTHETIC"
    unit: Mapped[str] = mapped_column(String(32))  # level 단위 (index, %, KRW 등)
    frequency: Mapped[str] = mapped_column(String(16), default="D")
    license: Mapped[str] = mapped_column(Text, default="")
    source_url: Mapped[str] = mapped_column(Text, default="")


class SeriesValue(Base):
    __tablename__ = "series_value"
    __table_args__ = (UniqueConstraint("series_id", "date", name="uq_series_date"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    series_id: Mapped[str] = mapped_column(ForeignKey("series.series_id", ondelete="CASCADE"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    value: Mapped[float] = mapped_column(Float)
    collected_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class PolicyEvent(Base):
    __tablename__ = "policy_event"
    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    country: Mapped[str] = mapped_column(String(8))
    type: Mapped[str] = mapped_column(String(16))  # tariff | rate | regulation
    title: Mapped[str] = mapped_column(String(300))
    summary: Mapped[str] = mapped_column(Text, default="")
    targets: Mapped[list] = mapped_column(JSONType, default=list)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_text: Mapped[str] = mapped_column(String(64), default="")
    announced_at: Mapped[date] = mapped_column(Date, index=True)
    source: Mapped[str] = mapped_column(String(100), default="")
    source_url: Mapped[str] = mapped_column(Text, default="")
    license: Mapped[str] = mapped_column(Text, default="")
    raw_text: Mapped[str] = mapped_column(Text, default="")
    is_demo: Mapped[bool] = mapped_column(default=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Portfolio(Base):
    __tablename__ = "portfolio"
    portfolio_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    base_currency: Mapped[str] = mapped_column(String(8), default="USD")
    description: Mapped[str] = mapped_column(Text, default="")
    aum: Mapped[float] = mapped_column(Float, default=0.0)  # 억 원


class Holding(Base):
    __tablename__ = "holding"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    portfolio_id: Mapped[str] = mapped_column(ForeignKey("portfolio.portfolio_id", ondelete="CASCADE"), index=True)
    asset_id: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(100))
    asset_class: Mapped[str] = mapped_column(String(16))
    weight: Mapped[float] = mapped_column(Float)  # %
    currency: Mapped[str] = mapped_column(String(8))
    sector: Mapped[str] = mapped_column(String(32))
    # 가격 시계열 정의: {"series_id": ...} 또는 {"duration": 8.7, "yield_series": "DGS10"}
    pricing: Mapped[dict] = mapped_column(JSONType, default=dict)
    factors: Mapped[list] = mapped_column(JSONType, default=list)  # 회귀 설명 변수 (factor_id 목록)


class FactorBeta(Base):
    __tablename__ = "factor_beta"
    __table_args__ = (UniqueConstraint("asset_id", "factor_id", "window_end", name="uq_beta"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[str] = mapped_column(String(64), index=True)
    factor_id: Mapped[str] = mapped_column(String(32))
    beta: Mapped[float] = mapped_column(Float)
    std_err: Mapped[float] = mapped_column(Float)
    r2: Mapped[float] = mapped_column(Float)
    window_start: Mapped[date] = mapped_column(Date)
    window_end: Mapped[date] = mapped_column(Date)


class Run(Base):
    __tablename__ = "run"
    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    parent_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entry: Mapped[str] = mapped_column(String(16))
    input_text: Mapped[str] = mapped_column(Text, default="")
    event_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    portfolio_id: Mapped[str] = mapped_column(String(32))
    horizon_days: Mapped[int] = mapped_column(Integer, default=20)
    as_of: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="queued")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str] = mapped_column(String(300), default="")
    llm_mode: Mapped[str] = mapped_column(String(16), default="offline")
    state: Mapped[dict] = mapped_column(JSONType, default=dict)  # 최종 RunState
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AgentStep(Base):
    __tablename__ = "agent_step"
    step_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("run.run_id", ondelete="CASCADE"), index=True)
    agent: Mapped[str] = mapped_column(String(32))
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    input: Mapped[dict] = mapped_column(JSONType, default=dict)
    output: Mapped[dict] = mapped_column(JSONType, default=dict)
    status: Mapped[str] = mapped_column(String(16))  # running | done | retry | failed | skip
    note: Mapped[str] = mapped_column(Text, default="")
    model: Mapped[str] = mapped_column(String(64), default="")
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class CalcLog(Base):
    __tablename__ = "calc_log"
    calc_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("run.run_id", ondelete="CASCADE"), index=True)
    code_hash: Mapped[str] = mapped_column(String(80))
    engine_version: Mapped[str] = mapped_column(String(16))
    inputs: Mapped[dict] = mapped_column(JSONType, default=dict)
    outputs: Mapped[dict] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
