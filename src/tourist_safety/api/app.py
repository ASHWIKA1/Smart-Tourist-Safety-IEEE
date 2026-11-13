"""FastAPI REST & WebSocket backend for Smart Tourist Safety Monitoring System."""

from __future__ import annotations

import json
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..anomaly import extract_window_features
from ..identity import VerifiableCredential
from ..models import (
    AlertPriority,
    GeoZone,
    GPSObservation,
    IncidentStatus,
    ZoneCategory,
    ZoneState,
)
from .database import (
    CredentialOffchainORM,
    GPSObservationORM,
    IncidentORM,
    LedgerAnchorORM,
    TouristProfileORM,
    UserORM,
    ZoneORM,
    ZoneTransitionORM,
)
from .schemas import (
    AuthResponse,
    ConsentUpdateRequest,
    CreateZoneRequest,
    GPSIngestRequest,
    IncidentResponse,
    IncidentStatusUpdateRequest,
    IssueCredentialRequest,
    LoginRequest,
    RegisterRequest,
    RevokeCredentialRequest,
    SOSRequest,
    TelemetryEvaluationResponse,
    TouristProfileResponse,
    VerifyCredentialRequest,
)
from .security import (
    TokenPrincipal,
    create_access_token,
    get_current_principal,
    hash_password,
    require_roles,
    verify_password,
)
from .services import SafetySystemRuntime, _ensure_utc


