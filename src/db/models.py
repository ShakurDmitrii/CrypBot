from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base


class RequestStatus(str, enum.Enum):
    NEW = "new"
    WAITING_PAYMENT = "waiting_payment"
    PAYMENT_RECEIVED = "payment_received"
    PROCESSING = "processing"
    DONE = "done"
    CANCELED = "canceled"
    DISPUTED = "disputed"


class AmlStatus(str, enum.Enum):
    PENDING = "pending"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    REJECTED = "rejected"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    requests: Mapped[list["ExchangeRequest"]] = relationship(back_populates="user")


class ExchangeRequest(Base):
    __tablename__ = "exchange_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(32), default="telegram")
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    direction: Mapped[str] = mapped_column(String(64), nullable=False)
    amount_send: Mapped[float] = mapped_column(Float, nullable=False)
    amount_receive: Mapped[float] = mapped_column(Float, nullable=False)
    base_rate: Mapped[float] = mapped_column(Float, nullable=False)
    margin_percent: Mapped[float] = mapped_column(Float, nullable=False)
    final_rate: Mapped[float] = mapped_column(Float, nullable=False)
    user_requisites: Mapped[str | None] = mapped_column(Text, nullable=True)
    exchange_requisites: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[RequestStatus] = mapped_column(
        Enum(RequestStatus, name="request_status"), default=RequestStatus.NEW, nullable=False
    )
    status_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="requests")
    history: Mapped[list["RequestStatusHistory"]] = relationship(back_populates="request")
    aml_checks: Mapped[list["AmlCheck"]] = relationship(back_populates="request")


class RequestStatusHistory(Base):
    __tablename__ = "request_status_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("exchange_requests.id"), index=True, nullable=False)
    status: Mapped[RequestStatus] = mapped_column(
        Enum(RequestStatus, name="request_status"), nullable=False
    )
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    changed_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    request: Mapped["ExchangeRequest"] = relationship(back_populates="history")


class AmlCheck(Base):
    __tablename__ = "aml_checks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[int | None] = mapped_column(
        ForeignKey("exchange_requests.id"), nullable=True, index=True
    )
    telegram_user_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    check_type: Mapped[str] = mapped_column(String(32), nullable=False)
    value: Mapped[str] = mapped_column(String(256), nullable=False)
    status: Mapped[AmlStatus] = mapped_column(
        Enum(AmlStatus, name="aml_status"), default=AmlStatus.PENDING, nullable=False
    )
    result_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    request: Mapped["ExchangeRequest | None"] = relationship(back_populates="aml_checks")
