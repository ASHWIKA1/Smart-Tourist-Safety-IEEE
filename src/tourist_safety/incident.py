"""End-to-end incident workflow orchestrating geo-fencing, anomaly detection,
SOS handling, and authority incident lifecycle management (Algorithm 3).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from .anomaly import HybridGeofenceIFDetector, extract_window_features
from .geofence import GeoFenceEngine
from .models import (
    AlertPriority,
    GeoPoint,
    GPSObservation,
    IncidentStatus,
    SafetyAlert,
    ZoneCategory,
    ZoneState,
)


class IncidentManager:
    """Evaluates incoming GPS windows and manages incident state transitions."""

    def __init__(
        self,
        geofence: GeoFenceEngine,
        detector: HybridGeofenceIFDetector,
    ) -> None:
        self.geofence = geofence
        self.detector = detector
        self.alerts: dict[str, SafetyAlert] = {}
        self.status_timestamps: dict[str, dict[str, datetime]] = {}

    def process_window(
        self,
        observations: list[GPSObservation],
        planned_route: Optional[list[GeoPoint]] = None,
    ) -> Optional[SafetyAlert]:
        if not observations:
            return None
        latest = max(observations, key=lambda o: o.timestamp)
        zone_results, _ = self.geofence.evaluate_observation(latest)
        top_zone = self.geofence.highest_risk_zone(zone_results)

        zone_ctx: tuple[Optional[ZoneCategory], ZoneState] = (
            (top_zone.category, top_zone.state)
            if top_zone is not None
            else (None, ZoneState.OUTSIDE)
        )

        feats = extract_window_features(observations, planned_route=planned_route)
        X = feats.to_vector().reshape(1, -1)
        anomaly_score = float(self.detector.score(X, [zone_ctx])[0])
        is_anomaly = bool(self.detector.predict(X, [zone_ctx])[0] == 1)

        if latest.sos_active:
            return self._create_alert(
                obs=latest,
                priority=AlertPriority.CRITICAL,
                reason="manual_sos_request",
                zone_id=top_zone.zone_id if top_zone else None,
                zone_category=top_zone.category if top_zone else None,
                anomaly_score=anomaly_score,
            )

        if (
            top_zone is not None
            and top_zone.category == ZoneCategory.RESTRICTED
            and top_zone.state == ZoneState.INSIDE
        ):
            return self._create_alert(
                obs=latest,
                priority=AlertPriority.HIGH,
                reason=f"restricted_zone_entry:{top_zone.zone_name}",
                zone_id=top_zone.zone_id,
                zone_category=top_zone.category,
                anomaly_score=anomaly_score,
            )

        if is_anomaly:
            return self._create_alert(
                obs=latest,
                priority=AlertPriority.WARNING,
                reason="movement_anomaly_detected",
                zone_id=top_zone.zone_id if top_zone else None,
                zone_category=top_zone.category if top_zone else None,
                anomaly_score=anomaly_score,
            )

        return None

    def _create_alert(
        self,
        obs: GPSObservation,
        priority: AlertPriority,
        reason: str,
        zone_id: Optional[str],
        zone_category: Optional[ZoneCategory],
        anomaly_score: Optional[float],
    ) -> SafetyAlert:
        alert_id = f"alert-{uuid.uuid4().hex[:10]}"
        alert = SafetyAlert(
            alert_id=alert_id,
            tourist_id=obs.tourist_id,
            timestamp=obs.timestamp,
            location=GeoPoint(lat=obs.lat, lon=obs.lon),
            priority=priority,
            reason=reason,
            zone_id=zone_id,
            zone_category=zone_category,
            anomaly_score=round(anomaly_score, 4) if anomaly_score is not None else None,
            status=IncidentStatus.PENDING,
        )
        self.alerts[alert_id] = alert
        self.status_timestamps[alert_id] = {
            IncidentStatus.PENDING.value: datetime.now(timezone.utc)
        }
        return alert

    def update_status(
        self,
        alert_id: str,
        new_status: IncidentStatus,
        at: Optional[datetime] = None,
    ) -> SafetyAlert:
        if alert_id not in self.alerts:
            raise KeyError(f"Unknown alert {alert_id}")
        alert = self.alerts[alert_id]
        alert.status = new_status
        self.status_timestamps[alert_id][new_status.value] = at or datetime.now(
            timezone.utc
        )
        return alert
