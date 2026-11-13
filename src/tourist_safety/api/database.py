"""SQLAlchemy 2.0 database models and session management.

Defaults to local SQLite for zero-config development/testing, and supports
PostgreSQL + PostGIS via the DATABASE_URL environment variable.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


def get_database_url() -> str:
    return os.getenv("DATABASE_URL", "sqlite:///./tourist_safety.db")


class Base(DeclarativeBase):
    pass


class UserORM(Base):
    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32))  # tourist | authority | admin
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class TouristProfileORM(Base):
    __tablename__ = "tourist_profiles"

    tourist_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True
    )
    full_name: Mapped[str] = mapped_column(String(255))
    nationality: Mapped[str] = mapped_column(String(64))
    passport_or_id_number: Mapped[str] = mapped_column(String(128))
    emergency_contact_name: Mapped[str] = mapped_column(String(255))
    emergency_contact_phone: Mapped[str] = mapped_column(String(64))
    tracking_consent: Mapped[bool] = mapped_column(Boolean, default=False)
    did: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class CredentialOffchainORM(Base):
    __tablename__ = "credentials_offchain"

    credential_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    tourist_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("tourist_profiles.tourist_id", ondelete="CASCADE"), index=True
    )
    did: Mapped[str] = mapped_column(String(128), index=True)
    issuer_did: Mapped[str] = mapped_column(String(128))
    credential_json: Mapped[str] = mapped_column(Text)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class LedgerAnchorORM(Base):
    __tablename__ = "ledger_anchors"

    credential_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    did: Mapped[str] = mapped_column(String(128), index=True)
    credential_hash: Mapped[str] = mapped_column(String(64))
    issuer_did: Mapped[str] = mapped_column(String(128))
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    revocation_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    block_hash: Mapped[str] = mapped_column(String(64))


class ZoneORM(Base):
    __tablename__ = "zones"

    zone_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(32))
    center_lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    center_lon: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    radius_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    buffer_m: Mapped[float] = mapped_column(Float, default=25.0)
    polygon_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class GPSObservationORM(Base):
    __tablename__ = "gps_observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tourist_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("tourist_profiles.tourist_id", ondelete="CASCADE"), index=True
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    accuracy_m: Mapped[float] = mapped_column(Float, default=5.0)
    sos_active: Mapped[bool] = mapped_column(Boolean, default=False)


class ZoneTransitionORM(Base):
    __tablename__ = "zone_transitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tourist_id: Mapped[str] = mapped_column(String(64), index=True)
    zone_id: Mapped[str] = mapped_column(String(64), index=True)
    category: Mapped[str] = mapped_column(String(32))
    previous_state: Mapped[str] = mapped_column(String(32))
    new_state: Mapped[str] = mapped_column(String(32))
    event_type: Mapped[str] = mapped_column(String(32))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class IncidentORM(Base):
    __tablename__ = "incidents"

    alert_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tourist_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("tourist_profiles.tourist_id", ondelete="CASCADE"), index=True
    )
    event_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    priority: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str] = mapped_column(String(255))
    zone_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    zone_category: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    anomaly_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    in_progress_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


def create_db_engine(database_url: Optional[str] = None):
    url = database_url or get_database_url()
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args, future=True)


def make_session_factory(engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
