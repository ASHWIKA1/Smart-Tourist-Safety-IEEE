"""Runtime service container wiring DB, Geo-fence, AI detector, Ledger, and WebSockets."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Optional

import numpy as np
from fastapi import WebSocket
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..anomaly import HybridGeofenceIFDetector, extract_window_features
from ..geofence import GeoFenceEngine
from ..identity import (
    CredentialIssuer,
    CredentialVerifier,
    LedgerRecord,
    PermissionedIdentityLedger,
)
from ..models import GeoPoint, GeoZone, ZoneCategory
from ..simulator import default_test_geography, generate_dataset
from .database import (
    Base,
    LedgerAnchorORM,
    ZoneORM,
    create_db_engine,
    make_session_factory,
)


class AlertBroadcaster:
    """Manages active Authority Dashboard WebSocket connections."""

    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._connections.add(ws)

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(ws)

    async def broadcast(self, payload: dict) -> None:
        async with self._lock:
            targets = list(self._connections)
        dead: list[WebSocket] = []
        message = json.dumps(payload, default=str)
        for ws in targets:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    self._connections.discard(ws)


class SafetySystemRuntime:
    """Holds initialized database engine, AI detector, geo-fence engine, and ledger."""

    def __init__(self, database_url: Optional[str] = None) -> None:
        self.engine = create_db_engine(database_url)
        Base.metadata.create_all(self.engine)
        self.SessionLocal = make_session_factory(self.engine)

        self.ledger = PermissionedIdentityLedger()
        self.issuer = CredentialIssuer("did:tourist:authority:in-tn-01")
        self.issuer.register_on_ledger(self.ledger)
        self.verifier = CredentialVerifier(self.ledger)

        default_zones, self.default_route = default_test_geography()
        self.geofence = GeoFenceEngine(default_zones)
        self.detector = self._train_baseline_detector()
        self.broadcaster = AlertBroadcaster()

        with self.SessionLocal() as db:
            self._seed_default_zones(db, default_zones)
            self._hydrate_zones_from_db(db)
            self._hydrate_ledger_from_db(db)

    @staticmethod
    def _train_baseline_detector() -> HybridGeofenceIFDetector:
        train_data = generate_dataset(n_trajectories=200, seed=42, gps_noise_m=3.5)
        val_data = generate_dataset(n_trajectories=80, seed=108, gps_noise_m=3.5)
        X_train = np.vstack(
            [
                extract_window_features(t.observations, t.planned_route).to_vector()
                for t in train_data
                if not t.is_anomalous
            ]
        )
        X_val = np.vstack(
            [
                extract_window_features(t.observations, t.planned_route).to_vector()
                for t in val_data
            ]
        )
        y_val = np.array([int(t.is_anomalous) for t in val_data])
        ctx_val = [t.zone_context for t in val_data]
        return HybridGeofenceIFDetector(
            n_estimators=150, contamination=0.08, random_state=42
        ).fit(X_train, X_val, y_val, ctx_val)

    @staticmethod
    def _seed_default_zones(db: Session, default_zones: list[GeoZone]) -> None:
        existing = db.scalars(select(ZoneORM.zone_id)).all()
        if existing:
            return
        for z in default_zones:
            db.add(
                ZoneORM(
                    zone_id=z.zone_id,
                    name=z.name,
                    category=z.category.value,
                    center_lat=z.center.lat if z.center else None,
                    center_lon=z.center.lon if z.center else None,
                    radius_m=z.radius_m,
                    buffer_m=z.buffer_m,
                    polygon_json=json.dumps([p.model_dump() for p in z.polygon])
                    if z.polygon
                    else None,
                )
            )
        db.commit()

    def _hydrate_zones_from_db(self, db: Session) -> None:
        rows = db.scalars(select(ZoneORM)).all()
        self.geofence = GeoFenceEngine([])
        for row in rows:
            polygon = (
                [GeoPoint(**p) for p in json.loads(row.polygon_json)]
                if row.polygon_json
                else None
            )
            center = (
                GeoPoint(lat=row.center_lat, lon=row.center_lon)
                if row.center_lat is not None and row.center_lon is not None
                else None
            )
            self.geofence.add_zone(
                GeoZone(
                    zone_id=row.zone_id,
                    name=row.name,
                    category=ZoneCategory(row.category),
                    center=center,
                    radius_m=row.radius_m,
                    buffer_m=row.buffer_m,
                    polygon=polygon,
                )
            )

    def _hydrate_ledger_from_db(self, db: Session) -> None:
        anchors = db.scalars(select(LedgerAnchorORM)).all()
        for a in anchors:
            rec = LedgerRecord(
                did=a.did,
                credential_id=a.credential_id,
                credential_hash=a.credential_hash,
                issuer_did=a.issuer_did,
                issued_at=_ensure_utc(a.issued_at),
                expires_at=_ensure_utc(a.expires_at),
                revoked=a.revoked,
                revoked_at=_ensure_utc(a.revoked_at) if a.revoked_at else None,
                revocation_reason=a.revocation_reason,
            )
            self.ledger.anchor_credential(rec)


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
