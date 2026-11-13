"""Pydantic request and response schemas for the FastAPI REST API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from ..identity import VerifiableCredential
from ..models import GeoPoint, IncidentStatus, ZoneCategory


class RegisterRequest(BaseModel):
    email: str
    password: str = Field(..., min_length=6)
    role: str = Field(default="tourist", pattern="^(tourist|authority|admin)$")
    full_name: Optional[str] = None
    nationality: str = "IN"
    passport_or_id_number: str = "UNVERIFIED"
    emergency_contact_name: str = "Not Provided"
    emergency_contact_phone: str = "Not Provided"
    tracking_consent: bool = False


class LoginRequest(BaseModel):
    email: str
    password: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    role: str


class ConsentUpdateRequest(BaseModel):
    tracking_consent: bool


class TouristProfileResponse(BaseModel):
    tourist_id: str
    full_name: str
    nationality: str
    passport_or_id_number: str
    emergency_contact_name: str
    emergency_contact_phone: str
    tracking_consent: bool
    did: Optional[str] = None


class IssueCredentialRequest(BaseModel):
    tourist_id: str
    validity_days: int = Field(default=30, ge=1, le=365)


class VerifyCredentialRequest(BaseModel):
    credential: VerifiableCredential
    presentation_nonce: Optional[str] = None


class RevokeCredentialRequest(BaseModel):
    reason: str = "revoked_by_authority"


class CreateZoneRequest(BaseModel):
    zone_id: Optional[str] = None
    name: str
    category: ZoneCategory
    center: Optional[GeoPoint] = None
    radius_m: Optional[float] = Field(default=None, gt=0.0)
    buffer_m: float = Field(default=25.0, ge=0.0)
    polygon: Optional[list[GeoPoint]] = None


class GPSIngestRequest(BaseModel):
    lat: float = Field(..., ge=-90.0, le=90.0)
    lon: float = Field(..., ge=-180.0, le=180.0)
    accuracy_m: float = Field(default=5.0, ge=0.0)
    timestamp: Optional[datetime] = None


class SOSRequest(BaseModel):
    lat: float = Field(..., ge=-90.0, le=90.0)
    lon: float = Field(..., ge=-180.0, le=180.0)
    accuracy_m: float = Field(default=5.0, ge=0.0)
    note: str = "manual_sos_request"


class IncidentStatusUpdateRequest(BaseModel):
    status: IncidentStatus


class IncidentResponse(BaseModel):
    alert_id: str
    tourist_id: str
    event_timestamp: datetime
    lat: float
    lon: float
    priority: str
    reason: str
    zone_id: Optional[str]
    zone_category: Optional[str]
    anomaly_score: Optional[float]
    status: str
    created_at: datetime
    acknowledged_at: Optional[datetime]
    in_progress_at: Optional[datetime]
    resolved_at: Optional[datetime]


class TelemetryEvaluationResponse(BaseModel):
    recorded: bool
    safety_status: str
    zone_evaluations: list[dict[str, Any]]
    transitions: list[dict[str, Any]]
    anomaly_score: Optional[float] = None
    anomaly_flagged: bool = False
    incident: Optional[IncidentResponse] = None