def create_app(database_url: Optional[str] = None) -> FastAPI:
    runtime = SafetySystemRuntime(database_url=database_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.runtime = runtime
        yield

    app = FastAPI(
        title="Smart Tourist Safety Monitoring & Incident Response API",
        version="0.2.0",
        lifespan=lifespan,
    )
    app.state.runtime = runtime

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def get_runtime(request: Request) -> SafetySystemRuntime:
        return request.app.state.runtime

    def get_db(rt: SafetySystemRuntime = Depends(get_runtime)):
        db = rt.SessionLocal()
        try:
            yield db
        finally:
            db.close()

    @app.get("/health")
    def health(rt: SafetySystemRuntime = Depends(get_runtime)):
        return {
            "status": "ok",
            "zones_loaded": len(rt.geofence.list_zones()),
            "ledger_blocks": rt.ledger.block_count(),
            "ledger_intact": rt.ledger.chain_is_intact(),
        }

    # --- Authentication & Registration ---

    @app.post("/api/v1/auth/register", response_model=AuthResponse, status_code=201)
    def register(req: RegisterRequest, db: Session = Depends(get_db)):
        existing = db.scalar(select(UserORM).where(UserORM.email == req.email))
        if existing is not None:
            raise HTTPException(status_code=409, detail="Email is already registered.")

        user_id = f"usr-{uuid.uuid4().hex[:12]}"
        user = UserORM(
            user_id=user_id,
            email=req.email,
            password_hash=hash_password(req.password),
            role=req.role,
        )
        db.add(user)

        if req.role == "tourist":
            profile = TouristProfileORM(
                tourist_id=user_id,
                full_name=req.full_name or req.email.split("@")[0],
                nationality=req.nationality,
                passport_or_id_number=req.passport_or_id_number,
                emergency_contact_name=req.emergency_contact_name,
                emergency_contact_phone=req.emergency_contact_phone,
                tracking_consent=req.tracking_consent,
            )
            db.add(profile)

        db.commit()
        token = create_access_token(user_id=user.user_id, email=user.email, role=user.role)
        return AuthResponse(access_token=token, user_id=user.user_id, role=user.role)

    @app.post("/api/v1/auth/login", response_model=AuthResponse)
    def login(req: LoginRequest, db: Session = Depends(get_db)):
        user = db.scalar(select(UserORM).where(UserORM.email == req.email))
        if user is None or not verify_password(req.password, user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid email or password.")
        token = create_access_token(user_id=user.user_id, email=user.email, role=user.role)
        return AuthResponse(access_token=token, user_id=user.user_id, role=user.role)

    # --- Tourist Profile & Consent ---

    @app.get("/api/v1/tourists/me", response_model=TouristProfileResponse)
    def get_my_profile(
        principal: TokenPrincipal = Depends(require_roles("tourist")),
        db: Session = Depends(get_db),
    ):
        prof = db.get(TouristProfileORM, principal.user_id)
        if prof is None:
            raise HTTPException(status_code=404, detail="Tourist profile not found.")
        return TouristProfileResponse(
            tourist_id=prof.tourist_id,
            full_name=prof.full_name,
            nationality=prof.nationality,
            passport_or_id_number=prof.passport_or_id_number,
            emergency_contact_name=prof.emergency_contact_name,
            emergency_contact_phone=prof.emergency_contact_phone,
            tracking_consent=prof.tracking_consent,
            did=prof.did,
        )

    @app.put("/api/v1/tourists/me/consent", response_model=TouristProfileResponse)
    def update_consent(
        req: ConsentUpdateRequest,
        principal: TokenPrincipal = Depends(require_roles("tourist")),
        db: Session = Depends(get_db),
    ):
        prof = db.get(TouristProfileORM, principal.user_id)
        if prof is None:
            raise HTTPException(status_code=404, detail="Tourist profile not found.")
        prof.tracking_consent = req.tracking_consent
        prof.updated_at = datetime.now(timezone.utc)
        db.commit()
        return TouristProfileResponse(
            tourist_id=prof.tourist_id,
            full_name=prof.full_name,
            nationality=prof.nationality,
            passport_or_id_number=prof.passport_or_id_number,
            emergency_contact_name=prof.emergency_contact_name,
            emergency_contact_phone=prof.emergency_contact_phone,
            tracking_consent=prof.tracking_consent,
            did=prof.did,
        )

    @app.get("/api/v1/tourists/{tourist_id}", response_model=TouristProfileResponse)
    def get_tourist_by_authority(
        tourist_id: str,
        _: TokenPrincipal = Depends(require_roles("authority", "admin")),
        db: Session = Depends(get_db),
    ):
        prof = db.get(TouristProfileORM, tourist_id)
        if prof is None:
            raise HTTPException(status_code=404, detail="Tourist profile not found.")
        return TouristProfileResponse(
            tourist_id=prof.tourist_id,
            full_name=prof.full_name,
            nationality=prof.nationality,
            passport_or_id_number=prof.passport_or_id_number,
            emergency_contact_name=prof.emergency_contact_name,
            emergency_contact_phone=prof.emergency_contact_phone,
            tracking_consent=prof.tracking_consent,
            did=prof.did,
        )

    # --- Digital Identity & Permissioned Ledger ---

    @app.post("/api/v1/credentials/issue")
    def issue_credential(
        req: IssueCredentialRequest,
        _: TokenPrincipal = Depends(require_roles("authority", "admin")),
        rt: SafetySystemRuntime = Depends(get_runtime),
        db: Session = Depends(get_db),
    ):
        prof = db.get(TouristProfileORM, req.tourist_id)
        if prof is None:
            raise HTTPException(status_code=404, detail="Tourist profile not found.")

        vc = rt.issuer.issue_credential(
            ledger=rt.ledger,
            full_name=prof.full_name,
            nationality=prof.nationality,
            passport_or_id_number=prof.passport_or_id_number,
            emergency_contact_name=prof.emergency_contact_name,
            emergency_contact_phone=prof.emergency_contact_phone,
            validity_days=req.validity_days,
        )
        prof.did = vc.credential_subject.did

        db.add(
            CredentialOffchainORM(
                credential_id=vc.credential_id,
                tourist_id=prof.tourist_id,
                did=vc.credential_subject.did,
                issuer_did=vc.issuer_did,
                credential_json=vc.model_dump_json(),
                issued_at=vc.issuance_date,
                expires_at=vc.expiration_date,
            )
        )
        latest_block = rt.ledger._blocks[-1]
        db.add(
            LedgerAnchorORM(
                credential_id=vc.credential_id,
                did=vc.credential_subject.did,
                credential_hash=vc.content_hash(),
                issuer_did=vc.issuer_did,
                issued_at=vc.issuance_date,
                expires_at=vc.expiration_date,
                revoked=False,
                block_hash=latest_block.block_hash,
            )
        )
        db.commit()
        return {
            "credential": vc.model_dump(mode="json"),
            "ledger_block_hash": latest_block.block_hash,
        }

    @app.get("/api/v1/credentials/me")
    def get_my_credential(
        principal: TokenPrincipal = Depends(require_roles("tourist")),
        db: Session = Depends(get_db),
    ):
        cred = db.scalar(
            select(CredentialOffchainORM)
            .where(CredentialOffchainORM.tourist_id == principal.user_id)
            .order_by(desc(CredentialOffchainORM.issued_at))
        )
        if cred is None:
            raise HTTPException(status_code=404, detail="No credential issued yet.")
        return json.loads(cred.credential_json)

    @app.post("/api/v1/credentials/verify")
    def verify_credential(
        req: VerifyCredentialRequest,
        _: TokenPrincipal = Depends(require_roles("authority", "admin")),
        rt: SafetySystemRuntime = Depends(get_runtime),
    ):
        res = rt.verifier.verify(
            req.credential, presentation_nonce=req.presentation_nonce
        )
        return {
            "valid": res.valid,
            "reason": res.reason,
            "did": res.did,
            "credential_id": res.credential_id,
            "hash_match": res.hash_match,
            "signature_valid": res.signature_valid,
            "issuer_trusted": res.issuer_trusted,
            "not_expired": res.not_expired,
            "not_revoked": res.not_revoked,
            "not_replayed": res.not_replayed,
            "latency_ms": round(res.latency_ms, 4),
        }

    @app.post("/api/v1/credentials/{credential_id}/revoke")
    def revoke_credential(
        credential_id: str,
        req: RevokeCredentialRequest,
        _: TokenPrincipal = Depends(require_roles("authority", "admin")),
        rt: SafetySystemRuntime = Depends(get_runtime),
        db: Session = Depends(get_db),
    ):
        anchor = db.get(LedgerAnchorORM, credential_id)
        if anchor is None:
            raise HTTPException(status_code=404, detail="Credential anchor not found.")
        now = datetime.now(timezone.utc)
        rt.ledger.revoke_credential(credential_id, reason=req.reason, revoked_at=now)
        anchor.revoked = True
        anchor.revoked_at = now
        anchor.revocation_reason = req.reason
        db.commit()
        return {"credential_id": credential_id, "revoked": True, "reason": req.reason}

    @app.get("/api/v1/ledger/blocks")
    def get_ledger_blocks(
        _: TokenPrincipal = Depends(require_roles("authority", "admin")),
        rt: SafetySystemRuntime = Depends(get_runtime),
    ):
        return {
            "chain_intact": rt.ledger.chain_is_intact(),
            "block_count": rt.ledger.block_count(),
            "blocks": [
                {
                    "index": b.index,
                    "timestamp": b.timestamp.isoformat(),
                    "tx_type": b.tx_type,
                    "payload": b.payload,
                    "prev_hash": b.prev_hash,
                    "block_hash": b.block_hash,
                }
                for b in rt.ledger._blocks
            ],
        }

    # --- Geo-fencing Zones ---

    @app.get("/api/v1/zones")
    def list_zones(
        _: TokenPrincipal = Depends(get_current_principal),
        rt: SafetySystemRuntime = Depends(get_runtime),
    ):
        return [z.model_dump(mode="json") for z in rt.geofence.list_zones()]

    @app.post("/api/v1/zones", status_code=201)
    def create_zone(
        req: CreateZoneRequest,
        _: TokenPrincipal = Depends(require_roles("authority", "admin")),
        rt: SafetySystemRuntime = Depends(get_runtime),
        db: Session = Depends(get_db),
    ):
        zone_id = req.zone_id or f"zone-{uuid.uuid4().hex[:8]}"
        zone = GeoZone(
            zone_id=zone_id,
            name=req.name,
            category=req.category,
            center=req.center,
            radius_m=req.radius_m,
            buffer_m=req.buffer_m,
            polygon=req.polygon,
        )
        rt.geofence.add_zone(zone)
        db.add(
            ZoneORM(
                zone_id=zone.zone_id,
                name=zone.name,
                category=zone.category.value,
                center_lat=zone.center.lat if zone.center else None,
                center_lon=zone.center.lon if zone.center else None,
                radius_m=zone.radius_m,
                buffer_m=zone.buffer_m,
                polygon_json=json.dumps([p.model_dump() for p in zone.polygon])
                if zone.polygon
                else None,
            )
        )
        db.commit()
        return zone.model_dump(mode="json")

    # --- GPS Telemetry, AI Evaluation & SOS ---

    @app.post("/api/v1/telemetry/gps", response_model=TelemetryEvaluationResponse)
    async def ingest_gps(
        req: GPSIngestRequest,
        principal: TokenPrincipal = Depends(require_roles("tourist")),
        rt: SafetySystemRuntime = Depends(get_runtime),
        db: Session = Depends(get_db),
    ):
        prof = db.get(TouristProfileORM, principal.user_id)
        if prof is None:
            raise HTTPException(status_code=404, detail="Tourist profile not found.")
        if not prof.tracking_consent:
            raise HTTPException(
                status_code=403,
                detail="Location tracking consent is disabled for this tourist.",
            )

        ts = _ensure_utc(req.timestamp or datetime.now(timezone.utc))
        obs_row = GPSObservationORM(
            tourist_id=principal.user_id,
            observed_at=ts,
            lat=req.lat,
            lon=req.lon,
            accuracy_m=req.accuracy_m,
            sos_active=False,
        )
        db.add(obs_row)
        db.commit()

        obs = GPSObservation(
            tourist_id=principal.user_id,
            timestamp=ts,
            lat=req.lat,
            lon=req.lon,
            accuracy_m=req.accuracy_m,
        )
        zone_evals, transitions = rt.geofence.evaluate_observation(obs)
        for tr in transitions:
            db.add(
                ZoneTransitionORM(
                    tourist_id=tr.tourist_id,
                    zone_id=tr.zone_id,
                    category=tr.category.value,
                    previous_state=tr.previous_state.value,
                    new_state=tr.new_state.value,
                    event_type=tr.event_type,
                    occurred_at=tr.timestamp,
                )
            )
        if transitions:
            db.commit()

        top_zone = rt.geofence.highest_risk_zone(zone_evals)
        zone_ctx = (
            (top_zone.category, top_zone.state)
            if top_zone is not None
            else (None, ZoneState.OUTSIDE)
        )

        # Pull recent window (up to 24 points) for AI evaluation
        recent_rows = list(
            reversed(
                db.scalars(
                    select(GPSObservationORM)
                    .where(GPSObservationORM.tourist_id == principal.user_id)
                    .order_by(desc(GPSObservationORM.observed_at))
                    .limit(24)
                ).all()
            )
        )
        anomaly_score: Optional[float] = None
        anomaly_flagged = False
        if len(recent_rows) >= 5:
            window_obs = [
                GPSObservation(
                    tourist_id=r.tourist_id,
                    timestamp=_ensure_utc(r.observed_at),
                    lat=r.lat,
                    lon=r.lon,
                    accuracy_m=r.accuracy_m,
                )
                for r in recent_rows
            ]
            feats = extract_window_features(
                window_obs, planned_route=rt.default_route
            ).to_vector().reshape(1, -1)
            anomaly_score = round(float(rt.detector.score(feats, [zone_ctx])[0]), 4)
            anomaly_flagged = bool(rt.detector.predict(feats, [zone_ctx])[0] == 1)

        created_incident: Optional[IncidentResponse] = None
        if (
            top_zone is not None
            and top_zone.category == ZoneCategory.RESTRICTED
            and top_zone.state == ZoneState.INSIDE
        ):
            created_incident = await _persist_and_broadcast_incident(
                db=db,
                rt=rt,
                tourist_id=principal.user_id,
                event_ts=ts,
                lat=req.lat,
                lon=req.lon,
                priority=AlertPriority.HIGH.value,
                reason=f"restricted_zone_entry:{top_zone.zone_name}",
                zone_id=top_zone.zone_id,
                zone_category=top_zone.category.value,
                anomaly_score=anomaly_score,
            )
        elif anomaly_flagged:
            created_incident = await _persist_and_broadcast_incident(
                db=db,
                rt=rt,
                tourist_id=principal.user_id,
                event_ts=ts,
                lat=req.lat,
                lon=req.lon,
                priority=AlertPriority.WARNING.value,
                reason="movement_anomaly_detected",
                zone_id=top_zone.zone_id if top_zone else None,
                zone_category=top_zone.category.value if top_zone else None,
                anomaly_score=anomaly_score,
            )

        safety_status = "safe"
        if created_incident is not None:
            safety_status = "alert"
        elif top_zone is not None and (
            top_zone.category in {ZoneCategory.CAUTION, ZoneCategory.RESTRICTED}
        ):
            safety_status = "caution"

        return TelemetryEvaluationResponse(
            recorded=True,
            safety_status=safety_status,
            zone_evaluations=[z.model_dump(mode="json") for z in zone_evals],
            transitions=[
                {
                    "zone_id": tr.zone_id,
                    "category": tr.category.value,
                    "event_type": tr.event_type,
                    "timestamp": tr.timestamp.isoformat(),
                }
                for tr in transitions
            ],
            anomaly_score=anomaly_score,
            anomaly_flagged=anomaly_flagged,
            incident=created_incident,
        )

    @app.get("/api/v1/telemetry/history/{tourist_id}")
    def get_gps_history(
        tourist_id: str,
        limit: int = Query(default=100, ge=1, le=1000),
        principal: TokenPrincipal = Depends(get_current_principal),
        db: Session = Depends(get_db),
    ):
        if principal.role == "tourist" and principal.user_id != tourist_id:
            raise HTTPException(status_code=403, detail="Cannot view another tourist's GPS history.")
        rows = db.scalars(
            select(GPSObservationORM)
            .where(GPSObservationORM.tourist_id == tourist_id)
            .order_by(desc(GPSObservationORM.observed_at))
            .limit(limit)
        ).all()
        return [
            {
                "id": r.id,
                "tourist_id": r.tourist_id,
                "timestamp": _ensure_utc(r.observed_at).isoformat(),
                "lat": r.lat,
                "lon": r.lon,
                "accuracy_m": r.accuracy_m,
                "sos_active": r.sos_active,
            }
            for r in rows
        ]

    @app.post("/api/v1/sos", response_model=IncidentResponse, status_code=201)
    async def trigger_sos(
        req: SOSRequest,
        principal: TokenPrincipal = Depends(require_roles("tourist")),
        rt: SafetySystemRuntime = Depends(get_runtime),
        db: Session = Depends(get_db),
    ):
        now = datetime.now(timezone.utc)
        db.add(
            GPSObservationORM(
                tourist_id=principal.user_id,
                observed_at=now,
                lat=req.lat,
                lon=req.lon,
                accuracy_m=req.accuracy_m,
                sos_active=True,
            )
        )
        db.commit()

        obs = GPSObservation(
            tourist_id=principal.user_id,
            timestamp=now,
            lat=req.lat,
            lon=req.lon,
            accuracy_m=req.accuracy_m,
            sos_active=True,
        )
        zone_evals, _ = rt.geofence.evaluate_observation(obs)
        top_zone = rt.geofence.highest_risk_zone(zone_evals)

        return await _persist_and_broadcast_incident(
            db=db,
            rt=rt,
            tourist_id=principal.user_id,
            event_ts=now,
            lat=req.lat,
            lon=req.lon,
            priority=AlertPriority.CRITICAL.value,
            reason=req.note or "manual_sos_request",
            zone_id=top_zone.zone_id if top_zone else None,
            zone_category=top_zone.category.value if top_zone else None,
            anomaly_score=None,
        )

    # --- Authority Incident Management & Live WebSocket ---

    @app.get("/api/v1/incidents", response_model=list[IncidentResponse])
    def list_incidents(
        status_filter: Optional[IncidentStatus] = Query(default=None, alias="status"),
        _: TokenPrincipal = Depends(require_roles("authority", "admin")),
        db: Session = Depends(get_db),
    ):
        stmt = select(IncidentORM).order_by(desc(IncidentORM.created_at))
        if status_filter is not None:
            stmt = stmt.where(IncidentORM.status == status_filter.value)
        rows = db.scalars(stmt).all()
        return [_incident_to_response(r) for r in rows]

    @app.patch("/api/v1/incidents/{alert_id}/status", response_model=IncidentResponse)
    async def update_incident_status(
        alert_id: str,
        req: IncidentStatusUpdateRequest,
        _: TokenPrincipal = Depends(require_roles("authority", "admin")),
        rt: SafetySystemRuntime = Depends(get_runtime),
        db: Session = Depends(get_db),
    ):
        row = db.get(IncidentORM, alert_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Incident not found.")
        now = datetime.now(timezone.utc)
        row.status = req.status.value
        if req.status == IncidentStatus.ACKNOWLEDGED and row.acknowledged_at is None:
            row.acknowledged_at = now
        elif req.status == IncidentStatus.IN_PROGRESS and row.in_progress_at is None:
            row.in_progress_at = now
        elif req.status == IncidentStatus.RESOLVED and row.resolved_at is None:
            row.resolved_at = now
        db.commit()
        db.refresh(row)

        resp = _incident_to_response(row)
        await rt.broadcaster.broadcast(
            {"event": "incident_updated", "incident": resp.model_dump(mode="json")}
        )
        return resp

    @app.websocket("/ws/authority/alerts")
    async def authority_alerts_ws(websocket: WebSocket):
        rt: SafetySystemRuntime = websocket.app.state.runtime
        await rt.broadcaster.connect(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            await rt.broadcaster.disconnect(websocket)

    return app


async def _persist_and_broadcast_incident(
    db: Session,
    rt: SafetySystemRuntime,
    tourist_id: str,
    event_ts: datetime,
    lat: float,
    lon: float,
    priority: str,
    reason: str,
    zone_id: Optional[str],
    zone_category: Optional[str],
    anomaly_score: Optional[float],
) -> IncidentResponse:
    row = IncidentORM(
        alert_id=f"alert-{uuid.uuid4().hex[:10]}",
        tourist_id=tourist_id,
        event_timestamp=event_ts,
        lat=lat,
        lon=lon,
        priority=priority,
        reason=reason,
        zone_id=zone_id,
        zone_category=zone_category,
        anomaly_score=anomaly_score,
        status=IncidentStatus.PENDING.value,
        created_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    resp = _incident_to_response(row)
    await rt.broadcaster.broadcast(
        {"event": "incident_created", "incident": resp.model_dump(mode="json")}
    )
    return resp


def _incident_to_response(row: IncidentORM) -> IncidentResponse:
    return IncidentResponse(
        alert_id=row.alert_id,
        tourist_id=row.tourist_id,
        event_timestamp=_ensure_utc(row.event_timestamp),
        lat=row.lat,
        lon=row.lon,
        priority=row.priority,
        reason=row.reason,
        zone_id=row.zone_id,
        zone_category=row.zone_category,
        anomaly_score=row.anomaly_score,
        status=row.status,
        created_at=_ensure_utc(row.created_at),
        acknowledged_at=_ensure_utc(row.acknowledged_at) if row.acknowledged_at else None,
        in_progress_at=_ensure_utc(row.in_progress_at) if row.in_progress_at else None,
        resolved_at=_ensure_utc(row.resolved_at) if row.resolved_at else None,
    )


app = create_app()
