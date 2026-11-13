"""Shared domain models for the Smart Tourist Safety Monitoring system."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class ZoneCategory(str, Enum):
    SAFE = "safe"
    CAUTION = "caution"
    RESTRICTED = "restricted"


class ZoneState(str, Enum):
    INSIDE = "inside"
    WARNING_BUFFER = "warning_buffer"
    OUTSIDE = "outside"


class GeoPoint(BaseModel):
    lat: float = Field(..., ge=-90.0, le=90.0)
    lon: float = Field(..., ge=-180.0, le=180.0)


class GPSObservation(BaseModel):
    tourist_id: str
    timestamp: datetime
    lat: float = Field(..., ge=-90.0, le=90.0)
    lon: float = Field(..., ge=-180.0, le=180.0)
    accuracy_m: float = Field(default=5.0, ge=0.0)
    sos_active: bool = False


class GeoZone(BaseModel):
    zone_id: str
    name: str
    category: ZoneCategory
    center: Optional[GeoPoint] = None
    radius_m: Optional[float] = Field(default=None, gt=0.0)
    buffer_m: float = Field(default=25.0, ge=0.0)
    polygon: Optional[list[GeoPoint]] = None


class ZoneEvaluationResult(BaseModel):
    zone_id: str
    zone_name: str
    category: ZoneCategory
    state: ZoneState
    distance_m: float
    action: str


class AlertPriority(str, Enum):
    INFO = "info"
    WARNING = "warning"
    HIGH = "high"
    CRITICAL = "critical"


class IncidentStatus(str, Enum):
    PENDING = "pending"
    ACKNOWLEDGED = "acknowledged"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"


class SafetyAlert(BaseModel):
    alert_id: str
    tourist_id: str
    timestamp: datetime
    location: GeoPoint
    priority: AlertPriority
    reason: str
    zone_id: Optional[str] = None
    zone_category: Optional[ZoneCategory] = None
    anomaly_score: Optional[float] = None
    status: IncidentStatus = IncidentStatus.PENDING
