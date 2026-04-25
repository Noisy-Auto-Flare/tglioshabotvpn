from datetime import datetime
from enum import Enum
from typing import Optional
from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base

class SubscriptionStatus(str, Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    PENDING = "pending"

class PaymentStatus(str, Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    balance: Mapped[float] = mapped_column(Float, default=0.0)
    referral_code: Mapped[str] = mapped_column(String, unique=True, index=True)
    referred_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    subscriptions: Mapped[list["Subscription"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    vpn_keys: Mapped[list["VPNKey"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    payments: Mapped[list["Payment"]] = relationship(back_populates="user", cascade="all, delete-orphan")

class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    plan: Mapped[str] = mapped_column(String)  # trial, 30, 90, 180, 360
    traffic_limit_gb: Mapped[Optional[int]] = mapped_column(Integer)
    start_date: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    end_date: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[SubscriptionStatus] = mapped_column(String, default=SubscriptionStatus.ACTIVE)
    reset_count: Mapped[int] = mapped_column(Integer, default=0)

    user: Mapped["User"] = relationship(back_populates="subscriptions")
    vpn_key: Mapped[Optional["VPNKey"]] = relationship(back_populates="subscription", cascade="all, delete-orphan")

class VPNKey(Base):
    __tablename__ = "vpn_keys"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    subscription_id: Mapped[Optional[int]] = mapped_column(ForeignKey("subscriptions.id"))
    uuid: Mapped[Optional[str]] = mapped_column(String, unique=True, index=True)
    config: Mapped[str] = mapped_column(Text)
    expire_at: Mapped[datetime] = mapped_column(DateTime)
    is_active: Mapped[bool] = mapped_column(default=True)
    error_message: Mapped[Optional[str]] = mapped_column(String)

    user: Mapped["User"] = relationship(back_populates="vpn_keys")
    subscription: Mapped[Optional["Subscription"]] = relationship(back_populates="vpn_key")

class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String, default="RUB")
    provider: Mapped[str] = mapped_column(String)  # balance, sbp, cryptobot, cryptomus, stars, ton
    status: Mapped[PaymentStatus] = mapped_column(String, default=PaymentStatus.PENDING)
    external_id: Mapped[Optional[str]] = mapped_column(String, unique=True, index=True)
    payload: Mapped[Optional[str]] = mapped_column(String) # tariff_id or plan_days
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    user: Mapped["User"] = relationship(back_populates="payments")

class Screen(Base):
    __tablename__ = "screens"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String, unique=True, index=True)
    text: Mapped[str] = mapped_column(Text)
    image_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
