from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.utcnow()


class ToolOrderModel(Base):
    __tablename__ = "gpt_tool_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_no: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    plan_type: Mapped[str] = mapped_column(String(20), index=True)
    link_mode: Mapped[str] = mapped_column(String(20), default="short")
    status: Mapped[str] = mapped_column(String(40), default="processing", index=True)

    checkout_url: Mapped[str] = mapped_column(Text, default="")
    short_url: Mapped[str] = mapped_column(Text, default="")
    stripe_checkout_url: Mapped[str] = mapped_column(Text, default="")
    checkout_session_id: Mapped[str] = mapped_column(String(180), default="")
    processor_entity: Mapped[str] = mapped_column(String(80), default="")
    source: Mapped[str] = mapped_column(String(80), default="")

    billing_country: Mapped[str] = mapped_column(String(8), default="")
    billing_currency: Mapped[str] = mapped_column(String(8), default="")

    account_email: Mapped[str] = mapped_column(String(255), default="", index=True)
    account_plan_type: Mapped[str] = mapped_column(String(80), default="")
    token_fingerprint: Mapped[str] = mapped_column(String(80), default="", index=True)

    last_error_code: Mapped[str] = mapped_column(String(120), default="")
    last_error_message: Mapped[str] = mapped_column(Text, default="")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    logs: Mapped[list["ToolOrderLogModel"]] = relationship(back_populates="order", cascade="all, delete-orphan")


class ToolOrderLogModel(Base):
    __tablename__ = "gpt_tool_order_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("gpt_tool_orders.id"), index=True)
    level: Mapped[str] = mapped_column(String(40), default="info")
    step: Mapped[str] = mapped_column(String(120), index=True)
    message: Mapped[str] = mapped_column(Text, default="")
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    order: Mapped[ToolOrderModel] = relationship(back_populates="logs")
